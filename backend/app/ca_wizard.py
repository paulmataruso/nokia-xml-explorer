"""
LTE carrier aggregation wizard: plans a CA setup for one eNB and writes it,
taking its values from a donor file (a working CA export in the corpus).
Phases 2 and 3 of the CA wizard; ca.py, the read-only check, validates every
plan afterwards.

Where things come from:
- Which cells pair up comes from the request: each PCell's SCells, in
  priority order. wizard_setup() offers presets and says which pairs the
  rules forbid and why.
- Values come from the donor: the eNB-wide CA objects (CAGENB, CADPR and its
  CBRS/LAA variants), CAREL and CAPR templates, the uplink CA mode, and CA
  tuning parameters from a curated list (_TUNING).
- Rules come from the same places as ca.py's. Official dictionary rules are
  applied (CA pools, flags a PCell and SCell must share,
  scellFastSchedulingSelect, maxNumScells, UE admission limits), and so are
  lessons from the corpus (CBRS TDD requests, carriers left over from an
  earlier frequency plan, SCell modulation).

Donor values are filtered by release. One is written only if some file of
the target's release in the corpus sets that parameter on that class
(`release_params`, built by main.py), so a newer donor can't add parameters
an older BTS would reject. A class no file of that release has is copied
unfiltered, and the plan says so.

Pure like parser.py and ca.py: bytes in, bytes and a plan dict out.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from .actions import PlanError
from .actions.doc import Doc as _Doc
from .actions.doc import natural as _natural
from .actions.doc import release_of
from .actions.doc import why as _why
from .ca import _MODULATION_RANK, _cells, _instance, _int, _kids, _label, _load, analyze_ca, analyze_loaded

# CA tuning a donor may supply. Values only: feature switches other than the
# CA switches themselves, RF settings (carrier, bandwidth, TDD config) and
# profiles shared with non-CA traffic are left out, because copying them
# would change more than CA. "SUB" is LNCEL_FDD or LNCEL_TDD.
_TUNING = {
    "LNBTS": (
        "caIntraCellHoMode", "caMinDlAmbr", "caMinUlAmbr", "caSchedFairFact", "caUlIntraBandAmpr",
        "dlCaPreferred", "multScellReleaseTimer", "sCellActivationCyclePeriod", "sCellActivationMethod",
        "sCellDeactivationTimereNB", "sCellpCellHARQFdbkUsage", "scellActivationLevel", "scellMeasCycle",
        "ulCaPathlossThr",
    ),
    "LNCEL": (
        "dlCaCqiWindow", "dlCaMinPcellCqi", "dlCaMinPcellCqiQci1", "longPeriodScellChEst",
        "scellBadChQualThr", "scellGoodChQualThr", "scellNotDetectableThr", "shortPeriodScellChEst",
        "ulCaMinPcellSinr", "ulCaMinPcellSinrQci1", "ulCaSinrWindow",
    ),
    "SUB": ("maxNumCaConfUe", "maxNumCaConfUe3c", "maxNumCaConfUeDc"),
}

# eNB-wide CA objects, copied from the donor (scalar parameters only) when
# the target has none. Their tables are left out: caClusterEnbList names
# the donor's neighbouring eNBs.
_ENB_OBJECTS = ("CAGENB", "CADPR", "CADPRCBRS", "CADPRLAA")

# CAREL parameters that describe the donor's own cells, never copied.
_CAREL_OWN = ("lcrId", "lnBtsId", "scellPrio", "maxNumOfSuppMimoLayer")

DEFAULT_OPTIONS = {
    "fillMissing": True,      # add donor CA tuning this file lacks
    "copyTuning": False,      # also replace CA tuning this file sets differently
    "raiseModulation": True,  # lift an SCell's DL modulation to its PCell's
    "barScellOnly": False,    # bar cells that are only ever SCells
    "cleanStale": True,       # retarget or remove CA entries for unused carriers
}

_INTERFERENCE_RANK = {"QPSK": 0, "16QAM": 1, "64QAM": 2}


def _lcr(cell: dict) -> int:
    return _int(cell["mo"]["p"].get("lcrId")) or 0


def _is_cbrs(cell: dict) -> bool:
    return cell["cbsdcel"] is not None or cell["band"] == 48


def _layers(scell: dict, fallback: Optional[str]) -> str:
    """maxNumOfSuppMimoLayer for a new CAREL, from the SCell's own MIMO mode:
    "Closed Loop MIMO (4x4)" -> 4-layer. In the corpus every 4x4 SCell has
    4-layer and every 2x2 one but a single pico SCell has 2-layer (a 2x2
    cell can't use the other two layers anyway)."""
    mode = (scell["sub"]["p"].get("dlMimoMode") if scell["sub"] else None) or ""
    m = re.search(r"\((\d+)x(\d+)\)", mode)
    if m:
        return "4-layer" if min(int(m.group(1)), int(m.group(2))) >= 4 else "2-layer"
    if mode:
        return "2-layer"
    return fallback or "2-layer"


def _mhz(bandwidth: Optional[str]) -> Optional[float]:
    m = re.match(r"\s*([\d.]+)", bandwidth or "")
    return float(m.group(1)) if m else None


def _band_combo(p: dict, s: dict) -> Optional[str]:
    """The 3GPP name of a two-carrier downlink combination, e.g. CA_48C or
    CA_5A-48A. Intra-band carriers count as contiguous when their spacing is
    the usual (BW1 + BW2) / 2 on the 300 kHz raster. Class B covers up to 100
    resource blocks in total and class C up to 200 (TS 36.101 Table 5.6A-1)."""
    if p["band"] is None or s["band"] is None:
        return None
    if p["band"] != s["band"]:
        lo, hi = sorted((p["band"], s["band"]))
        return f"CA_{lo}A-{hi}A"
    bw_p, bw_s = _mhz(p["bandwidth"]), _mhz(s["bandwidth"])
    e_p, e_s = _int(p["earfcn"]), _int(s["earfcn"])
    if None in (bw_p, bw_s, e_p, e_s):
        return None
    spacing = abs(e_p - e_s) / 10
    if abs(spacing - (bw_p + bw_s) / 2) <= 0.3:
        total_rb = (bw_p + bw_s) * 5
        return f"CA_{p['band']}{'B' if total_rb <= 100 else 'C'}"
    return f"CA_{p['band']}A-{p['band']}A"


class _Enb:
    """One LNBTS of the target: its cells, current relations, which pairs the
    rules allow, and the per-PCell limits."""

    def __init__(self, lnbts: dict, kids: dict[str, list[dict]], mos: list[dict]):
        self.lnbts = lnbts
        self.dn = lnbts["dn"]
        self.p = lnbts["p"]
        self.kids = kids
        self.own_id = _instance(self.dn)
        self.release = release_of(lnbts["version"])
        self.cells = sorted(_cells(lnbts, kids), key=_lcr)
        self.by_dn = {c["mo"]["dn"]: c for c in self.cells}
        self.by_lcr = {c["mo"]["p"].get("lcrId"): c for c in self.cells if c["mo"]["p"].get("lcrId") is not None}
        self.carriers = {c["earfcn"] for c in self.cells if c["earfcn"]}
        self.flex = self.p.get("actFlexScellSelect") == "true"
        self.ul_on = self.p.get("actULCAggr") not in (None, "false")
        self.radio = self._radio_groups(mos)

        # Own-eNB relations resolved to SCells; foreign ones are kept as-is.
        self.relations: list[dict] = []
        for cell in self.cells:
            for carel in cell["carels"]:
                lcr = carel["p"].get("lcrId")
                enb = carel["p"].get("lnBtsId") or self.own_id
                self.relations.append({
                    "carel": carel, "pcell": cell, "foreign": enb != self.own_id,
                    "scell": None if enb != self.own_id else self.by_lcr.get(lcr),
                })

    def _radio_groups(self, mos: list[dict]) -> dict[str, str]:
        """Cell -> the radio modules (RMOD) its LCELL channels use. LCELL-n
        maps to the LNCEL with lcrId n. On a multi-sector site this recovers
        the sectors (the CBRS 3S3C export pairs exactly the cells that share
        an RMOD); a pico's two cells each have their own RMOD."""
        rmods: dict[str, set[str]] = {}
        for m in mos:
            ref = m["p"].get("antlDN") or m["p"].get("resourceDN")
            if not ref:
                continue
            lcell = next((s for s in m["dn"].split("/") if s.startswith("LCELL-")), None)
            rmod = next((s for s in ref.split("/") if s.startswith("RMOD-")), None)
            if lcell and rmod:
                rmods.setdefault(lcell[len("LCELL-"):], set()).add(rmod)
        out = {}
        for c in self.cells:
            r = rmods.get(c["mo"]["p"].get("lcrId") or "")
            if r:
                out[c["mo"]["dn"]] = "+".join(sorted(r, key=_natural))
        return out

    def ul_blockers(self) -> list[dict]:
        return [c for c in self.cells if c["mo"]["p"].get("actFlexDupGap") == "true"]

    def block(self, p: dict, s: dict) -> Optional[str]:
        """Why `s` can't be an SCell of `p`, or None. Mirrors ca.py's errors."""
        if p is s:
            return "Same cell"
        if not p["earfcn"] or not s["earfcn"]:
            return "No carrier (EARFCN) set"
        if s["mo"]["p"].get("lcrId") is None:
            return f"{_label(s['mo']['dn'])} has no lcrId"
        if p["earfcn"] == s["earfcn"]:
            return "Same carrier"
        if p["tech"] == "FDD" and p["bandwidth"] in ("1.4 MHz", "3 MHz"):
            return f"A {p['bandwidth']} FDD cell can't be a PCell"
        if p["sub"] and p["sub"]["p"].get("actSdlc") == "true":
            return f"{_label(p['mo']['dn'])} is downlink-only (actSdlc), so it can only be an SCell"
        if p["tech"] != s["tech"] and self.p.get("supportedCellTechnology") != "mixed_FDD_TDD":
            return "FDD and TDD cells pair only when supportedCellTechnology is mixed_FDD_TDD"
        if p["tech"] == "TDD" and s["tech"] == "TDD" and p["sub"] and s["sub"]:
            pf, sf = p["sub"]["p"].get("tddFrameConf"), s["sub"]["p"].get("tddFrameConf")
            if pf != sf:
                return f"Different TDD frame configs ({pf} and {sf})"
            ps, ss = p["sub"]["p"].get("tddSpecSubfConf"), s["sub"]["p"].get("tddSpecSubfConf")
            if p["band"] == s["band"] and ps != ss:
                return f"Different special subframe configs ({ps} and {ss})"
        return None

    def limits(self, cell: dict) -> dict:
        """Official per-PCell limits (actDLCAggr 2.1.1 / 2.1.2 / 3.1.x)."""
        if self.flex:
            tdd = cell["tech"] == "TDD"
            return {"total": 5 if tdd else None, "perCarrier": 5 if tdd else 6, "carriers": 5 if tdd else 6}
        return {"total": 2, "perCarrier": 1, "carriers": 2}

    def current(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for cell in self.cells:
            mine = [r for r in self.relations if r["pcell"] is cell and r["scell"] is not None and r["scell"] is not cell]
            mine.sort(key=lambda r: (_int(r["carel"]["p"].get("scellPrio")) or 99, _natural(r["carel"]["dn"])))
            seen: list[str] = []
            for r in mine:
                if r["scell"]["mo"]["dn"] not in seen:
                    seen.append(r["scell"]["mo"]["dn"])
            if seen:
                out[cell["mo"]["dn"]] = seen
        return out

    # --- Presets ------------------------------------------------------------

    def _pick(self, pcell: dict, candidates: list[dict]) -> list[str]:
        lim = self.limits(pcell)
        cap = 3 if self.flex else 2
        pr = self.radio.get(pcell["mo"]["dn"])

        def key(s: dict) -> tuple:
            same_radio = pr is not None and self.radio.get(s["mo"]["dn"]) == pr
            return (0 if same_radio else 1, 0 if s["band"] == pcell["band"] else 1, _lcr(s))

        chosen: list[str] = []
        per_carrier: Counter = Counter()
        for s in sorted(candidates, key=key):
            if self.block(pcell, s):
                continue
            if len(chosen) >= cap or (lim["total"] is not None and len(chosen) >= lim["total"]):
                break
            if per_carrier[s["earfcn"]] >= lim["perCarrier"]:
                continue
            if s["earfcn"] not in per_carrier and len(per_carrier) >= lim["carriers"]:
                continue
            chosen.append(s["mo"]["dn"])
            per_carrier[s["earfcn"]] += 1
        return chosen

    def presets(self) -> tuple[list[dict], Optional[str]]:
        def rels(mapping: dict[str, list[str]]) -> list[dict]:
            return [{"pcell": p, "scells": s} for p, s in mapping.items() if s]

        out = []
        current = self.current()
        if current:
            out.append({"key": "current", "label": "Current setup",
                        "detail": "The relations this file has now.", "relations": rels(current)})

        everything = {c["mo"]["dn"]: self._pick(c, self.cells) for c in self.cells}
        groups = Counter(self.radio.get(c["mo"]["dn"]) for c in self.cells if self.radio.get(c["mo"]["dn"]))
        by_radio = None
        if len(groups) >= 2 and any(n >= 2 for n in groups.values()):
            by_radio = {
                c["mo"]["dn"]: self._pick(c, [s for s in self.cells
                                              if self.radio.get(s["mo"]["dn"]) == self.radio.get(c["mo"]["dn"])])
                for c in self.cells
            }
        licensed = [c for c in self.cells if not _is_cbrs(c)]
        cbrs = [c for c in self.cells if _is_cbrs(c)]
        lic_cbrs = {c["mo"]["dn"]: self._pick(c, cbrs) for c in licensed} if licensed and cbrs else None

        if any(everything.values()):
            out.append({"key": "all", "label": "Every allowed pair",
                        "detail": "Each cell is a PCell for every other cell the rules allow, up to the per-PCell limits.",
                        "relations": rels(everything)})
        if by_radio and any(by_radio.values()):
            out.append({"key": "radio", "label": "Within each radio",
                        "detail": "Only cells on the same radio module pair up, like the sectors of a macro site.",
                        "relations": rels(by_radio)})
        if lic_cbrs and any(lic_cbrs.values()):
            out.append({"key": "licensed_cbrs", "label": "Licensed to CBRS",
                        "detail": "Licensed cells are PCells, CBRS cells are only SCells.",
                        "relations": rels(lic_cbrs)})

        keys = [p["key"] for p in out]
        if "current" in keys:
            default = "current"
        elif "licensed_cbrs" in keys:
            default = "licensed_cbrs"
        elif "radio" in keys and all(n >= 2 for n in groups.values()):
            default = "radio"
        else:
            default = keys[0] if keys else None
        return out, default

    # --- Requests -----------------------------------------------------------

    def normalize(self, relations: list[dict]) -> dict[str, list[str]]:
        """{pcell dn: [scell dn, ...]} from the request, checked against the
        rules. Raises PlanError listing every problem."""
        problems: list[str] = []
        pairs: dict[str, list[str]] = {}
        for rel in relations:
            pdn = rel.get("pcell")
            p = self.by_dn.get(pdn or "")
            if p is None:
                problems.append(f"{pdn} is not a cell of {_label(self.dn)}.")
                continue
            scells = pairs.setdefault(pdn, [])
            for sdn in rel.get("scells") or []:
                s = self.by_dn.get(sdn)
                if s is None:
                    problems.append(f"{sdn} is not a cell of {_label(self.dn)}.")
                elif sdn not in scells:
                    reason = self.block(p, s)
                    if reason:
                        problems.append(f"{_label(pdn)} → {_label(sdn)}: {reason}.")
                    else:
                        scells.append(sdn)
        for pdn, sdns in pairs.items():
            p = self.by_dn[pdn]
            lim = self.limits(p)
            name = _label(pdn)
            flex_note = "with" if self.flex else "without"
            if lim["total"] is not None and len(sdns) > lim["total"]:
                problems.append(f"{name} has {len(sdns)} SCells; at most {lim['total']} {flex_note} flexible SCell selection.")
            per_carrier = Counter(self.by_dn[s]["earfcn"] for s in sdns)
            for carrier, n in per_carrier.items():
                if n > lim["perCarrier"]:
                    problems.append(f"{name} has {n} SCells on EARFCN {carrier}; at most {lim['perCarrier']} per carrier.")
            if len(per_carrier) > lim["carriers"]:
                problems.append(f"{name}'s SCells span {len(per_carrier)} carriers; at most {lim['carriers']}.")
        if problems:
            raise PlanError(problems)
        return pairs

    def setup(self) -> dict:
        presets, default = self.presets()
        blocked: dict[str, dict[str, str]] = {}
        for p in self.cells:
            for s in self.cells:
                if p is not s and (reason := self.block(p, s)):
                    blocked.setdefault(p["mo"]["dn"], {})[s["mo"]["dn"]] = reason
        current = self.current()
        roles = {}
        for c in self.cells:
            dn = c["mo"]["dn"]
            is_p = bool(current.get(dn))
            is_s = any(dn in s for s in current.values())
            roles[dn] = "both" if is_p and is_s else "pcell" if is_p else "scell" if is_s else "none"
        return {
            "id": self.dn,
            "label": _label(self.dn),
            "lnBtsId": self.own_id,
            "release": self.release,
            "dl": self.p.get("actDLCAggr") == "true",
            "ul": self.p.get("actULCAggr"),
            "ulOn": self.ul_on,
            "ulBlockedBy": [_label(c["mo"]["dn"]) for c in self.ul_blockers()],
            "flexScellSelect": self.flex,
            "supportedCellTechnology": self.p.get("supportedCellTechnology"),
            "foreignRelations": sum(1 for r in self.relations if r["foreign"]),
            "cells": [{
                "id": c["mo"]["dn"],
                "label": _label(c["mo"]["dn"]),
                "name": c["mo"]["p"].get("cellName"),
                "lcrId": c["mo"]["p"].get("lcrId"),
                "tech": c["tech"],
                "earfcn": c["earfcn"],
                "band": c["band"],
                "bandwidth": c["bandwidth"],
                "tdd": (f"{c['sub']['p'].get('tddFrameConf')}/{c['sub']['p'].get('tddSpecSubfConf')}"
                        if c["tech"] == "TDD" and c["sub"] else None),
                "cbrs": _is_cbrs(c),
                "radio": self.radio.get(c["mo"]["dn"]),
                "role": roles[c["mo"]["dn"]],
                "limits": self.limits(c),
            } for c in self.cells],
            "blocked": blocked,
            "current": [{"pcell": p, "scells": s} for p, s in current.items()],
            "presets": presets,
            "defaultPreset": default,
        }


def wizard_setup(raw: bytes) -> dict:
    """Everything the wizard's first steps need: per eNB, the cells, the
    pairs the rules forbid (with reasons), the current relations and the
    presets."""
    mos = _load(raw)
    kids = _kids(mos)
    return {"enbs": [_Enb(m, kids, mos).setup() for m in mos if m["cls"] == "LNBTS"]}


# --- Donors -----------------------------------------------------------------

def profile(raw: bytes) -> dict:
    """What main.py's corpus index keeps per file: which parameters each
    class sets per release (for the release filter), and, for a working CA
    export, a summary of its setup to rank it as a donor. A working export
    has downlink CA on, at least one CAREL and no errors in the CA check."""
    return profile_loaded(_load(raw))


def profile_loaded(mos: list[dict]) -> dict:
    """profile() on a file ca._load() has already read."""
    params: dict[tuple[Optional[str], str], set[str]] = {}
    for m in mos:
        params.setdefault((release_of(m["version"]), m["cls"]), set()).update(m["p"])
    analysis = analyze_loaded(mos)
    donor = None
    enbs = [e for e in analysis["enbs"] if e["dl"] and e["relations"]]
    if enbs and analysis["summary"]["errors"] == 0:
        enb = max(enbs, key=lambda e: len(e["relations"]))
        cls_here = {m["cls"] for m in mos if m["dn"].startswith(enb["id"] + "/")}
        cells_in_ca = [c for c in enb["cells"] if c["role"] != "none"]
        two_way = all(c["role"] == "both" for c in cells_in_ca)
        donor = {
            "release": release_of(enb["version"]),
            "techs": sorted({c["tech"] for c in cells_in_ca if c["tech"]}),
            "bands": sorted({c["band"] for c in cells_in_ca if c["band"] is not None}),
            "cbrs": "CADPRCBRS" in cls_here,
            "laa": "CADPRLAA" in cls_here,
            "cells": len(enb["cells"]),
            "relations": len(enb["relations"]),
            "pattern": "two-way" if two_way else "one-way",
            "ul": enb["ul"] if enb["ulOn"] else None,
            "flexScellSelect": enb["flexScellSelect"],
            "capr": "CAPR" in cls_here,
            "warnings": sum(1 for f in enb["findings"] if f["severity"] == "warning"),
        }
    lnbts = next((m for m in mos if m["cls"] == "LNBTS"), None)
    return {"release": release_of(lnbts["version"]) if lnbts else None, "params": params, "donor": donor}


def rank_donors(enb_setup: dict, donors: list[dict], want_ul: bool = False) -> list[dict]:
    """Donors (profile()["donor"] plus name/source) best match first, each
    with the reasons it scored."""
    techs = {c["tech"] for c in enb_setup["cells"] if c["tech"]}
    bands = {c["band"] for c in enb_setup["cells"] if c["band"] is not None}
    cbrs = any(c["cbrs"] for c in enb_setup["cells"])
    release = enb_setup.get("release") or ""
    line = re.match(r"[A-Za-z]+", release)
    ranked = []
    for d in donors:
        score, reasons = 0, []
        if d["release"] == release:
            score += 50
            reasons.append(f"Same release ({release})")
        elif line and d["release"] and d["release"].startswith(line.group(0)):
            score += 15
            reasons.append(f"Same product line ({line.group(0)})")
        if techs and techs <= set(d["techs"]):
            score += 20
            reasons.append(" + ".join(sorted(techs)) + " like this file")
        shared = sorted(bands & set(d["bands"]))
        if shared:
            score += 10 * min(len(shared), 3)
            reasons.append("Band " + ", ".join(str(b) for b in shared))
        if cbrs and d["cbrs"]:
            score += 15
            reasons.append("Has a CBRS CA profile")
        elif cbrs:
            score -= 10
        if want_ul and d["ul"]:
            score += 5
        score -= min(abs(d["cells"] - len(enb_setup["cells"])), 5)
        ranked.append({**d, "score": score, "reasons": reasons})
    ranked.sort(key=lambda d: (-d["score"], d["name"].lower()))
    return ranked


class _Donor:
    """The donor file's CA setup, reduced to the templates the wizard copies."""

    def __init__(self, raw: bytes, name: str):
        mos = _load(raw)
        kids = _kids(mos)
        best = None
        for lnbts in (m for m in mos if m["cls"] == "LNBTS"):
            cells = _cells(lnbts, kids)
            n = sum(len(c["carels"]) for c in cells)
            if lnbts["p"].get("actDLCAggr") == "true" and n and (best is None or n > best[2]):
                best = (lnbts, cells, n)
        if best is None:
            raise PlanError([f"{name} has no working CA setup to copy from (downlink CA on, with CAREL relations)."])
        self.name = name
        self.lnbts, self.cells, _ = best
        self.p = self.lnbts["p"]
        self.release = release_of(self.lnbts["version"])
        self.objects = {cls: next((m for m in kids[self.lnbts["dn"]] if m["cls"] == cls), None) for cls in _ENB_OBJECTS}
        self.ul_value = self.p.get("actULCAggr")
        self.ul_on = self.ul_value not in (None, "false")
        self.pcells = [c for c in self.cells if c["carels"]]
        self.uses_capr = any(c["caprs"] for c in self.pcells)
        self.capr_own = any(m["p"].get("earfcnDL") == c["earfcn"] for c in self.pcells for m in c["caprs"])

    def cell(self, tech: Optional[str], strict: bool = False) -> Optional[dict]:
        """The donor PCell standing in for a target cell of this technology:
        any PCell when none matches, or None if `strict`."""
        return next((c for c in self.pcells if c["tech"] == tech), None if strict else self.pcells[0])

    def carel(self, tech: Optional[str]) -> dict:
        return self.cell(tech)["carels"][0]["p"] if self.cell(tech)["carels"] else {}

    def capr(self, tech: Optional[str], own: bool) -> Optional[dict]:
        ordered = sorted(self.pcells, key=lambda c: c["tech"] != tech)
        for c in ordered:
            for m in c["caprs"]:
                if (m["p"].get("earfcnDL") == c["earfcn"]) == own:
                    return m["p"]
        return None


# --- Writing ----------------------------------------------------------------

class _Planner:
    def __init__(self, raw: bytes, enb: _Enb, donor: _Donor, pairs: dict[str, list[str]], ul: bool,
                 options: dict, release_params: Optional[dict[str, set[str]]]):
        self.doc = _Doc(raw)
        self.enb = enb
        self.donor = donor
        self.pairs = pairs
        self.ul = ul
        self.opts = options
        self.release_params = release_params
        self.skipped: dict[tuple[str, str], dict] = {}
        self.unverified: set[str] = set()
        self.notes: list[str] = []
        self.created: set[str] = set()
        lnbts_class = (self.doc.mos[enb.dn].get("class") or "NOKLTE:LNBTS")
        self.ns = lnbts_class.rsplit(":", 1)[0] + ":" if ":" in lnbts_class else ""
        self.version = enb.lnbts["version"]
        # Cells in CA after this plan, and the groups they form.
        self.ca_cells = {d for p, ss in pairs.items() if ss for d in [p, *ss]}
        self.scell_of: dict[str, list[str]] = {}
        for p, ss in pairs.items():
            for s in ss:
                self.scell_of.setdefault(s, []).append(p)
        self.components = self._components()

    # Helpers -----------------------------------------------------------------

    def _components(self) -> list[list[dict]]:
        parent = {d: d for d in self.ca_cells}

        def find(d: str) -> str:
            while parent[d] != d:
                parent[d] = parent[parent[d]]
                d = parent[d]
            return d

        for p, ss in self.pairs.items():
            for s in ss:
                parent[find(s)] = find(p)
        groups: dict[str, list[dict]] = {}
        for d in sorted(self.ca_cells, key=_natural):
            groups.setdefault(find(d), []).append(self.enb.by_dn[d])
        return list(groups.values())

    def allowed(self, cls: str, name: str) -> Optional[bool]:
        if self.release_params is None:
            return None
        names = self.release_params.get(cls)
        return None if names is None else name in names

    def donor_values(self, cls: str, params: dict[str, Optional[str]], exclude: tuple = ()) -> list[tuple[str, str]]:
        out = []
        for name, value in params.items():
            if name in exclude or value is None:
                continue
            ok = self.allowed(cls, name)
            if ok is False:
                self.skipped.setdefault((cls, name), {
                    "class": cls, "param": name, "value": value,
                    "reason": f"No {self.enb.release} file in your corpus sets {name} on {cls}, so an older BTS "
                              "may not know it.",
                })
                continue
            if ok is None:
                self.unverified.add(cls)
            out.append((name, value))
        return sorted(out, key=lambda x: x[0].lower())

    def put(self, dn: str, name: str, value: Optional[str], why: dict) -> bool:
        if value is None:
            return False
        return self.doc.set(dn, name, value, why)

    def put_donor(self, dn: str, cls: str, name: str, value: Optional[str], why: dict) -> bool:
        if value is None:
            return False
        if self.allowed(cls, name) is False:
            self.skipped.setdefault((cls, name), {
                "class": cls, "param": name, "value": value,
                "reason": f"No {self.enb.release} file in your corpus sets {name} on {cls}, so an older BTS may not know it.",
            })
            return False
        return self.doc.set(dn, name, value, why)

    def cur(self, dn: str, name: str) -> Optional[str]:
        return self.doc.get(dn, name)

    def _lnbts_fdd(self, name: str) -> Optional[str]:
        sub = next((m for m in self.enb.kids[self.enb.dn] if m["cls"] == "LNBTS_FDD"), None)
        return sub["p"].get(name) if sub else None

    def prefix(self, cell: dict) -> str:
        return "2.1" if cell["tech"] == "FDD" else "3.1"

    # Steps -------------------------------------------------------------------

    def switches(self) -> None:
        b = self.enb.dn
        self.put(b, "actDLCAggr", "true", _why("switches", "Turns downlink CA on.", "choice"))
        if self.cur(b, "actEnhAcAndGbrServices") != "true":
            self.put(b, "actEnhAcAndGbrServices", "true",
                     _why("switches", "Downlink CA can only be on when this is on. Every CA file in your corpus has it on.",
                          "official", ("actDLCAggr", "1.1")))
        if self.ul:
            self.put(b, "actULCAggr", self.donor.ul_value,
                     _why("switches", f"Turns uplink CA on, in the mode {self.donor.name} uses.", "donor"))
        else:
            if self.enb.ul_on:
                self.put(b, "actULCAggr", "false", _why("switches", "You chose downlink CA only.", "choice"))
            for flag, rule in (("actAdvUlScellHandling", "1.3"), ("actInterEnbULCAggr", "1.2")):
                if self.cur(b, flag) == "true":
                    self.put(b, flag, "false",
                             _why("switches", f"{flag} needs uplink CA on.", "official", ("actULCAggr", rule)))
        if any(c["tech"] == "FDD" for c in self.enb.cells) and self.cur(b, "caSchedFairFact") is None:
            self.put(b, "caSchedFairFact", self.donor.p.get("caSchedFairFact") or "0",
                     _why("switches", "Must be set when downlink CA is on with FDD cells.", "official",
                          ("actDLCAggr", "2.1.9")))

    def objects(self) -> None:
        enb = self.enb
        has_cbrs = any(_is_cbrs(c) for c in enb.cells)
        has_laa = any(c["band"] == 46 for c in enb.cells)
        if has_laa and self._lnbts_fdd("actUnlicensedAcc") == "off":
            self.notes.append("actUnlicensedAcc is off, which disables the Band 46 (LAA) cells. Turn LAA on for them "
                              "to carry traffic.")
        for cls in _ENB_OBJECTS:
            existing = [m for m in enb.kids[enb.dn] if m["cls"] == cls]
            if cls == "CADPRCBRS" and not has_cbrs or cls == "CADPRLAA" and not has_laa:
                continue
            if cls == "CADPR" and len(existing) > 1:
                self.notes.append(f"{_label(enb.dn)} has {len(existing)} CADPR objects; downlink CA needs exactly one. "
                                  "Delete the extra one by hand.")
            if existing:
                continue
            src = self.donor.objects.get(cls)
            if src is None:
                self.notes.append(f"{self.donor.name} has no {cls}, so none was added.")
                continue
            reason = {
                "CAGENB": "CA settings for the whole eNB. Downlink CA needs one.",
                "CADPR": "The default CA profile. Downlink CA needs exactly one.",
                "CADPRCBRS": "The CA profile for CBRS cells.",
                "CADPRLAA": "The CA profile for LAA cells.",
            }[cls]
            basis = "official" if cls in ("CAGENB", "CADPR") else "donor"
            dn = self.doc.create(enb.dn, cls, self.doc.next_free(enb.dn, cls, 0), self.donor_values(cls, src["p"]),
                                 self.ns + cls, self.version,
                                 _why("objects", reason + f" Values from {self.donor.name}.", basis,
                                      ("actDLCAggr", "1.3") if basis == "official" else None))
            self.created.add(dn)

    def relations(self) -> None:
        enb, doc = self.enb, self.doc
        for cell in enb.cells:
            pdn = cell["mo"]["dn"]
            name = _label(pdn)
            wanted = self.pairs.get(pdn, [])
            kept: dict[str, str] = {}
            for r in (r for r in enb.relations if r["pcell"] is cell and not r["foreign"]):
                carel = r["carel"]["dn"]
                s = r["scell"]
                if s is None:
                    doc.delete(carel, _why("relations", f"Points at lcrId {r['carel']['p'].get('lcrId')}, which no "
                                           f"cell on {_label(enb.dn)} has.", "official",
                                           ("actDLCAggr", f"{self.prefix(cell)}.6")))
                elif s is cell:
                    doc.delete(carel, _why("relations", f"{name} can't be its own SCell.", "official",
                                           ("actDLCAggr", f"{self.prefix(cell)}.5")))
                elif s["mo"]["dn"] in kept:
                    doc.delete(carel, _why("relations", f"A second relation to {_label(s['mo']['dn'])}.", "official",
                                           ("actDLCAggr", f"{self.prefix(cell)}.5")))
                elif s["mo"]["dn"] not in wanted:
                    doc.delete(carel, _why("relations", f"{_label(s['mo']['dn'])} is no longer an SCell of {name}.",
                                           "choice"))
                else:
                    kept[s["mo"]["dn"]] = carel
            template = self.donor.carel(cell["tech"])
            prios = self._priorities(wanted, kept)
            for sdn in wanted:
                s = enb.by_dn[sdn]
                prio = prios[sdn]
                if sdn in kept:
                    self.put(kept[sdn], "scellPrio", prio,
                             _why("relations", "Priority in the order you chose (1 is tried first).", "choice"))
                    continue
                params = dict(self.donor_values("CAREL", template, _CAREL_OWN))
                params.update({"lcrId": s["mo"]["p"].get("lcrId"), "lnBtsId": enb.own_id})
                for field, value in (("scellPrio", prio),
                                     ("maxNumOfSuppMimoLayer", _layers(s, template.get("maxNumOfSuppMimoLayer")))):
                    if self.allowed("CAREL", field) is not False:
                        params[field] = value
                dn = doc.create(pdn, "CAREL", doc.next_free(pdn, "CAREL", 1),
                                sorted(params.items(), key=lambda x: x[0].lower()), self.ns + "CAREL", self.version,
                                _why("relations", f"{_label(sdn)} (lcrId {params['lcrId']}) becomes an SCell of {name}. "
                                     f"Other values from {self.donor.name}.", "choice"))
                self.created.add(dn)
            self._caprs(cell, wanted)

    def _priorities(self, wanted: list[str], kept: dict[str, str]) -> dict[str, str]:
        """scellPrio per SCell. While the kept relations come first and their
        priorities already follow the requested order, they keep them (ties
        included, which working files use) and new ones go after; otherwise
        all are renumbered 1, 2, ..."""
        first = [s for s in wanted if s in kept]
        current = [_int(self.cur(kept[s], "scellPrio")) for s in first]
        if wanted[:len(first)] == first and None not in current and current == sorted(current):
            out = {s: str(v) for s, v in zip(first, current)}
            last = current[-1] if current else 0
            for s in wanted[len(first):]:
                last = min(last + 1, 10)
                out[s] = str(last)
            return out
        return {s: str(min(i + 1, 10)) for i, s in enumerate(wanted)}

    def _caprs(self, cell: dict, wanted: list[str]) -> None:
        """A PCell's CAPRs cover its SCells' carriers (and its own, when the
        donor's do). A CAPR left on a carrier nothing uses is retargeted
        before a new one is added, which is how the corpus's stale pico
        profile was fixed by hand."""
        pdn = cell["mo"]["dn"]
        name = _label(pdn)
        existing = [{"dn": m["dn"], "e": m["p"].get("earfcnDL"), "p": m["p"]} for m in cell["caprs"]]
        if not wanted or not (self.donor.uses_capr or existing):
            return
        need = [self.enb.by_dn[s]["earfcn"] for s in wanted]
        if self.donor.capr_own:
            need.append(cell["earfcn"])
        need = list(dict.fromkeys(need))
        covered = {e["e"] for e in existing}
        stale = [e for e in existing if e["e"] not in self.enb.carriers
                 or (e["e"] == cell["earfcn"] and not self.donor.capr_own and cell["earfcn"] not in need)]
        for carrier in need:
            if carrier in covered:
                continue
            if self.opts["cleanStale"] and stale:
                e = stale.pop(0)
                was = e["e"]
                self.put(e["dn"], "earfcnDL", carrier, _why(
                    "relations",
                    f"Was left on EARFCN {was}, " + ("which no cell uses" if was not in self.enb.carriers
                                                    else f"{name}'s own carrier") +
                    f"; retargeted to its SCell carrier {carrier} instead of adding another CA profile.", "files"))
                covered.add(carrier)
                continue
            template = self.donor.capr(cell["tech"], carrier == cell["earfcn"]) or self.donor.capr(cell["tech"], False) \
                or (existing[0]["p"] if existing else {})
            params = dict(self.donor_values("CAPR", template, ("earfcnDL",)))
            params["earfcnDL"] = carrier
            dn = self.doc.create(pdn, "CAPR", self.doc.next_free(pdn, "CAPR", 0),
                                 sorted(params.items(), key=lambda x: x[0].lower()), self.ns + "CAPR", self.version,
                                 _why("relations", f"CA profile for EARFCN {carrier} on {name}. In your corpus's CA files a "
                                      "PCell's CAPRs cover its SCells' carriers. Values from "
                                      f"{self.donor.name if self.donor.uses_capr else 'its existing CAPR'}.", "files"))
            self.created.add(dn)
            covered.add(carrier)
        if self.opts["cleanStale"]:
            for e in stale:
                if e["e"] not in self.enb.carriers:
                    self.doc.delete(e["dn"], _why("cleanup", f"{name}'s {_label(e['dn'])} points at EARFCN {e['e']}, "
                                                  "which no cell on this eNB uses.", "files"))

    def cells(self) -> None:
        enb, doc = self.enb, self.doc
        pools = Counter(v for c in enb.cells if (v := c["mo"]["p"].get("caPoolId")) is not None)
        default_pool = pools.most_common(1)[0][0] if pools else "0"
        in_comp: set[str] = set()
        for comp in self.components:
            dns = [c["mo"]["dn"] for c in comp]
            in_comp.update(dns)
            cv = Counter(v for c in comp if (v := c["mo"]["p"].get("caPoolId")) is not None)
            pool = cv.most_common(1)[0][0] if cv else default_pool
            for c in comp:
                if self.cur(c["mo"]["dn"], "caPoolId") != pool:
                    self.put(c["mo"]["dn"], "caPoolId", pool, _why(
                        "cells", f"A PCell and its SCells must share a CA pool; {', '.join(_label(d) for d in dns)} use "
                                 f"{pool}.", "official", ("actDLCAggr", f"{self.prefix(c)}.7.1")))
            # Flags a PCell and its SCells must agree on.
            for name, on_sub, rule in (("rcEnableDl", False, ("2.1.8", "3.1.7")),
                                       ("rcEnableUl", False, ("2.1.8", "3.1.7")),
                                       ("actAutoPucchAlloc", True, ("2.1.10", "3.1.8"))):
                def where(c: dict) -> Optional[str]:
                    return (c["sub"]["dn"] if c["sub"] else None) if on_sub else c["mo"]["dn"]
                values = {self.cur(where(c), name) for c in comp if where(c)}
                if len(values) <= 1:
                    continue
                rep = self.donor.cell(comp[0]["tech"])
                donor_v = (rep["sub"]["p"] if on_sub and rep["sub"] else rep["mo"]["p"]).get(name)
                first_p = next((c for c in comp if self.pairs.get(c["mo"]["dn"])), comp[0])
                target = donor_v or self.cur(where(first_p), name)
                for c in comp:
                    if where(c) and self.cur(where(c), name) != target:
                        self.put(where(c), name, target, _why(
                            "cells", f"A PCell and its SCells must match on {name}; set to {target} as in "
                                     f"{self.donor.name if donor_v else _label(first_p['mo']['dn'])}.",
                            "official", ("actDLCAggr", rule[0] if c["tech"] == "FDD" else rule[1])))
        for c in enb.cells:
            if c["mo"]["dn"] not in in_comp and self.cur(c["mo"]["dn"], "caPoolId") is None:
                self.put(c["mo"]["dn"], "caPoolId", default_pool, _why(
                    "cells", "Every LNCEL needs a caPoolId when downlink CA is on. Exports that run CA on air often "
                             "leave it out, so this follows the dictionary rather than your files.",
                    "official", ("actDLCAggr", f"{self.prefix(c)}.3")))

        for c in enb.cells:
            dn = c["mo"]["dn"]
            name = _label(dn)
            n = len(self.pairs.get(dn, []))
            if n:
                if self.cur(dn, "scellFastSchedulingSelect") is None:
                    self.put(dn, "scellFastSchedulingSelect",
                             self.donor.cell(c["tech"])["mo"]["p"].get("scellFastSchedulingSelect") or "normal",
                             _why("cells", "Every PCell must set it.", "official", ("actDLCAggr", "1.3")))
                self._max_scells(c, n)
            if c["cbsdcel"] is not None and c["tech"] == "TDD" and c["sub"] and dn in self.ca_cells:
                cb = c["cbsdcel"]["dn"]
                for prefix in ("desired", "fallB"):
                    for own, theirs in (("tddFrameConf", f"{prefix}TddFrameConf"), ("tddSpecSubfConf", f"{prefix}TddSpecSubfConf")):
                        actual = self.cur(c["sub"]["dn"], own)
                        if self.cur(cb, theirs) is not None and actual is not None:
                            self.put(cb, theirs, actual, _why(
                                "cells", f"{name} runs {own} {actual}. The SAS grants what CBSDCEL asks for, so a "
                                         "different request could move the cell off its CA partners' TDD config.",
                                "files"))
            # A PCell must be open; an SCell-only cell can be barred.
            sib = c["sib"]["dn"] if c["sib"] else None
            if sib and n and self.cur(sib, "cellBarred") == "barred":
                self.put(sib, "cellBarred", "notBarred", _why(
                    "cells", f"{name} is now a PCell, so phones must be able to camp on it.", "choice"))
                if (_int(self.cur(sib, "cellReSelPrio")) or 0) == 0:
                    others = [_int(self.cur(o["sib"]["dn"], "cellReSelPrio")) for o in enb.cells
                              if o["sib"] and o is not c and self.cur(o["sib"]["dn"], "cellBarred") != "barred"]
                    prio = str(max((o for o in others if o is not None), default=7))
                    self.put(sib, "cellReSelPrio", prio, _why(
                        "cells", "Reselection priority 0 was set while it was barred; this matches the other open cells.",
                        "choice"))
            elif (sib and not n and dn in self.ca_cells and self.opts["barScellOnly"]
                  and not (c["sub"] and c["sub"]["p"].get("actSdlc") == "true")):
                self.put(sib, "cellBarred", "barred", _why(
                    "cells", f"{name} is only ever an SCell; barred, phones reach it only through CA. The one-way "
                             "pico in your corpus does this.", "choice"))
                self.put(sib, "cellReSelPrio", "0", _why("cells", "Matches the barred SCell in your corpus.", "choice"))
        if self.opts["raiseModulation"]:
            self._modulation()

    def _max_scells(self, c: dict, n: int) -> None:
        """Let a UE use all of a PCell's SCells at once when PUCCH is sized
        automatically (as in every CA file in the corpus). With manual PUCCH,
        raising it would need PUCCH changes, so it's left with a note."""
        dn = c["mo"]["dn"]
        name = _label(dn)
        current = _int(self.cur(dn, "maxNumScells")) or 1
        auto = c["sub"] is not None and self.cur(c["sub"]["dn"], "actAutoPucchAlloc") == "true"
        want = min(n, 3 if c["tech"] == "TDD" else 2)
        floor_rule = None
        cagenb = next((d for d in self.doc.mos if d.startswith(self.enb.dn + "/CAGENB-")
                       and d.count("/") == self.enb.dn.count("/") + 1), None)
        if (c["tech"] == "FDD" and self.ul and cagenb
                and self.cur(cagenb, "maxDlCaConfigForUlCa") == "max_5CC_DL_CA"):
            want = max(want, 3)
            floor_rule = ("maxNumScells", "1.8")
        if current >= want:
            return
        if not auto:
            self.notes.append(f"{name} sizes PUCCH by hand (actAutoPucchAlloc false), so maxNumScells stays {current}; "
                              f"raising it to {want} would need PUCCH changes. The check below lists them.")
            return
        self.put(dn, "maxNumScells", str(want), _why(
            "cells",
            f"Lets a UE use {want} SCells at once." + (" Uplink CA with max_5CC_DL_CA needs at least 3." if floor_rule else
                                                      f" {name} has {n} SCells."),
            "official" if floor_rule else "choice", floor_rule))
        if want > 2 and c["tech"] == "FDD":
            if c["sub"] and self.cur(c["sub"]["dn"], "actUciOnlyGrants") != "true":
                self.put(c["sub"]["dn"], "actUciOnlyGrants", "true", _why(
                    "cells", "The dictionary requires it when maxNumScells is above 2.", "official",
                    ("maxNumScells", "1.5")))
            if self.cur(dn, "cellType") != "large" and self.cur(dn, "actEicic") == "true":
                self.put(dn, "actEicic", "false", _why(
                    "cells", "eICIC must be off when maxNumScells is above 2, unless cellType is large.", "official",
                    ("maxNumScells", "1.6")))

    def _modulation(self) -> None:
        """An SCell only adds downlink, so it shouldn't cap below its PCells.
        Raising it also lifts the limits the lower cap put on related
        parameters (actModulationSchemeDl rules 1.1-1.4)."""
        for sdn, pdns in self.scell_of.items():
            s = self.enb.by_dn[sdn]
            mine = self.cur(sdn, "actModulationSchemeDl")
            best = max(pdns, key=lambda d: _MODULATION_RANK.get(self.cur(d, "actModulationSchemeDl") or "", -1))
            target = self.cur(best, "actModulationSchemeDl")
            if target is None or _MODULATION_RANK.get(mine or "", -1) >= _MODULATION_RANK.get(target, -1):
                continue
            name = _label(sdn)
            if (target == "256QAM" and s["sub"] and s["tech"] == "TDD"
                    and self.cur(s["sub"]["dn"], "actTmSwitch") == "true"):
                self.notes.append(f"{name} stays at {mine}: 256QAM with TM switching (actTmSwitch) also needs a TMSWPR "
                                  "profile, which the wizard doesn't create.")
                continue
            self.put(sdn, "actModulationSchemeDl", target, _why(
                "cells", f"{_label(best)} allows {target}; downlink is all an SCell adds, so a lower cap limits CA.",
                "files"))
            if target == "256QAM" and self.cur(sdn, "actDl256QamChQualEst") is None:
                self.put(sdn, "actDl256QamChQualEst", self.cur(best, "actDl256QamChQualEst") or "false", _why(
                    "cells", "256QAM needs actDl256QamChQualEst configured. Same value as the PCell.", "official",
                    ("actModulationSchemeDl", "1.4")))
            p_int, s_int = self.cur(best, "dlInterferenceModulation"), self.cur(sdn, "dlInterferenceModulation")
            if (p_int in _INTERFERENCE_RANK and _INTERFERENCE_RANK.get(s_int or "", -1) < _INTERFERENCE_RANK[p_int]):
                self.put(sdn, "dlInterferenceModulation", p_int, _why(
                    "cells", f"Was held at {s_int} by the old modulation cap; now matches {_label(best)}.", "official",
                    ("dlInterferenceModulation", None)))

    def fill(self) -> None:
        """Donor CA tuning: added where this file lacks it (fillMissing), or
        replacing a different value (copyTuning)."""
        fill, tune = self.opts["fillMissing"], self.opts["copyTuning"]
        if not fill and not tune:
            return

        def apply(dn: str, cls: str, name: str, value: Optional[str]) -> None:
            if value is None:
                return
            old = self.cur(dn, name)
            if old is None and fill:
                self.put_donor(dn, cls, name, value, _why("fill", f"Not set here; {self.donor.name} sets {value}.", "donor"))
            elif old is not None and old != value and tune:
                self.put_donor(dn, cls, name, value, _why("tuning", f"{self.donor.name} uses {value}.", "donor"))

        enb = self.enb
        for name in _TUNING["LNBTS"]:
            apply(enb.dn, "LNBTS", name, self.donor.p.get(name))
        for cls in _ENB_OBJECTS:
            src = self.donor.objects.get(cls)
            for m in (m for m in enb.kids[enb.dn] if m["cls"] == cls and m["dn"] not in self.created):
                if src is not None:
                    for name, value in src["p"].items():
                        apply(m["dn"], cls, name, value)
        for c in enb.cells:
            rep = self.donor.cell(c["tech"], strict=True)
            if c["mo"]["dn"] not in self.ca_cells or rep is None:
                continue
            for name in _TUNING["LNCEL"]:
                apply(c["mo"]["dn"], "LNCEL", name, rep["mo"]["p"].get(name))
            if c["sub"] and rep["sub"] and c["sub"]["cls"] == rep["sub"]["cls"]:
                for name in _TUNING["SUB"]:
                    apply(c["sub"]["dn"], c["sub"]["cls"], name, rep["sub"]["p"].get(name))
            if tune:
                template = self.donor.carel(c["tech"])
                for carel in c["carels"]:
                    if carel["dn"] in self.doc.mos:
                        for name, value in template.items():
                            if name not in _CAREL_OWN:
                                apply(carel["dn"], "CAREL", name, value)

    def cleanup(self) -> None:
        """CA-aware idle-mode load balancing lists carriers in tables. A row
        for a carrier no cell uses is retargeted to a new SCell carrier its
        CAIMLBP doesn't list yet; otherwise it's reported."""
        if not self.opts["cleanStale"]:
            return
        enb = self.enb
        for cag in (m for m in enb.kids[enb.dn] if m["cls"] == "CAGENB"):
            for lbp in (m for m in enb.kids[cag["dn"]] if m["cls"] == "CAIMLBP"):
                pcell_carriers = {row.get("earfcnDL") for row in lbp["lists"].get("pcellConfig", [])}
                for row_i, row in enumerate(lbp["lists"].get("pcellConfig", [])):
                    if row.get("earfcnDL") not in enb.carriers:
                        self.notes.append(f"{_label(lbp['dn'])} pcellConfig row {row_i + 1} lists EARFCN "
                                          f"{row.get('earfcnDL')}, which no cell uses. Left as is.")
                scell_carriers = []
                for pdn, ss in self.pairs.items():
                    if enb.by_dn[pdn]["earfcn"] in pcell_carriers:
                        scell_carriers += [enb.by_dn[s]["earfcn"] for s in ss]
                for lbs in (m for m in enb.kids[lbp["dn"]] if m["cls"] == "CAIMLBS"):
                    rows = lbs["lists"].get("scellConfig", [])
                    listed = {r.get("earfcnDL") for r in rows}
                    missing = [e for e in dict.fromkeys(scell_carriers) if e not in listed]
                    for i, r in enumerate(rows):
                        if r.get("earfcnDL") in enb.carriers:
                            continue
                        if missing:
                            carrier = missing.pop(0)
                            self.doc.set_item(lbs["dn"], "scellConfig", i, "earfcnDL", carrier, _why(
                                "cleanup", f"Listed EARFCN {r.get('earfcnDL')}, which no cell uses; retargeted to the "
                                           f"SCell carrier {carrier}.", "files"))
                        else:
                            self.notes.append(f"{_label(lbs['dn'])} scellConfig row {i + 1} lists EARFCN "
                                              f"{r.get('earfcnDL')}, which no cell uses. Left as is.")

    def admission(self) -> None:
        """maxNumActUE >= maxNumCaConfUe >= its Dc/3c limits, after any
        donor values landed (maxNumCaConfUe rules)."""
        for c in self.enb.cells:
            if c["mo"]["dn"] not in self.pairs or not c["sub"]:
                continue
            sub = c["sub"]["dn"]
            act, conf = _int(self.cur(sub, "maxNumActUE")), _int(self.cur(sub, "maxNumCaConfUe"))
            if act is not None and conf is not None and conf > act:
                self.put(sub, "maxNumCaConfUe", str(act), _why(
                    "cells", f"Can't admit more CA UEs than UEs (maxNumActUE is {act}).", "official",
                    ("maxNumCaConfUe", None)))
                conf = act
            for name in ("maxNumCaConfUeDc", "maxNumCaConfUe3c"):
                v = _int(self.cur(sub, name))
                if conf is not None and v is not None and v > conf:
                    self.put(sub, name, str(conf), _why(
                        "cells", f"Must not exceed maxNumCaConfUe ({conf}).", "official", ("maxNumCaConfUe", None)))


def _confirm(enb: _Enb, pairs: dict[str, list[str]], ul: bool) -> list[str]:
    """What the XML can't show and the user has to check before loading it."""
    combos = []
    for p, ss in pairs.items():
        for s in ss:
            combo = _band_combo(enb.by_dn[p], enb.by_dn[s])
            if combo and combo not in combos:
                combos.append(combo)
    out = [
        "The BTS is licensed for LTE1089 Downlink carrier aggregation - 2 CC, which Nokia's dictionary lists as an "
        "optional feature" + (", and has uplink CA (LTE1092 Uplink carrier aggregation - 2 CC)" if ul else "") + ".",
        "The baseband has capacity for the carriers in CA.",
    ]
    if combos:
        out.append(f"Your phones support {' / '.join(combos)} (3GPP band combination names).")
    if any(_is_cbrs(enb.by_dn[d]) for d in {d for p, ss in pairs.items() for d in [p, *ss]}):
        out.append("The SAS grants every CBRS carrier in CA. Each is granted on its own, and CA stops while one is "
                   "suspended.")
    return out


def plan_ca(raw: bytes, donor_raw: bytes, donor_name: str, request: dict,
            release_index: Optional[dict[Optional[str], dict[str, set[str]]]] = None) -> tuple[bytes, dict]:
    """Plans the request against the file and returns (new bytes, plan).
    `release_index` is {release: {class: parameter names}} over the corpus;
    without it nothing is filtered. Raises PlanError for a request the rules
    forbid, XmlParseError for an unreadable file. Nothing is written;
    main.py decides that."""
    mos = _load(raw)
    kids = _kids(mos)
    lnbts_all = [m for m in mos if m["cls"] == "LNBTS"]
    lnbts = next((m for m in lnbts_all if m["dn"] == request.get("enb")), lnbts_all[0] if len(lnbts_all) == 1 else None)
    if lnbts is None:
        raise PlanError(["This file has no LTE eNB (LNBTS) to set up CA on." if not lnbts_all
                         else "Say which eNB (LNBTS) to set up."])
    enb = _Enb(lnbts, kids, mos)
    pairs = enb.normalize(request.get("relations") or [])
    if not any(pairs.values()):
        raise PlanError(["Pick at least one PCell and SCell pair."])
    ul = bool(request.get("ul"))
    if ul and enb.ul_blockers():
        raise PlanError([f"Uplink CA can't be on while actFlexDupGap is true on "
                         f"{', '.join(_label(c['mo']['dn']) for c in enb.ul_blockers())} (actULCAggr rule 2.4)."])
    donor = _Donor(donor_raw, donor_name)
    if ul and not donor.ul_on:
        raise PlanError([f"{donor_name} runs downlink CA only, so it has no uplink CA mode to copy. Pick a donor "
                         "that runs uplink CA, or turn uplink CA off."])
    options = {**DEFAULT_OPTIONS, **{k: bool(v) for k, v in (request.get("options") or {}).items() if k in DEFAULT_OPTIONS}}

    release_params = release_index.get(enb.release, {}) if release_index is not None else None
    planner = _Planner(raw, enb, donor, pairs, ul, options, release_params)
    planner.switches()
    planner.objects()
    planner.relations()
    planner.cells()
    planner.fill()
    planner.cleanup()
    planner.admission()
    new_bytes = planner.doc.raw()

    def enb_summary(analysis: dict) -> dict:
        e = next((x for x in analysis["enbs"] if x["id"] == enb.dn), None)
        findings = e["findings"] if e else []
        return {
            "errors": sum(1 for f in findings if f["severity"] == "error"),
            "warnings": sum(1 for f in findings if f["severity"] == "warning"),
            "infos": sum(1 for f in findings if f["severity"] == "info"),
            "findings": findings,
            "relations": e["relations"] if e else [],
            "cells": e["cells"] if e else [],
        }

    before, after = enb_summary(analyze_loaded(mos)), enb_summary(analyze_ca(new_bytes))
    n_rel = sum(len(s) for s in pairs.values())
    # The first new relation, else the first one the eNB has after the change.
    first_carel = next((c["dn"] for c in planner.doc.changes if c["op"] == "create" and c["class"] == "CAREL"),
                       after["relations"][0]["id"] if after["relations"] else None)
    return new_bytes, {
        "enb": enb.dn,
        "release": enb.release,
        "donor": {"name": donor.name, "release": donor.release},
        "ul": ul,
        "options": options,
        "changes": planner.doc.changes,
        "skipped": list(planner.skipped.values()),
        "unverifiedClasses": sorted(planner.unverified),
        "notes": planner.notes,
        "before": before,
        "after": after,
        "confirm": _confirm(enb, pairs, ul),
        "firstRelation": first_carel,
        "label": f"CA wizard: {'DL + UL' if ul else 'DL'} CA, {n_rel} relation{'s' if n_rel != 1 else ''} "
                 f"(values from {donor.name})",
    }

"""
Add a carrier to measure or redirect to, on picked cells: the objects that
tell a cell's UEs about another LTE or NR carrier (PROJECT_STATE §9.9,
"Carriers").

Kinds, and what each writes on every picked cell (or, for NR cells, on
the NRSYSINFO_PROFILE the cells broadcast):
- an LTE carrier for LTE cells: IRFIM (idle-mode reselection) and LNHOIF
  (inter-frequency handover), 1-16 of each per cell;
- an NR carrier for LTE cells: a row in NRFIM-1's nrCarFrqL (every file
  has one NRFIM per cell, with a row per carrier), its SSB NR-ARFCN, band
  and SSB subcarrier spacing;
- an NR carrier for NR cells: NRIRFIM (SIB4), at most 8 (TS 38.331
  maxFreq);
- an LTE carrier for NR cells: NRLIM (SIB5), at most 8 (TS 38.331
  maxEUTRA-Carrier);
- redirection on release: REDRT with redirRat eutra (redirFreqEutra), or
  REDRT with redirRat nr, a row in its redirNrCarFrq; NRREDRT on NR cells.
  Production numbers REDRT by RAT (0 eutra, 1 utraFDD, 5 geran, 9 nr), so
  a copy keeps its template's id where it is free.

An NR carrier is named by its SSB: TS 38.331 V17.6.0 SIB4 field
descriptions, dl-CarrierFreq "indicates center frequency of the SS block
of the neighbour cells"; the LTE side measures the same value (production
LTE cells list 502110, the SSB of their gNB's GSCN 6276).

Settings come from a template: the cell's own object of the class, else
another cell's of this file, else one from another file (values only,
release-filtered), else, for NRREDRT, production's own (BUILTIN): every one
of the 130 production cells with VoNR has NRREDRT-0 set alike but for its
carrier. The carrier, band and SCS come from the inputs; the
SCS keeps the template's spelling ("30KHz" on NRFIM, "30 KHz" on NRIRFIM,
"30kHz" on REDRT). Reselection priorities, thresholds and the measurement
bandwidth are the template's, with a note: the files set the bandwidth as
policy, not from the carrier (one deployment measures its 20 MHz carriers
over 50 and 75 RBs, another its 10 MHz ones over 100).

A cell that has entries for the carrier already has them replaced
instead of getting another beside them (the owner, 2026-11-03: the
cleaning actions clear out what they replace): one entry per carrier, the
others removed (a row, or an object nothing names), and the one kept set
to the carrier, band and SCS given, each old value in its reason. Its
priorities and thresholds stay: they are that carrier's own tuning, which
a template from another carrier would get wrong. A cell whose own carrier
it is is left alone and said in the plan; nothing to do at all is refused.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from . import Context, PlanError, finish
from .carrier_files import kind_of
from .doc import Doc, instance, label, release_of, why
from .qos_replace import _namers
from .sites import lte_cell, nr_cell

ID = "carrier"
TITLE = "Add a carrier to measure or redirect to"
GROUP = "Mobility"
SUMMARY = "Reselection, handover or redirection to another LTE or NR carrier on picked cells."
UI = "form"
KEYWORDS = ("carrier frequency EARFCN NR-ARFCN SSB IRFIM LNHOIF NRFIM NRIRFIM NRLIM REDRT NRREDRT reselection "
            "handover redirect inter-frequency inter-RAT measurement")

LTE, NR = "earfcn", "ssb"
KINDS = {
    "lte-lte": {"label": "An LTE carrier for LTE cells", "parent": "LNCEL", "input": LTE, "objects": ("IRFIM", "LNHOIF"),
                "detail": "Idle-mode reselection (IRFIM) and inter-frequency handover (LNHOIF) to another EARFCN."},
    "nr-lte": {"label": "An NR carrier for LTE cells", "parent": "LNCEL", "input": NR, "objects": ("NRFIM",),
               "detail": "Reselection from LTE to NR: a row in the cell's NRFIM nrCarFrqL. For EN-DC and SA anchors."},
    "redirect-lte": {"label": "An LTE carrier LTE cells redirect to", "parent": "LNCEL", "input": LTE,
                     "objects": ("REDRT:eutra",),
                     "detail": "Release with redirect to another EARFCN (REDRT, redirRat eutra)."},
    "redirect-lte-nr": {"label": "An NR carrier LTE cells redirect to", "parent": "LNCEL", "input": NR,
                        "objects": ("REDRT:nr",),
                        "detail": "Release with redirect to NR (REDRT, redirRat nr: a row in its redirNrCarFrq)."},
    "nr-nr": {"label": "An NR carrier for NR cells", "parent": "NRSYSINFO_PROFILE", "input": NR, "objects": ("NRIRFIM",),
              "detail": "Inter-frequency reselection: an NRIRFIM in the system information profile the cells use."},
    "lte-nr": {"label": "An LTE carrier for NR cells", "parent": "NRSYSINFO_PROFILE", "input": LTE, "objects": ("NRLIM",),
               "detail": "Reselection from NR to LTE: an NRLIM in the system information profile the cells use."},
    "redirect-nr": {"label": "An LTE carrier NR cells redirect to", "parent": "NRCELL", "input": LTE,
                    "objects": ("NRREDRT",),
                    "detail": "Release with redirect to LTE (NRREDRT, redirRat eutra)."},
}

# How each object names its carrier: a parameter, or a field of a row (the
# object then holds one row per carrier, and a new carrier is a new row).
OBJECTS = {
    "IRFIM": {"cls": "IRFIM", "param": "dlCarFrqEut", "ids": (1, 16)},
    "LNHOIF": {"cls": "LNHOIF", "param": "eutraCarrierInfo", "ids": (1, 16)},
    "REDRT:eutra": {"cls": "REDRT", "rat": "eutra", "param": "redirFreqEutra", "ids": (0, None)},
    "REDRT:nr": {"cls": "REDRT", "rat": "nr", "row": ("redirNrCarFrq", "carrierFreqNrCell"), "ids": (0, None)},
    "NRFIM": {"cls": "NRFIM", "row": ("nrCarFrqL", "dlCarFrqNr"), "ids": (1, None)},
    "NRIRFIM": {"cls": "NRIRFIM", "param": "dlCarrierFreq", "ids": (1, 8)},
    "NRLIM": {"cls": "NRLIM", "param": "carrierFreq", "ids": (1, 8)},
    "NRREDRT": {"cls": "NRREDRT", "param": "redirFreqEutra", "ids": (0, None)},
}
# Production's settings where no file loaded has the object, all but the carrier.
BUILTIN = {
    "NRREDRT": {"inst": "0", "p": {"redirRat": "eutra", "redirPrio": "4", "redirPrioBadUlRadio": "4"},
                "from": "production's NRREDRT (alike on all 130 production cells with VoNR)"},
}
SCS = ("15 kHz", "30 kHz", "120 kHz")
EARFCN_MAX, NR_ARFCN_MAX = 262143, 3279165  # TS 36.331 ARFCN-ValueEUTRA-r9, TS 38.331 ARFCN-ValueNR


def _parents(ctx: Context, kind: str) -> list[dict]:
    return ctx.site.of(KINDS[kind]["parent"])


def _objects(site, parent: str, key: str) -> list[dict]:
    spec = OBJECTS[key]
    return [m for m in site.child(parent, spec["cls"]) if "rat" not in spec or m["p"].get("redirRat") == spec["rat"]]


def _carriers(m: dict, key: str) -> list[str]:
    spec = OBJECTS[key]
    if "row" in spec:
        name, field = spec["row"]
        return [r.get(field) for r in m["lists"].get(name, [])]
    return [m["p"].get(spec["param"])]


def _profile_cells(ctx: Context, profile: str) -> list[dict]:
    """The NR cells that broadcast a system information profile (named in
    full, or relative to the gNB)."""
    gnb = profile.rsplit("/", 1)[0]
    return [c for c in ctx.site.child(gnb, "NRCELL")
            if c["p"].get("nrSysInfoProfileDN") in (profile, profile[len(gnb) + 1:])]


def _own(ctx: Context, kind: str, parent: dict) -> set[str]:
    """The carriers the parent's cells are on, of the kind's input."""
    site = ctx.site
    if parent["cls"] == "LNCEL":
        x = lte_cell(site, parent)
        return {x["earfcn"]} if KINDS[kind]["input"] == LTE and x["earfcn"] else set()
    cells = _profile_cells(ctx, parent["dn"]) if parent["cls"] == "NRSYSINFO_PROFILE" else [parent]
    if KINDS[kind]["input"] == NR:
        gnb = {"dn": parent["dn"].rsplit("/NRCELL-", 1)[0].rsplit("/NRSYSINFO_PROFILE-", 1)[0], "p": {}}
        return {nr_cell(site, gnb, c)["ssb"] for c in cells} - {None}
    return set()


def available(ctx: Context) -> Optional[str]:
    if any(_parents(ctx, k) for k in _kinds_with_templates(ctx)):
        return None
    return "This file has no LTE or NR cell, or no file has carrier settings to copy for its cells."


def _kinds_with_templates(ctx: Context) -> set[str]:
    have = {key for f in ctx.corpus() for key in (f.get("carriers") or {})} | {kind_of(m) for m in ctx.site.mos}
    return {k for k, spec in KINDS.items() if all(key in have for key in spec["objects"])}


def _target_label(ctx: Context, m: dict) -> str:
    site = ctx.site
    if m["cls"] == "LNCEL":
        x = lte_cell(site, m)
        return f"{label(m['dn'])} · {x['name'] or 'no name'} · EARFCN {x['earfcn'] or '?'}"
    if m["cls"] == "NRCELL":
        return f"{label(m['dn'])} · {m['p'].get('cellName') or 'no name'} · NR-ARFCN {m['p'].get('nrarfcn') or '?'}"
    cells = _profile_cells(ctx, m["dn"])
    return f"{label(m['dn'])} · " + (f"used by {', '.join(label(c['dn']) for c in cells)}" if cells else "no cell uses it")


def _suggestions(ctx: Context, input_: str) -> tuple[list[dict], dict]:
    """Carriers to offer: this file's cells first, then the other files'.
    Returns the options and, per carrier, its bandwidth or band and SCS."""
    here: dict[str, list[str]] = {}
    facts: dict[str, dict] = {}
    seen: Counter = Counter()
    site = ctx.site
    if input_ == LTE:
        for c in site.of("LNCEL"):
            x = lte_cell(site, c)
            if x["earfcn"]:
                here.setdefault(x["earfcn"], []).append(label(c["dn"]))
                facts.setdefault(x["earfcn"], {"bw": x["bw"]})
    else:
        for g in site.of("NRBTS"):
            for c in site.child(g["dn"], "NRCELL"):
                x = nr_cell(site, g, c)
                if x["ssb"]:
                    here.setdefault(x["ssb"], []).append(label(c["dn"]))
                    facts.setdefault(x["ssb"], {"band": x["band"], "scs": x["scs"]})
    for f in ctx.corpus():
        if (f["source"], f["name"]) == (ctx.source, ctx.filename):
            continue
        sites = f.get("sites") or {}
        carriers = set()
        if input_ == LTE:
            for e in sites.get("enbs", []):
                for c in e["cells"]:
                    if c.get("earfcn"):
                        carriers.add(c["earfcn"])
                        facts.setdefault(c["earfcn"], {"bw": c.get("bw")})
        else:
            for g in sites.get("gnbs", []):
                for c in g["cells"]:
                    if c.get("ssb"):
                        carriers.add(c["ssb"])
                        facts.setdefault(c["ssb"], {"band": c.get("band"), "scs": c.get("scs")})
        seen.update(carriers)
    out = []

    def describe(v: str) -> str:
        x = facts.get(v) or {}
        if input_ == LTE:
            return f"EARFCN {v}" + (f" · {x['bw']}" if x.get("bw") else "")
        return f"SSB {v}" + (f" · n{x['band']}" if x.get("band") else "") + (f" · {x['scs']}" if x.get("scs") else "")

    for v, cells in sorted(here.items(), key=lambda kv: int(kv[0])):
        out.append({"value": v, "label": describe(v), "name": ", ".join(cells[:4]) + (" here" if cells else ""),
                    "group": "This file"})
    for v, n in seen.most_common(24):
        if v not in here:
            out.append({"value": v, "label": describe(v), "name": f"in {n} file{'s' if n != 1 else ''}",
                        "group": "Other files"})
    return out, facts


def _scs_label(v: Optional[str]) -> Optional[str]:
    digits = "".join(ch for ch in v or "" if ch.isdigit())
    return f"{digits} kHz" if f"{digits} kHz" in SCS else None


def setup(ctx: Context) -> dict:
    kinds, targets, earfcns, ssbs, band_by, scs_by = [], {}, {}, {}, {}, {}
    lte, lte_facts = _suggestions(ctx, LTE)
    nr, nr_facts = _suggestions(ctx, NR)
    copyable = _kinds_with_templates(ctx)
    for k, spec in KINDS.items():
        # Offered where there are cells for it and an object of the kind to copy, here or in another file.
        parents = _parents(ctx, k)
        if not parents or k not in copyable:
            continue
        kinds.append({"value": k, "key": k, "label": spec["label"], "details": [spec["detail"]],
                      "group": "Measure and reselect" if not k.startswith("redirect") else "Redirect on release"})
        targets[k] = [{"value": m["dn"], "label": _target_label(ctx, m)} for m in parents]
        opts, facts, store = (lte, lte_facts, earfcns) if spec["input"] == LTE else (nr, nr_facts, ssbs)
        store[k] = [{**o, "key": f"{k}|{o['value']}"} for o in opts]
        for o in opts:
            x = facts.get(o["value"]) or {}
            if x.get("band"):
                band_by[f"{k}|{o['value']}"] = x["band"]
            if _scs_label(x.get("scs")):
                scs_by[f"{k}|{o['value']}"] = _scs_label(x["scs"])
    lte_kinds = [k for k in KINDS if KINDS[k]["input"] == LTE]
    nr_kinds = [k for k in KINDS if KINDS[k]["input"] == NR]
    return {
        "intro": "Tells the picked cells' UEs about another carrier: to reselect to, hand over to, or be redirected "
                 "to on release. The settings are copied from the cell's own objects of the kind where it has one.",
        "fields": [
            {"id": "kind", "label": "Add", "type": "select", "options": kinds,
             "default": kinds[0]["value"] if len(kinds) == 1 else None},
            {"id": "targets", "label": "On", "type": "checks", "dependsOn": "kind", "optionsByKey": targets},
            {"id": "earfcn", "label": "EARFCN", "type": "combo", "dependsOn": "kind", "optionsByKey": earfcns,
             "showIf": {"field": "kind", "in": lte_kinds}, "placeholder": "66786"},
            {"id": "ssb", "label": "SSB NR-ARFCN", "type": "combo", "dependsOn": "kind", "optionsByKey": ssbs,
             "showIf": {"field": "kind", "in": nr_kinds}, "placeholder": "502110",
             "hint": "Where the carrier's SSB is (TS 38.331 SIB4 dl-CarrierFreq: the centre of the SS block), not "
                     "the channel centre."},
            {"id": "band", "label": "NR band", "type": "text", "dependsOn": "ssb", "defaultByKey": band_by,
             "showIf": {"field": "kind", "in": ["nr-lte", "nr-nr"]}, "placeholder": "41"},
            {"id": "scs", "label": "SSB subcarrier spacing", "type": "select", "dependsOn": "ssb",
             "defaultByKey": scs_by, "options": [{"value": s, "label": s} for s in SCS],
             "showIf": {"field": "kind", "in": nr_kinds}},
        ],
    }


class _Plan:
    def __init__(self, ctx: Context, doc: Doc, kind: str, inputs: dict):
        self.ctx, self.doc, self.site, self.kind, self.inputs = ctx, doc, ctx.site, kind, inputs
        self.index = ctx.release_index()
        self.notes: list[str] = []
        self.skipped: dict[str, list[str]] = {}
        self.copied: dict[str, list[str]] = {}
        self.dropped: set[str] = set()
        self.replaced: dict[str, list[str]] = {}
        self.focus: Optional[str] = None

    def template(self, parent: dict, key: str) -> Optional[dict]:
        """The settings to copy: the parent's own object of the kind, else
        another of this file, else another file's."""
        mine = _objects(self.site, parent["dn"], key)
        others = [m for p in self.site.of(parent["cls"]) if p is not parent for m in _objects(self.site, p["dn"], key)]
        for m in mine + others:
            lists = {k: [dict(r) for r in v] for k, v in m["lists"].items() if k not in m["simple"]}
            return {"p": dict(m["p"]), "lists": lists, "simple": {k: list(v) for k, v in m["simple"].items()},
                    "inst": instance(m["dn"]), "from": f"{label(m['dn'])} of {label(m['dn'].rsplit('/', 1)[0])}",
                    "donor": False}
        rel = release_of(parent["version"])
        cls = OBJECTS[key]["cls"]
        known = self.index.get(rel, {}).get(cls) if self.index else None

        def keep(name: str) -> bool:
            ok = known is None or name in known
            if not ok:
                self.dropped.add(f"{cls}.{name}")
            return ok

        files = sorted(self.ctx.corpus(), key=lambda f: (f.get("release") != rel, f["name"]))
        for f in files:
            t = (f.get("carriers") or {}).get(key)
            if t and (f["source"], f["name"]) != (self.ctx.source, self.ctx.filename):
                return {"p": {k: v for k, v in t["p"].items() if keep(k)},
                        "lists": {k: v for k, v in t["lists"].items() if keep(k)}, "simple": {},
                        "inst": t.get("inst"), "from": "another file", "donor": True, "version": t.get("version")}
        b = BUILTIN.get(key)
        if b:
            return {"p": {k: v for k, v in b["p"].items() if keep(k)}, "lists": {}, "simple": {}, "inst": b["inst"],
                    "from": b["from"], "donor": False}
        return None

    def overrides(self, key: str, t: dict) -> tuple[dict, dict]:
        """(parameters, row fields) that set the template to the carrier."""
        i = self.inputs

        def scs(old: Optional[str]) -> str:
            n = "".join(ch for ch in i.get("scs") or "" if ch.isdigit())
            return re.sub(r"\d+", n, old) if old and re.search(r"\d+", old) else f"{n}kHz"

        if key == "IRFIM":
            return {"dlCarFrqEut": i["earfcn"]}, {}
        if key == "LNHOIF":
            return {"eutraCarrierInfo": i["earfcn"]}, {}
        if key in ("REDRT:eutra", "NRREDRT"):
            return {"redirRat": "eutra", "redirFreqEutra": i["earfcn"]}, {}
        if key == "NRLIM":
            return {"carrierFreq": i["earfcn"]}, {}
        if key == "NRIRFIM":
            return {"dlCarrierFreq": i["ssb"], "freqBandIndicatorNR": i["band"], "ssbScs": scs(t["p"].get("ssbScs"))}, {}
        row = (t["lists"].get(OBJECTS[key]["row"][0]) or [{}])[0]
        if key == "NRFIM":
            return {}, {"dlCarFrqNr": i["ssb"], "nrMultiBandInfo1": i["band"], "ssbScsNr": scs(row.get("ssbScsNr"))}
        return {"redirRat": "nr"}, {"carrierFreqNrCell": i["ssb"],
                                    "ssbSubcarrierSpacing": scs(row.get("ssbSubcarrierSpacing"))}

    def free(self, parent: str, key: str, prefer: Optional[str]) -> Optional[str]:
        spec = OBJECTS[key]
        lo, hi = spec["ids"]
        taken = {instance(m["dn"]) for m in self.site.child(parent, spec["cls"])}
        taken |= {instance(d) for d in self.doc.children(parent, spec["cls"])}
        if prefer and prefer.isdigit() and prefer not in taken and int(prefer) >= lo and (hi is None or int(prefer) <= hi):
            return prefer
        i = lo
        while str(i) in taken:
            i += 1
        return str(i) if hi is None or i <= hi else None

    def class_args(self, parent: dict, cls: str, t: dict) -> dict:
        if self.doc.of_class(cls):
            return {}
        info = self.doc.class_info(parent["cls"])
        return {"full_class": f"{info[0].rsplit(':', 1)[0]}:{cls}" if info and ":" in info[0] else None,
                "version": parent["version"]}

    def replace(self, parent: dict, key: str, carrier: str, what: str, have: list[dict]) -> None:
        """The parent's entries for the carrier: the first set to the inputs, the others removed."""
        spec, doc = OBJECTS[key], self.doc
        first, fixed = have[0], []
        p_over, row_over = self.overrides(key, {"p": first["p"], "lists": first["lists"]})
        w = lambda k, old, new: why("carrier", f"{what[0].upper() + what[1:]}: {k} {new}, as given (was {old}).",
                                    "choice")
        if "row" in spec:
            name, field = spec["row"]
            rows = [(m, i, r) for m in have for i, r in enumerate(m["lists"].get(name, [])) if r.get(field) == carrier]
            m, i, row = rows[0]
            for k, v in row_over.items():
                if row.get(k) != v:
                    doc.set_item(m["dn"], name, i, k, v, w(k, row.get(k) or "unset", v))
                    fixed.append(f"{k} {row.get(k) or 'unset'} → {v}")
            for m2, i2, _ in reversed(rows[1:]):
                doc.remove_item(m2["dn"], name, i2, why("carrier", f"A second entry for {what}: the first stays.",
                                                        "choice"))
                fixed.append(f"a second {name} row removed")
        for k, v in p_over.items():
            if first["p"].get(k) != v:
                doc.set(first["dn"], k, v, w(k, first["p"].get(k) or "unset", v))
                fixed.append(f"{k} {first['p'].get(k) or 'unset'} → {v}")
        if "row" not in spec and have[1:]:
            namers = _namers(doc, parent["dn"].split("/", 1)[0])
            for m in have[1:]:
                if namers[m["dn"]]:
                    self.notes.append(f"{label(m['dn'])} of {label(parent['dn'])} is a second {spec['cls']} for "
                                      f"{what}, kept since {', '.join(label(x) for x in sorted(namers[m['dn']]))} "
                                      "names it.")
                    continue
                doc.delete(m["dn"], why("carrier", f"A second {spec['cls']} for {what}: {label(first['dn'])} stays.",
                                        "choice"))
                fixed.append(f"{label(m['dn'])} removed")
        if fixed:
            self.replaced.setdefault(f"{label(parent['dn'])} {label(first['dn'])}", []).extend(fixed)
            self.focus = self.focus or first["dn"]
        else:
            self.skipped.setdefault(f"already {what}", []).append(label(parent["dn"]))

    def add(self, parent: dict, key: str, carrier: str, what: str) -> None:
        spec = OBJECTS[key]
        have = [m for m in _objects(self.site, parent["dn"], key) if carrier in _carriers(m, key)]
        if have:
            self.replace(parent, key, carrier, what, have)
            return
        t = self.template(parent, key)
        if not t:
            self.skipped.setdefault(f"no {spec['cls']} to copy in any file", []).append(label(parent["dn"]))
            return
        p_over, row_over = self.overrides(key, t)
        w = why("carrier", f"{what[0].upper() + what[1:]}, set like " + (f"an {spec['cls']} of another file." if t["donor"]
                                                                         else f"{t['from']}."),
                "donor" if t["donor"] else "files")
        mine = _objects(self.site, parent["dn"], key)
        if "row" in spec and mine:
            # One object holds the carriers as rows: a new row like its first.
            name, _ = spec["row"]
            row = {**((mine[0]["lists"].get(name) or t["lists"].get(name) or [{}])[0]), **row_over}
            self.doc.add_item(mine[0]["dn"], name, list(row.items()), w)
            self.focus = self.focus or mine[0]["dn"]
        else:
            inst = self.free(parent["dn"], key, t["inst"] if key.startswith("REDRT") else None)
            if inst is None:
                self.skipped.setdefault(f"every {spec['cls']} id in use ({spec['ids'][0]}-{spec['ids'][1]})",
                                        []).append(label(parent["dn"]))
                return
            params = {**t["p"], **p_over}
            dn = self.doc.create(parent["dn"], spec["cls"], inst, list(params.items()), w=w,
                                 **self.class_args(parent, spec["cls"], t))
            for name, rows in t["lists"].items():
                if "row" in spec and name == spec["row"][0]:
                    rows = [{**(rows or [{}])[0], **row_over}]
                for r in rows:
                    self.doc.add_item(dn, name, list(r.items()), w)
            for name, vals in t["simple"].items():
                self.doc.set_values(dn, name, vals, w)
            self.focus = self.focus or dn
        self.copied.setdefault(t["from"], []).append(label(parent["dn"]))


def _number(value: Optional[str], hi: int, what: str, problems: list[str]) -> Optional[str]:
    v = (value or "").strip()
    if not v.isdigit() or int(v) > hi:
        problems.append(f"The {what} is a number from 0 to {hi}.")
        return None
    return str(int(v))


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    kind = inputs.get("kind") or ""
    if kind not in KINDS or not _parents(ctx, kind):
        raise PlanError(["Pick what to add."])
    spec = KINDS[kind]
    problems: list[str] = []
    targets = [ctx.site.by_dn[d] for d in inputs.get("targets") or [] if d in ctx.site.by_dn
               and ctx.site.by_dn[d]["cls"] == spec["parent"]]
    if not targets:
        problems.append("Pick the cells to add it on.")
    clean = dict(inputs)
    if spec["input"] == LTE:
        clean["earfcn"] = _number(inputs.get("earfcn"), EARFCN_MAX, "EARFCN", problems)
        carrier = clean["earfcn"]
        what = f"EARFCN {carrier}"
    else:
        clean["ssb"] = _number(inputs.get("ssb"), NR_ARFCN_MAX, "SSB NR-ARFCN", problems)
        carrier = clean["ssb"]
        if kind in ("nr-lte", "nr-nr") and not (inputs.get("band") or "").strip().isdigit():
            problems.append("The NR band is a number (41 for n41).")
        clean["band"] = (inputs.get("band") or "").strip()
        if inputs.get("scs") not in SCS:
            problems.append("Pick the SSB subcarrier spacing.")
        what = f"the NR carrier with its SSB at {carrier}"
    if problems:
        raise PlanError(problems)

    doc = Doc(ctx.raw)
    p = _Plan(ctx, doc, kind, clean)
    for t in targets:
        if carrier in _own(ctx, kind, t):
            p.skipped.setdefault("on it already (their own carrier)", []).append(label(t["dn"]))
            continue
        for key in spec["objects"]:
            p.add(t, key, carrier, what)
    if not doc.changes:
        raise PlanError([f"Nothing to add: {', '.join(cells)} {reason}." for reason, cells in p.skipped.items()]
                        or ["Nothing to add."])
    for source, cells in p.copied.items():
        p.notes.append(f"{', '.join(sorted(set(cells)))}: settings copied from {source}.")
    if p.copied:
        p.notes.append("Check the reselection priority, thresholds and measurement bandwidth (for redirection, its "
                       "priority) suit the new carrier: they are the template's.")
    for where, fixed in p.replaced.items():
        p.notes.append(f"Replaced {where}'s entry for it: {'; '.join(fixed)}. Its priorities and thresholds stay, "
                       "the carrier's own.")
    for reason, cells in p.skipped.items():
        p.notes.append(f"Left alone: {', '.join(cells)} ({reason}).")
    if p.dropped:
        p.notes.append(f"Left out, as no file of this release sets them: {', '.join(sorted(p.dropped)[:8])}.")
    done = len({c for cells in p.copied.values() for c in cells} | {w.split(" ")[0] for w in p.replaced})
    return finish(ctx, doc, {"label": f"Add {what}", "summary": f"{spec['label']}: {what}, on {done} of {len(targets)}.",
                             "notes": p.notes, "confirm": [], "focus": p.focus})

"""
Set up voice: VoLTE on an eNB's cells or VoNR on a gNB's, with the QoS
profiles voice needs and the voice features the production files run.
PROJECT_STATE §9.9 has the plan and the corpus findings.

Everything voice needs is added where the file lacks it, and changed where
it is there (the owner, 2026-11-04: "if there are not the required MO in
the SCP YOU MUST ADD THEM, if they are already there then you will change
them").

VoLTE (the LTE18/SBTS18A dictionary's rules):
- The eNB: conversational voice on (LNBTS_FDD/_TDD actConvVoice), which
  needs multiple bearers (actMultBearers); an eNB without the LNBTS_FDD
  or _TDD its cells need gets one (number 0, as every file numbers them)
  with its Mandatory switches at the knowledge base's real-file defaults,
  release-filtered. QCI 1 and 5 in its QCI table, added through the QoS
  action's planner when missing, from another file of the release, else
  of another release.
- Each cell, where it doesn't set them already: harqMaxTrVoLteDl (must be
  configured with conversational voice, rule 1.1), n310Qci1 and t310Qci1
  (allowed only with it), and the QCI 1 carrier aggregation thresholds at
  0, off, when the eNB aggregates (they must be configured on a PCell).
- Picked features, as on the 68 production 25R2 cells (11 eNBs) that run
  them all: ROHC (LNBTS actPdcpRohc); TTI bundling with what rules
  actTtiBundling and ttibOperMode make it need; VoLTE proactive uplink
  grants; extended VoLTE talk time (LTE1406) and the QCI 1 BLER target,
  each with its table row; no EN-DC during VoLTE calls, where the eNB runs
  EN-DC. A cell TTI bundling isn't allowed on (actTtiBundling 1.1, 2.1,
  3.1) is left without it, and said.

VoNR (no NR dictionary: the 130 production 25R2 cells with VoNR on, all
but one alike, and their 27 gNBs):
- 5QI 1 and 5 rebuilt as production's (qos_replace.replace_nr): their
  mappings, and the bearers and profiles only those use, replaced by
  production's templates numbered as production numbers them; a gNB set
  as production comes out unchanged. A mapping keeps the slices the one
  it replaces named; a new one names those the gNB's own mappings name
  (production's all four of the gNB's, the lab gNBs' none).
- Each SA cell: actVoNR with its reservation, scheduling-request period
  and radio-link timers; picked: Enhanced VoNR, VoNR link adaptation, VoNR
  uplink coverage (incremental coding gain), EPS fallback by redirection;
  ROHC on the gNB. NSA-only cells are left: their voice runs on LTE.
- EPS fallback redirects to the LTE carrier in the cell's NRREDRT: a cell
  without one gets one through the carrier action's planner, to the
  EARFCN given, which the form offers from the cell's own LTE reselection
  carrier (NRLIM): each of the 130 production cells has one NRLIM carrier
  and one NRREDRT, to it. Without one there, this file's LTE cells'
  carrier; the form asks when neither is known.
- A cell's VoNR DRX profile (voNRNrDrxDN) is pointed at the one the 5QI 1
  bearer uses, as production has both on Default VoNR.

Production's values win over the picked cells' own, and the notes list
each old one (the owner, 2026-11-03: "Use the canned value"); so do the
eVTT and BLER target rows. Kept where set: what a cell that wasn't picked
must configure (harqMaxTrVoLteDl), and the QCI 1 aggregation thresholds,
which aren't production's tuning. The LTE QCI 1 and 5 rows are added only
when missing: no production template exists for them. Every parameter goes
through the release filter: written only where some file of the target's
release sets it on that class (all of them in the profile's own release).

3GPP: the AMF's "IMS voice over PS session supported" indication is TS
23.501 §5.16.3.2, read from the ETSI text of V17.10.0 when this was built.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

from . import Context, PlanError, carrier, finish, qos
from .doc import Doc, instance, label, release_of, why
from .qos_replace import replace_nr
from .sites import lte_cell

ID = "voice"
TITLE = "Set up VoLTE or VoNR"
GROUP = "Features"
SUMMARY = ("Voice on an eNB's or gNB's cells: the QCI or 5QI 1 and 5 bearers, and the voice features production "
           "runs (ROHC, TTI bundling, Enhanced VoNR, EPS fallback).")
UI = "form"
KEYWORDS = ("VoLTE VoNR voice IMS conversational QCI 1 5QI 1 ROHC TTI bundling eVTT EPS fallback actConvVoice "
            "actVoNR voiceFBMode")

LTE, NR = "lte", "nr"
PROFILE_RELEASE = {LTE: "xL25R2", NR: qos.TEMPLATE_RELEASE}  # the profiles' release: exempt from the filter

LTE_FEATURES = [
    {"value": "rohc", "label": "Robust header compression (ROHC)",
     "details": ["LNBTS actPdcpRohc (LTE11): compresses the voice packets' IP, UDP and RTP headers."]},
    {"value": "ttib", "label": "TTI bundling",
     "details": ["actTtiBundling (LTE907): a UE at the cell edge sends each voice packet over four TTIs, with the "
                 "settings the dictionary makes it need.",
                 "Not on cells it isn't allowed on (uplink link adaptation off, 1.4 MHz FDD, TDD other than "
                 "frame configuration 1, shared cell resources)."]},
    {"value": "grants", "label": "VoLTE proactive uplink grants",
     "details": ["maxNumVoLteProactUlGrantsPerTti 1: the cell grants the uplink every 10 ms during a call, before "
                 "the UE asks."]},
    {"value": "evtt", "label": "Extended VoLTE talk time",
     "details": ["actQci1eVTT (LTE1406) with its QCI 1 configuration (qci1eVTTConfig)."]},
    {"value": "bler", "label": "QCI 1 BLER target",
     "details": ["actQci1BlerTgt with its row (qci1BlerTgtConfig): a block error rate target of its own for voice "
                 "in link adaptation."]},
    {"value": "noendc", "label": "No EN-DC during VoLTE calls",
     "details": ["LNBTS actVoLteNoEnDc \"all QCI1 calls\": a UE in a VoLTE call gets no NR leg, as on the 11 "
                 "production eNBs that run VoLTE."]},
]
NR_FEATURES = [
    {"value": "enhanced", "label": "Enhanced VoNR",
     "details": ["actEnhancedVoNR, with GBR admission control in its Enhanced VoNR mode."]},
    {"value": "la", "label": "VoNR link adaptation",
     "details": ["A 2% BLER target for voice in both directions, a clamped initial CQI offset and a minimum uplink "
                 "transport block for VoNR."]},
    {"value": "coverage", "label": "VoNR uplink coverage",
     "details": ["actVoNRIncCodingGain: more PRBs for a voice packet at the cell edge (incremental coding gain)."]},
    {"value": "fallback", "label": "EPS fallback by redirection",
     "details": ["voiceFBMode redirection: a UE that can't do VoNR is sent to LTE for the call, to the carriers in "
                 "the cell's NRREDRT."]},
    {"value": "rohc", "label": "Robust header compression (ROHC) on the gNB",
     "details": ["NRBTS actRohc."]},
]

# The production profiles: (name, value, kind). A "switch" is set; a
# "value" is written where the cell has none. LTE: the 68 production 25R2
# cells with all the features on, which all agree; NR: the 130 production
# 25R2 cells with VoNR on (129 agree on every one).
LTE_RLF = [("n310Qci1", "n20"), ("t310Qci1", "2000ms")]
TTIB = [("ttiBundlingBlerTarget", "12"), ("ttiBundlingBlerThreshold", "15"), ("ttiBundlingSinrThreshold", "10"),
        ("ttibOperMode", "sinrBasedTtibOnOffAllowed")]
TTIB_SINR = [("ttibSinrThresholdIn", "20"), ("ttibSinrThresholdOut", "24")]
TTIB_DWELL = [("ttibSinrDwellTimeIn", "200"), ("ttibSinrDwellTimeOut", "200")]
TTIB_EXTRA = [("ttibUlsMinTbs", "144"), ("ttibMinDelayAfterBearerSetup", "0"), ("ttibAltUlPrbThreshold", "0")]
GRANTS = [("voLteProactUlGrantNonTtibTxSkip", "0"), ("voLteProactUlGrantPeriodTtibTxSkip", "0")]
EVTT_ROW = [("qci1DlTargetBler", "30"), ("qci1HarqMaxTrDl", "7"), ("qci1HarqMaxTrUl", "7"),
            ("qci1ReconStopTimer", "50"), ("qci1ThroughputFactorDl", "40"), ("qci1ThroughputFactorUl", "40"),
            ("qci1UlTargetBler", "2")]
BLER_ROW = [("qci1DlTargetBler", "60"), ("qci1HarqMaxTxDl", "4"), ("qci1HarqMaxTxUl", "4"), ("qci1UlTargetBler", "6")]

NR_CELL = [("vonrReservation", "15"), ("preferredVoNrSrPeriod", "slots40"), ("n310VoNR", "n10"),
           ("t310VoNR", "2000ms")]
NR_LA = [("actTargetBlerVoNR", "true", "switch"), ("dllaTargetBlerVoNR", "2", "value"),
         ("ullaTargetBlerVoNR", "2", "value"), ("actMaxInitDeltaCqiClampVoNR", "true", "switch"),
         ("maxInitDeltaCqiClampVoNR", "-1500", "value"), ("actUlMinTbsForVoNR", "true", "switch"),
         ("ulMinTbsForVoNR", "168", "value"), ("numPuschPrbForMinTbsVoNR", "2", "value"),
         ("percRedSEDlRat1VoNR", "10", "value")]
NR_COVERAGE = [("actVoNRIncCodingGain", "true", "switch"), ("maxPrbsVoNRIncCodingGain", "32", "value"),
               ("numTxPrbVoNRIncCodingGain", "2", "value"), ("stepUpNumPrbsVoNRIncCodingGain", "20", "value")]

LTE_FILES = "as on the 68 production 25R2 cells that run VoLTE with every feature"
NR_FILES = "as on the 130 production 25R2 cells with VoNR on"


# --- Reading ------------------------------------------------------------------

def _enbs(ctx: Context) -> list[dict]:
    return [e for e in qos._enbs(ctx) if ctx.site.child(e["dn"], "LNCEL")]


def _sa_cells(ctx: Context, gnb: dict) -> list[dict]:
    return [c for c in ctx.site.child(gnb["dn"], "NRCELL") if "SA" in (c["p"].get("cellDepType") or "SA").split("+")]


def _gnbs(ctx: Context) -> list[dict]:
    return [g for g in qos._gnbs(ctx) if qos.SA in qos._sides(ctx, g) and _sa_cells(ctx, g)]


def _runs_endc(ctx: Context, enb: dict) -> bool:
    return enb["p"].get("actLteNrDualConnectivity") == "true"


def available(ctx: Context) -> Optional[str]:
    if _enbs(ctx) or _gnbs(ctx):
        return None
    if any(ctx.site.child(g["dn"], "NRCELL") for g in qos._gnbs(ctx)):
        return ("This file's gNB has no SA cell, or its release has no 5QI mappings: its voice runs on LTE, and the "
                "file has no LTE eNB with cells.")
    return "This file has no LTE eNB with cells and no 5G gNB."


def _cell_option(c: dict, now: str) -> dict:
    name = c["p"].get("cellName")
    return {"value": c["dn"], "label": label(c["dn"]) + (f" · {name}" if name else ""), "hint": now}


def _slices_named(ctx: Context, gnb: dict) -> bool:
    return any(m["lists"].get("snssaiList") for m in ctx.site.child(gnb["dn"], "NRDRB_5QI"))


def _reselect_to(ctx: Context, gnb: str, cell: dict) -> list[str]:
    """The LTE carriers the cell's UEs reselect to (the NRLIMs of the system
    information profile it broadcasts), highest priority first."""
    prof = cell["p"].get("nrSysInfoProfileDN") or ""
    prof = prof if prof.startswith("MRBTS-") else f"{gnb}/{prof}"
    lims = ctx.site.child(prof, "NRLIM")
    rank = lambda m: tuple(-int(m["p"].get(k) or 0) if (m["p"].get(k) or "0").isdigit() else 0
                           for k in ("cellReselectionPriority", "cellReselectionSubPriority"))
    return list(dict.fromkeys(m["p"]["carrierFreq"] for m in sorted(lims, key=rank) if m["p"].get("carrierFreq")))


def _file_lte(ctx: Context) -> list[str]:
    """This file's LTE cells' carriers, the most cells' first."""
    n: dict[str, int] = defaultdict(int)
    for c in ctx.site.of("LNCEL"):
        e = lte_cell(ctx.site, c)["earfcn"]
        if e:
            n[e] += 1
    return sorted(n, key=lambda e: -n[e])


def _no_redirect(ctx: Context, gnb: dict) -> list[dict]:
    return [c for c in _sa_cells(ctx, gnb) if not ctx.site.child(c["dn"], "NRREDRT")]


def _fallback_carriers(ctx: Context, gnb: dict, cells: list[dict]) -> list[str]:
    """What EPS fallback can redirect the cells to: their reselection
    carriers, then this file's LTE carriers."""
    return list(dict.fromkeys([e for c in cells for e in _reselect_to(ctx, gnb["dn"], c)] + _file_lte(ctx)))


def setup(ctx: Context) -> dict:
    site = ctx.site
    targets, cells, features, slices, slice_default = [], {}, {}, {}, {}
    fallback, fallback_default = {}, {}
    for enb in _enbs(ctx):
        key = f"{LTE}|{enb['dn']}"
        subs = site.child(enb["dn"], "LNBTS_FDD") + site.child(enb["dn"], "LNBTS_TDD")
        on = any(s["p"].get("actConvVoice") == "true" for s in subs)
        targets.append({"value": key, "key": key, "group": f"eNB {instance(enb['dn'])}",
                        "label": f"{label(enb['dn'])} · VoLTE" + (" (conversational voice on)" if on else ""),
                        "details": ["QCI 1 and 5 bearers, conversational voice, and the picked features in the "
                                    "cells."]})
        cells[key] = [_cell_option(c, "TTI bundling on" if c["p"].get("actTtiBundling") == "true" else "")
                      for c in site.child(enb["dn"], "LNCEL")]
        features[key] = [f for f in LTE_FEATURES if f["value"] != "noendc" or _runs_endc(ctx, enb)]
    for gnb in _gnbs(ctx):
        key = f"{NR}|{gnb['dn']}"
        sa = _sa_cells(ctx, gnb)
        on = sum(c["p"].get("actVoNR") == "true" for c in sa)
        targets.append({"value": key, "key": key, "group": f"gNB {instance(gnb['dn'])}",
                        "label": f"{label(gnb['dn'])} · VoNR" + (f" (on in {on} of {len(sa)} cells)" if on else ""),
                        "details": ["5QI 1 and 5 mappings, VoNR and the picked features in the SA cells."]})
        cells[key] = [_cell_option(c, "VoNR on" if c["p"].get("actVoNR") == "true" else "") for c in sa]
        features[key] = NR_FEATURES
        need = _no_redirect(ctx, gnb)
        if need:
            known = _fallback_carriers(ctx, gnb, need)
            fallback[key] = [{"value": e, "label": f"EARFCN {e}"} for e in known]
            if known:
                fallback_default[key] = known[0]
        mapped = qos._mapped(Doc(ctx.raw), gnb["dn"], qos.SA)
        own = site.child(gnb["dn"], "SNSSAI")
        if own and not {"1", "5"} <= set(mapped):
            slices[key] = [{"value": s["dn"], "label": f"{label(s['dn'])} · SST {s['p'].get('sst', '?')}"
                                                       + (f" · SD {s['p']['sd']}" if s["p"].get("sd") else "")}
                           for s in own]
            slice_default[key] = [s["dn"] for s in own] if _slices_named(ctx, gnb) else []
    return {
        "intro": "Sets up voice on an eNB's or gNB's cells: the QCI or 5QI 1 (voice) and 5 (IMS signalling) bearers "
                 "(a gNB's rebuilt as production's), and the voice features the production files run. Production's "
                 "values replace the cells' own, and the review lists each old one.",
        "fields": [
            {"id": "target", "label": "Where", "type": "select", "options": targets,
             "default": targets[0]["value"] if len(targets) == 1 else None},
            {"id": "cells", "label": "Cells", "type": "checks", "dependsOn": "target", "optionsByKey": cells,
             "hint": "The features go on these cells. On an eNB, conversational voice is the eNB's: every cell gets "
                     "what it then needs."},
            {"id": "features", "label": "Features", "type": "checks", "dependsOn": "target",
             "optionsByKey": features, "optional": True,
             "hint": "All ticked: production's voice set. None: only voice itself."},
            {"id": "slices", "label": "Slices for 5QI 1 and 5", "type": "checks", "dependsOn": "target",
             "optionsByKey": slices, "defaultByKey": slice_default, "optional": True,
             "hint": "As the gNB's other mappings: production's name every slice, the lab gNBs' none."},
            {"id": "fallbackEarfcn", "label": "LTE carrier for EPS fallback (EARFCN)", "type": "combo",
             "dependsOn": "target", "optionsByKey": fallback, "defaultByKey": fallback_default, "optional": True,
             "showIf": {"field": "target", "in": list(fallback)}, "placeholder": "66786",
             "hint": "With EPS fallback ticked, each cell without an NRREDRT gets one, redirecting here. Offered "
                     "first: the LTE carrier the cells reselect to (NRLIM), which production's cells redirect to."},
        ],
    }


# --- Planning -----------------------------------------------------------------

class _Plan:
    def __init__(self, ctx: Context, doc: Doc, side: str):
        self.ctx, self.doc, self.side = ctx, doc, side
        self.index = ctx.release_index()
        self.notes: list[str] = []
        self.todo: list[str] = []
        self.kept: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        self.replaced: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        self.unknown: dict[str, set[str]] = defaultdict(set)
        self.ruled: dict[str, set[str]] = defaultdict(set)  # written on the dictionary's word alone
        self.touched: list[str] = []

    def known(self, dn: str, name: str, required: bool = False) -> bool:
        """Whether the object may carry `name`: it does, or some file of its
        release sets it on that class (any, in the profile's release). One a
        dictionary rule requires is known in any release of 18 or later when
        the dictionaries (LTE18, SBTS18A) have it: the rule is theirs."""
        if self.doc.get(dn, name) is not None or not self.index:
            return True
        m = self.ctx.site.by_dn.get(dn)
        rel = release_of(m["version"]) if m else None
        if m is None or rel == PROFILE_RELEASE[self.side]:
            return True
        if name in self.index.get(rel, {}).get(m["cls"], set()):
            return True
        n = re.search(r"\d{2}", rel or "")
        meta = ((_catalog(self.ctx).get(m["cls"]) or {}).get("params") or {}).get(name) or {}
        if required and n and int(n.group()) >= 18 and meta.get("confidence") == "official":
            self.ruled[rel].add(name)
            return True
        self.unknown[rel or "this release"].add(name)
        return False

    def put(self, dn: str, name: str, value: str, reason: str, basis: str = "files", rule=None) -> bool:
        """A setting written as given (a switch, or a value a rule forces)."""
        if not self.known(dn, name, basis == "official" and rule is not None) or self.doc.get(dn, name) == value:
            return False
        self.doc.set(dn, name, value, why("voice", reason, basis, rule))
        self.touched.append(dn)
        return True

    def value(self, dn: str, name: str, value: str, reason: str, basis: str = "files", rule=None,
              keep: bool = False) -> None:
        """Production's value, over the object's own (the owner, 2026-11-03: the canned value wins, and the
        review lists the old one). `keep`: written only where the object has none, for what isn't
        production's tuning (a cell that wasn't picked, a value a rule makes it configure)."""
        now = self.doc.get(dn, name)
        if now is not None and now != value:
            if keep:
                self.kept[(name, now, value)].append(label(dn))
                return
            if self.put(dn, name, value, f"{reason} Was {now} here.", basis, rule):
                self.replaced[(name, now, value)].append(label(dn))
            return
        self.put(dn, name, value, reason, basis, rule)

    def row(self, dn: str, name: str, row: list[tuple[str, str]], w) -> None:
        """A table's one row as production's: added, or each field set to production's."""
        rows = self.doc.items(dn, name)
        if not rows:
            self.doc.add_item(dn, name, row, w)
            return
        for k, v in row:
            if rows[0].get(k) != v:
                self.replaced[(f"{name} {k}", rows[0].get(k) or "unset", v)].append(label(dn))
                self.doc.set_item(dn, name, 0, k, v, w)

    def finish_notes(self) -> None:
        for what, values in (("Set to production's values, over the site's own", self.replaced),
                             ("Kept, as the cells weren't picked or it isn't production's tuning", self.kept)):
            if values:
                parts = [f"{name} {now} → {prod} on {', '.join(sorted(set(where)))}" if values is self.replaced
                         else f"{name} {now} on {', '.join(sorted(set(where)))} (production {prod})"
                         for (name, now, prod), where in sorted(values.items())]
                self.notes.append(f"{what}: " + "; ".join(parts[:8])
                                  + (f"; and {len(parts) - 8} more." if len(parts) > 8 else "."))
        for rel, names in sorted(self.ruled.items()):
            self.notes.append(f"Written as the dictionary's rules require, though no {rel} file loaded sets them: "
                              f"{', '.join(sorted(names))}.")
        for rel, names in sorted(self.unknown.items()):
            self.notes.append(f"Not written, because no {rel} file sets them: {', '.join(sorted(names))}.")


def _catalog(ctx: Context) -> dict:
    """The knowledge base's classes (class_catalog.json)."""
    cat = ctx.kb.get("catalog") or {}
    return cat.get("classes") or cat


def _pick(inputs: dict, key: str, options: list[dict]) -> list[str]:
    values = [o["value"] for o in options]
    got = inputs.get(key)
    return values if got is None else [v for v in got if v in values]


def _lte_template(ctx: Context, enb: dict, q: str) -> Optional[str]:
    _, templates = qos._lte_options(ctx, enb, qos._others(ctx))
    opts = templates.get(f"{qos.LTE}|{enb['dn']}|{q}") or []
    return opts[0]["value"] if opts else None


def _add_subs(ctx: Context, p: _Plan, enb: dict) -> list[str]:
    """The LNBTS_FDD or _TDD (or both) the eNB's cells need, where it has
    none: number 0, with its Mandatory parameters at the knowledge base's
    real-file defaults (those some file of the release sets on the class),
    conversational voice set on it next."""
    doc, dn = p.doc, enb["dn"]
    tdd = {lte_cell(ctx.site, c)["tdd"] or (c["p"].get("cellTechnology") or "").startswith("TDD")
           for c in ctx.site.child(dn, "LNCEL")}
    info = doc.class_info("LNBTS")
    rel = release_of(enb["version"])
    made = []
    for cls in (["LNBTS_FDD"] if False in tdd or not tdd else []) + (["LNBTS_TDD"] if True in tdd else []):
        meta = (_catalog(ctx).get(cls) or {}).get("params") or {}
        known = p.index.get(rel, {}).get(cls) if p.index else None
        params = []
        for name, m in meta.items():
            value = m.get("resolvedDefault") or (m.get("exampleValues") or [None])[0]
            if m.get("requiredOnCreation") == "Mandatory" and value is not None and name != "actConvVoice" \
                    and (known is None or name in known):
                params.append((name, str(value)))
        made.append(doc.create(dn, cls, "0", params, w=why(
            "voice", f"Conversational voice is set in the eNB's {cls}, and it has none: added, with its Mandatory "
                     "settings at their defaults, as the files set them.", "files"),
            full_class=f"{info[0].rsplit(':', 1)[0]}:{cls}" if info and ":" in info[0] else None,
            version=enb["version"]))
        p.touched.append(made[-1])
    p.notes.append(f"{label(dn)} had no {' or '.join(c.rsplit('/', 1)[1].rsplit('-', 1)[0] for c in made)}: added "
                   f"as {', '.join(label(c) for c in made)}, with its Mandatory switches at their defaults (off), as "
                   "the files of its release set them.")
    return made


def _ceil4(n: int) -> int:
    return -(-n // 4) * 4


def _plan_lte(ctx: Context, doc: Doc, enb: dict, cells: list[str], features: set[str]) -> dict:
    p = _Plan(ctx, doc, LTE)
    dn = enb["dn"]
    for q in ("1", "5"):
        if doc.items(dn, f"qciTab{q}"):
            continue
        template = _lte_template(ctx, enb, q) or qos.qci_donor(ctx, enb, q)
        if not template:
            raise PlanError([f"The eNB has no QCI {q} in its QCI table, and no file loaded has one to take its "
                             "settings from: load a file with VoLTE."])
        out = qos._plan_lte(ctx, doc, enb, {"value": q, "template": template})
        p.notes += [n for n in out["notes"] if not n.startswith("VoLTE also uses")]
        p.touched.append(dn)
    if doc.get(dn, "actMultBearers") == "false":
        p.put(dn, "actMultBearers", "true", "Conversational voice needs multiple bearers: actConvVoice must be false "
                                            "while actMultBearers is.", "official", ("actConvVoice", None))
    subs = doc.children(dn, "LNBTS_FDD") + doc.children(dn, "LNBTS_TDD")
    if not subs:
        subs = _add_subs(ctx, p, enb)
    turned = [sub for sub in subs if p.put(sub, "actConvVoice", "true", "Conversational voice on: the eNB sets up "
                                                                       "QCI 1 bearers for VoLTE calls.", "choice")]
    if turned:
        p.notes.append("actConvVoice takes effect in each cell after the cell is next locked and unlocked (the "
                       "dictionary).")
    if "rohc" in features:
        p.put(dn, "actPdcpRohc", "true", f"Robust header compression on for voice bearers, {LTE_FILES}.")
    if "noendc" in features and _runs_endc(ctx, enb):
        p.put(dn, "actVoLteNoEnDc", "all QCI1 calls", f"No NR leg while a UE is in a VoLTE call, {LTE_FILES}.")
    ca = doc.get(dn, "actDLCAggr") == "true"
    skipped = []
    # Conversational voice is the eNB's: every cell gets what it then must configure.
    for cell in doc.of_class("LNCEL", dn):
        tech = doc.get(cell, "cellTechnology") or "FDD"
        if tech.startswith("NB-IoT"):
            continue
        p.value(cell, "harqMaxTrVoLteDl", "4", f"Must be configured with conversational voice on; 4 {LTE_FILES}.",
                "official", ("harqMaxTrVoLteDl", "2.1" if tech == "TDD" else "1.1"), keep=cell not in cells)
        if ca:
            for name in ("dlCaMinPcellCqiQci1", "ulCaMinPcellSinrQci1"):
                p.value(cell, name, "0", "The eNB aggregates carriers, so with conversational voice on a PCell must "
                                         "configure it; 0 leaves the QCI 1 threshold off.", "official",
                        ("actConvVoice", None), keep=True)
    for cell in cells:
        tech = doc.get(cell, "cellTechnology") or "FDD"
        if tech.startswith("NB-IoT"):
            skipped.append(f"{label(cell)} is an NB-IoT cell")
            continue
        for name, v in LTE_RLF:
            p.value(cell, name, v, f"The voice bearers' radio link failure setting, allowed with conversational voice "
                                   f"on; {v} {LTE_FILES}.")
        if "ttib" in features:
            why_not = _ttib(p, cell, tech)
            if why_not:
                skipped.append(f"TTI bundling on {label(cell)}: {why_not}")
        if "grants" in features:
            _grants(p, cell)
        if "evtt" in features:
            _evtt(p, cell)
        if "bler" in features and p.known(cell, "actQci1BlerTgt"):
            p.put(cell, "actQci1BlerTgt", "true", f"A BLER target of its own for voice, {LTE_FILES}.")
            p.row(cell, "qci1BlerTgtConfig", BLER_ROW, why("voice", f"The QCI 1 BLER target's settings, {LTE_FILES}.",
                                                           "files"))
    if skipped:
        p.notes.append("Left out: " + "; ".join(skipped) + ".")
    p.finish_notes()
    return {
        "label": f"VoLTE on {label(dn)}",
        "summary": f"VoLTE on eNB {instance(dn)}: {len(cells)} cell{'s' if len(cells) != 1 else ''}",
        "notes": p.notes, "todo": p.todo,
        "confirm": ["The IMS core serves this eNB's PLMN, and the MME tells UEs that IMS voice over PS sessions are "
                    "supported: without both, UEs don't place VoLTE calls."],
        "focus": next((c for c in p.touched if c in cells), p.touched[0] if p.touched else None),
    }


def _ttib(p: _Plan, cell: str, tech: str) -> Optional[str]:
    """TTI bundling with what it needs, or why the cell can't have it."""
    doc = p.doc
    c = doc.params(cell)
    sub = next(iter(doc.children(cell, "LNCEL_TDD" if tech == "TDD" else "LNCEL_FDD")), None)
    s = doc.params(sub) if sub else {}
    if not p.known(cell, "actTtiBundling"):
        return None
    if c.get("actUlLnkAdp") not in ("eUlLa", "fUlLa"):
        return f"its uplink link adaptation is {c.get('actUlLnkAdp') or 'unset'}, and needs eUlLa or fUlLa (rule 1.1)"
    if c.get("cellResourceSharingMode") not in (None, "none", "DLonly"):
        return f"it shares cell resources ({c['cellResourceSharingMode']}; rule 1.1)"
    if tech != "TDD" and s.get("dlChBw") == "1.4 MHz":
        return "it is a 1.4 MHz cell (rule 2.1)"
    if tech == "TDD" and s.get("tddFrameConf") not in (None, "1"):
        return f"its TDD frame configuration is {s['tddFrameConf']}, and needs 1 (rule 3.1)"
    mandatory = ("actTtiBundling", "3.1" if tech == "TDD" else "2.2")
    p.put(cell, "actTtiBundling", "true", f"TTI bundling on for cell-edge voice, {LTE_FILES}.")
    tx = int(c.get("harqMaxTxUl") or 0)
    boost = c.get("actVoipCovBoost") == "true"
    floor = max(tx, 12 if boost else 0)
    now = c.get("harqMaxTrUlTtiBundling")
    if now is None:
        p.put(cell, "harqMaxTrUlTtiBundling", str(max(12, _ceil4(floor))),
              f"Required with TTI bundling; 12 {LTE_FILES}, and at least harqMaxTxUl ({tx}).", "official", mandatory)
    elif now.isdigit() and int(now) < floor:
        p.put(cell, "harqMaxTrUlTtiBundling", str(_ceil4(floor)),
              f"Must be at least harqMaxTxUl ({tx})" + (" and 12 with VoIP coverage boost on" if boost else "") + ".",
              "official", ("harqMaxTrUlTtiBundling", "1.3" if boost and int(now) < 12 else "1.2"))
    for name, v in TTIB:
        p.value(cell, name, v, f"Required with TTI bundling; {v} {LTE_FILES}.", "official", mandatory)
    if (doc.get(cell, "ttibOperMode") or "").startswith("sinr"):
        for name, v in TTIB_SINR:
            p.value(cell, name, v, f"Needed with SINR-based TTI bundling; {v} {LTE_FILES}.", "official",
                    ("ttibOperMode", "1.2"))
        for name, v in TTIB_DWELL:
            if tech == "TDD":
                if doc.get(cell, name) is not None:
                    doc.unset(cell, name, why("voice", "A TDD cell can't configure it with SINR-based TTI bundling.",
                                              "official", ("ttibOperMode", "3.1")))
            else:
                p.value(cell, name, v, f"Needed with SINR-based TTI bundling on FDD; {v} {LTE_FILES}.", "official",
                        ("ttibOperMode", "2.1"))
    p.value(cell, "actTtibRsc", "true", "Must be configured with TTI bundling; true, the default, as production.",
            "official", ("actTtibRsc", None))
    if c.get("actUlLnkAdp") == "fUlLa":
        for name in ("eUlLaLowMcsThr", "eUlLaLowPrbThr"):
            p.value(cell, name, "1", "Must be configured with fast uplink link adaptation and TTI bundling; 1, the "
                                     "default, as production.", "official", ("eUlLaLowMcsThr", None))
    if c.get("actCatM") == "true" and s.get("ulChBw") == "5 MHz":
        p.put(cell, "ttibMinUlPrb", "2", "A Cat-M cell of 5 MHz uplink must use 2.", "official", mandatory)
    else:
        p.value(cell, "ttibMinUlPrb", "3", f"The fewest uplink PRBs in TTI bundling; 3 {LTE_FILES}.")
    for name, v in TTIB_EXTRA:
        p.value(cell, name, v, f"{v} {LTE_FILES}.")
    return None


def _grants(p: _Plan, cell: str) -> None:
    doc = p.doc
    if doc.get(cell, "maxNumVoLteProactUlGrantsPerTti") in (None, "0"):
        p.put(cell, "maxNumVoLteProactUlGrantsPerTti", "1",
              f"Proactive uplink grants on, for one UE per TTI (the least every bandwidth allows), {LTE_FILES}.")
    if doc.get(cell, "maxNumVoLteProactUlGrantsPerTti") in (None, "0"):
        return  # not in this release: nor what it needs
    for name in ("voLteProactUlGrantPeriodRegTx", "voLteProactUlGrantPeriodTtib"):
        if doc.get(cell, name) in (None, "0"):
            p.put(cell, name, "10", f"Must be configured with proactive grants on; every 10 ms {LTE_FILES} (0 turns "
                                    "them off for these UEs).", "official", (name, "1.1"))
    for name, v in GRANTS:
        p.value(cell, name, v, f"{v} {LTE_FILES}.")


def _evtt(p: _Plan, cell: str) -> None:
    doc = p.doc
    if not p.put(cell, "actQci1eVTT", "true", f"Extended VoLTE talk time on, {LTE_FILES}.") and \
            doc.get(cell, "actQci1eVTT") != "true":
        return
    w = why("voice", f"Must be configured with extended VoLTE talk time on; {LTE_FILES}.", "official",
            ("actQci1eVTT", "1.1"))
    tx = doc.get(cell, "harqMaxTxUl")
    boost = doc.get(cell, "actVoipCovBoost") == "true" and tx
    p.row(cell, "qci1eVTTConfig", [(k, v) for k, v in EVTT_ROW if not (boost and k == "qci1HarqMaxTrUl")], w)
    if boost:
        for i, row in enumerate(doc.items(cell, "qci1eVTTConfig")):
            if row.get("qci1HarqMaxTrUl") != tx:
                doc.set_item(cell, "qci1eVTTConfig", i, "qci1HarqMaxTrUl", tx, why(
                    "voice", f"With VoIP coverage boost on it must equal harqMaxTxUl ({tx}).", "official",
                    ("actQci1eVTT", "1.3")))
    if doc.get(cell, "actSmartDrx") == "true":
        for sdrx in doc.children(cell, "SDRX"):
            for prof, rule_no in (("drxSmartProfile2", "1.2"), ("drxSmartProfile6", "1.4")):
                for i, row in enumerate(doc.items(sdrx, prof)):
                    if row.get("drxLongCycle") and row.get("drxShortCycle") != row["drxLongCycle"]:
                        doc.set_item(sdrx, prof, i, "drxShortCycle", row["drxLongCycle"], why(
                            "voice", f"With Smart DRX and extended VoLTE talk time on, {prof}'s short cycle must equal "
                                     "its long cycle.", "official", ("actQci1eVTT", rule_no)))


def _redirect(ctx: Context, p: _Plan, gnb: dict, cells: list[str], earfcn: Optional[str]) -> None:
    """An NRREDRT on each cell without one, through the carrier action's
    planner (settings from the gNB's own, else another file's): to the
    EARFCN given, else the cell's reselection carrier, else this file's LTE
    carrier."""
    plans: dict[str, carrier._Plan] = {}
    for cell in cells:
        m = ctx.site.by_dn[cell]
        e = earfcn or next(iter(_fallback_carriers(ctx, gnb, [m])), None)
        if not e:
            raise PlanError([f"EPS fallback redirects to an LTE carrier, and {label(cell)} has no NRREDRT, no LTE "
                             "reselection carrier (NRLIM) and this file no LTE cell to take one from: give the "
                             "carrier's EARFCN."])
        cp = plans.setdefault(e, carrier._Plan(ctx, p.doc, "redirect-nr", {"earfcn": e}))
        cp.add(m, "NRREDRT", e, f"EPS fallback to EARFCN {e}")
    for e, cp in plans.items():
        if cp.skipped:
            raise PlanError([f"No NRREDRT to copy in any file: {', '.join(c)} ({r})." for r, c in cp.skipped.items()])
        for source, where in cp.copied.items():
            p.notes.append(f"EPS fallback: {', '.join(sorted(set(where)))} had no NRREDRT; one added to EARFCN {e}, "
                           f"its other settings copied from {source}.")
        p.notes += [n.replace("Left out, as", "NRREDRT: left out, as") for n in cp.notes]
        if cp.dropped:
            p.notes.append(f"NRREDRT: left out, as no file of this release sets them: {', '.join(sorted(cp.dropped))}.")
        p.touched += [cp.focus] if cp.focus else []


def _plan_nr(ctx: Context, doc: Doc, gnb: dict, cells: list[str], features: set[str], slices: list[str],
             earfcn: Optional[str] = None) -> dict:
    p = _Plan(ctx, doc, NR)
    dn = gnb["dn"]
    had, before = qos._mapped(doc, dn, qos.SA), len(doc.changes)
    out = replace_nr(ctx, doc, qos.SA, gnb, {"1", "5"}, slices=slices)
    p.notes += out["notes"]
    made = [v for v in out["values"] if v not in had]
    rebuilt = len(doc.changes) > before
    p.touched += out["written"]
    p.value(dn, "tRLFindForDUVoNR", "2000ms", f"The DU's radio link failure timer for VoNR; 2000ms on the 27 "
                                              "production gNBs with VoNR.")
    if "rohc" in features:
        p.put(dn, "actRohc", "true", "Robust header compression on, as on the 27 production gNBs with VoNR.")
    drb = next((doc.get(m, "nrDrbDN") for m, _ in qos._mapped(doc, dn, qos.SA).get("1", [])), None)
    drb = drb if not drb or drb.startswith("MRBTS-") else f"{dn}/{drb}"
    voice_drx = doc.get(drb, "nrDrxDN") if drb and doc.exists(drb) else None
    voice_drx = voice_drx if not voice_drx or voice_drx.startswith("MRBTS-") else f"{dn}/{voice_drx}"
    no_redirect = []
    for cell in cells:
        p.put(cell, "actVoNR", "true", f"VoNR on: voice calls stay on NR, {NR_FILES}.", "choice")
        for name, v in NR_CELL:
            p.value(cell, name, v, f"{v} {NR_FILES}.")
        if "enhanced" in features:
            p.put(cell, "actEnhancedVoNR", "true", f"Enhanced VoNR on, {NR_FILES}.")
            if doc.get(cell, "actGBRAdmissionControl") in (None, "off"):
                p.put(cell, "actGBRAdmissionControl", "EnhancedVoNR", f"GBR admission control in its Enhanced VoNR "
                                                                      f"mode, {NR_FILES}.")
        for group, rows in (("la", NR_LA), ("coverage", NR_COVERAGE)):
            if group in features:
                for name, v, kind in rows:
                    (p.put if kind == "switch" else p.value)(cell, name, v, f"{v} {NR_FILES}.")
        if "fallback" in features:
            p.put(cell, "voiceFBMode", "redirection", f"EPS fallback by redirection for UEs without VoNR, "
                                                      f"{NR_FILES}.")
            if not doc.children(cell, "NRREDRT"):
                no_redirect.append(cell)
        cell_drx = doc.get(cell, "voNRNrDrxDN")
        cell_drx = cell_drx if not cell_drx or cell_drx.startswith("MRBTS-") else f"{dn}/{cell_drx}"
        if voice_drx and cell_drx != voice_drx:
            p.put(cell, "voNRNrDrxDN", voice_drx, f"VoNR calls use the DRX profile the 5QI 1 bearer uses, "
                                                  f"{label(voice_drx)}, as production has both on Default VoNR"
                                                  + (f" (was {label(cell_drx)})." if cell_drx else "."))
    if no_redirect:
        _redirect(ctx, p, gnb, no_redirect, earfcn)
    p.finish_notes()
    return {
        "label": f"VoNR on {label(dn)}",
        "summary": f"VoNR on gNB {instance(dn)}: {len(cells)} cell{'s' if len(cells) != 1 else ''}"
                   + (f", 5QI {' and '.join(made)} mapped" if made else ", 5QI 1 and 5 as production" if rebuilt
                      else ""),
        "notes": p.notes, "todo": p.todo,
        "confirm": ["The IMS core serves this gNB's PLMN, and the AMF tells UEs that IMS voice over PS sessions are "
                    "supported (TS 23.501 §5.16.3.2)."]
                   + (["The core marks voice and IMS signalling flows 5QI 1 and 5 (the SMF and PCF)."] if made else [])
                   + (["The LTE network carries voice for UEs that fall back (EPS fallback): the MME and IMS serve "
                       "them there."] if "fallback" in features else []),
        "focus": next((c for c in p.touched if c in cells), p.touched[0] if p.touched else None),
    }


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    side, _, dn = (inputs.get("target") or "").partition("|")
    doc = Doc(ctx.raw)
    if side == LTE:
        enb = next((e for e in _enbs(ctx) if e["dn"] == dn), None)
        if not enb:
            raise PlanError(["Pick the eNB."])
        cells = _pick(inputs, "cells", [{"value": c["dn"]} for c in ctx.site.child(dn, "LNCEL")])
        features = set(_pick(inputs, "features", LTE_FEATURES))
        if not cells:
            raise PlanError(["Pick the cells."])
        out = _plan_lte(ctx, doc, enb, cells, features)
    elif side == NR:
        gnb = next((g for g in _gnbs(ctx) if g["dn"] == dn), None)
        if not gnb:
            raise PlanError(["Pick the gNB."])
        cells = _pick(inputs, "cells", [{"value": c["dn"]} for c in _sa_cells(ctx, gnb)])
        features = set(_pick(inputs, "features", NR_FEATURES))
        own = [s["dn"] for s in ctx.site.child(dn, "SNSSAI")]
        slices = [s for s in inputs.get("slices") or [] if s in own] if "slices" in inputs else \
            (own if _slices_named(ctx, gnb) else [])
        if not cells:
            raise PlanError(["Pick the cells."])
        earfcn = (inputs.get("fallbackEarfcn") or "").strip() or None
        if earfcn and (not earfcn.isdigit() or int(earfcn) > carrier.EARFCN_MAX):
            raise PlanError([f"The EPS fallback EARFCN is a number from 0 to {carrier.EARFCN_MAX}."])
        out = _plan_nr(ctx, doc, gnb, cells, features, slices, earfcn and str(int(earfcn)))
    else:
        raise PlanError(["Pick where voice goes."])
    if not doc.changes:
        raise PlanError([f"Voice is set up already as picked: nothing to change on {label(dn)}'s cells."])
    return finish(ctx, doc, out)

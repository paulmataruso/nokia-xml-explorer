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
- an LTE carrier NR cells hand over to: an NRHOIR (the B2 measurement)
  for the EARFCN under the gNB, named in each cell's nrhoirDNList (full
  distNames). Production has one, NRHOIR-1, on each of its 27 gNBs, named
  by all 130 cells, on the carrier their NRLIM and NRREDRT name too;
- redirection on release: REDRT with redirRat eutra (redirFreqEutra), or
  REDRT with redirRat nr, a row in its redirNrCarFrq; NRREDRT on NR cells.
  Production numbers REDRT by RAT (0 eutra, 1 utraFDD, 5 geran, 9 nr), so
  a copy keeps its template's id where it is free.

An NR carrier on LTE cells is broadcast in SIB24, so its eNB gets actSIB24
true where its release has the switch: every eNB in the corpus whose cells
list NR carriers has it on (11), and none with it off lists any (84). A
redirect turns on its BTS's actRedirect the same way: LNBTS "enabled" (the
dictionary: it "enables the feature UE context release with redirect"; all
11 eNBs that redirect to NR have it), NRBTS "true" (all 27 gNBs with an
NRREDRT, and none of the 59 without). Where no file of the BTS's release
has the switch, the object that needs it isn't added either, and the plan
says why. A profile broadcasts NRLIM in SIB5 and NRIRFIM in SIB4, so its
sibSchedulingList gets that SIB, broadcasting, when it lacks it: every
profile in the corpus with an NRLIM schedules SIB5 (27 of 27), and every
one with an NRIRFIM SIB4 (29 of 29). An NR cell with no profile gets
production's (profile_of(), for the actions that chain this), where its
release has the class.

An NR carrier is named by its SSB: TS 38.331 V17.6.0 SIB4 field
descriptions, dl-CarrierFreq "indicates center frequency of the SS block
of the neighbour cells"; the LTE side measures the same value (production
LTE cells list 502110, the SSB of their gNB's GSCN 6276).

Settings come from a template: the cell's own object of the class, else
another cell's of this file, else one from another file (values only,
release-filtered), else production's own (BUILTIN), set alike but for the
carrier wherever production has it: NRREDRT-0 on the 130 production cells
with VoNR, NRLIM-1 and NRHOIR-1 on the 27 gNBs, NRFIM-1 and REDRT-9 (to
NR) on the 79 LTE cells. The
release filter reads parameters only, so lists are copied whole. The
carrier, band and SCS come from the inputs; the
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
    "ho-nr": {"label": "An LTE carrier NR cells hand over to", "parent": "NRCELL", "input": LTE,
              "objects": ("NRHOIR",),
              "detail": "Handover from NR to LTE: an NRHOIR (B2 measurement) for the EARFCN, which the cells name."},
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
    # Under the gNB, and named by the cells (a list of distNames) instead of under each.
    "NRHOIR": {"cls": "NRHOIR", "param": "earfcnValue", "ids": (1, None), "named": "nrhoirDNList"},
}
# Production's settings where no file loaded has the object, all but the carrier.
BUILTIN = {
    "NRREDRT": {"inst": "0", "release": "NRBTSCL25R2", "p": {"redirRat": "eutra", "redirPrio": "4", "redirPrioBadUlRadio": "4"},
                "from": "production's NRREDRT (alike on all 130 production cells with VoNR)"},
    "NRFIM": {"inst": "1", "release": "xL25R2", "from": "production's NRFIM (alike on all 79 production LTE cells but for the carrier)",
              "p": {"tResNr": "1"},
              "lists": {"nrCarFrqL": [{"deriveSsbIndexNr": "true", "nrCelResPrio": "7", "nrCelResSubPrio": "oDot4",
                                       "nrFrqThrH": "10", "nrFrqThrL": "6", "pMaxNr": "23", "qRxLevMinNr": "-112",
                                       "ssbMtcDurationNr": "2sf", "ssbMtcOffsetNr": "0", "ssbMtcPeriodicityNr": "20sf",
                                       "ssbScsNr": "30KHz"}]}},
    "REDRT:nr": {"inst": "9", "release": "xL25R2", "from": "production's REDRT-9 (alike on all 79 production LTE cells but for the carrier)",
                 "p": {"addGsmSIToRedirMsg": "both", "addUtranSIToRedirMsg": "both", "redirRat": "nr",
                       "redirectPrio": "4"},
                 "lists": {"redirNrCarFrq": [{"ssbDuration": "sf2", "ssbOffset": "0", "ssbPeriodicity": "sf20",
                                              "ssbSubcarrierSpacing": "30kHz"}]}},
    "NRLIM": {"inst": "1", "release": "NRBTSCL25R2", "from": "production's NRLIM (alike on all 27 production profiles but for the carrier)",
              "p": {"allowedMeasBw": "mbw100", "cellReselectionPriority": "6", "cellReselectionSubPriority": "oDot2",
                    "pMaxEutra": "23", "presenceAntPort1": "true", "qQualMin": "-34", "qRxLevMin": "-56",
                    "threshXHigh": "1", "threshXLow": "3"}},
    "NRHOIR": {"inst": "1", "release": "NRBTSCL25R2", "from": "production's NRHOIR (alike on all 27 production gNBs but for the carrier)",
               "p": {"allowedMeasBandwidth": "mbw100", "b1MeasRedirectEnabled": "none", "b2MeashoEnabled": "rsrp",
                     "b2Threshold1hoRsrp": "51", "b2Threshold1hoRsrpVoNr": "51", "b2Threshold1hoRsrq": "50",
                     "b2Threshold1hoRsrqVoNr": "50", "eutraFreqQOffsetRange": "0dB", "presenceAntennaPort1": "true",
                     "reportAmount": "r8", "reportInterval": "ms240", "widebandRsrqMeas": "true"},
               "lists": {
                   "b1MeasRedirectRsrp": [{"b1HysteresisRedirectRsrp": "0", "b1ThresholdRedirectRsrp": "18",
                                           "b1TimeToTriggerRedirectRsrp": "ms480"}],
                   "b1MeasRedirectRsrq": [{"b1HysteresisRedirectRsrq": "0", "b1ThresholdRedirectRsrq": "2",
                                           "b1TimeToTriggerRedirectRsrq": "ms480"}],
                   "eutraB2MeashoRsrp": [{"b2HysteresishoRsrp": "0", "b2HysteresishoRsrpVoNr": "0",
                                          "b2Threshold2hoRsrp": "30", "b2Threshold2hoRsrpVoNr": "30",
                                          "b2TimeToTriggerhoRsrp": "ms320", "b2TimeToTriggerhoRsrpVoNr": "ms320"}],
                   "eutraB2MeashoRsrq": [{"b2HysteresishoRsrq": "0", "b2HysteresishoRsrqVoNr": "0",
                                          "b2Threshold2hoRsrq": "2", "b2Threshold2hoRsrqVoNr": "2",
                                          "b2TimeToTriggerhoRsrq": "ms480", "b2TimeToTriggerhoRsrqVoNr": "ms480"}]}},
}
SCS = ("15 kHz", "30 kHz", "120 kHz")
SIB = {"NRLIM": "sibType5", "NRIRFIM": "sibType4"}  # the SIB a profile broadcasts the object in
SIB_ROW = {"sibBroadcastStatus": "broadcasting", "sibPeriodicity": "rf8", "sibScope": "cellSpecific"}
# Production's profile: NRSYSINFO_PROFILE-0, alike on all 27 production gNBs, named by all 130 cells in full.
PROFILE = {"inst": "0", "release": "NRBTSCL25R2",
           "p": {"addHystSfHigh": "dB0", "addHystSfMedium": "dB0", "combRelaxedMeasCond": "false",
                 "combRelaxedMeasCond2": "false", "highPrioMeasRelax": "false", "nCellChangeHigh": "2",
                 "nCellChangeMedium": "1", "qHyst": "dB4", "sNonIntraSearchP": "4", "siWindowLength": "s40",
                 "systemInformationTargetRate": "157", "tEvaluation": "s30", "tHystNormal": "s30",
                 "tReselectionEutra": "2", "threshServingLowP": "3"},
           "sibs": ("sibType2", "sibType3", "sibType5", "sibType8", "sibType4")}
# The switch each kind of cell's BTS needs for a carrier object: (parameter, on, why, basis).
SWITCH = {
    ("LNCEL", "NRFIM"): ("actSIB24", "true", "SIB24 carries the cells' NR carriers (NRFIM nrCarFrqL) to idle UEs: "
                                             "every eNB in the files this was built from that lists NR carriers has "
                                             "it on (11), and none with it off lists any (84).", "files"),
    ("LNCEL", "REDRT"): ("actRedirect", "enabled", "Release with redirect, which the cells' REDRT redirects to: the "
                                                   "dictionary has it enable the feature UE context release with "
                                                   "redirect.", "official"),
    ("NRCELL", "NRREDRT"): ("actRedirect", "true", "Release with redirect, which the cells' NRREDRT redirects to: on "
                                                   "in all 27 production gNBs with an NRREDRT, off in all 59 "
                                                   "without.", "files"),
}
EARFCN_MAX, NR_ARFCN_MAX = 262143, 3279165  # TS 36.331 ARFCN-ValueEUTRA-r9, TS 38.331 ARFCN-ValueNR


def _parents(ctx: Context, kind: str) -> list[dict]:
    return ctx.site.of(KINDS[kind]["parent"])


def _objects(site, parent: str, key: str) -> list[dict]:
    spec = OBJECTS[key]
    if "named" in spec:
        cell = site.by_dn.get(parent) or {}
        return [site.by_dn[d] for d in (cell.get("simple") or {}).get(spec["named"], []) if d in site.by_dn]
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
    have = ({key for f in ctx.corpus() for key in (f.get("carriers") or {})} | {kind_of(m) for m in ctx.site.mos}
            | set(BUILTIN))
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
        self.linked: dict[str, list[str]] = {}  # cells now naming an object the gNB had
        self.unproven: set[tuple] = set()  # (class, release, BUILTIN's) written in a release no file shows it in
        self.switched: dict[str, list[str]] = {}  # switch -> BTSs it was turned on on
        self.scheduled: dict[str, list[str]] = {}  # SIB -> profiles that now broadcast it
        self.profiles: dict[str, str] = {}  # gNB -> the profile this plan made for it
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
                        "lists": {k: [dict(r) for r in v] for k, v in t["lists"].items()}, "simple": {},
                        "inst": t.get("inst"), "from": "another file", "donor": True, "version": t.get("version")}
        b = BUILTIN.get(key)
        if b:
            if self.index and known is None and rel != b["release"]:
                self.unproven.add((cls, rel, b["release"]))
            return {"p": {k: v for k, v in b["p"].items() if keep(k)},
                    "lists": {k: [dict(r) for r in v] for k, v in (b.get("lists") or {}).items()},
                    "simple": {}, "inst": b["inst"], "from": b["from"], "donor": False}
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
        if key == "NRHOIR":
            return {"earfcnValue": i["earfcn"]}, {}
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
        if "named" in spec:
            self.add_named(parent, key, carrier, what)
            return
        missing = self.switch(parent, spec["cls"])
        if missing:
            self.skipped.setdefault(f"no file of its release has {missing}, which {spec['cls']} needs",
                                    []).append(label(parent["dn"]))
            return
        if parent["cls"] == "NRSYSINFO_PROFILE" and key in SIB:
            self.schedule(parent["dn"], SIB[key], spec["cls"])
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
            dn = self.doc.create(parent["dn"], spec["cls"], inst, sorted(params.items(), key=lambda kv: kv[0].lower()),
                                 w=w,
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

    def switch(self, cell: dict, cls: str) -> Optional[str]:
        """The switch the cell's BTS needs for the class (SWITCH), on. Returns
        "BTS switch" when no file of the BTS's release has it."""
        if (cell["cls"], cls) not in SWITCH:
            return None
        name, on, reason, basis = SWITCH[(cell["cls"], cls)]
        bts = cell["dn"].rsplit("/", 1)[0]
        m = self.site.by_dn.get(bts)
        if not m or self.doc.get(bts, name) == on:
            return None
        if self.index and name not in self.index.get(release_of(m["version"]), {}).get(m["cls"], set()):
            return f"{m['cls']} {name}"
        self.doc.set(bts, name, on, why("carrier", reason, basis))
        self.switched.setdefault(name, []).append(label(bts))
        return None

    def schedule(self, profile: str, sib: str, cls: str) -> None:
        """The profile broadcasts the SIB its new object goes out in."""
        doc = self.doc
        rows = doc.items(profile, "sibSchedulingList")
        i = next((i for i, r in enumerate(rows) if r.get("sibType") == sib), None)
        w = why("carrier", f"The {cls} goes out in {sib[:3].upper()}{sib[7:]}: every profile in the files this was "
                           f"built from with an {cls} broadcasts it.", "files")
        if i is None:
            doc.add_item(profile, "sibSchedulingList", [*SIB_ROW.items(), ("sibType", sib)], w)
        elif rows[i].get("sibBroadcastStatus") != "broadcasting":
            doc.set_item(profile, "sibSchedulingList", i, "sibBroadcastStatus", "broadcasting", w)
        else:
            return
        self.scheduled.setdefault(f"{sib[:3].upper()}{sib[7:]}", []).append(label(profile))

    def profile_of(self, cell: dict) -> Optional[dict]:
        """The system information profile an NR cell broadcasts, as a parent
        for add(). A cell with none gets production's, shared by the gNB's
        cells that have none, where its release has the class; else None."""
        doc, gnb = self.doc, cell["dn"].rsplit("/", 1)[0]
        ref = doc.get(cell["dn"], "nrSysInfoProfileDN") or ""
        for dn in (ref, f"{gnb}/{ref}") if ref else ():
            if doc.exists(dn):
                return self.site.by_dn.get(dn) or {"dn": dn, "cls": "NRSYSINFO_PROFILE", "version": cell["version"]}
        if self.index and "NRSYSINFO_PROFILE" not in self.index.get(release_of(cell["version"]), {}):
            return None
        dn = self.profiles.get(gnb)
        if dn is None:
            made = why("carrier", "The system information the cells broadcast, set like production's "
                                  "NRSYSINFO_PROFILE (alike on all 27 production gNBs).", "files")
            dn = doc.create(gnb, "NRSYSINFO_PROFILE", doc.next_free(gnb, "NRSYSINFO_PROFILE", int(PROFILE["inst"])),
                            sorted(PROFILE["p"].items(), key=lambda kv: kv[0].lower()), w=made,
                            **self.class_args(cell, "NRSYSINFO_PROFILE", {}))
            for sib in PROFILE["sibs"]:
                doc.add_item(dn, "sibSchedulingList", [*SIB_ROW.items(), ("sibType", sib)], made)
            self.profiles[gnb] = dn
        doc.set(cell["dn"], "nrSysInfoProfileDN", dn,
                why("carrier", f"{label(cell['dn'])} broadcasts {label(dn)}: every production cell names its gNB's "
                               "profile (130 of 130), in full.", "files"))
        return {"dn": dn, "cls": "NRSYSINFO_PROFILE", "version": cell["version"]}

    def add_named(self, cell: dict, key: str, carrier: str, what: str) -> None:
        """An object of the gNB for the carrier, named in the cell's list: the
        one the gNB has, else a new one like the template."""
        spec, doc = OBJECTS[key], self.doc
        gnb, cls, field, named = cell["dn"].rsplit("/", 1)[0], spec["cls"], spec["param"], spec["named"]
        names = doc.values(cell["dn"], named)
        mine = [d for d in names if doc.cls(d) == cls and doc.get(d, field) == carrier]
        if mine:
            self.skipped.setdefault(f"already {what}", []).append(label(cell["dn"]))
            return
        dn = next((d for d in doc.children(gnb, cls) if doc.get(d, field) == carrier), None)
        w = why("carrier", f"{what[0].upper() + what[1:]}: {label(cell['dn'])} names "
                           + (f"{label(dn)}, the gNB's {cls} for it." if dn else f"the new {cls} for it."), "files")
        if dn is None:
            t = self.template(cell, key)
            if not t:
                self.skipped.setdefault(f"no {cls} to copy in any file", []).append(label(cell["dn"]))
                return
            inst = self.free(gnb, key, t["inst"])
            made = why("carrier", f"{what[0].upper() + what[1:]}, set like "
                                  + (f"an {cls} of another file." if t["donor"] else f"{t['from']}."),
                       "donor" if t["donor"] else "files")
            dn = doc.create(gnb, cls, inst, sorted({**t["p"], **self.overrides(key, t)[0]}.items(),
                                                   key=lambda kv: kv[0].lower()),
                            w=made, **self.class_args(cell, cls, t))
            for name, rows in t["lists"].items():
                for r in rows:
                    doc.add_item(dn, name, list(r.items()), made)
            for name, vals in t["simple"].items():
                doc.set_values(dn, name, vals, made)
            self.copied.setdefault(t["from"], []).append(label(cell["dn"]))
        else:
            self.linked.setdefault(label(dn), []).append(label(cell["dn"]))
        doc.add_value(cell["dn"], named, dn, w)
        self.focus = self.focus or dn


def notes(p: _Plan) -> list[str]:
    """Everything a plan has to say: what it copied, replaced and left alone,
    and plan_notes()."""
    out = list(p.notes)
    for source, cells in p.copied.items():
        out.append(f"{', '.join(sorted(set(cells)))}: settings copied from {source}.")
    if p.copied:
        out.append("Check the reselection priority, thresholds and measurement bandwidth (for redirection, its "
                   "priority) suit the new carrier: they are the template's.")
    for where, fixed in p.replaced.items():
        out.append(f"Replaced {where}'s entry for it: {'; '.join(fixed)}. Its priorities and thresholds stay, "
                   "the carrier's own.")
    for reason, cells in p.skipped.items():
        out.append(f"Left alone: {', '.join(cells)} ({reason}).")
    if p.dropped:
        out.append(f"Left out, as no file of this release sets them: {', '.join(sorted(p.dropped)[:8])}.")
    return out + plan_notes(p)


def plan_notes(p: _Plan) -> list[str]:
    """What a plan did beyond the carrier objects, for any action chaining it."""
    out = [f"{', '.join(cells)} now name{'s' if len(cells) == 1 else ''} {dn}, the gNB's for it."
           for dn, cells in p.linked.items()]
    for gnb, dn in p.profiles.items():
        out.append(f"{label(gnb)}'s cells broadcast no system information profile, so they now name {label(dn)}, set "
                   "like production's (alike on all 27 production gNBs).")
    for sib, where in p.scheduled.items():
        out.append(f"{', '.join(sorted(set(where)))} now broadcast{'s' if len(set(where)) == 1 else ''} {sib}, which "
                   "the new carrier goes out in.")
    for name, where in p.switched.items():
        out.append(f"Turned on {name} on {', '.join(sorted(set(where)))}: "
                   + ("its cells broadcast their NR carriers in SIB24." if name == "actSIB24" else
                      "release with redirect, for the redirect added."))
    for cls, rel, theirs in sorted(p.unproven):
        out.append(f"No file of {rel} has an {cls}: it is written as production's ({theirs}). Check this release "
                   "takes it.")
    return out


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
    done = len({c for cells in [*p.copied.values(), *p.linked.values()] for c in cells}
               | {w.split(" ")[0] for w in p.replaced})
    return finish(ctx, doc, {"label": f"Add {what}", "summary": f"{spec['label']}: {what}, on {done} of {len(targets)}.",
                             "notes": notes(p), "confirm": [], "focus": p.focus})

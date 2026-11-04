"""
Add a QoS profile: a 5QI on a gNB (SA), a QCI on a gNB for EN-DC bearers,
or a QCI on an LTE eNB. PROJECT_STATE §9.9 has the plan and the corpus
findings.

5G, SA: NRDRB_5QI-n (fiveqiValueList, dataForwarding, snssaiList) names an
NRDRB, which names its NRDRB_MAC, NRDRB_PDCP, NRDRB_RLC_AM or _UM (by
rlcMode) and NRDRX. 5G, EN-DC: NRDRB_QCI-n (qciValueList) names an NRDRB the
same way.
- n is the value when that is free, as production numbers them (the
  owner's rule, 2026-11-04: "By 5QI value, as Nokia"); a second mapping of
  5QI 1-9 takes 20 + 5QI; else the lowest free from 2, since 1 is only for
  the mapping of 5QI (or QCI) 1.
- The bearer is a new NRDRB with the template's settings, or one the gNB
  already has (the lab gNBs put every 5QI on one). A new one is NRDRB-(10 +
  5QI) for 5QI 1-9 and NRDRB-QCI for EN-DC QCIs, as production numbers
  them, else the lowest free from 20.
- Its profiles are reused when the gNB has one with the same values, so
  they don't multiply; else made with the lowest free id. A DRX profile
  with no twin reuses the gNB's NRDRX of the template's id (NRDRX-0..3 are
  NoDRX, Default NonGbr, Default VoNR and Default ANR on every 25R2 gNB),
  with a note when its values differ.
- One 5QI is mapped once per slice: production maps 5QI 6 twice, for
  different slices. A mapping that names no slice overlaps every other.
- The resource type must match 3GPP's for a standardized value: a GBR 5QI
  needs a GBR bearer, and a non-GBR one a non-GBR bearer.

LTE: the eNB's qciTabN row, set field by field to the template's, through
the release filter. The pdcpProfN and rlcProfN rows it names are added
when missing; one that exists with other values is kept, because other
QCIs share it. Its DRX profile must be defined in every cell's DRX, or the
row keeps its own. EN-DC fields stay as they are: the EN-DC action owns
them.

Templates: production's (qos_templates.py, built from the 27 production
25R2 gNBs, which all agree), the other files' profiles of the same value,
and this file's own profiles of any value. Their values are profile
settings, never identities: slices are picked from this gNB's own.

3GPP: TS 23.501 Table 5.7.4-1 (5QI) and TS 23.203 Table 6.1.7-A (QCI), read
from the ETSI PDFs of V17.10.0 and V17.2.0 when this was built.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from ..parser import _local, _text
from . import Context, PlanError, finish
from .doc import Doc, instance, label, natural, release_of, why
from .neighbours import number
from .qos_files import LTE_PROFILE_FIELDS, bearer, bearer_signature, lte_profiles, summary
from .qos_templates import TEMPLATES
from .tidy import REPEAT

ID = "qos"
TITLE = "Add a QCI or 5QI profile"
GROUP = "Features"
SUMMARY = ("Map a 5QI or QCI to a bearer with all its settings: the gNB's NRDRB with its MAC, PDCP, RLC and DRX "
           "profiles, or the eNB's QCI table.")
UI = "form"
KEYWORDS = "QoS QCI 5QI quality of service bearer DRB NRDRB NRDRB_5QI NRDRB_QCI qciTab VoLTE VoNR slice SNSSAI"

SA, NSA, LTE = "5qi", "qci-nr", "lte"
OWN, PRESET, OTHER, REPLACE = "own", "preset", "other", "replace"
TEMPLATE_RELEASE = "NRBTSCL25R2"  # the built-in templates' release: exempt from the release filter

# 3GPP characteristics: resource type, priority level, packet delay budget,
# packet error rate, example services.
FIVEQI = {
    1: ("GBR", "20", "100 ms", "10⁻²", "Conversational voice"),
    2: ("GBR", "40", "150 ms", "10⁻³", "Conversational video (live streaming)"),
    3: ("GBR", "30", "50 ms", "10⁻³", "Real-time gaming, V2X messages"),
    4: ("GBR", "50", "300 ms", "10⁻⁶", "Non-conversational video (buffered streaming)"),
    65: ("GBR", "7", "75 ms", "10⁻²", "Mission-critical push-to-talk voice"),
    66: ("GBR", "20", "100 ms", "10⁻²", "Non-mission-critical push-to-talk voice"),
    67: ("GBR", "15", "100 ms", "10⁻³", "Mission-critical video"),
    71: ("GBR", "56", "150 ms", "10⁻⁶", "Live uplink streaming"),
    72: ("GBR", "56", "300 ms", "10⁻⁴", "Live uplink streaming"),
    73: ("GBR", "56", "300 ms", "10⁻⁸", "Live uplink streaming"),
    74: ("GBR", "56", "500 ms", "10⁻⁸", "Live uplink streaming"),
    76: ("GBR", "56", "500 ms", "10⁻⁴", "Live uplink streaming"),
    5: ("Non-GBR", "10", "100 ms", "10⁻⁶", "IMS signalling"),
    6: ("Non-GBR", "60", "300 ms", "10⁻⁶", "Buffered video, TCP-based (web, e-mail, file sharing)"),
    7: ("Non-GBR", "70", "100 ms", "10⁻³", "Voice, live video, interactive gaming"),
    8: ("Non-GBR", "80", "300 ms", "10⁻⁶", "Buffered video, TCP-based (web, e-mail, file sharing)"),
    9: ("Non-GBR", "90", "300 ms", "10⁻⁶", "Buffered video, TCP-based (web, e-mail, file sharing)"),
    10: ("Non-GBR", "90", "1100 ms", "10⁻⁶", "Buffered video, TCP-based, with satellite delay"),
    69: ("Non-GBR", "5", "60 ms", "10⁻⁶", "Mission-critical delay-sensitive signalling"),
    70: ("Non-GBR", "55", "200 ms", "10⁻⁶", "Mission-critical data"),
    79: ("Non-GBR", "65", "50 ms", "10⁻²", "V2X messages"),
    80: ("Non-GBR", "68", "10 ms", "10⁻⁶", "Low-latency eMBB, augmented reality"),
    82: ("Delay-critical GBR", "19", "10 ms", "10⁻⁴", "Discrete automation"),
    83: ("Delay-critical GBR", "22", "10 ms", "10⁻⁴", "Discrete automation, V2X"),
    84: ("Delay-critical GBR", "24", "30 ms", "10⁻⁵", "Intelligent transport systems"),
    85: ("Delay-critical GBR", "21", "5 ms", "10⁻⁵", "Electricity distribution, high voltage"),
    86: ("Delay-critical GBR", "18", "5 ms", "10⁻⁴", "V2X collision avoidance, platooning"),
    87: ("Delay-critical GBR", "25", "5 ms", "10⁻³", "Interactive service, motion tracking"),
    88: ("Delay-critical GBR", "25", "10 ms", "10⁻³", "Interactive service, motion tracking"),
    89: ("Delay-critical GBR", "25", "15 ms", "10⁻⁴", "Visual content for cloud or split rendering"),
    90: ("Delay-critical GBR", "25", "20 ms", "10⁻⁴", "Visual content for cloud or split rendering"),
}
QCI = {
    1: ("GBR", "2", "100 ms", "10⁻²", "Conversational voice"),
    2: ("GBR", "4", "150 ms", "10⁻³", "Conversational video (live streaming)"),
    3: ("GBR", "3", "50 ms", "10⁻³", "Real-time gaming, V2X messages"),
    4: ("GBR", "5", "300 ms", "10⁻⁶", "Non-conversational video (buffered streaming)"),
    65: ("GBR", "0.7", "75 ms", "10⁻²", "Mission-critical push-to-talk voice"),
    66: ("GBR", "2", "100 ms", "10⁻²", "Non-mission-critical push-to-talk voice"),
    67: ("GBR", "1.5", "100 ms", "10⁻³", "Mission-critical video"),
    75: ("GBR", "2.5", "50 ms", "10⁻²", "V2X messages"),
    5: ("Non-GBR", "1", "100 ms", "10⁻⁶", "IMS signalling"),
    6: ("Non-GBR", "6", "300 ms", "10⁻⁶", "Buffered video, TCP-based (web, e-mail, file sharing)"),
    7: ("Non-GBR", "7", "100 ms", "10⁻³", "Voice, live video, interactive gaming"),
    8: ("Non-GBR", "8", "300 ms", "10⁻⁶", "Buffered video, TCP-based (web, e-mail, file sharing)"),
    9: ("Non-GBR", "9", "300 ms", "10⁻⁶", "Buffered video, TCP-based (web, e-mail, file sharing)"),
    69: ("Non-GBR", "0.5", "60 ms", "10⁻⁶", "Mission-critical delay-sensitive signalling"),
    70: ("Non-GBR", "5.5", "200 ms", "10⁻⁶", "Mission-critical data"),
    79: ("Non-GBR", "6.5", "50 ms", "10⁻²", "V2X messages"),
    80: ("Non-GBR", "6.8", "10 ms", "10⁻⁶", "Low-latency eMBB, augmented reality"),
}
SPEC = {SA: "TS 23.501 Table 5.7.4-1", NSA: "TS 23.203 Table 6.1.7-A", LTE: "TS 23.203 Table 6.1.7-A"}
NAME = {SA: "5QI", NSA: "QCI", LTE: "QCI"}
MAPPING = {SA: ("NRDRB_5QI", "fiveqiValueList"), NSA: ("NRDRB_QCI", "qciValueList")}
ENDC_FIELDS = {"lteNrDualConnectSupport", "nrPdcpProfIdx", "arpEnDcMask", "startArpEnDc", "stopArpEnDc"}


def _table(side: str) -> dict:
    return FIVEQI if side == SA else QCI


def _gbr(res: Optional[str]) -> Optional[bool]:
    return None if res is None else res != "Non-GBR" and not res.startswith("nonGBR")


def _gnbs(ctx: Context) -> list[dict]:
    return [m for m in ctx.site.of("NRBTS") if m["dn"].count("/") == 1]


def _sides(ctx: Context, gnb: dict) -> list[str]:
    """SA and EN-DC, where the gNB's release has the mapping class (or the
    gNB has one already)."""
    index = ctx.release_index()
    rel = release_of(gnb["version"])
    here = {m["cls"] for m in ctx.site.mos if m["dn"].startswith(gnb["dn"] + "/")}
    if "NRDRB" not in here and index and "NRDRB" not in index.get(rel, {}):
        return []
    return [side for side in (SA, NSA) if MAPPING[side][0] in here or not index or rel == TEMPLATE_RELEASE
            or MAPPING[side][0] in index.get(rel, {})]


def _enbs(ctx: Context) -> list[dict]:
    return [m for m in ctx.site.of("LNBTS") if any(k.startswith("qciTab") for k in m["lists"])]


def available(ctx: Context) -> Optional[str]:
    if _enbs(ctx) or any(_sides(ctx, g) for g in _gnbs(ctx)):
        return None
    if _gnbs(ctx):
        return "This file's gNB release has no QoS mappings (NRDRB_5QI or NRDRB_QCI) in any file, and it has no LTE eNB."
    return "This file has no LTE eNB with a QCI table and no 5G gNB."


# --- Reading ------------------------------------------------------------------

def _here(ctx: Context) -> dict:
    if not hasattr(ctx, "_qos"):
        ctx._qos = summary(ctx.mos)
    return ctx._qos


def _others(ctx: Context) -> list[dict]:
    """Other files' QoS summaries, newest first."""
    return [f for f in sorted(ctx.corpus(), key=lambda f: -(f.get("mtime") or 0))
            if f.get("qos") and not (f["name"] == ctx.filename and f["source"] == ctx.source)]


def _bearers(ctx: Context, gnb: dict) -> list[dict]:
    """This gNB's NRDRBs as templates: {dn, bearer}."""
    by_dn = ctx.site.by_dn
    return [{"dn": d["dn"], "bearer": bearer(by_dn, gnb["dn"], d["dn"])} for d in ctx.site.child(gnb["dn"], "NRDRB")]


def _bearer_label(b: Optional[dict]) -> str:
    if not b:
        return "no bearer"
    p = b["drb"]["p"]
    mac = (b["parts"].get("nrDrbMacDN") or {}).get("p") or {}
    out = [p.get("resType") or "?", (p.get("rlcMode") or "?").replace("RLC_", "RLC "), f"DSCP {p.get('dscp', '?')}"]
    if mac:
        out.append(f"lcgid {mac.get('lcgid', '?')}, priority {mac.get('schedulPrio', '?')}")
    return " · ".join(out)


def _bearer_diff(a: dict, b: dict) -> str:
    """What bearer `b` sets differently from `a`, as "NRDRB_MAC delayTarget
    75, schedulPrio 8"."""
    out = []
    for name, x, y in [("NRDRB", a["drb"], b["drb"]),
                       *[(b["parts"][k]["cls"], a["parts"].get(k) or {}, b["parts"][k]) for k in b["parts"]]]:
        changed = [f"{k} {y['p'].get(k)}" for k in sorted(set(x.get("p") or {}) | set(y["p"]))
                   if (x.get("p") or {}).get(k) != y["p"].get(k)]
        if changed:
            out.append(f"{name} {', '.join(changed[:4])}" + (" and more" if len(changed) > 4 else ""))
    return "; ".join(out) or "lists only"


def _row_label(row: dict) -> str:
    return (f"{row.get('resType') or '?'} · priority {row.get('prio', '?')} · DSCP {row.get('dscp', '?')} · lcgid "
            f"{row.get('lcgid', '?')} · {(row.get('rlcMode') or '?').replace('RLC_', 'RLC ')}")


def _value_details(side: str, v: int) -> list[str]:
    std = _table(side).get(v)
    if not std:
        return [f"Not a standardized {NAME[side]} in {SPEC[side]}: an operator-specific value."]
    return [f"{SPEC[side]}: {std[0]}, priority level {std[1]}, packet delay budget {std[2]}, packet error rate "
            f"{std[3]}. {std[4]}."]


def _value_label(side: str, v: int) -> str:
    std = _table(side).get(v)
    return f"{NAME[side]} {v}" + (f" · {std[0]} · {std[4]}" if std else "")


def _production_missing(side: str, mapped: set[str]) -> list[str]:
    return [v for v in TEMPLATES["5qi" if side == SA else "qci"] if v not in mapped]


def _nr_options(ctx: Context, gnb: dict, side: str, mine: dict, others: list[dict]):
    """The value options, and the template options per value, for one gNB
    and side."""
    kind = "5qi" if side == SA else "qci"
    profiles = [p for p in mine.get(gnb["dn"], []) if p["kind"] == kind]
    mapped: dict[str, list[dict]] = {}
    for p in profiles:
        for v in p["values"]:
            mapped.setdefault(v, []).append(p)
    target = f"{side}|{gnb['dn']}"
    values, templates = [], {}
    order = sorted(_table(side), key=lambda v: (_gbr(_table(side)[v][0]) is False, v))
    if side == SA:
        order = [v for v in order if not _table(side)[v][0].startswith("Delay")] + \
            [v for v in order if _table(side)[v][0].startswith("Delay")]
    extra = sorted({int(v) for v in mapped if v.isdigit() and int(v) not in _table(side)})
    for v in [*order, *extra]:
        here = mapped.get(str(v), [])
        status = (f"Mapped here: {', '.join(label(p['dn']) for p in here)}"
                  + (f", for {sum(len(p['slices']) for p in here)} slice(s)" if any(p["slices"] for p in here) else "")
                  + (". Another mapping must name other slices." if side == SA else ".")) if here else "Not mapped here."
        values.append({"value": str(v), "key": f"{target}|{v}", "label": _value_label(side, v),
                       "group": "Mapped here" if here else "Not mapped here",
                       "details": _value_details(side, v) + [status]})
    missing = _production_missing(side, set(mapped))
    if missing:
        values.append({"value": PRESET, "key": f"{target}|{PRESET}", "group": "Several at once",
                       "label": f"Every {NAME[side]} production gNBs map that this one lacks ({', '.join(missing)})",
                       "details": [f"Each with production's template and a bearer of its own, as on all "
                                   f"{TEMPLATES[kind][missing[0]]['of']} production gNBs in the files this was "
                                   "built from."]})
    if TEMPLATES[kind]:
        values.append({"value": REPLACE, "key": f"{target}|{REPLACE}", "group": "Several at once",
                       "label": f"Replace every {NAME[side]} mapping with production's set "
                                f"({', '.join(TEMPLATES[kind])})",
                       "details": [f"Removes this gNB's {MAPPING[side][0]} mappings and the bearers and profiles only "
                                   "they use (NRDRB-1, the default bearer, stays), then writes production's, numbered "
                                   "as production numbers them: "
                                   + ("NRDRB_5QI-5 maps 5QI 5 to NRDRB-15, whose MAC is NRDRB_MAC-5."
                                      if side == SA else "NRDRB_QCI-6 maps QCI 6 to NRDRB-6."),
                                   "An object already on its production number keeps it and gets the template's "
                                   "values; the review lists each old value. The slices stay the site's."]})
    values.append({"value": OTHER, "key": f"{target}|{OTHER}", "group": "Other",
                   "label": f"Another {NAME[side]} (type it in)", "details": ["An operator-specific value, say."]})

    def option(value, group, text, details):
        return {"value": value, "key": value, "group": group, "label": text, "details": details}

    own = [option(f"here|{p['dn']}", "This file", f"Copy {label(p['dn'])} ({NAME[side]} {', '.join(p['values'])}) · "
                  f"{_bearer_label(p['bearer'])}", ["Its bearer settings and profiles, for the new value."])
           for p in profiles if p["bearer"]]
    used = {p["bearer"] and bearer_signature(p["bearer"]) for p in profiles}
    for b in _bearers(ctx, gnb):
        if bearer_signature(b["bearer"]) not in used:
            used.add(bearer_signature(b["bearer"]))
            own.append(option(f"drb|{b['dn']}", "This file", f"Copy {label(b['dn'])} · {_bearer_label(b['bearer'])}",
                              ["The settings and profiles of this bearer, which no mapping of this kind names."]))
    for v in [*[str(x) for x in order], *[str(x) for x in extra], OTHER]:
        opts, seen = [], set()
        built = TEMPLATES[kind].get(v)
        if built:
            seen.add(bearer_signature(built["bearer"]))
            opts.append(option(f"builtin|{kind}|{v}", "Production template", _bearer_label(built["bearer"]),
                               [f"What {built['gnbs']} of the {built['of']} production gNBs in the files this was "
                                f"built from map {NAME[side]} {v} to."]))
            for i, alt in enumerate(built.get("variants") or [], 1):
                seen.add(bearer_signature(alt["bearer"]))
                opts.append(option(f"builtin|{kind}|{v}|{i}", "Production template",
                                   f"Second mapping · {_bearer_label(alt['bearer'])}",
                                   [f"{alt['gnbs']} of the {built['of']} production gNBs in the files this was built "
                                    f"from map {NAME[side]} {v} a second time, for other slices, to this bearer. It "
                                    f"differs from the first in {_bearer_diff(built['bearer'], alt['bearer'])}."]))
        if v == OTHER or not built:
            std = _table(side).get(int(v)) if v.isdigit() else None
            for x, t in sorted(TEMPLATES[kind].items(), key=lambda kv: std is not None and _gbr(std[0]) !=
                               _gbr(kv[1]["bearer"]["drb"]["p"].get("resType"))):
                opts.append(option(f"builtin|{kind}|{x}", "Production templates of other values",
                                   f"Like {NAME[side]} {x} · {_bearer_label(t['bearer'])}",
                                   [f"Production's {NAME[side]} {x} bearer."]))
        for f in others if v != OTHER else ():
            for g in f["qos"]["gnbs"]:
                for p in g["profiles"]:
                    if p["kind"] != kind or v not in p["values"] or not p["bearer"]:
                        continue
                    sig = bearer_signature(p["bearer"])
                    if sig in seen:
                        continue
                    seen.add(sig)
                    opts.append(option(f"file|{f['key']}|{p['dn']}", "In other files", _bearer_label(p["bearer"]),
                                       [f"{label(p['dn'])} of {f['name']}."]))
        opts += own
        templates[f"{target}|{v}"] = opts
    return values, templates, mapped


def _extras(side: str, mapped: dict) -> list[dict]:
    """The values this gNB maps and production doesn't: a replace removes them unless picked."""
    kind = "5qi" if side == SA else "qci"
    return [{"value": v, "label": f"Keep {_value_label(side, int(v))}",
             "details": [f"Mapped here ({', '.join(label(p['dn']) for p in ps)}); production gNBs map no "
                         f"{NAME[side]} {v}. Kept with its own bearer settings, numbered by its value."]}
            for v, ps in sorted(mapped.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)
            if v.isdigit() and v not in TEMPLATES[kind]]


def qci_donor(ctx: Context, enb: dict, q: str, prefer=lambda row: False) -> Optional[str]:
    """A template for qciTab q: another file's row for that QCI, from an eNB
    of this one's release first, then one `prefer` takes (by the row)."""
    rel, best = release_of(enb["version"]), None
    for f in ctx.corpus():
        for e in (f.get("qos") or {}).get("enbs", []):
            for t in e["tabs"]:
                if t["qci"] == q:
                    rank = (release_of(e["version"]) != rel, not prefer(t["row"]))
                    if best is None or rank < best[0]:
                        best = (rank, f"file|{f['key']}|{e['dn']}|{q}")
    return best[1] if best else None


def _lte_options(ctx: Context, enb: dict, others: list[dict]):
    rel = release_of(enb["version"])
    tabs = {t["qci"]: t for t in next((e["tabs"] for e in _here(ctx)["enbs"] if e["dn"] == enb["dn"]), [])}
    known = set(tabs)
    for f in others:
        for e in f["qos"]["enbs"]:
            if release_of(e["version"]) == rel:
                known |= {t["qci"] for t in e["tabs"]}
    target = f"{LTE}|{enb['dn']}"
    values, templates = [], {}
    for q in sorted(known, key=int):
        t = tabs.get(q)
        values.append({"value": q, "key": f"{target}|{q}", "label": _value_label(LTE, int(q)),
                       "group": "In this eNB's QCI table" if t else f"Not in this eNB's table ({rel} files have it)",
                       "details": _value_details(LTE, int(q))
                       + ([f"Now: {t['row'].get('qciSupp') or 'no qciSupp'} · {_row_label(t['row'])}."] if t else [])})
        opts, seen = [], {t["sig"]} if t else set()
        for same in (True, False):
            for f in others:
                for e in f["qos"]["enbs"]:
                    if (release_of(e["version"]) == rel) != same:
                        continue
                    for x in e["tabs"]:
                        if x["qci"] != q or x["sig"] in seen:
                            continue
                        seen.add(x["sig"])
                        opts.append({"value": f"file|{f['key']}|{e['dn']}|{q}", "key": f"file|{f['key']}|{q}",
                                     "group": f"In other {rel} files" if same else "In files of other releases",
                                     "label": _row_label(x["row"]),
                                     "details": [f"qciTab{q} of {label(e['dn'])} in {f['name']}"
                                                 + ("" if same else f" ({release_of(e['version'])})") + "."]})
        for x, other in sorted(tabs.items(), key=lambda kv: int(kv[0])):
            if x != q:
                opts.append({"value": f"here|{enb['dn']}|{x}", "key": f"here|{x}", "group": "This eNB",
                             "label": f"Like its QCI {x} · {_row_label(other['row'])}",
                             "details": [f"qciTab{x}'s settings, for QCI {q}."]})
        templates[f"{target}|{q}"] = opts
    return values, templates


def setup(ctx: Context) -> dict:
    site, others = ctx.site, _others(ctx)
    mine = {g["dn"]: g["profiles"] for g in _here(ctx)["gnbs"]}
    targets, values, templates, defaults, drbs, slices, slice_default = [], {}, {}, {}, {}, {}, {}
    keep = {}
    for gnb in _gnbs(ctx):
        for side in _sides(ctx, gnb):
            key = f"{side}|{gnb['dn']}"
            targets.append({"value": key, "key": key, "group": f"gNB {instance(gnb['dn'])}",
                            "label": f"{label(gnb['dn'])} · " + ("5QI, for SA" if side == SA else "QCI, for EN-DC"),
                            "details": ["NRDRB_5QI: which bearer each 5QI's flows use, for which slices."
                                        if side == SA else
                                        "NRDRB_QCI: which bearer the gNB gives the NR leg of an EN-DC bearer of each "
                                        "QCI."]})
            v, t, mapped = _nr_options(ctx, gnb, side, mine, others)
            values[key] = v
            if _extras(side, mapped):
                keep[f"{key}|{REPLACE}"] = _extras(side, mapped)
            templates.update(t)
            defaults.update({k: opts[0]["value"] for k, opts in t.items() if opts})
            users: dict[str, list[str]] = {}
            for p in mine.get(gnb["dn"], []):
                d = site.by_dn.get(p["dn"], {}).get("p", {}).get("nrDrbDN")
                if d:
                    users.setdefault(d if d.startswith("MRBTS-") else f"{gnb['dn']}/{d}", []).append(
                        f"{'5QI' if p['kind'] == '5qi' else 'QCI'} {', '.join(p['values'])}")
            drbs[key] = [{"value": OWN, "label": "Its own bearer (a new NRDRB), with the template's settings"}] + [
                {"value": d["dn"], "label": f"Share {label(d['dn'])} · {d['p'].get('resType', '?')} · "
                                           f"{(d['p'].get('rlcMode') or '?').replace('RLC_', 'RLC ')} · DSCP "
                                           f"{d['p'].get('dscp', '?')}",
                 "details": [f"Now used by {'; '.join(users[d['dn']])}." if d["dn"] in users else "No mapping uses it."]}
                for d in site.child(gnb["dn"], "NRDRB")]
            if side == SA:
                opts = [{"value": s["dn"], "label": f"{label(s['dn'])} · SST {s['p'].get('sst', '?')}"
                                                    + (f" · SD {s['p']['sd']}" if s["p"].get("sd") else "")}
                        for s in site.child(gnb["dn"], "SNSSAI")]
                if opts:
                    slices[key] = opts
                    slice_default[key] = []
    for enb in _enbs(ctx):
        key = f"{LTE}|{enb['dn']}"
        targets.append({"value": key, "key": key, "group": f"eNB {instance(enb['dn'])}",
                        "label": f"{label(enb['dn'])} · QCI table",
                        "details": ["qciTabN: the LTE bearer settings of each QCI, with the PDCP and RLC profiles they "
                                    "name."]})
        v, t = _lte_options(ctx, enb, others)
        values[key] = v
        templates.update(t)
        defaults.update({k: opts[0]["value"] for k, opts in t.items() if opts})
    other = {"field": "value", "equals": OTHER}

    def by_value(per_target: dict) -> dict:
        """A target's options under each of its value options' keys, but a replace's."""
        return {o["key"]: opts for t, opts in per_target.items() for o in values.get(t, [])
                if o["value"] != REPLACE}
    return {
        "intro": "Adds a QoS profile with all its settings, from a template: production's, another file's, or one of "
                 "this file's own profiles. On a gNB the bearer's MAC, PDCP, RLC and DRX profiles are reused where the "
                 "gNB has the same ones.",
        "fields": [
            {"id": "target", "label": "Where", "type": "select", "options": targets,
             "default": targets[0]["value"] if len(targets) == 1 else None},
            {"id": "value", "label": "QCI or 5QI", "type": "select", "dependsOn": "target", "optionsByKey": values},
            {"id": "custom", "label": "Value", "type": "text", "showIf": other, "placeholder": "128",
             "hint": "1 to 255."},
            {"id": "template", "label": "Settings from", "type": "select", "dependsOn": "value",
             "optionsByKey": templates, "defaultByKey": defaults},
            # By value, not target, so a replace (which keeps each mapping's slices and bearer rules) asks neither.
            {"id": "drb", "label": "Bearer", "type": "select", "dependsOn": "value", "optionsByKey": by_value(drbs),
             "defaultByKey": {k: OWN for k in by_value(drbs)}},
            {"id": "slices", "label": "Slices", "type": "checks", "dependsOn": "value",
             "optionsByKey": by_value(slices), "defaultByKey": by_value(slice_default), "optional": True,
             "hint": "None ticked: the mapping names no slice, as on the lab gNBs. Production names the slices that "
                     "use the 5QI."},
            {"id": "keep", "label": "Keep", "type": "checks", "dependsOn": "value", "optionsByKey": keep,
             "defaultByKey": {k: [] for k in keep}, "optional": True,
             "hint": "Values production doesn't map are removed unless picked here."},
        ],
    }


# --- Planning: 5G ---------------------------------------------------------------

def _template(ctx: Context, value: str, kind: str):
    """The template a `template` input names: (content, where it is from)."""
    parts = value.split("|")
    if parts[0] == "builtin" and len(parts) in (3, 4) and parts[2] in TEMPLATES.get(parts[1], {}):
        built = TEMPLATES[parts[1]][parts[2]]
        what = f"production's {NAME[SA if parts[1] == '5qi' else NSA]} {parts[2]} template"
        if len(parts) == 3:
            return built, what
        i = int(parts[3]) if parts[3].isdigit() else 0
        if 1 <= i <= len(built.get("variants") or []):
            return built["variants"][i - 1], what + " for its second mapping"
    if parts[0] == "drb":
        gnb = parts[1].rsplit("/", 1)[0]
        b = bearer(ctx.site.by_dn, gnb, parts[1])
        if b:
            return {"p": {}, "bearer": b}, f"this file's {label(parts[1])}"
    if parts[0] == "here":
        dn = parts[1]
        for g in _here(ctx)["gnbs"]:
            for p in g["profiles"]:
                if p["dn"] == dn and p["bearer"]:
                    return p, f"this file's {label(dn)}"
        if len(parts) == 3:  # an LTE row of this eNB
            for e in _here(ctx)["enbs"]:
                for t in e["tabs"] if e["dn"] == dn else ():
                    if t["qci"] == parts[2]:
                        return t, f"this eNB's QCI {parts[2]}"
    if parts[0] == "file" and len(parts) >= 3:
        f = next((f for f in ctx.corpus() if f.get("key") == parts[1] and f.get("qos")), None)
        if f and len(parts) == 3:
            for g in f["qos"]["gnbs"]:
                for p in g["profiles"]:
                    if p["dn"] == parts[2] and p["bearer"]:
                        return p, f"{label(p['dn'])} of {f['name']}"
        if f and len(parts) == 4:
            for e in f["qos"]["enbs"]:
                for t in e["tabs"] if e["dn"] == parts[2] else ():
                    if t["qci"] == parts[3]:
                        return t, f"qciTab{parts[3]} of {f['name']}"
    raise PlanError(["Pick the settings to start from."])


def _el_values(doc: Doc, dn: str) -> dict:
    """An object's settings as qos_files.values_of() reads them."""
    el = doc.mos[dn]
    p, simple, rows = {}, {}, {}
    for c in el:
        tag = _local(c.tag)
        if tag == "p":
            p[c.get("name")] = _text(c)
        elif tag == "list":
            kids = list(c)
            if kids and all(_local(k.tag) == "p" for k in kids):
                simple[c.get("name")] = [_text(k) or "" for k in kids]
            else:
                rows[c.get("name")] = [{x.get("name"): _text(x) for x in k if _local(x.tag) == "p"} for k in kids]
    return {"p": p, "simple": simple, "rows": rows}


class _Nr:
    def __init__(self, ctx: Context, doc: Doc, gnb: dict, side: str):
        self.ctx, self.doc, self.gnb, self.side = ctx, doc, gnb, side
        self.dn = gnb["dn"]
        self.release = release_of(gnb["version"])
        self.index = ctx.release_index()
        self.notes: list[str] = []
        self.reused: list[str] = []
        self.focus: Optional[str] = None

    def known(self, cls: str, name: str) -> bool:
        return not self.index or self.release == TEMPLATE_RELEASE or name in self.index.get(self.release, {}).get(cls, set())

    def filtered(self, cls: str, content: dict) -> dict:
        return {"p": {k: v for k, v in content["p"].items() if self.known(cls, k)},
                "simple": {k: v for k, v in content["simple"].items() if self.known(cls, k)},
                "rows": {k: v for k, v in content["rows"].items() if self.known(cls, k)}}

    def full_class(self, cls: str) -> Optional[str]:
        if self.doc.of_class(cls):
            return None
        info = self.doc.class_info("NRBTS")
        return f"{info[0].rsplit(':', 1)[0]}:{cls}" if info and ":" in info[0] else None

    def make(self, cls: str, inst: str, content: dict, reason: str, basis: str, extra=()) -> str:
        w = why("qos", reason, basis)
        params = sorted([*content["p"].items(), *extra])
        dn = self.doc.create(self.dn, cls, inst, params, full_class=self.full_class(cls),
                             version=None if self.doc.of_class(cls) else self.gnb["version"], w=w)
        for name, vals in sorted(content["simple"].items()):
            self.doc.set_values(dn, name, vals, w)
        for name, rows in sorted(content["rows"].items()):
            for row in rows:
                self.doc.add_item(dn, name, sorted(row.items()), w)
        return dn

    def free(self, cls: str, prefer: list[int], start: int) -> str:
        taken = {instance(d) for d in self.doc.of_class(cls, self.dn)}
        for i in prefer:
            if str(i) not in taken:
                return str(i)
        return self.doc.next_free(self.dn, cls, start).rsplit("-", 1)[-1]

    def part(self, cls: str, part: dict) -> str:
        """An existing profile with the template's values, else a new one."""
        content = self.filtered(cls, part)
        for dn in self.doc.of_class(cls, self.dn):
            if _el_values(self.doc, dn) == content:
                self.reused.append(label(dn))
                return dn
        same = f"{self.dn}/{cls}-{part.get('inst')}"
        if cls == "NRDRX" and self.doc.exists(same):
            now = _el_values(self.doc, same)["p"]
            diff = [f"{k} {now.get(k) or 'unset'} here, {v} in the template" for k, v in content["p"].items()
                    if now.get(k) != v]
            self.notes.append(f"The bearer uses {label(same)}, the gNB's DRX profile of the template's id"
                              + (f"; its values differ ({'; '.join(diff[:3])}). The DRX action sets the standard "
                                 "profiles." if diff else "."))
            return same
        inst = self.free(cls, [], 0 if cls == "NRDRX" else 1)
        return self.make(cls, inst, content, f"A {cls} profile with the template's values; the gNB has none like it.",
                         "donor")

    def bearer(self, b: dict, v: int, source: str) -> str:
        refs = [(name, self.part(part["cls"], part)) for name, part in sorted(b["parts"].items())]
        prefer = [10 + v] if self.side == SA and v < 10 else [v] if self.side == NSA else []
        inst = self.free("NRDRB", prefer, 20)
        return self.make("NRDRB", inst, self.filtered("NRDRB", b["drb"]),
                         f"The bearer for {NAME[self.side]} {v}, with the settings of {source}.", "donor",
                         extra=[(name, dn) for name, dn in refs])

    def mapping(self, v: int, p: dict, drb: str, slices: list[str], source: str) -> str:
        cls, values = MAPPING[self.side]
        prefer = [v] + ([REPEAT + v] if self.side == SA and 1 <= v <= 9 else [])
        inst = self.free(cls, prefer, 2)
        if self.side == SA and not p.get("dataForwarding"):
            # A bearer template carries no mapping settings: as the gNB's other
            # mappings, else IRATDataFwd (all but production's 5QI 1).
            seen = Counter(self.doc.get(m, "dataForwarding") for m in self.doc.of_class(cls, self.dn))
            seen.pop(None, None)
            p = {**p, "dataForwarding": seen.most_common(1)[0][0] if seen else "IRATDataFwd"}
        w = why("qos", f"Maps {NAME[self.side]} {v} to {label(drb)}"
                + (f", for {', '.join(label(s) for s in slices)}" if slices else "")
                + (f"; dataForwarding as {source}" if p.get("dataForwarding") else "")
                + (f". Numbered by its value, as production numbers them." if inst == str(v) else
                   f". {v} is taken, so {inst}: a second mapping of a value is 20 above it, as production "
                   f"numbers them." if inst == str(REPEAT + v) else
                   f". Production numbers a mapping by its value, and {v} is taken, so the lowest free from 2 (1 "
                   f"is for the mapping of {NAME[self.side]} 1)."), "choice")
        params = sorted([*((k, x) for k, x in p.items() if self.known(cls, k)), ("nrDrbDN", drb)])
        dn = self.doc.create(self.dn, cls, inst, params, full_class=self.full_class(cls),
                             version=None if self.doc.of_class(cls) else self.gnb["version"], w=w)
        self.doc.set_values(dn, values, [str(v)], w)
        for s in slices:
            self.doc.add_item(dn, "snssaiList", [("snssaiDN", s)], w)
        return dn


def _mapped(doc: Doc, gnb: str, side: str) -> dict[str, list[tuple[str, set[str]]]]:
    """{value: [(mapping, its slice distNames)]} as the plan goes."""
    cls, values = MAPPING[side]
    out: dict[str, list[tuple[str, set[str]]]] = {}
    for dn in doc.of_class(cls, gnb):
        slices = {r.get("snssaiDN") or "" for r in doc.items(dn, "snssaiList")}
        slices = {s if s.startswith("MRBTS-") else f"{gnb}/{s}" for s in slices}
        for v in doc.values(dn, values):
            out.setdefault(v, []).append((dn, slices))
    return out


def _plan_nr(ctx: Context, doc: Doc, side: str, gnb: dict, inputs: dict) -> dict:
    kind = "5qi" if side == SA else "qci"
    value = inputs.get("value") or ""
    if value == REPLACE:
        return _plan_replace(ctx, doc, side, gnb, inputs)
    nr = _Nr(ctx, doc, gnb, side)
    problems: list[str] = []
    if value == PRESET:
        mapped = set(_mapped(doc, gnb["dn"], side))
        jobs = [(int(v), f"builtin|{kind}|{v}") for v in _production_missing(side, mapped)]
        if not jobs:
            raise PlanError([f"This gNB already maps every {NAME[side]} production gNBs map."])
    else:
        v = number(inputs.get("custom") if value == OTHER else value, 1, 255, f"The {NAME[side]}", problems)
        if problems:
            raise PlanError(problems)
        jobs = [(int(v), inputs.get("template") or "")]
    drb_choice = inputs.get("drb") or OWN
    if drb_choice != OWN and not doc.exists(drb_choice):
        raise PlanError(["Pick the bearer."])
    slices = [s for s in (inputs.get("slices") or []) if side == SA]
    for s in slices:
        if doc.cls(s) != "SNSSAI" or not s.startswith(gnb["dn"] + "/"):
            raise PlanError([f"{s} isn't one of this gNB's slices."])
    made = []
    for v, template in jobs:
        content, source = _template(ctx, template, kind)
        for dn, theirs in _mapped(doc, gnb["dn"], side).get(str(v), []):
            if side == NSA:
                problems.append(f"QCI {v} is mapped already ({label(dn)}).")
            elif not slices or not theirs or theirs & set(slices):
                both = sorted(theirs & set(slices))
                problems.append(f"5QI {v} is mapped already by {label(dn)}"
                                + (f" for {', '.join(label(s) for s in both)}" if both else
                                   ", which names no slice, so it covers them all" if not theirs else
                                   f" (for {', '.join(label(s) for s in sorted(theirs))}): pick the other slices this "
                                   "mapping is for") + ".")
        std = _table(side).get(v)
        if drb_choice == OWN:
            res = content["bearer"]["drb"]["p"].get("resType")
        else:
            res = doc.get(drb_choice, "resType")
        if std and _gbr(std[0]) is not None and _gbr(res) is not None and _gbr(std[0]) != _gbr(res):
            problems.append(f"{NAME[side]} {v} is {std[0]} ({SPEC[side]}), but "
                            + ("the template's bearer" if drb_choice == OWN else label(drb_choice))
                            + f" is {res}. Pick a {'GBR' if _gbr(std[0]) else 'non-GBR'} one.")
        if std and std[0].startswith("Delay"):
            nr.notes.append(f"5QI {v} is delay-critical GBR. No file in the corpus maps one, and no NRDRB resType "
                            "seen says delay-critical: check the release supports it.")
        if problems:
            raise PlanError(problems)
        if drb_choice == OWN:
            drb = nr.bearer(content["bearer"], v, source)
        else:
            drb = drb_choice
            others = [x for x, maps in _mapped(doc, gnb["dn"], side).items()
                      if any(doc.get(m, "nrDrbDN") in (drb, label(drb)) for m, _ in maps)]
            if others:
                nr.notes.append(f"{label(drb)} also carries {NAME[side]} {', '.join(sorted(others, key=int))}: they "
                                "share its scheduling, RLC and DRX settings.")
        made.append(nr.mapping(v, content.get("p") or {}, drb, slices, source))
    if nr.reused:
        nr.notes.append(f"Reused {', '.join(sorted(set(nr.reused), key=natural))}: the gNB had profiles with the "
                        "template's values.")
    if side == SA and not slices and ctx.site.child(gnb["dn"], "SNSSAI"):
        nr.notes.append("The mapping names no slice, as on the lab gNBs.")
    values = [str(v) for v, _ in jobs]
    return {
        "label": f"{NAME[side]} {', '.join(values)} on {label(gnb['dn'])}",
        "summary": f"{NAME[side]} {', '.join(values)} on gNB {instance(gnb['dn'])}",
        "notes": nr.notes,
        "confirm": [f"The core marks the flows meant for {NAME[side]} {', '.join(values)} with that value "
                    f"({'the SMF and PCF' if side == SA else 'the MME and PCRF'})"
                    + (", for the slices picked here." if slices else ".")]
                   + ([f"The eNB makes QCI {', '.join(values)} EN-DC-eligible (qciTab lteNrDualConnectSupport: the "
                       "EN-DC action, 4G side)."] if side == NSA else []),
        "focus": made[0] if made else None,
    }


def _plan_replace(ctx: Context, doc: Doc, side: str, gnb: dict, inputs: dict) -> dict:
    from .qos_replace import replace_nr  # it builds on this module

    out = replace_nr(ctx, doc, side, gnb, None, frozenset(inputs.get("keep") or []))
    if not doc.changes:
        raise PlanError([f"{label(gnb['dn'])}'s {NAME[side]} mappings are production's already, numbered as "
                         "production numbers them."])
    values = sorted(set(out["values"]), key=int)
    built = TEMPLATES.get("5qi" if side == SA else "qci", {})
    own = [v for v in values if v not in built]
    return {
        "label": f"Production's {NAME[side]} set on {label(gnb['dn'])}",
        "summary": f"{NAME[side]} {', '.join(v for v in values if v in built)} on gNB {instance(gnb['dn'])} as "
                   "production" + (f", {', '.join(own)} kept with {'its' if len(own) == 1 else 'their'} own settings"
                                   if own else "")
                   + (f", {len(out['removed'])} object{'s' if len(out['removed']) != 1 else ''} removed"
                      if out["removed"] else ""),
        "notes": out["notes"],
        "confirm": [f"The core marks each flow with its {NAME[side]} "
                    f"({'the SMF and PCF' if side == SA else 'the MME and PCRF'}): the values no longer mapped carry "
                    "no flows."],
        "focus": out["written"][0] if out["written"] else None,
    }


# --- Planning: LTE ----------------------------------------------------------------

def _release_fields(ctx: Context, release: Optional[str]) -> tuple[set[str], set[str]]:
    """qciTab fields and LNBTS lists the release's files write (empty: no
    other file of the release, so no filter)."""
    fields, lists = set(), set()
    for f in ctx.corpus():
        for e in (f.get("qos") or {}).get("enbs", []):
            if release_of(e["version"]) == release:
                fields |= e["fields"]
                lists |= e["lists"]
    return fields, lists


def _plan_lte(ctx: Context, doc: Doc, enb: dict, inputs: dict) -> dict:
    q = inputs.get("value") or ""
    if not q.isdigit():
        raise PlanError(["Pick the QCI."])
    content, source = _template(ctx, inputs.get("template") or "", "lte")
    dn, name = enb["dn"], f"qciTab{q}"
    rel = release_of(enb["version"])
    fields, lists = _release_fields(ctx, rel)
    fields |= {k for t in lte_profiles(enb) for k in t["row"]}
    lists |= set(enb["lists"])
    now = doc.items(dn, name)
    row = now[0] if now else None
    notes, kept = [], []
    write = {k: v for k, v in content["row"].items()
             if k != "qci" and k not in ENDC_FIELDS and v is not None and (not fields or k in fields)}
    w = why("qos", f"QCI {q} as {source}.", "donor")
    for field, prefix in LTE_PROFILE_FIELDS.items():
        idx = write.get(field)
        if not idx:
            continue
        prof = f"{prefix}{idx}"
        theirs = content["profiles"].get(prof)
        if doc.items(dn, prof):
            if theirs and doc.items(dn, prof) != theirs:
                users = [t["qci"] for t in lte_profiles(enb) if t["qci"] != q
                         and any(t["row"].get(f) == idx for f, pre in LTE_PROFILE_FIELDS.items() if pre == prefix)]
                notes.append(f"{prof} here differs from the template's; it is kept as it is"
                             + (f": QCI {', '.join(users)} use it too." if users else "."))
        elif theirs and prof in lists:
            for r in theirs:
                doc.add_item(dn, prof, sorted(r.items()), why("qos", f"The {prefix[:4].upper()} profile QCI {q} names "
                                                                     f"({field} {idx}), from {source}.", "donor"))
        else:
            kept.append(field)
            notes.append(f"The template's {field} {idx} names {prof}, which {rel or 'this release'} doesn't have: "
                         f"QCI {q} keeps its own" + (f" ({row.get(field)})." if row and row.get(field) else "."))
            write.pop(field)
    drx = write.get("drxProfileIndex")
    if drx:
        cells = [d for d in ctx.site.of("DRX", dn)]
        defined = [{r.get("drxProfileIndex") for rows in d["lists"].values() for r in rows} for d in cells]
        if defined and not all(drx in x for x in defined):
            write.pop("drxProfileIndex")
            notes.append(f"The template uses DRX profile {drx}, which not every cell's DRX defines: QCI {q} keeps "
                         + (f"profile {row.get('drxProfileIndex')}." if row and row.get("drxProfileIndex") else
                            "no DRX profile.") + " The DRX action adds the profiles.")
    if row is None:
        doc.add_item(dn, name, sorted([("qci", q), *write.items()]), w)
    else:
        for k, v in sorted(write.items()):
            if row.get(k) != v:
                doc.set_item(dn, name, 0, k, v, w)
    endc = [k for k in ENDC_FIELDS if content["row"].get(k) and (row or {}).get(k) != content["row"].get(k)]
    if endc:
        notes.append(f"EN-DC settings ({', '.join(sorted(endc))}) are left as they are: the EN-DC action sets them.")
    std = QCI.get(int(q))
    res = write.get("resType") or (row or {}).get("resType")
    if std and _gbr(res) is not None and _gbr(std[0]) != _gbr(res):
        notes.append(f"QCI {q} is {std[0]} in {SPEC[LTE]}, and the row says {res}.")
    if q == "1":
        notes.append("VoLTE also uses the cells' QCI 1 settings (LNCEL *Qci1 parameters and lists), which this "
                     "doesn't change.")
    return {
        "label": f"QCI {q} on {label(dn)}",
        "summary": f"QCI {q} on eNB {instance(dn)}" + ("" if doc.changes else ": already as the template"),
        "notes": notes,
        "confirm": [],
        "focus": f"{dn}::list::{name}::item::0" if doc.changes else None,
    }


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    side, _, dn = (inputs.get("target") or "").partition("|")
    doc = Doc(ctx.raw)
    if side == LTE:
        enb = next((m for m in _enbs(ctx) if m["dn"] == dn), None)
        if not enb:
            raise PlanError(["Pick where the profile goes."])
        out = _plan_lte(ctx, doc, enb, inputs)
    else:
        gnb = next((m for m in _gnbs(ctx) if m["dn"] == dn and side in _sides(ctx, m)), None)
        if not gnb:
            raise PlanError(["Pick where the profile goes."])
        out = _plan_nr(ctx, doc, side, gnb, inputs)
    return finish(ctx, doc, out)

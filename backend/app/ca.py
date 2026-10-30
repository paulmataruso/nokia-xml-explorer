"""
LTE carrier aggregation (CA) check: reads a file's LNBTS / LNCEL / CAREL
setup and reports what it finds. Phase 1 of the CA wizard, so it is
read-only and never writes a file.

Every finding names where its rule comes from (`basis`):

- "official": a cross-parameter rule from Nokia's own parameter
  dictionaries (LTE18 / SBTS18A), mostly the notes on actDLCAggr in
  parameters.json. `rule` carries the dictionary's own parameter and rule
  number so it can be looked up there. The dictionaries are older than many
  real exports, so a rule that working files break is a warning, not an
  error: caPoolId is the known case (exports that run CA on air leave it
  out on every cell).
- "files": a pattern learned by comparing the corpus's CA files with each
  other. Not documented anywhere; reported as a warning or a note.
- "general": plain facts about the setup (fewer than two cells, an SCell on
  another eNB) that need no rule.

Pure (bytes) -> dict like parser.py: no FastAPI, no knowledge base.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Optional

from .parser import XmlParseError, _local, _short_class, _strip_leading_junk, _text

# Downlink EARFCN ranges per E-UTRA band, from 3GPP TS 36.101 Table 5.7.3-1.
# Only bands whose ranges are certain are listed; anything else shows no
# band rather than a guessed one.
_BANDS = (
    (1, 0, 599), (2, 600, 1199), (3, 1200, 1949), (4, 1950, 2399),
    (5, 2400, 2649), (7, 2750, 3449), (8, 3450, 3799), (12, 5010, 5179),
    (13, 5180, 5279), (14, 5280, 5379), (17, 5730, 5849), (20, 6150, 6449),
    (25, 8040, 8689), (26, 8690, 9039), (28, 9210, 9659), (29, 9660, 9769),
    (30, 9770, 9869), (38, 37750, 38249), (39, 38250, 38649),
    (40, 38650, 39649), (41, 39650, 41589), (42, 41590, 43589),
    (43, 43590, 45589), (46, 46790, 54539), (48, 55240, 56739),
    (66, 66436, 67335), (71, 68586, 68935),
)

# Classes that exist only for CA, listed in the panel's setup summary.
_CA_CLASSES = ("CAGENB", "CADPR", "CADPRCBRS", "CADPRLAA", "CAIMLBP", "CAIMLBS", "CAPR", "CAREL")

_MODULATION_RANK = {"QPSK": 0, "16QAM": 1, "64QAM": 2, "256QAM": 3}


def band_for_earfcn(earfcn: Optional[str]) -> Optional[int]:
    try:
        n = int(earfcn)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    for band, lo, hi in _BANDS:
        if lo <= n <= hi:
            return band
    return None


def _int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parent(dn: str) -> str:
    return dn.rsplit("/", 1)[0] if "/" in dn else ""


def _label(dn: str) -> str:
    return dn.rsplit("/", 1)[-1]


def _instance(dn: str) -> str:
    return _label(dn).rsplit("-", 1)[-1]


def _pid(dn: str, name: str) -> str:
    """Tree node id of a direct <p> -- the id scheme parser.py uses."""
    return f"{dn}::p::{name}"


def _item_pid(dn: str, list_name: str, index: int, name: str) -> str:
    return f"{dn}::list::{list_name}::item::{index}::p::{name}"


def _load(raw_bytes: bytes) -> list[dict]:
    cleaned = _strip_leading_junk(raw_bytes)
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as e:
        raise XmlParseError(str(e)) from e
    mos = []
    for el in root.iter():
        if _local(el.tag) != "managedObject":
            continue
        params: dict[str, Optional[str]] = {}
        lists: dict[str, list[dict]] = {}
        for child in el:
            tag = _local(child.tag)
            if tag == "p":
                params[child.get("name") or ""] = _text(child)
            elif tag == "list":
                lists[child.get("name") or ""] = [
                    {p.get("name") or "": _text(p) for p in item if _local(p.tag) == "p"} for item in child
                ]
        mos.append({
            "dn": el.get("distName") or "",
            "cls": _short_class(el.get("class")),
            "p": params,
            "lists": lists,
            "version": el.get("version"),
        })
    return mos


class _Findings:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, severity: str, basis: str, title: str, detail: str, targets: list[tuple[str, str]],
            rule: Optional[tuple[str, Optional[str]]] = None) -> None:
        self.items.append({
            "severity": severity,
            "basis": basis,
            "rule": {"param": rule[0], "number": rule[1]} if rule else None,
            "title": title,
            "detail": detail,
            "targets": [{"id": i, "label": label} for i, label in targets],
        })


def _cells(lnbts: dict, kids: dict[str, list[dict]]) -> list[dict]:
    def child(dn: str, cls: str) -> Optional[dict]:
        return next((m for m in kids[dn] if m["cls"] == cls), None)

    cells = []
    for mo in kids[lnbts["dn"]]:
        if mo["cls"] != "LNCEL":
            continue
        dn = mo["dn"]
        fdd, tdd = child(dn, "LNCEL_FDD"), child(dn, "LNCEL_TDD")
        sub = fdd or tdd
        pucch = (child(sub["dn"], "MPUCCH_FDD") or child(sub["dn"], "MPUCCH_TDD")) if sub else None
        earfcn = fdd["p"].get("earfcnDL") if fdd else tdd["p"].get("earfcn") if tdd else None
        cells.append({
            "mo": mo,
            "sub": sub,
            "pucch": pucch,
            "sib": child(dn, "SIB"),
            "cbsdcel": child(dn, "CBSDCEL"),
            "carels": [m for m in kids[dn] if m["cls"] == "CAREL"],
            "caprs": [m for m in kids[dn] if m["cls"] == "CAPR"],
            "tech": "FDD" if fdd else "TDD" if tdd else mo["p"].get("cellTechnology"),
            "earfcn": earfcn,
            "band": band_for_earfcn(earfcn),
            "bandwidth": fdd["p"].get("dlChBw") if fdd else tdd["p"].get("chBw") if tdd else None,
        })
    return cells


def _analyze_enb(lnbts: dict, kids: dict[str, list[dict]]) -> dict:
    b = lnbts["p"]
    enb_dn = lnbts["dn"]
    own_id = _instance(enb_dn)
    f = _Findings()
    cells = _cells(lnbts, kids)
    by_lcr = {c["mo"]["p"].get("lcrId"): c for c in cells if c["mo"]["p"].get("lcrId") is not None}
    carriers = {c["earfcn"] for c in cells if c["earfcn"]}

    dl_on = b.get("actDLCAggr") == "true"
    ul_value = b.get("actULCAggr")
    ul_on = ul_value not in (None, "false")
    flex = b.get("actFlexScellSelect") == "true"
    descendants = _descendants(enb_dn, kids)

    # Finding targets: (tree node id, label) pairs the panel turns into
    # "show in tree" links.
    def lnbts_p(name: str) -> tuple[str, str]:
        return _pid(enb_dn, name), f"{_label(enb_dn)} · {name}"

    def cell_p(cell: dict, name: str, on_sub: bool = False) -> tuple[str, str]:
        mo = cell["sub"] if on_sub and cell["sub"] else cell["mo"]
        return _pid(mo["dn"], name), f"{_label(cell['mo']['dn'])} · {name}"

    def cell_t(cell: dict) -> tuple[str, str]:
        return cell["mo"]["dn"], _label(cell["mo"]["dn"])

    # Relations, resolved to cells. A CAREL's lcrId is the SCell's lcrId, not
    # its LNCEL instance number; lnBtsId says which eNB it lives on.
    relations = []
    scell_of: dict[str, list[dict]] = defaultdict(list)  # SCell dn -> PCells
    for cell in cells:
        for carel in cell["carels"]:
            lcr = carel["p"].get("lcrId")
            enb = carel["p"].get("lnBtsId") or own_id
            foreign = enb != own_id
            target = None if foreign else by_lcr.get(lcr)
            relations.append({"carel": carel, "pcell": cell, "scell": target, "lcrId": lcr, "lnBtsId": enb, "foreign": foreign})
            if target is not None and target is not cell:
                scell_of[target["mo"]["dn"]].append(cell)
    pcells = [c for c in cells if c["carels"]]

    # --- Switches -----------------------------------------------------------
    if not dl_on:
        needs_dl = [(n, v) for n, v in (
            ("actA3ScellSelect", b.get("actA3ScellSelect") == "true"),
            ("actInterEnbDLCAggr", b.get("actInterEnbDLCAggr") == "true"),
            ("actPcellSwap", b.get("actPcellSwap") == "true"),
            ("actULCAggr", ul_on),
        ) if v]
        blocking = [c for c in cells if c["mo"]["p"].get("actCaBlocking") == "true"]
        if needs_dl or blocking:
            names = [n for n, _ in needs_dl] + (["actCaBlocking"] if blocking else [])
            f.add("error", "official",
                  f"Downlink CA is off, but {', '.join(names)} needs it on",
                  "actDLCAggr must be true when any of these is set. Turn downlink CA on, or switch these off.",
                  [lnbts_p("actDLCAggr")] + [lnbts_p(n) for n, _ in needs_dl] + [cell_p(c, "actCaBlocking") for c in blocking],
                  ("actDLCAggr", "1.2"))
        elif pcells:
            f.add("warning", "general",
                  "CA relations exist, but downlink CA is switched off",
                  f"actDLCAggr is {b.get('actDLCAggr') or 'not set'}, so the eNB ignores the "
                  f"{len(relations)} CAREL relation{'s' if len(relations) != 1 else ''} below. "
                  "Set actDLCAggr to true to use them.",
                  [lnbts_p("actDLCAggr")])
    else:
        if b.get("actEnhAcAndGbrServices") != "true":
            f.add("error", "official",
                  "Downlink CA needs actEnhAcAndGbrServices on",
                  f"actDLCAggr can only be true when actEnhAcAndGbrServices is true; here it is "
                  f"{b.get('actEnhAcAndGbrServices') or 'not set'}. Every CA file in the corpus has it on. "
                  "Changing it needs a BTS restart.",
                  [lnbts_p("actEnhAcAndGbrServices")], ("actDLCAggr", "1.1"))
        cagenb = [m for m in kids[enb_dn] if m["cls"] == "CAGENB"]
        cadpr = [m for m in kids[enb_dn] if m["cls"] == "CADPR"]
        if not cagenb:
            f.add("error", "official", "No CAGENB object",
                  f"Downlink CA needs one CAGENB (CA settings for the whole eNB) under {_label(enb_dn)}.",
                  [(enb_dn, _label(enb_dn))], ("actDLCAggr", "1.3"))
        if len(cadpr) != 1:
            f.add("error", "official", "No CADPR object" if not cadpr else f"{len(cadpr)} CADPR objects",
                  f"Downlink CA needs exactly one CADPR (the default CA profile) under {_label(enb_dn)}.",
                  [(m["dn"], _label(m["dn"])) for m in cadpr] or [(enb_dn, _label(enb_dn))], ("actDLCAggr", "1.3"))
        lacking = [c for c in pcells if c["mo"]["p"].get("scellFastSchedulingSelect") is None]
        if lacking:
            f.add("error", "official", "PCell without scellFastSchedulingSelect",
                  "Every cell that has a CAREL (a PCell) must set scellFastSchedulingSelect.",
                  [cell_t(c) for c in lacking], ("actDLCAggr", "1.3"))
        if any(c["tech"] == "FDD" for c in cells) and b.get("caSchedFairFact") is None:
            f.add("error", "official", "caSchedFairFact is not set",
                  "With downlink CA on and FDD cells on this eNB, caSchedFairFact must be configured.",
                  [(enb_dn, _label(enb_dn))], ("actDLCAggr", "2.1.9"))
        if not relations:
            f.add("info", "files", "Downlink CA is on, but no cell has a CAREL relation",
                  "No SCell is defined in this file. Some exports run CA this way (an xL19A macro export in "
                  "the corpus does), presumably with SCells chosen automatically; that isn't confirmed.",
                  [lnbts_p("actDLCAggr")])
        missing_pool = [c for c in cells if c["mo"]["p"].get("caPoolId") is None]
        if missing_pool:
            f.add("warning", "official", "caPoolId is not set on every cell",
                  "The dictionary says every LNCEL needs a caPoolId when downlink CA is on. Exports that run CA "
                  "on air leave it out on every cell, so this rule may be out of date for newer releases. A "
                  "PCell and its SCells must still agree (see any pool mismatch below).",
                  [cell_t(c) for c in missing_pool],
                  ("actDLCAggr", "2.1.3" if any(c["tech"] == "FDD" for c in cells) else "3.1.3"))

    if b.get("actAdvUlScellHandling") == "true" and not ul_on:
        f.add("error", "official", "actAdvUlScellHandling needs uplink CA on",
              "actAdvUlScellHandling is true, so actULCAggr must not be false.",
              [lnbts_p("actAdvUlScellHandling"), lnbts_p("actULCAggr")], ("actULCAggr", "1.3"))
    if b.get("actInterEnbULCAggr") == "true" and not ul_on:
        f.add("error", "official", "actInterEnbULCAggr needs uplink CA on",
              "actInterEnbULCAggr is true, so actULCAggr must not be false.",
              [lnbts_p("actInterEnbULCAggr"), lnbts_p("actULCAggr")], ("actULCAggr", "1.2"))
    flex_gap = [c for c in cells if c["mo"]["p"].get("actFlexDupGap") == "true"]
    if ul_on and flex_gap:
        f.add("error", "official", "Uplink CA is on with a flexible duplexing gap",
              "actULCAggr must be false when actFlexDupGap is true on any cell.",
              [lnbts_p("actULCAggr")] + [cell_p(c, "actFlexDupGap") for c in flex_gap], ("actULCAggr", "2.4"))

    if len(cells) < 2:
        f.add("info", "general", "CA needs at least two cells",
              f"{_label(enb_dn)} has {len(cells)} cell{'s' if len(cells) != 1 else ''}. Intra-eNB CA pairs a "
              "PCell with an SCell on another carrier of the same eNB.",
              [(enb_dn, _label(enb_dn))])

    # --- Relations, per PCell ----------------------------------------------
    for cell in pcells:
        p = cell["mo"]["p"]
        name = _label(cell["mo"]["dn"])
        own_lcr = p.get("lcrId")
        tech = cell["tech"]
        prefix = "2.1" if tech == "FDD" else "3.1"
        mine = [r for r in relations if r["pcell"] is cell]
        seen: dict[tuple[str, str], dict] = {}
        for r in mine:
            carel_t = (_pid(r["carel"]["dn"], "lcrId"), f"{name}/{_label(r['carel']['dn'])} · lcrId")
            key = (r["lnBtsId"], r["lcrId"])
            if key == (own_id, own_lcr):
                f.add("error", "official", f"{name} has a CA relation to itself",
                      f"{_label(r['carel']['dn'])} points at lcrId {own_lcr}, which is {name}'s own lcrId.",
                      [carel_t], ("actDLCAggr", f"{prefix}.5"))
            elif key in seen:
                f.add("error", "official", f"{name} has two relations to the same SCell",
                      f"{_label(seen[key]['carel']['dn'])} and {_label(r['carel']['dn'])} both point at lcrId "
                      f"{r['lcrId']} on eNB {r['lnBtsId']}.",
                      [carel_t], ("actDLCAggr", f"{prefix}.5"))
            seen.setdefault(key, r)
            if r["foreign"]:
                f.add("info", "general", f"{name} has an SCell on another eNB",
                      f"{_label(r['carel']['dn'])} points at lcrId {r['lcrId']} on eNB {r['lnBtsId']} (this one "
                      f"is {own_id}). That's inter-eNB CA (actInterEnbDLCAggr is "
                      f"{b.get('actInterEnbDLCAggr') or 'not set'}); the SCell can't be checked from this file.",
                      [carel_t])
            elif r["scell"] is None and key != (own_id, own_lcr):
                f.add("error", "official", f"{name} points at a cell that doesn't exist",
                      f"{_label(r['carel']['dn'])} points at lcrId {r['lcrId']}, but no LNCEL on this eNB has that "
                      "lcrId. A CAREL's lcrId is the SCell's lcrId, not its LNCEL number.",
                      [carel_t], ("actDLCAggr", f"{prefix}.6"))
            elif r["scell"] is not None and r["scell"] is not cell and r["scell"]["earfcn"] == cell["earfcn"]:
                f.add("error", "official", f"{name}'s SCell is on its own carrier",
                      f"{_label(r['scell']['mo']['dn'])} uses EARFCN {cell['earfcn']}, the same as {name}. An SCell "
                      "must be on a different carrier.",
                      [carel_t, cell_t(r["scell"])], ("actDLCAggr", f"{prefix}.1.0"))

        targets = [r["scell"] for r in mine if r["scell"] is not None and r["scell"] is not cell]
        per_carrier: dict[str, list[dict]] = defaultdict(list)
        for t in targets:
            per_carrier[t["earfcn"]].append(t)
        other_carriers = [c for c in per_carrier if c != cell["earfcn"]]
        if flex:
            limit_total = 5 if tech == "TDD" else None
            limit_layer = 5 if tech == "TDD" else 6
            limit_carriers = 5 if tech == "TDD" else 6
            sub_rule = "2"
        else:
            limit_total, limit_layer, limit_carriers, sub_rule = 2, 1, 2, "1"
        flex_note = "with" if flex else "without"
        if limit_total is not None and len(mine) > limit_total:
            f.add("error", "official", f"{name} has {len(mine)} CA relations",
                  f"At most {limit_total} CAREL per PCell {flex_note} flexible SCell selection (actFlexScellSelect).",
                  [cell_t(cell)], ("actDLCAggr", f"{prefix}.{sub_rule}.{'2' if not flex else '3'}"))
        for carrier, ts in per_carrier.items():
            if len(ts) > limit_layer:
                f.add("error", "official", f"{name} has {len(ts)} SCells on EARFCN {carrier}",
                      f"At most {limit_layer} SCell per carrier {flex_note} flexible SCell selection.",
                      [cell_t(t) for t in ts], ("actDLCAggr", f"{prefix}.{sub_rule}.1"))
            if flex and len({t["bandwidth"] for t in ts}) > 1:
                f.add("error", "official", f"{name}'s SCells on EARFCN {carrier} differ in bandwidth",
                      "SCells of one PCell on the same carrier must have the same bandwidth.",
                      [cell_t(t) for t in ts], ("actDLCAggr", f"{prefix}.2.2"))
        if len(other_carriers) > limit_carriers:
            f.add("error", "official", f"{name}'s SCells span {len(other_carriers)} carriers",
                  f"At most {limit_carriers} SCell carriers per PCell {flex_note} flexible SCell selection.",
                  [cell_t(cell)], ("actDLCAggr", f"{prefix}.{sub_rule}.0"))
        if tech == "FDD" and cell["bandwidth"] in ("1.4 MHz", "3 MHz"):
            f.add("error", "official", f"{name} is too narrow to be a PCell",
                  f"A {cell['bandwidth']} FDD cell can't have CAREL relations.",
                  [cell_t(cell)], ("actDLCAggr", "2.1.11.2"))

        # PCell and SCell must agree on these.
        for scell in {t["mo"]["dn"]: t for t in targets}.values():
            sname = _label(scell["mo"]["dn"])
            pair = f"{name} and its SCell {sname}"
            p_pool, s_pool = cell["mo"]["p"].get("caPoolId"), scell["mo"]["p"].get("caPoolId")
            if p_pool != s_pool:
                if p_pool is not None and s_pool is not None:
                    detail = f"{name} has caPoolId {p_pool} and {sname} has {s_pool}."
                elif p_pool is not None:
                    detail = f"{name} has caPoolId {p_pool}; {sname} has none."
                else:
                    detail = f"{sname} has caPoolId {s_pool}; {name} has none."
                f.add("error", "official", f"{pair} are in different CA pools",
                      detail + " A PCell and its SCells must have the same caPoolId.",
                      [cell_p(cell, "caPoolId"), cell_p(scell, "caPoolId")], ("actDLCAggr", f"{prefix}.7.1"))
            for flag in ("rcEnableDl", "rcEnableUl"):
                if cell["mo"]["p"].get(flag) != scell["mo"]["p"].get(flag):
                    f.add("error", "official", f"{pair} differ in {flag}",
                          f"{name}: {cell['mo']['p'].get(flag)}, {sname}: {scell['mo']['p'].get(flag)}. "
                          "They must match.",
                          [cell_p(cell, flag), cell_p(scell, flag)],
                          ("actDLCAggr", "2.1.8" if tech == "FDD" else "3.1.7"))
            pa = cell["sub"]["p"].get("actAutoPucchAlloc") if cell["sub"] else None
            sa = scell["sub"]["p"].get("actAutoPucchAlloc") if scell["sub"] else None
            if pa != sa:
                f.add("error", "official", f"{pair} differ in actAutoPucchAlloc",
                      f"{name}: {pa}, {sname}: {sa}. They must match.",
                      [cell_p(cell, "actAutoPucchAlloc", True), cell_p(scell, "actAutoPucchAlloc", True)],
                      ("actDLCAggr", "2.1.10" if tech == "FDD" else "3.1.8"))
            if cell["tech"] == "TDD" and scell["tech"] == "TDD" and cell["sub"] and scell["sub"]:
                for conf, rule_param, same_band_only in (("tddFrameConf", "tddFrameConf", False),
                                                         ("tddSpecSubfConf", "tddSpecSubfConf", True)):
                    if same_band_only and cell["band"] != scell["band"]:
                        continue
                    pv, sv = cell["sub"]["p"].get(conf), scell["sub"]["p"].get(conf)
                    if pv != sv:
                        f.add("error", "official", f"{pair} use different TDD {'special subframes' if same_band_only else 'frame configs'}",
                              f"{name}: {conf} {pv}, {sname}: {sv}. A PCell and its SCells must use the same "
                              f"{conf}{' when they are in the same band' if same_band_only else ''}.",
                              [cell_p(cell, conf, True), cell_p(scell, conf, True)], (rule_param, None))

        # PUCCH sizing, checked only when PUCCH isn't allocated automatically.
        sub = cell["sub"]
        pucch = cell["pucch"]
        if dl_on and sub and pucch and sub["p"].get("actAutoPucchAlloc") == "false":
            pp = pucch["p"]

            def pucch_t(param: str) -> tuple[str, str]:
                return _pid(pucch["dn"], param), f"{name} · {param}"

            n_carel = len(mine)
            max_scells = _int(p.get("maxNumScells")) or 1
            n1 = _int(pp.get("n1PucchAn"))
            f3 = _int(pp.get("nPucchF3Prbs"))
            ncqi = _int(pp.get("nCqiRb"))
            r = "2.1.12" if tech == "FDD" else "3.2"
            if n1 is not None and (n_carel == 1 or max_scells > 1) and not (n1 == 10 or n1 >= 72):
                f.add("error", "official", f"{name}'s n1PucchAn is too small for CA",
                      f"n1PucchAn is {n1}; with {n_carel} CAREL and maxNumScells {max_scells} it must be 10 or at least 72.",
                      [pucch_t("n1PucchAn")], ("actDLCAggr", f"{r}.5" if tech == "FDD" else f"{r}.1"))
            elif n1 is not None and n_carel >= 2 and max_scells == 1 and n1 < 72:
                f.add("error", "official", f"{name}'s n1PucchAn is too small for CA",
                      f"n1PucchAn is {n1}; with {n_carel} CAREL relations and maxNumScells 1 it must be at least 72.",
                      [pucch_t("n1PucchAn")], ("actDLCAggr", f"{r}.6" if tech == "FDD" else f"{r}.2"))
            if f3 is not None and max_scells > 1 and f3 <= 0:
                f.add("error", "official", f"{name} has no PUCCH format 3 PRBs",
                      f"maxNumScells is {max_scells}, so nPucchF3Prbs must be above 0.",
                      [pucch_t("nPucchF3Prbs")], ("actDLCAggr", f"{r}.1" if tech == "FDD" else f"{r}.3"))
            if tech == "FDD" and f3 is not None and max_scells <= 1 and f3 != 0:
                f.add("error", "official", f"{name} reserves PUCCH format 3 PRBs it can't use",
                      f"maxNumScells is {max_scells}, so nPucchF3Prbs must be 0 (it is {f3}).",
                      [pucch_t("nPucchF3Prbs")], ("actDLCAggr", "2.1.12.2"))
            if ncqi is not None and f3 is not None:
                blanked = (_int(sub["p"].get("blankedPucch")) or 0) if tech == "FDD" else 0
                if ncqi <= f3 + blanked:
                    f.add("error", "official", f"{name}'s nCqiRb is too small",
                          f"nCqiRb ({ncqi}) must be greater than nPucchF3Prbs ({f3})"
                          + (f" plus blankedPucch ({blanked})." if tech == "FDD" else "."),
                          [pucch_t("nCqiRb")], ("actDLCAggr", "2.1.12.3" if tech == "FDD" else "3.2.4"))
            if tech == "FDD" and (_int(pp.get("deltaPucchShift")) or 0) > 2:
                f.add("error", "official", f"{name}'s deltaPucchShift is above 2",
                      f"deltaPucchShift is {pp.get('deltaPucchShift')}; for a PCell it must be 2 or less.",
                      [pucch_t("deltaPucchShift")], ("actDLCAggr", "2.1.12.7"))
            if tech == "TDD" and n1 is not None and (_int(sub["p"].get("maxNumCaConfUe")) or 0) > 100 and n1 < 144:
                f.add("error", "official", f"{name}'s n1PucchAn is too small for its CA load",
                      f"maxNumCaConfUe is {sub['p'].get('maxNumCaConfUe')}, so n1PucchAn must be at least 144 (it is {n1}).",
                      [pucch_t("n1PucchAn"), cell_p(cell, "maxNumCaConfUe", True)], ("actDLCAggr", "3.1.10"))

        # Admission limits for CA UEs on the PCell.
        if dl_on and sub:
            sub_p = sub["p"]
            conf, act = _int(sub_p.get("maxNumCaConfUe")), _int(sub_p.get("maxNumActUE"))
            dc, c3 = _int(sub_p.get("maxNumCaConfUeDc")), _int(sub_p.get("maxNumCaConfUe3c"))
            if conf is not None and act is not None and act < conf:
                f.add("error", "official", f"{name} admits more CA UEs than UEs",
                      f"maxNumActUE ({act}) must be at least maxNumCaConfUe ({conf}).",
                      [cell_p(cell, "maxNumCaConfUe", True), cell_p(cell, "maxNumActUE", True)], ("maxNumCaConfUe", None))
            if conf is not None and max(dc or 0, c3 or 0) > conf:
                f.add("error", "official", f"{name}'s CA UE limits don't nest",
                      f"maxNumCaConfUeDc ({dc}) and maxNumCaConfUe3c ({c3}) must not exceed maxNumCaConfUe ({conf}).",
                      [cell_p(cell, "maxNumCaConfUe", True)], ("maxNumCaConfUe", None))

        # CAPR is a per-carrier CA profile. In the corpus a PCell's CAPR always
        # covers its SCells' carriers; one left on the PCell's own carrier
        # after a frequency change is a stale leftover.
        if cell["caprs"]:
            capr_carriers = {m["p"].get("earfcnDL") for m in cell["caprs"]}
            scell_carriers = {t["earfcn"] for t in targets if t["earfcn"]}
            for capr in cell["caprs"]:
                e = capr["p"].get("earfcnDL")
                if e is not None and e not in carriers:
                    f.add("warning", "files", f"{name}'s {_label(capr['dn'])} points at an unused carrier",
                          f"Its earfcnDL is {e}, but no cell on this eNB uses that carrier. It was probably left "
                          "over from an earlier frequency plan.",
                          [(_pid(capr["dn"], "earfcnDL"), f"{name}/{_label(capr['dn'])} · earfcnDL")])
            uncovered = sorted(scell_carriers - capr_carriers)
            own = [m for m in cell["caprs"] if m["p"].get("earfcnDL") == cell["earfcn"]]
            if uncovered and own:
                f.add("warning", "files", f"{name}'s CA profile targets its own carrier",
                      f"{_label(own[0]['dn'])} has earfcnDL {cell['earfcn']}, {name}'s own carrier, and no CAPR covers "
                      f"its SCell carrier {', '.join(uncovered)}. In the corpus's CA files a PCell's CAPR points at "
                      "the SCell's carrier, so this looks left over from an earlier frequency plan.",
                      [(_pid(own[0]["dn"], "earfcnDL"), f"{name}/{_label(own[0]['dn'])} · earfcnDL")])

    # --- Cells in CA: settings learned from the corpus -----------------------
    for cell in cells:
        dn = cell["mo"]["dn"]
        name = _label(dn)
        pcells_here = scell_of.get(dn, [])
        if not cell["carels"] and not pcells_here:
            continue
        cbsd = cell["cbsdcel"]
        if cbsd and cell["tech"] == "TDD" and cell["sub"]:
            actual = (cell["sub"]["p"].get("tddFrameConf"), cell["sub"]["p"].get("tddSpecSubfConf"))
            for prefix in ("desired", "fallB"):
                wanted = (cbsd["p"].get(f"{prefix}TddFrameConf"), cbsd["p"].get(f"{prefix}TddSpecSubfConf"))
                if wanted[0] is not None and wanted != actual:
                    kind = "requested" if prefix == "desired" else "fallback"
                    f.add("warning", "files", f"{name}'s CBRS {kind} TDD config doesn't match the cell",
                          f"CBSDCEL asks for {wanted[0]}/{wanted[1]} ({prefix}TddFrameConf/{prefix}TddSpecSubfConf), but "
                          f"the cell runs {actual[0]}/{actual[1]}. Everywhere else in the corpus the two match. If the "
                          "granted config follows CBSDCEL, the PCell and SCell would run different TDD configs and CA "
                          "can't work.",
                          [(_pid(cbsd["dn"], f"{prefix}TddFrameConf"), f"{name} · {prefix}TddFrameConf"),
                           cell_p(cell, "tddFrameConf", True)])
        if pcells_here:
            rank = _MODULATION_RANK.get(cell["mo"]["p"].get("actModulationSchemeDl") or "")
            best = max(pcells_here, key=lambda c: _MODULATION_RANK.get(c["mo"]["p"].get("actModulationSchemeDl") or "", -1))
            best_rank = _MODULATION_RANK.get(best["mo"]["p"].get("actModulationSchemeDl") or "")
            if rank is not None and best_rank is not None and rank < best_rank:
                f.add("warning", "files", f"SCell {name} is capped at {cell['mo']['p'].get('actModulationSchemeDl')}",
                      f"Its PCell {_label(best['mo']['dn'])} allows {best['mo']['p'].get('actModulationSchemeDl')}. "
                      "Downlink is all an SCell adds, so a lower cap limits what CA gains.",
                      [cell_p(cell, "actModulationSchemeDl"), cell_p(best, "actModulationSchemeDl")])
            if not cell["carels"] and cell["sib"] and cell["sib"]["p"].get("cellBarred") != "barred":
                sib = cell["sib"]
                f.add("info", "files", f"Phones that camp on {name} get no CA",
                      f"{name} is only ever an SCell (it has no CAREL of its own) but isn't barred, so phones can "
                      f"camp on it (cellReSelPrio {sib['p'].get('cellReSelPrio')}) and use it without CA. Bar it to "
                      "serve CA only, or give it a relation back. Both setups occur in working files.",
                      [(_pid(sib["dn"], "cellBarred"), f"{name} · cellBarred"),
                       (_pid(sib["dn"], "cellReSelPrio"), f"{name} · cellReSelPrio")])

    # CA-aware idle-mode load balancing lists carriers in CAIMLBP/CAIMLBS
    # tables; entries no cell uses are leftovers, harmless while it's off.
    idle_lb_on = b.get("actIdleLBCaAwareAdv") == "true"
    for mo in (m for m in descendants if m["cls"] in ("CAIMLBP", "CAIMLBS")):
        for list_name, items in mo["lists"].items():
            for i, item in enumerate(items):
                e = item.get("earfcnDL")
                if e is not None and e not in carriers:
                    f.add("warning" if idle_lb_on else "info", "files",
                          f"{_label(mo['dn'])} lists a carrier no cell uses",
                          f"{list_name} row {i + 1} has earfcnDL {e}, but no cell on this eNB uses that carrier. "
                          + ("CA-aware idle-mode load balancing (actIdleLBCaAwareAdv) is on, so this entry matters."
                             if idle_lb_on else
                             "actIdleLBCaAwareAdv is off, so it has no effect today; it was probably left over "
                             "from an earlier frequency plan."),
                          [(_item_pid(mo["dn"], list_name, i, "earfcnDL"), f"{_label(mo['dn'])} · {list_name} row {i + 1}")])

    roles = {}
    for cell in cells:
        is_p, is_s = bool(cell["carels"]), cell["mo"]["dn"] in scell_of
        roles[cell["mo"]["dn"]] = "both" if is_p and is_s else "pcell" if is_p else "scell" if is_s else "none"

    order = {"error": 0, "warning": 1, "info": 2}
    findings = sorted(f.items, key=lambda x: order[x["severity"]])
    return {
        "id": enb_dn,
        "label": _label(enb_dn),
        "lnBtsId": own_id,
        "version": lnbts["version"],
        "dl": dl_on,
        "ul": ul_value,
        "ulOn": ul_on,
        "flexScellSelect": flex,
        "supportedCellTechnology": b.get("supportedCellTechnology"),
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
            "caPoolId": c["mo"]["p"].get("caPoolId"),
            "modulationDl": c["mo"]["p"].get("actModulationSchemeDl"),
            "barred": (c["sib"]["p"].get("cellBarred") == "barred") if c["sib"] else None,
            "reselPrio": c["sib"]["p"].get("cellReSelPrio") if c["sib"] else None,
            "cbrs": c["cbsdcel"] is not None,
            "role": roles[c["mo"]["dn"]],
        } for c in cells],
        "relations": [{
            "id": r["carel"]["dn"],
            "label": _label(r["carel"]["dn"]),
            "pcell": r["pcell"]["mo"]["dn"],
            "scell": r["scell"]["mo"]["dn"] if r["scell"] else None,
            "lcrId": r["lcrId"],
            "lnBtsId": r["lnBtsId"],
            "foreign": r["foreign"],
            "scellPrio": r["carel"]["p"].get("scellPrio"),
            "mimoLayers": r["carel"]["p"].get("maxNumOfSuppMimoLayer"),
        } for r in relations],
        "caObjects": [
            {"class": cls, "ids": ids}
            for cls in _CA_CLASSES
            if (ids := sorted(m["dn"] for m in descendants if m["cls"] == cls))
        ],
        "findings": findings,
    }


def _descendants(dn: str, kids: dict[str, list[dict]]) -> list[dict]:
    out, stack = [], list(kids[dn])
    while stack:
        mo = stack.pop()
        out.append(mo)
        stack.extend(kids[mo["dn"]])
    return out


def analyze_ca(raw_bytes: bytes) -> dict:
    """The CA setup and findings for every LNBTS in the file. `summary.state`
    is "none" (no LTE eNB), "off" or "on" (downlink CA on for some eNB)."""
    mos = _load(raw_bytes)
    kids: dict[str, list[dict]] = defaultdict(list)
    for mo in mos:
        kids[_parent(mo["dn"])].append(mo)
    enbs = [_analyze_enb(mo, kids) for mo in mos if mo["cls"] == "LNBTS"]
    counts = {"error": 0, "warning": 0, "info": 0}
    for enb in enbs:
        for finding in enb["findings"]:
            counts[finding["severity"]] += 1
    return {
        "enbs": enbs,
        "summary": {
            "state": "none" if not enbs else "on" if any(e["dl"] for e in enbs) else "off",
            "ul": any(e["ulOn"] for e in enbs),
            "errors": counts["error"],
            "warnings": counts["warning"],
            "infos": counts["info"],
        },
    }

"""
Add a PLMN for RAN sharing: a further PLMN on LTE cells, or a PLMN on a
gNB.

LTE: each cell's furtherPlmnIdL gets a row (mcc, mnc, mncLength,
cellReserve, autoRemovalAllowed); the eNB's primary PLMN stays LNBTS
mcc/mnc. The dictionary's rules (LNCEL furtherPlmnIdL) are checked: not
on a CSG cell (1.1), at most 7 different further PLMNs on the eNB (1.2),
and the row limits of 1.4, 3 and 5 MHz cells by maxCrSibDl (2.x).

5G: an NRPLMN (mcc, mnc, mncLength) under the NRBTS, added to the cells'
PLMN sets (NRPLMNSET_SA, NRPLMNSET_NSA, where the cells have them: one
set per cell listing its PLMNs in all 130 production cells), to the
slices offered in it (193 of 205 slices in the files this was built from
list all their gNB's PLMNs) and to the resource-group profile's default
lists, with the group the first PLMN uses. At most 12 PLMNs: TS 38.331
maxPLMN, read from the ETSI PDF of V17.6.0 when this was built.

The files write mcc and mnc without leading zeros and mncLength for the
MNC's digits (001-01 is mcc 1, mnc 1, mncLength 2). Noted: an MME or AMF
that reported its PLMNs (LNMME accMmePlmnsList, SERVEDAMF guAMI) without
the new one.
"""
from __future__ import annotations

import re
from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, label, why
from .links import Site, _runtime

ID = "plmn"
TITLE = "Add a PLMN"
GROUP = "Core network"
SUMMARY = "Another operator's PLMN on the cells of an eNB or a gNB (RAN sharing), with its slices and sets."
UI = "form"
KEYWORDS = "PLMN MCC MNC RAN sharing MOCN further PLMN furtherPlmnIdL NRPLMN NRPLMNSET operator"

MAX_NR = 12
NOT_RESERVED, RESERVED = "Not Reserved", "Reserved"
# 2.x of LNCEL furtherPlmnIdL: (maxCrSibDl bound, rows allowed), first bound the value is below.
NARROW = {"a": [(0.075, 0), (0.085, 2), (0.095, 3), (99, 5)],
          "b": [(0.19, 1), (0.21, 2), (0.23, 3), (0.26, 4), (99, 5)]}


def _enbs(site: Site) -> list[dict]:
    return [m for m in site.of("LNBTS") if not _runtime(m["dn"])]


def _gnbs(site: Site) -> list[dict]:
    return [m for m in site.of("NRBTS") if not _runtime(m["dn"])]


def _plmn(p: dict) -> tuple[str, str, str]:
    return str(int(p.get("mcc") or 0)), str(int(p.get("mnc") or 0)), str(p.get("mncLength") or "2")


def _text(mcc: str, mnc: str, length: str) -> str:
    return f"{int(mcc):03d}-{int(mnc):0{int(length)}d}"


def _parse(mcc: str, mnc: str) -> tuple[Optional[tuple[str, str, str]], list[str]]:
    mcc, mnc = (mcc or "").strip(), (mnc or "").strip()
    out = []
    if not re.fullmatch(r"\d{3}", mcc):
        out.append(f"{mcc!r} isn't an MCC: three digits (001 for a test network)." if mcc else "Enter the MCC.")
    if not re.fullmatch(r"\d{2,3}", mnc):
        out.append(f"{mnc!r} isn't an MNC: two or three digits, as the operator writes it (01 and 001 are two "
                   "different MNCs)." if mnc else "Enter the MNC.")
    if out:
        return None, out
    return (str(int(mcc)), str(int(mnc)), str(len(mnc))), []


def available(ctx: Context) -> Optional[str]:
    if _gnbs(ctx.site) or any(ctx.site.child(e["dn"], "LNCEL") for e in _enbs(ctx.site)):
        return None
    return "This file has no eNB with cells and no gNB."


def setup(ctx: Context) -> dict:
    site = ctx.site
    targets, cells, slices, reserve = [], {}, {}, {}
    for e in _enbs(site):
        mine = site.child(e["dn"], "LNCEL")
        if not mine:
            continue
        further = sorted({_text(*_plmn(r)) for c in mine for r in c["lists"].get("furtherPlmnIdL", [])})
        targets.append({"value": e["dn"], "key": e["dn"], "group": "LTE eNB: a further PLMN in its cells",
                        "label": f"{label(e['dn'])} · {_text(*_plmn(e['p']))}"
                                 + (f" + {', '.join(further)}" if further else "")})
        cells[e["dn"]] = [{"value": c["dn"], "label": label(c["dn"])} for c in mine]
        rows = [r for c in mine for r in c["lists"].get("furtherPlmnIdL", [])]
        reserve[e["dn"]] = rows[0].get("cellReserve") if rows else NOT_RESERVED
    for g in _gnbs(site):
        plmns = [_text(*_plmn(p["p"])) for p in site.child(g["dn"], "NRPLMN")]
        targets.append({"value": g["dn"], "key": g["dn"], "group": "5G gNB",
                        "label": f"{label(g['dn'])} · {', '.join(plmns) or 'no NRPLMN'}"})
        cells[g["dn"]] = [{"value": c["dn"], "label": label(c["dn"])} for c in site.child(g["dn"], "NRCELL")
                          if site.child(c["dn"], "NRPLMNSET_SA") or site.child(c["dn"], "NRPLMNSET_NSA")]
        slices[g["dn"]] = [{"value": s["dn"], "label": f"{label(s['dn'])} · SST {s['p'].get('sst')}"
                            + (f" SD {s['p']['sd']}" if s["p"].get("sd") else "")}
                           for s in site.child(g["dn"], "SNSSAI")]
        reserve[g["dn"]] = NOT_RESERVED
    return {
        "intro": "Adds another operator's PLMN to the cells of an eNB, or to a gNB. The core network must serve it "
                 "too.",
        "fields": [
            {"id": "target", "label": "On", "type": "select", "options": targets,
             "default": targets[0]["value"] if len(targets) == 1 else None},
            {"id": "mcc", "label": "MCC", "type": "text", "placeholder": "310"},
            {"id": "mnc", "label": "MNC", "type": "text", "placeholder": "410 or 41",
             "hint": "As the operator writes it: its digits give the MNC length."},
            {"id": "cells", "label": "Cells", "type": "checks", "dependsOn": "target", "optionsByKey": cells,
             "hint": "On a gNB, the cells whose PLMN sets list it."},
            {"id": "slices", "label": "Slices offered in it", "type": "checks", "dependsOn": "target",
             "optionsByKey": slices},
            {"id": "reserved", "label": "Reserved for operator use", "type": "select", "dependsOn": "target",
             "options": [{"value": NOT_RESERVED, "label": "Not reserved"},
                         {"value": RESERVED, "label": "Reserved (only the operator's access classes 11 and 15)"}],
             "defaultByKey": reserve},
        ],
    }


def _num(v: Optional[str]) -> Optional[float]:
    try:
        return float(re.sub(r"[^0-9.]", "", v or "") or "x")
    except ValueError:
        return None


def _narrow_limit(site: Site, cell: dict) -> Optional[tuple[int, str]]:
    """Rows furtherPlmnIdL may hold on a 1.4, 3 or 5 MHz FDD cell (2.x)."""
    if (cell["p"].get("cellTechnology") or "FDD") != "FDD":
        return None
    fdd = next(iter(site.child(cell["dn"], "LNCEL_FDD")), None)
    if not fdd:
        return None
    bw = _num(fdd["p"].get("dlChBw"))
    blank = sum(int(_num(fdd["p"].get(k)) or 0) for k in ("numBlankDlPrbsUp", "numBlankDlPrbsDown"))
    slim = fdd["p"].get("actDlSlimCarrier") == "true" and blank > 0
    case = "a" if (bw == 3 and not slim) or (bw == 5 and slim) else "b" if bw == 1.4 or (slim and bw == 3) else None
    if not case:
        return None
    cr = _num(cell["p"].get("maxCrSibDl") or "0.26")
    if cr is None:
        return None
    # The files write it in hundredths ("26" for the dictionary's 0.26, its default).
    cr = cr / 100 if cr > 1 else cr
    allowed = next(n for bound, n in NARROW[case] if cr < bound)
    return allowed, f"a {fdd['p'].get('dlChBw')} cell with maxCrSibDl {cr:.2f}"


def _plan_lte(ctx, doc, enb, plmn, cells, reserved, notes, problems, w):
    site = ctx.site
    if plmn == _plmn(enb["p"]):
        problems.append(f"{_text(*plmn)} is {label(enb['dn'])}'s primary PLMN already.")
        return
    further = {_plmn(r) for c in site.child(enb["dn"], "LNCEL") for r in c["lists"].get("furtherPlmnIdL", [])}
    if plmn not in further and len(further) >= 7:
        problems.append(f"{label(enb['dn'])}'s cells already have 7 different further PLMNs, the most the dictionary "
                        "allows on one eNB (LNCEL furtherPlmnIdL 1.2).")
    todo = []
    for dn in cells:
        c = site.by_dn[dn]
        rows = c["lists"].get("furtherPlmnIdL", [])
        if any(_plmn(r) == plmn for r in rows):
            continue
        if c["p"].get("csgType") == "CSG":
            problems.append(f"{label(dn)} is a CSG cell: the dictionary allows it no further PLMN (1.1).")
            continue
        lim = _narrow_limit(site, c)
        if lim and len(rows) + 1 > lim[0]:
            problems.append(f"{label(dn)} is {lim[1]}: it may list {lim[0]} further PLMN"
                            f"{'s' if lim[0] != 1 else ''} (LNCEL furtherPlmnIdL 2.x). Raise maxCrSibDl or leave the "
                            "cell out.")
            continue
        todo.append(dn)
    if not todo and not problems:
        problems.append(f"Every picked cell already has {_text(*plmn)}.")
    if problems:
        return
    for dn in todo:
        rows = site.by_dn[dn]["lists"].get("furtherPlmnIdL", [])
        auto = rows[0].get("autoRemovalAllowed") if rows else "false"
        doc.add_item(dn, "furtherPlmnIdL", [("autoRemovalAllowed", auto or "false"), ("cellReserve", reserved),
                                            ("mcc", plmn[0]), ("mnc", plmn[1]), ("mncLength", plmn[2])],
                     w(f"{_text(*plmn)} in SIB1. autoRemovalAllowed {auto or 'false'}"
                       + (", as the cell's other further PLMNs." if rows else ", the dictionary's default.")))
    served = [m for m in site.of("LNMME", enb["dn"]) if m["lists"].get("accMmePlmnsList")]
    if served and not any(_plmn(r) == plmn for m in served for r in m["lists"]["accMmePlmnsList"]):
        notes.append(f"The MMEs report the PLMNs they serve (accMmePlmnsList), and {_text(*plmn)} isn't among "
                     "them: its UEs can't attach until an MME serves it.")
    return todo


def _plan_nr(ctx, doc, gnb, plmn, cells, slices, reserved, notes, problems, w):
    site = ctx.site
    g = gnb["dn"]
    have = site.child(g, "NRPLMN")
    if any(_plmn(p["p"]) == plmn for p in have):
        problems.append(f"{label(g)} already has {_text(*plmn)}.")
    if len(have) + 1 > MAX_NR:
        problems.append(f"{label(g)} has {len(have)} PLMNs; a cell broadcasts at most {MAX_NR} (TS 38.331 maxPLMN).")
    if problems:
        return
    dn = doc.create(g, "NRPLMN", doc.next_free(g, "NRPLMN"), [("mcc", plmn[0]), ("mnc", plmn[1]),
                                                             ("mncLength", plmn[2])],
                    w=w(f"The PLMN {_text(*plmn)}; mcc and mnc without leading zeros, as the files write them."))
    for c in cells:
        for cls in ("NRPLMNSET_SA", "NRPLMNSET_NSA"):
            for s in site.child(c, cls):
                doc.add_value(s["dn"], "nrPlmnDNList", dn, w(f"{label(c)} broadcasts {_text(*plmn)} with the set's "
                                                              "tracking area."))
                if reserved == RESERVED and s["p"].get("cellReservedForOperatorUse") != "reserved":
                    notes.append(f"{label(s['dn'])} is notReserved for every PLMN it lists: cellReservedForOperatorUse "
                                 "is per set, so a reserved PLMN needs a set of its own.")
    for s in slices:
        doc.add_value(s, "nrPlmnDNList", dn, w(f"The slice is offered in {_text(*plmn)}."))
    for prof in site.child(g, "NRRESOURCEGROUP_PROFILE"):
        for ln in ("defaultRgSaList", "defaultRgNsaList"):
            rows = prof["lists"].get(ln, [])
            if rows and "nrResourceGroupId" in rows[0]:
                doc.add_item(prof["dn"], ln, [("nrPlmnDN", dn), ("nrResourceGroupId", rows[0]["nrResourceGroupId"])],
                             w(f"{_text(*plmn)} uses the default resource group of {label(rows[0].get('nrPlmnDN') or '')}."))
    amfs = [a for a in site.of("SERVEDAMF", g) if a["lists"].get("guAMI")]
    if amfs and not any(_plmn(r) == plmn for a in amfs for r in a["lists"]["guAMI"]):
        notes.append(f"The AMFs report the PLMNs they serve (guAMI), and {_text(*plmn)} isn't among them: its UEs "
                     "can't register until an AMF serves it.")
    return dn


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    target = site.by_dn.get(inputs.get("target") or "")
    if not target or target["cls"] not in ("LNBTS", "NRBTS"):
        raise PlanError(["Pick the eNB or gNB."])
    plmn, problems = _parse(inputs.get("mcc"), inputs.get("mnc"))
    if problems:
        raise PlanError(problems)
    reserved = inputs.get("reserved") if inputs.get("reserved") in (NOT_RESERVED, RESERVED) else NOT_RESERVED
    own = "LNCEL" if target["cls"] == "LNBTS" else "NRCELL"
    cells = [c for c in (inputs.get("cells") or []) if site.by_dn.get(c, {}).get("cls") == own
             and c.startswith(target["dn"] + "/")]
    notes = []
    doc = Doc(ctx.raw)
    w = lambda reason, basis="choice": why("plmn", reason, basis)
    if target["cls"] == "LNBTS":
        if not cells:
            raise PlanError(["Tick the cells to broadcast it in."])
        done = _plan_lte(ctx, doc, target, plmn, cells, reserved, notes, problems, w)
        focus, summary = None, f"{_text(*plmn)} on {len(done or [])} cell{'s' if len(done or []) != 1 else ''} of {label(target['dn'])}"
    else:
        slices = [s for s in (inputs.get("slices") or []) if site.by_dn.get(s, {}).get("cls") == "SNSSAI"]
        focus = _plan_nr(ctx, doc, target, plmn, cells, slices, reserved, notes, problems, w)
        summary = f"{_text(*plmn)} on {label(target['dn'])}"
        if reserved == RESERVED and not cells:
            notes.append("Reserved for operator use is set per cell PLMN set; this gNB's cells have none, so it isn't "
                         "written.")
    if problems:
        raise PlanError(problems)
    return finish(ctx, doc, {
        "label": f"PLMN {_text(*plmn)}",
        "summary": summary,
        "notes": notes,
        "confirm": [f"The core network serves {_text(*plmn)} (an MME or AMF that accepts it), and the sharing "
                    "agreement covers these cells."],
        "focus": focus,
    })

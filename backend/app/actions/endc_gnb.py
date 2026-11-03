"""
Add a 5G gNB to an LTE eNB for EN-DC (NSA, option 3X): an LNADJGNB for the
X2 link to the gNB, and an LNRELGNBCELL from each chosen LTE cell to each
chosen NR cell.

The gNB comes from another site's file in the tool (its id, id length,
PLMN, X2 C-plane address and cells, from sites.summary) or is typed in.
Running it again for the same gNB adds what is missing.

What is written (the dictionary, LTE18; the corpus is the owner's DHI lab,
19 eNBs with an LNADJGNB, and one site with 22 UE-learned relations):
  - LNADJGNB: administrativeState unlocked, cPlaneIpAddr, cPlaneIpAddrCtrl
    oamControlled, the Mandatory set with its defaults. adjGnbId,
    adjGnbIdLength and plmnId are "Value set by the system" in LTE18, but
    the xL25R2 files write them, so they are written where some file of the
    eNB's release does (the release index). Ids 0-31, lowest free.
  - LNRELGNBCELL: gnbIdLength, lteNrDualConnectAllowed allowed, nrCellId,
    removeAllowed true (the default, and every relation in the tool that
    sets it), and nrCgiPlmnId as a row (all 33 relations in the tool; none
    writes the scalar mcc/mnc). nrCellId is the NCI: gNB id shifted left
    by 36 - gnbIdLength, plus the cell's lcrId. nrStatus and sourceOfData
    are set by the system. Ids 0-255, lowest free; the NR-CGI must differ
    from the cell's other relations (nrCellId rule), so an existing one is
    skipped.
  - Relations are optional: UE-based ANR learns them once X2 is up (22 of
    the 33 in the tool were learned that way).
EN-DC itself (actLteNrDualConnectivity, LTE4088) isn't switched on here;
when it is off, a note says what turning it on needs (its rule 1.2).
"""
from __future__ import annotations

import re
from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, instance, label, release_of, why
from .neighbours import (anr_budget, distinguish, from_text, lte_enbs, number, own_addresses, parse_plmn,
                         plmn_text, same_node, same_plmn, sources)
from .sites import lte_cell, nci
from .transport import check_ip, lte_cplane, reachable

ID = "endc-gnb"
TITLE = "Add an EN-DC gNB (X2)"
GROUP = "Neighbours"
SUMMARY = "Add a 5G gNB this eNB can use for EN-DC (NSA): the X2 link to it, and relations to its cells."
UI = "form"
KEYWORDS = "EN-DC ENDC NSA dual connectivity 5G NR gNB gNodeB neighbour neighbor X2 LNADJGNB LNRELGNBCELL"

MANUAL = "manual"
ID_RANGE = {"LNADJGNB": (0, 31), "LNRELGNBCELL": (0, 255)}


def _endc_on(enb: dict) -> bool:
    return enb["p"].get("actLteNrDualConnectivity") == "true"


def _id_length(site, enb: dict) -> str:
    """The gNB id length this eNB's EN-DC objects already use, if they agree."""
    seen = {m["p"].get("adjGnbIdLength") for m in site.child(enb["dn"], "LNADJGNB")}
    seen |= {m["p"].get("gnbIdLength") for m in site.of("LNRELGNBCELL", enb["dn"])}
    seen.discard(None)
    return seen.pop() if len(seen) == 1 else ""


def _cell_text(c: dict) -> str:
    return (f"cell {c['lcrId']} · PCI {c.get('pci') or '?'} · NR-ARFCN {c.get('arfcn') or '?'}"
            + (f" · {c['name']}" if c.get("name") else ""))


def _sources(ctx: Context) -> list[dict]:
    return sources(ctx, "gnbs", lambda e: not e["cells"] and not e["ip"], ("id", "idLength", "plmn", "ip", "cells"))


def _existing(site, enb: dict, ip: Optional[str], gnb_id: Optional[str], plmn: Optional[dict]) -> Optional[dict]:
    """The LNADJGNB for this gNB: the one with its address, else the one with
    its id and PLMN (the address may have changed)."""
    for m in site.child(enb["dn"], "LNADJGNB"):
        if ip and (m["p"].get("cPlaneIpAddr") or "").lower() == ip.lower():
            return m
    for m in site.child(enb["dn"], "LNADJGNB"):
        if gnb_id and m["p"].get("adjGnbId") == gnb_id and same_node(m, "plmnId", plmn):
            return m
    return None


def available(ctx: Context) -> Optional[str]:
    if lte_enbs(ctx.site):
        return None
    return "This file has no LTE eNB with cells (LNBTS and LNCEL)."


def setup(ctx: Context) -> dict:
    site = ctx.site
    targets, srcs, nb_cells, own_cells, plmns, lengths = [], {}, {}, {}, {}, {}
    found = _sources(ctx)
    for enb in lte_enbs(site):
        dn = enb["dn"]
        cells = [lte_cell(site, c) | {"dn": c["dn"]} for c in site.child(dn, "LNCEL")
                 if c["p"].get("lcrId") not in (None, "")]
        gnbs = site.child(dn, "LNADJGNB")
        targets.append({"value": dn, "key": dn, "label": f"{label(dn)} · eNB {instance(dn)}"
                        + (f" · {enb['p']['enbName']}" if enb["p"].get("enbName") else ""),
                        "details": [f"{len(cells)} cell{'s' if len(cells) != 1 else ''}, {len(gnbs)} EN-DC "
                                    f"gNB{'s' if len(gnbs) != 1 else ''}.",
                                    "EN-DC is on (actLteNrDualConnectivity)." if _endc_on(enb) else
                                    "EN-DC is off (actLteNrDualConnectivity): the gNB is added, but no UE uses it "
                                    "until EN-DC is on."]})
        opts, tails = [], []
        for e in found:
            have = _existing(site, enb, e["ip"], e["id"], e["plmn"])
            details = [from_text(e), f"PLMN {plmn_text(e['plmn']) or '?'}, gNB id length "
                                     f"{e['idLength'] or '?'}, X2 C-plane {e['ip'] or 'not in that file'}."]
            details += [_cell_text(c).capitalize() + "." for c in e["cells"][:6]]
            other = have and have["p"].get("adjGnbId") not in (None, "", e["id"])
            if other:
                details.append(f"{label(have['dn'])} has its address for gNB {have['p']['adjGnbId']}: check which "
                               "gNB is there.")
            elif have:
                details.append(f"Already an EN-DC gNB ({label(have['dn'])}): what's missing is added.")
            opts.append({"value": e["key"], "key": e["key"], "group": "Sites in the tool", "details": details,
                         "label": f"gNB {e['id']}" + (f" {e['name']}" if e.get("name") else "")})
            tails.append(f"{len(e['cells'])} cell{'s' if len(e['cells']) != 1 else ''}"
                         + (" · its address is another gNB's" if other else " · already a neighbour" if have else ""))
            nb_cells[e["key"]] = [{"value": c["lcrId"], "label": _cell_text(c)} for c in e["cells"]]
        distinguish(opts, found, tails)
        opts.append({"value": MANUAL, "key": MANUAL, "group": "By hand", "label": "Enter the gNB by hand",
                     "details": ["Its id, id length, address and PLMN, and the lcrIds of the cells to relate to."]})
        srcs[dn] = opts
        own_cells[dn] = [{"value": c["dn"], "label": f"{label(c['dn'])} · PCI {c['pci']} · EARFCN {c['earfcn']}"
                          + (f" · {c['name']}" if c.get("name") else "")} for c in cells]
        plmns[dn] = plmn_text({k: enb["p"].get(k) for k in ("mcc", "mnc", "mncLength")})
        lengths[dn] = _id_length(site, enb)
    manual = {"field": "source", "equals": MANUAL}
    return {
        "intro": "Adds the X2 link to a 5G gNB (LNADJGNB) and a relation (LNRELGNBCELL) from each LTE cell you "
                 "pick to each of its NR cells, so UEs on those cells can add the NR cell for EN-DC.",
        "fields": [
            {"id": "target", "label": "This eNB", "type": "select", "options": targets,
             "default": targets[0]["value"] if len(targets) == 1 else None},
            {"id": "source", "label": "gNB", "type": "select", "dependsOn": "target", "optionsByKey": srcs},
            {"id": "cells", "label": "Relations to its cells", "type": "checks", "dependsOn": "source",
             "optionsByKey": nb_cells, "optional": True},
            {"id": "gnbId", "label": "gNB id", "type": "text", "showIf": manual, "placeholder": "500078"},
            {"id": "idLength", "label": "gNB id length (bits)", "type": "text", "showIf": manual,
             "dependsOn": "target", "defaultByKey": lengths, "placeholder": "22-32",
             "hint": "The gNB's own gNbIdLength (NRBTS). The NR cell identity is built from it."},
            {"id": "ip", "label": "Its X2 C-plane address", "type": "text", "showIf": manual,
             "placeholder": "10.0.1.48"},
            {"id": "plmn", "label": "Its PLMN (MCC-MNC)", "type": "text", "showIf": manual, "dependsOn": "target",
             "defaultByKey": plmns, "placeholder": "310-410"},
            {"id": "lcrIds", "label": "Relations to its cells (lcrIds)", "type": "text", "showIf": manual,
             "optional": True, "placeholder": "1, 2, 3",
             "hint": "Leave empty to add the X2 link only: UE-based ANR then learns the relations."},
            {"id": "from", "label": "Relations from these cells", "type": "checks", "dependsOn": "target",
             "optionsByKey": own_cells},
        ],
    }


def _gnb(ctx: Context, inputs: dict) -> dict:
    """The gNB as {id, idLength, plmn, ip, cells, from}."""
    src = inputs.get("source") or ""
    problems: list[str] = []
    if src == MANUAL:
        nb = {"id": number(inputs.get("gnbId"), 0, 4294967295, "The gNB id", problems),
              "idLength": number(inputs.get("idLength"), 22, 32, "The gNB id length", problems), "from": None}
        ip = (inputs.get("ip") or "").strip()
        problem, _ = check_ip(ip) if ip else ("Enter the gNB's X2 C-plane address.", [])
        if problem:
            problems.append(problem)
        nb["ip"] = ip
        nb["plmn"] = parse_plmn(inputs.get("plmn") or "")
        if not nb["plmn"]:
            problems.append("Enter the PLMN as MCC-MNC, for example 310-410 or 001-01.")
        if nb["id"] and nb["idLength"] and int(nb["id"]) >= 1 << int(nb["idLength"]):
            problems.append(f"gNB id {nb['id']} doesn't fit in {nb['idLength']} bits (at most "
                            f"{(1 << int(nb['idLength'])) - 1}).")
        nb["cells"] = []
        text = (inputs.get("lcrIds") or "").strip()
        if text and nb["idLength"]:
            top = (1 << (36 - int(nb["idLength"]))) - 1
            for part in [x for x in re.split(r"[\s,;]+", text) if x]:
                lcr = number(part, 0, top, f"A cell lcrId (with a {nb['idLength']}-bit gNB id)", problems)
                if lcr is not None and lcr not in {c["lcrId"] for c in nb["cells"]}:
                    nb["cells"].append({"lcrId": lcr, "pci": None, "arfcn": None, "name": None})
    else:
        match = next((e for e in _sources(ctx) if e["key"] == src), None)
        if not match:
            raise PlanError(["Pick the gNB."])
        picked = inputs.get("cells")
        picked = {c["lcrId"] for c in match["cells"]} if picked is None else set(picked)
        nb = {"id": match["id"], "idLength": match["idLength"], "plmn": match["plmn"], "ip": match["ip"],
              "cells": [c for c in match["cells"] if c["lcrId"] in picked], "from": match["file"]}
        if not nb["ip"]:
            problems.append(f"{match['file']} has no address on gNB {match['id']}'s planes (NRBTS x2Cplane). "
                            "Enter the gNB by hand instead.")
        if not nb["plmn"]:
            problems.append(f"{match['file']} doesn't say gNB {match['id']}'s PLMN (NRPLMN).")
        if nb["cells"] and nb["idLength"] in (None, ""):
            problems.append(f"{match['file']} doesn't say gNB {match['id']}'s id length (NRBTS gNbIdLength), "
                            "which the NR cell identity needs.")
    for c in nb["cells"]:
        c["nci"] = nci(nb["id"], nb["idLength"], c["lcrId"])
        if c["nci"] is None and not problems:
            problems.append(f"Cell {c['lcrId']} of gNB {nb['id']} has no NR cell identity: the id, id length and "
                            "lcrId don't fit in 36 bits.")
    if problems:
        raise PlanError(problems)
    return nb


class _Plan:
    def __init__(self, ctx: Context, doc: Doc, enb: dict, nb: dict):
        self.ctx, self.doc, self.site = ctx, doc, ctx.site
        self.enb, self.nb = enb, nb
        info = doc.class_info("LNBTS")
        self.prefix = (info[0] if info and ":" in info[0] else "NOKLTE:LNBTS").rsplit(":", 1)[0]
        self.notes: list[str] = []
        self.made: dict[str, int] = {}
        index = ctx.release_index()
        written = index.get(release_of(enb["version"]), {}).get("LNADJGNB", set())
        self.identity = bool(index) and "adjGnbId" in written

    def plmn_row(self) -> list[tuple[str, str]]:
        p = self.nb["plmn"]
        return [("mcc", p["mcc"]), ("mnc", p["mnc"]), ("mncLength", p["mncLength"])]

    def create(self, parent: str, cls: str, params: list[tuple[str, str]], w: dict) -> str:
        lo, hi = ID_RANGE[cls]
        inst = self.doc.next_free(parent, cls, lo)
        if int(inst) > hi:
            raise PlanError([f"{label(parent)} has every {cls} id ({lo}-{hi}) in use."])
        first = not self.doc.of_class(cls)
        dn = self.doc.create(parent, cls, inst, params, full_class=f"{self.prefix}:{cls}" if first else None,
                             version=self.enb["version"] if first else None, w=w)
        self.made[cls] = self.made.get(cls, 0) + 1
        return dn

    def adj(self) -> str:
        nb, doc = self.nb, self.doc
        src = f"from {nb['from']}" if nb["from"] else "as entered"
        existing = _existing(self.site, self.enb, nb["ip"], nb["id"], nb["plmn"])
        if existing:
            dn, p = existing["dn"], existing["p"]
            if p.get("adjGnbId") not in (None, "", nb["id"]):
                raise PlanError([f"{label(dn)} has {p.get('cPlaneIpAddr')} for gNB {p['adjGnbId']}, not gNB "
                                 f"{nb['id']}. Check which gNB is at that address."])
            if (p.get("cPlaneIpAddr") or "").lower() != nb["ip"].lower():
                doc.set(dn, "cPlaneIpAddr", nb["ip"], why("endc", f"gNB {nb['id']}'s X2 C-plane address, {src}.",
                                                         "choice"))
            if p.get("cPlaneIpAddrCtrl") == "enbControlled":
                doc.set(dn, "cPlaneIpAddrCtrl", "oamControlled",
                        why("endc", "A planned address: with enbControlled, ANR maintains it instead.",
                            "official", ("cPlaneIpAddrCtrl", None)))
            if p.get("administrativeState") == "locked":
                self.notes.append(f"{label(dn)} is locked (administrativeState): unlock it, or the eNB won't use "
                                  f"gNB {nb['id']}.")
            return dn
        params = [("administrativeState", "unlocked"), ("cPlaneIpAddr", nb["ip"]),
                  ("cPlaneIpAddrCtrl", "oamControlled")]
        if self.identity and nb["id"] and nb["idLength"]:
            params = [("adjGnbId", nb["id"]), ("adjGnbIdLength", nb["idLength"])] + params
        dn = self.create(self.enb["dn"], "LNADJGNB", params,
                         why("endc", f"gNB {nb['id']} at {nb['ip']}, {src}. Unlocked, and oamControlled: the operator "
                                     "keeps the address (ANR-learned ones are enbControlled)."
                             + (" adjGnbId, adjGnbIdLength and plmnId as this release's files write them."
                                if len(params) > 3 else ""), "official", ("cPlaneIpAddrCtrl", None)))
        if len(params) > 3:
            doc.add_item(dn, "plmnId", self.plmn_row(), why("endc", f"gNB {nb['id']}'s PLMN.", "choice"))
        return dn

    def rel(self, own: dict, cell: dict) -> None:
        nb = self.nb
        if any(m["p"].get("nrCellId") == cell["nci"]
               and same_node(m, "nrCgiPlmnId", nb["plmn"])
               for m in self.site.child(own["dn"], "LNRELGNBCELL")):
            return
        dn = self.create(own["dn"], "LNRELGNBCELL", [
            ("gnbIdLength", nb["idLength"]), ("lteNrDualConnectAllowed", "allowed"), ("nrCellId", cell["nci"]),
            ("removeAllowed", "true")],
            why("endc", f"{label(own['dn'])} to cell {cell['lcrId']} of gNB {nb['id']} (NCI {cell['nci']}: the gNB "
                        f"id shifted left by {36 - int(nb['idLength'])} bits, plus the lcrId), EN-DC allowed. "
                        "removeAllowed is the default.", "official"))
        self.doc.add_item(dn, "nrCgiPlmnId", self.plmn_row(), why("endc", "The PLMN of the NR cell's NR-CGI.",
                                                                  "choice"))


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    enb = next((m for m in lte_enbs(site) if m["dn"] == inputs.get("target")), None)
    if not enb:
        raise PlanError(["Pick this file's eNB."])
    nb = _gnb(ctx, inputs)
    if nb["ip"].lower() in own_addresses(site):
        raise PlanError([f"{nb['ip']} is one of this BTS's own addresses."])
    cells = {c["dn"]: c for c in site.child(enb["dn"], "LNCEL") if c["p"].get("lcrId") not in (None, "")}
    picked = inputs.get("from")
    chosen = [cells[d] for d in (picked if picked is not None else cells) if d in cells]
    if nb["cells"] and not chosen:
        raise PlanError(["Pick at least one cell of this eNB to relate to the gNB's cells."])

    doc = Doc(ctx.raw)
    p = _Plan(ctx, doc, enb, nb)
    lnadjgnb = p.adj()
    for own in chosen if nb["cells"] else []:
        for cell in nb["cells"]:
            p.rel(own, cell)
    problem, note = anr_budget(site, enb, p.made)
    if problem:
        raise PlanError([problem])
    if note:
        p.notes.append(note)
    if not _endc_on(enb):
        p.notes.append("EN-DC is off on this eNB (actLteNrDualConnectivity false), so no UE uses the gNB yet. "
                       "Turning it on needs an NRDCDPR and tLteNrDualConnectPrep (its rule 1.2), and the LTE4088 "
                       "licence.")
    if not nb["cells"]:
        p.notes.append("No relation is added: UE-based ANR learns them once the X2 link is up (22 of the 33 "
                       "relations in the files this was built from were learned that way).")
    mine = {k: enb["p"].get(k) for k in ("mcc", "mnc", "mncLength")}
    if mine.get("mcc") and not same_plmn(mine, nb["plmn"]):
        p.notes.append(f"gNB {nb['id']}'s PLMN is {plmn_text(nb['plmn'])}, this eNB's {plmn_text(mine)}.")
    if reachable(site, nb["ip"]) is None:
        p.notes.append(f"Nothing in this file reaches {nb['ip']}: it is on none of the BTS's subnets and no static "
                       "route covers it. Add a route, or the X2 link won't come up.")
    source = lte_cplane(site, enb["dn"], None)
    made = ", ".join(f"{n} {cls}" for cls, n in p.made.items())
    return finish(ctx, doc, {
        "label": f"EN-DC gNB {nb['id']} on {label(enb['dn'])}",
        "summary": f"gNB {nb['id']} with {len(nb['cells'])} cell{'s' if len(nb['cells']) != 1 else ''}"
                   + (f" ({made} new)" if made else ""),
        "notes": p.notes,
        "confirm": [f"gNB {nb['id']} at {nb['ip']} accepts X2 from this eNB" + (f" ({source})" if source else "")
                    + ", on SCTP port 36422."]
                   + ([f"The gNB id, id length and lcrIds match gNB {nb['id']}'s own (NRBTS gNbIdLength, NRCELL "
                       "lcrId): the NR cell identity is built from them."] if not nb["from"] else []),
        "focus": lnadjgnb,
    })

"""
Add a 5G gNB to an LTE eNB as a neighbour: the eNB side of "Add a
neighbour gNB" (neighbour_gnb.py hands an eNB here). An LNADJGNB for the
X2 link to the gNB and an LNRELGNBCELL from each chosen LTE cell to each
chosen NR cell, for EN-DC (NSA, option 3X); and, whether EN-DC is on or
not, what the chosen LTE cells need to send UEs to the gNB's carriers.

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

Per NR carrier of the gNB's cells (their SSB, band and SSB subcarrier
spacing), on the chosen LTE cells, through the carrier action's planner
(carrier.py; settings from the cell's own, else another file's, else
production's): a row in NRFIM nrCarFrqL (reselection, with SIB24 on the
eNB) and in the redirRat nr REDRT's redirNrCarFrq (redirect on release).
All 11 production eNBs that broadcast NR carriers do both, on all 79
cells, and none of the 104 others does either. On the LNBTS, what the 11
have on and the others that set them off: actUeBasedAnrNr (UE-based ANR
learns the gNB's cells), actHoFromNr and actHoFromNrDlDataForward (the
gNB's handovers to LTE come in), each where the eNB's release has it.
Handover from LTE to NR (actHOtoNR) is off in every file, so it isn't
turned on, and a note says so.
EN-DC itself (actLteNrDualConnectivity, LTE4088) isn't switched on here
(the EN-DC action does that); when it is off, a note says what turning it
on needs (its rule 1.2).
"""
from __future__ import annotations

import re
from typing import Optional

from . import Context, PlanError, carrier, finish
from .doc import Doc, instance, label, release_of, why
from .neighbours import (anr_budget, distinguish, from_text, group, lookup, lte_enbs, nearby, number, own_addresses,
                         parse_plmn, picked, plmn_text, same_node, same_plmn, sources)
from .sites import lte_cell, nci
from .transport import check_ip, lte_cplane, reachable

MANUAL = "manual"
ID_RANGE = {"LNADJGNB": (0, 31), "LNRELGNBCELL": (0, 255)}
SWITCHES = (
    ("actUeBasedAnrNr", "UE-based ANR for NR: the eNB learns the gNB's cells from UE measurements"),
    ("actHoFromNr", "handover from NR: the gNB's handovers to LTE come in"),
    ("actHoFromNrDlDataForward", "downlink data forwarding on handover from NR"),
)


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


def _taken(site, enb: dict, e: dict) -> bool:
    """Whether this eNB has the gNB's address for another gNB."""
    have = _existing(site, enb, e["ip"], e["id"], e["plmn"])
    return bool(have) and have["p"].get("adjGnbId") not in (None, "", e["id"])


def _carrier_text(c: dict) -> str:
    return f"SSB {c.get('ssb') or '?'}" + (f" · n{c['band']}" if c.get("band") else "") + (
        f" · {c['scs']}" if c.get("scs") else "")


def setup_parts(ctx: Context) -> dict:
    """The eNB targets' share of the "Add a neighbour gNB" form: per eNB,
    the gNBs to offer, its cells, its PLMN and gNB id length; per gNB, its
    cells."""
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
                        "details": [f"{len(cells)} cell{'s' if len(cells) != 1 else ''}, {len(gnbs)} neighbour "
                                    f"gNB{'s' if len(gnbs) != 1 else ''} (LNADJGNB).",
                                    "EN-DC is on (actLteNrDualConnectivity)." if _endc_on(enb) else
                                    "EN-DC is off (actLteNrDualConnectivity): UEs reselect and are redirected to "
                                    "the gNB, and the cell relations wait for EN-DC."]})
        opts, tails = [], []
        near = nearby(site, lte_cplane(site, dn, None), found, stale=lambda e: _taken(site, enb, e))
        for e in near:
            have = _existing(site, enb, e["ip"], e["id"], e["plmn"])
            details = [from_text(e), f"PLMN {plmn_text(e['plmn']) or '?'}, gNB id length "
                                     f"{e['idLength'] or '?'}, X2 C-plane {e['ip'] or 'not in that file'}."]
            details += [_cell_text(c).capitalize() + "." for c in e["cells"][:6]]
            nr = sorted({_carrier_text(c) for c in e["cells"] if c.get("ssb")})
            if nr:
                details.append(f"NR carrier{'s' if len(nr) != 1 else ''}: {', '.join(nr)}.")
            other = _taken(site, enb, e)
            if other:
                details.append(f"{label(have['dn'])} has its address for gNB {have['p']['adjGnbId']}: check which "
                               "gNB is there.")
            elif have:
                details.append(f"Already an EN-DC gNB ({label(have['dn'])}): what's missing is added.")
            opts.append({"value": e["key"], "key": e["key"], "group": group(e), "details": details,
                         "label": f"gNB {e['id']}" + (f" {e['name']}" if e.get("name") else "")})
            tails.append(f"{len(e['cells'])} cell{'s' if len(e['cells']) != 1 else ''}"
                         + (" · its address is another gNB's" if other else " · already a neighbour" if have else ""))
            nb_cells[e["key"]] = [{"value": c["lcrId"], "label": _cell_text(c)} for c in e["cells"]]
        distinguish(opts, near, tails)
        opts.append({"value": MANUAL, "key": MANUAL, "group": "By hand", "label": "Enter the gNB by hand",
                     "details": ["Its id, id length, address and PLMN, its NR carrier, and the lcrIds of the cells "
                                 "to relate to."]})
        srcs[dn] = opts
        own_cells[dn] = [{"value": c["dn"], "label": f"{label(c['dn'])} · PCI {c['pci']} · EARFCN {c['earfcn']}"
                          + (f" · {c['name']}" if c.get("name") else "")} for c in cells]
        plmns[dn] = plmn_text({k: enb["p"].get(k) for k in ("mcc", "mnc", "mncLength")})
        lengths[dn] = _id_length(site, enb)
    return {"targets": targets, "sources": srcs, "nb_cells": nb_cells, "own_cells": own_cells, "plmns": plmns,
            "lengths": lengths}


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
        nb["carriers"] = []
        ssb = (inputs.get("ssb") or "").strip()
        if ssb:
            ssb = number(ssb, 0, carrier.NR_ARFCN_MAX, "The SSB NR-ARFCN", problems)
            band = number(inputs.get("band"), 1, 1024, "The NR band", problems)
            if inputs.get("scs") not in carrier.SCS:
                problems.append("Pick the SSB subcarrier spacing.")
            elif ssb and band:
                nb["carriers"] = [{"ssb": ssb, "band": band, "scs": inputs["scs"]}]
        text = (inputs.get("lcrIds") or "").strip()
        if text and nb["idLength"]:
            top = (1 << (36 - int(nb["idLength"]))) - 1
            for part in [x for x in re.split(r"[\s,;]+", text) if x]:
                lcr = number(part, 0, top, f"A cell lcrId (with a {nb['idLength']}-bit gNB id)", problems)
                if lcr is not None and lcr not in {c["lcrId"] for c in nb["cells"]}:
                    nb["cells"].append({"lcrId": lcr, "pci": None, "arfcn": None, "name": None})
    else:
        match = lookup(ctx, _sources(ctx), src, "gnbs")
        if not match:
            raise PlanError(["Pick the gNB."])
        wanted = inputs.get("cells")
        wanted = {c["lcrId"] for c in match["cells"]} if wanted is None else set(wanted)
        nb = {"id": match["id"], "idLength": match["idLength"], "plmn": match["plmn"], "ip": match["ip"],
              "cells": [c for c in match["cells"] if c["lcrId"] in wanted], "from": match["file"],
              "carriers": list({(c["ssb"], c["band"], c["scs"]): {"ssb": c["ssb"], "band": c["band"], "scs": c["scs"]}
                                for c in match["cells"] if c.get("ssb") and c.get("band") and c.get("scs")}.values())}
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

    def mobility(self, cells: list[dict]) -> carrier._Plan:
        """Reselection and redirect to the gNB's NR carriers on the cells,
        and the LNBTS switches for the neighbour gNB."""
        nb, doc, dn = self.nb, self.doc, self.enb["dn"]
        cp = carrier._Plan(self.ctx, doc, "nr-lte", {})
        for c in nb.get("carriers") or []:
            cp.inputs = c
            what = f"gNB {nb['id']}'s NR carrier, SSB {c['ssb']}"
            for own in cells:
                cp.add(own, "NRFIM", c["ssb"], f"reselection to {what}")
                cp.add(own, "REDRT:nr", c["ssb"], f"redirect to {what}")
        index = self.ctx.release_index()
        rel = release_of(self.enb["version"])
        missing = []
        for name, what in SWITCHES:
            if doc.get(dn, name) == "true":
                continue
            if index and name not in index.get(rel, {}).get("LNBTS", set()):
                missing.append(name)
                continue
            doc.set(dn, name, "true", why("neighbour", f"{what[0].upper() + what[1:]}: on in all 11 production "
                                                       "eNBs that broadcast NR carriers, off in the others that set "
                                                       "it.", "files"))
        if missing:
            self.notes.append(f"No file of {rel} has {', '.join(missing)} on the LNBTS, so "
                              f"{'it is' if len(missing) == 1 else 'they are'} left out.")
        return cp


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    enb = next((m for m in lte_enbs(site) if m["dn"] == inputs.get("target")), None)
    if not enb:
        raise PlanError(["Pick this file's eNB."])
    nb = _gnb(ctx, inputs)
    if nb["ip"].lower() in own_addresses(site):
        raise PlanError([f"{nb['ip']} is one of this BTS's own addresses."])
    cells = {c["dn"]: c for c in site.child(enb["dn"], "LNCEL") if c["p"].get("lcrId") not in (None, "")}
    chosen = picked(cells, inputs, "from")
    if (nb["cells"] or nb["carriers"]) and not chosen:
        raise PlanError(["Pick at least one cell of this eNB: the relations and the gNB's carriers go on it."])

    doc = Doc(ctx.raw)
    p = _Plan(ctx, doc, enb, nb)
    lnadjgnb = p.adj()
    for own in chosen if nb["cells"] else []:
        for cell in nb["cells"]:
            p.rel(own, cell)
    cp = p.mobility(chosen)
    problem, note = anr_budget(site, enb, p.made)
    if problem:
        raise PlanError([problem])
    if note:
        p.notes.append(note)
    p.notes += carrier.notes(cp)
    if not nb.get("carriers"):
        p.notes.append(f"gNB {nb['id']}'s NR carrier isn't known, so no reselection (NRFIM) or redirect (REDRT) to "
                       "it is added: " + (f"{nb['from']} doesn't say its cells' SSB (gscnOrSsPbchArfcn). Add the carrier "
                                          "with the carrier action, or enter the gNB by hand with its SSB."
                                          if nb["from"] else "enter its SSB, band and SCS to add them."))
    p.notes.append("Handover from LTE to NR (actHOtoNR) isn't turned on: it is off in every file in the tool. UEs "
                   "reach the gNB by reselection and redirect" + (", and through EN-DC." if _endc_on(enb) else "."))
    if not _endc_on(enb):
        p.notes.append("EN-DC is off on this eNB (actLteNrDualConnectivity false): the cell relations are for when "
                       "it is on. Turning it on (the EN-DC action) needs an NRDCDPR and tLteNrDualConnectPrep (its "
                       "rule 1.2), and the LTE4088 licence.")
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
        "label": f"Neighbour gNB {nb['id']} on {label(enb['dn'])}",
        "summary": f"gNB {nb['id']} with {len(nb['cells'])} cell{'s' if len(nb['cells']) != 1 else ''}"
                   + (f" ({made} new)" if made else ""),
        "notes": p.notes,
        "confirm": [f"gNB {nb['id']} at {nb['ip']} accepts X2 from this eNB" + (f" ({source})" if source else "")
                    + ", on SCTP port 36422."]
                   + ([f"The gNB id, id length and lcrIds match gNB {nb['id']}'s own (NRBTS gNbIdLength, NRCELL "
                       "lcrId): the NR cell identity is built from them."] if not nb["from"] else []),
        "focus": lnadjgnb,
    })

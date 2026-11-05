"""
Add a neighbour eNB, to an LTE eNB or a 5G gNB. To an eNB, over X2: an
LNADJ for the other eNB, an LNADJL per neighbour cell, an LNREL from each
chosen cell of this eNB to each neighbour cell, and the carrier settings
an inter-frequency neighbour needs. To a gNB, the carriers its cells hand
over, reselect and redirect to, and if picked the X2 link: gnb_enb.py,
which this hands a gNB to.

In a run (run.py), "More neighbour eNBs" adds others the same way, with
all their cells, and "Their end" adds this site to each neighbour's own
file: an eNB gets this eNB (here), a gNB's eNB its gNB (neighbour_gnb),
relating the cells each end picked here.

The neighbour comes from another site's file in the tool, or this file's
own co-sited eNB (its eNB id, PLMN, C-plane address and cells, from
sites.summary), or is typed in, one cell at a time. Taking the neighbour's identity from its own file is the
one exception to the no-identity-from-other-files rule: it describes that
site, not this one. Running it again for the same eNB adds what is missing
and corrects what differs, so cells can be added one by one.

What is written is the dictionary's creation set, which is also what the
operator-planned neighbours of the corpus carry (the xL20C-xL23R1 files;
the 25R2 site's are mostly ANR-learned, with ids counting down from 255):
  - LNADJ: adjEnbId, cPlaneIpAddr, cPlaneIpAddrCtrl oamControlled ("the
    responsibility of the operator to configure the correct cPlaneIpAddr";
    ANR-learned ones are enbControlled), rlfBasedRCRsupported (the
    neighbour's actRLFbasedRCR, which it "must be aligned with"; false when
    unknown), plmnId.
  - LNADJL: ecgiLcrId, fDlEarfcn, phyCellId, tac and bcPlmnIdList, the
    Mandatory set. ecgiAdjEnbId, sourceOfData and the bandwidths are "Value
    set by the system": the eNB fills them in over X2.
  - LNREL: every Mandatory parameter with its default, except removeAllowed
    false (385 of 494 planned relations), so ANR doesn't remove a planned
    relation; ecgiPlmnId.
  - Ids are the lowest free ones, as the dictionary asks for LNADJ, LNADJL
    and LNREL, "to avoid rejection of plan file activation due to colliding"
    ids when ANR creates objects.
  - Inter-frequency (the inter-frequency link rule): the source cell gets
    an IRFIM for the neighbour's EARFCN, copied from one of the eNB's
    IRFIMs, and an LNHOIF the same way (ids 1-16). Their priorities and
    thresholds are the copied carrier's; a note says so.
"""
from __future__ import annotations

from typing import Optional

from . import Context, PlanError, finish, gnb_enb
from .doc import Doc, instance, label, why
from .neighbours import (BOTH, anr_budget, distinguish, far, from_text, group, here, id_clash, lcr_ids, lookup,
                         lte_enbs, nearby, number, own_addresses, parse_plmn, picked, plmn_text, run_fields, same_node,
                         sources)
from .sites import NRB, lte_cell
from .transport import check_ip, lte_cplane, reachable

ID = "neighbour-enb"
TITLE = "Add a neighbour eNB"
GROUP = "Neighbours"
SUMMARY = ("Add an LTE site as a neighbour: to an eNB over X2 (its cells, and relations to them), or to a gNB (the "
           "LTE carriers to hand over, reselect and redirect to).")
UI = "form"
KEYWORDS = ("neighbour neighbor X2 adjacent eNodeB eNB cell relation handover reselection redirect LNADJ LNADJL LNREL "
            "IRFIM LNHOIF ANR gNB gNodeB NR to LTE inter-RAT NRHOIR NRLIM NRREDRT LTEENB "
            "neighbour cell roam roaming mobility idle")

MANUAL = "manual"
BANDWIDTHS = ("1.4 MHz", "3 MHz", "5 MHz", "10 MHz", "15 MHz", "20 MHz")


def _enbs(ctx: Context) -> list[dict]:
    return lte_enbs(ctx.site)


def _cell_text(c: dict) -> str:
    return (f"cell {c['lcrId']} · PCI {c.get('pci') or '?'} · EARFCN {c.get('earfcn') or '?'} · TAC {c.get('tac') or '?'}"
            + (f" · {c['name']}" if c.get("name") else ""))


def _sources(ctx: Context, enb: dict) -> list[dict]:
    """Neighbour candidates from the other files: one per distinct eNB (id,
    PLMN, address, cells), from the newest file that has it."""
    own, mine = instance(enb["dn"]), own_addresses(ctx.site)
    # In another file, a site at this BTS's own address is this BTS in another export; one with its id is
    # another BTS (lab files reuse ids), offered and refused only where the PLMN is the same too.
    return (here(ctx, "enbs", lambda e: not e["cells"] or e["id"] == own)
            + sources(ctx, "enbs", lambda e: not e["cells"] or (e.get("ip") or "").strip().lower() in mine,
                      ("id", "plmn", "ip", "cells")))


def _plmn(enb: dict) -> Optional[dict]:
    return {k: enb["p"].get(k) for k in ("mcc", "mnc", "mncLength")} if enb["p"].get("mcc") else None


def _existing(lnadjs: list[dict], enb_id: Optional[str], plmn: Optional[dict]) -> Optional[dict]:
    """The LNADJ for this neighbour: its eNB id and PLMN (the global eNB id)."""
    return next((m for m in lnadjs if m["p"].get("adjEnbId") == enb_id and same_node(m, "plmnId", plmn)), None)


def available(ctx: Context) -> Optional[str]:
    if _enbs(ctx) or gnb_enb.gnbs(ctx.site):
        return None
    return "This file has no LTE eNB or 5G gNB with cells."


def setup(ctx: Context) -> dict:
    site = ctx.site
    targets, sources, nb_cells, own_cells, plmns, earfcns, tacs, bws, bw_opts = [], {}, {}, {}, {}, {}, {}, {}, {}
    both = bool(_enbs(ctx)) and bool(gnb_enb.gnbs(site))
    for enb in _enbs(ctx):
        dn = enb["dn"]
        cells = [lte_cell(site, c) | {"dn": c["dn"]} for c in site.child(dn, "LNCEL")
                 if c["p"].get("lcrId") not in (None, "")]
        lnadjs = site.child(dn, "LNADJ")
        targets.append({"value": dn, "key": dn, "label": f"{label(dn)} · eNB {instance(dn)}"
                        + (f" · {enb['p']['enbName']}" if enb["p"].get("enbName") else ""),
                        "details": [f"{len(cells)} cell{'s' if len(cells) != 1 else ''}, {len(lnadjs)} neighbour "
                                    f"eNB{'s' if len(lnadjs) != 1 else ''}."]} | ({"group": "LTE eNB"} if both else {}))
        own_plmn = _plmn(enb)
        opts, tails, found = [], [], nearby(site, lte_cplane(site, dn, None), _sources(ctx, enb))
        for e in found:
            have = _existing(lnadjs, e["id"], e["plmn"])
            details = [from_text(e), f"PLMN {plmn_text(e['plmn']) or '?'}, X2 C-plane {e['ip'] or 'not in that file'}."]
            details += [_cell_text(c).capitalize() + "." for c in e["cells"][:6]]
            if have:
                details.append(f"Already a neighbour ({label(have['dn'])}): what's missing is added.")
            clash = id_clash("eNB", e["id"], e["plmn"], instance(dn), own_plmn)
            if clash:
                details.append(clash)
            opts.append({"value": e["key"], "key": e["key"], "details": details, "group": group(e),
                         "label": f"eNB {e['id']}" + (f" {e['name']}" if e.get("name") else "")})
            tails.append(f"{len(e['cells'])} cell{'s' if len(e['cells']) != 1 else ''}"
                         + (" · already a neighbour" if have else "") + (" · same eNB id" if clash else ""))
            nb_cells[e["key"]] = [{"value": c["lcrId"], "label": _cell_text(c)} for c in e["cells"]]
        distinguish(opts, found, tails)
        opts.append({"value": MANUAL, "key": MANUAL, "group": "By hand", "label": "Enter the neighbour by hand",
                     "details": ["One cell at a time: run it again with the same eNB id to add another."]})
        sources[dn] = opts
        own_cells[dn] = [{"value": c["dn"], "label": f"{label(c['dn'])} · PCI {c['pci']} · EARFCN {c['earfcn']}"
                          + (f" · {c['name']}" if c.get("name") else "")} for c in cells]
        plmns[dn] = plmn_text(own_plmn)
        earfcns[dn] = cells[0]["earfcn"] or ""
        tacs[dn] = cells[0]["tac"] or ""
        bw_opts[dn] = [{"value": b, "label": b} for b in BANDWIDTHS]
        bws[dn] = cells[0]["bw"] if cells[0]["bw"] in BANDWIDTHS else "20 MHz"
    found = gnb_enb.enb_sources(ctx)
    nr = gnb_enb.setup_parts(ctx, found)
    for t in nr["targets"]:
        dn = t["value"]
        targets.append(t if both else {k: v for k, v in t.items() if k != "group"})
        opts, tails, near = [], [], nearby(site, nr["x2_addresses"][dn], found)
        for e in near:
            state = nr["states"][dn][e["key"]]
            details = [from_text(e), f"PLMN {plmn_text(e['plmn']) or '?'}, X2 C-plane {e['ip'] or 'not in that file'}."]
            details += [_cell_text(c).capitalize() + "." for c in e["cells"][:6]]
            if state:
                details.append(f"{state[0].upper() + state[1:]}: what's missing is added.")
            opts.append({"value": e["key"], "key": e["key"], "group": group(e), "details": details,
                         "label": f"eNB {e['id']}" + (f" {e['name']}" if e.get("name") else "")})
            tails.append(f"{len(e['cells'])} cell{'s' if len(e['cells']) != 1 else ''}" + (f" · {state}" if state else ""))
            nb_cells[e["key"]] = [{"value": c["lcrId"], "label": _cell_text(c)} for c in e["cells"]]
        distinguish(opts, near, tails)
        opts.append({"value": gnb_enb.MANUAL, "key": gnb_enb.MANUAL, "group": "By hand",
                     "label": "Enter the eNB by hand",
                     "details": ["Its id, PLMN and carrier (DL EARFCN), and its address for an X2 link."]})
        sources[dn] = opts
        plmns[dn] = nr["plmns"][dn]
        earfcns[dn] = nr["earfcns"][dn]
    manual = {"field": "source", "equals": MANUAL}
    typed = {"field": "source", "in": [MANUAL, gnb_enb.MANUAL]}
    return {
        "intro": "On an eNB: adds the other eNB (LNADJ), its cells (LNADJL) and a relation (LNREL) from each cell "
                 "you pick here to each of its cells, with the carrier settings a neighbour on another EARFCN needs. "
                 "On a gNB: adds the eNB's carriers to hand over to (NRHOIR), reselect to (NRLIM) and redirect to "
                 "(NRREDRT), with the switches that turn them on; the gNB learns the eNB's cells from UEs (ANR).",
        "fields": [
            {"id": "target", "label": "This site", "type": "select", "options": targets,
             "default": targets[0]["value"] if len(targets) == 1 else None},
            {"id": "source", "label": "Neighbour", "type": "select", "dependsOn": "target", "optionsByKey": sources},
            {"id": "cells", "label": "Its cells", "type": "checks", "dependsOn": "source", "optionsByKey": nb_cells},
            {"id": "enbId", "label": "Neighbour eNB id", "type": "text", "showIf": typed, "placeholder": "0-1048575"},
            {"id": "ip", "label": "Its X2 C-plane address", "type": "text", "showIf": manual,
             "placeholder": "10.0.1.47"},
            {"id": "enbIp", "label": "Its X2 C-plane address", "type": "text", "optional": True,
             "showIf": {"field": "source", "equals": gnb_enb.MANUAL}, "placeholder": "10.0.1.47",
             "hint": "Only for an X2 link: handover from NR to LTE goes through the core (N26), not X2."},
            {"id": "plmn", "label": "Its PLMN (MCC-MNC)", "type": "text", "showIf": typed, "dependsOn": "target",
             "defaultByKey": plmns, "placeholder": "310-410"},
            {"id": "lcrId", "label": "Cell lcrId (the ECGI cell id)", "type": "text", "showIf": manual,
             "placeholder": "0-255"},
            {"id": "pci", "label": "Cell PCI", "type": "text", "showIf": manual, "placeholder": "0-503"},
            {"id": "earfcn", "label": "Cell DL EARFCN", "type": "text", "showIf": typed, "dependsOn": "target",
             "defaultByKey": earfcns, "placeholder": "66786"},
            {"id": "tac", "label": "Cell TAC", "type": "text", "showIf": manual, "dependsOn": "target",
             "defaultByKey": tacs},
            {"id": "bw", "label": "Cell bandwidth", "type": "select", "showIf": manual, "dependsOn": "target",
             "optionsByKey": bw_opts, "defaultByKey": bws},
            {"id": "from", "label": "Relations from these cells", "type": "checks", "dependsOn": "target",
             "optionsByKey": own_cells},
            {"id": "nrCells", "label": "On these cells", "type": "checks", "dependsOn": "target",
             "optionsByKey": nr["nr_cells"]},
            {"id": "x2", "label": "X2", "type": "checks", "dependsOn": "target", "optionsByKey": nr["x2"],
             "defaultByKey": nr["x2_default"], "optional": True},
            *run_fields(sources, "eNB"),
        ],
    }


def legs(ctx: Context, inputs: dict) -> list[dict]:
    """The run's other changes: the more neighbours on this file, then, with
    "Their end", this site on each neighbour's file, relating the cells
    picked here (theirs from the "cells" pick, this site's from "from" or
    "nrCells")."""
    site, target, src = ctx.site, inputs.get("target") or "", inputs.get("source") or ""
    on_gnb = any(g["dn"] == target for g in gnb_enb.gnbs(site))
    more = [k for k in dict.fromkeys(inputs.get("more") or []) if far(k) and k != src]
    out = [{"file": None, "action": ID, "inputs": {**inputs, "source": k, "cells": None},
            "what": f"eNB {instance(far(k)[1])} as a neighbour too"} for k in more]
    if BOTH not in (inputs.get("both") or []):
        return out
    me = f"{'gNB' if on_gnb else 'eNB'} {instance(target)}"
    mine = lcr_ids(site, inputs.get("nrCells" if on_gnb else "from"), target, "NRCELL" if on_gnb else "LNCEL")
    for k in [src] + more:
        there = far(k)
        if there:
            out.append({"file": there[0], "action": "neighbour-gnb" if on_gnb else ID,
                        "inputs": {"target": there[1], "source": f"{ctx.key}|{target}", "cells": mine,
                                   "fromLcr": inputs.get("cells") if k == src else None},
                        "what": f"{me} as eNB {instance(there[1])}'s neighbour"})
    return out


def _neighbour(ctx: Context, enb: dict, inputs: dict) -> dict:
    """The neighbour eNB as {id, plmn, ip, rlf, cells, from}."""
    src = inputs.get("source") or ""
    problems: list[str] = []
    if src == MANUAL:
        nb = {"id": number(inputs.get("enbId"), 0, 1048575, "The eNB id", problems), "rlf": None, "from": None}
        ip = (inputs.get("ip") or "").strip()
        problem, _ = check_ip(ip) if ip else ("Enter the neighbour's X2 C-plane address.", [])
        if problem:
            problems.append(problem)
        nb["ip"] = ip
        nb["plmn"] = parse_plmn(inputs.get("plmn") or "")
        if not nb["plmn"]:
            problems.append("Enter the PLMN as MCC-MNC, for example 310-410 or 001-01.")
        bw = inputs.get("bw") or "20 MHz"
        cell = {"lcrId": number(inputs.get("lcrId"), 0, 255, "The lcrId", problems),
                "pci": number(inputs.get("pci"), 0, 503, "The PCI", problems),
                "earfcn": number(inputs.get("earfcn"), 0, 262143, "The EARFCN", problems),
                "tac": number(inputs.get("tac"), 0, 65535, "The TAC", problems),
                "bw": bw if bw in BANDWIDTHS else "20 MHz", "name": None}
        nb["cells"] = [cell]
    else:
        match = lookup(ctx, _sources(ctx, enb), src, "enbs")
        if not match:
            raise PlanError(["Pick the neighbour eNB."])
        wanted = set(inputs.get("cells") or [c["lcrId"] for c in match["cells"]])
        nb = {"id": match["id"], "plmn": match["plmn"], "ip": match["ip"], "rlf": match["rlf"],
              "cells": [c for c in match["cells"] if c["lcrId"] in wanted], "from": match["file"]}
        if not nb["cells"]:
            problems.append("Pick at least one of its cells.")
        if not nb["plmn"]:
            problems.append(f"{match['file']} doesn't say eNB {match['id']}'s PLMN (LNBTS mcc/mnc).")
        if not nb["ip"]:
            problems.append(f"{match['file']} has no C-plane address for eNB {match['id']} (TRSNW cPlane or IPNO "
                            "cPlaneIpAddress). Enter the neighbour by hand instead.")
        for c in nb["cells"]:
            if c.get("pci") in (None, "") or c.get("earfcn") in (None, "") or c.get("tac") in (None, ""):
                problems.append(f"{match['file']} lacks the PCI, EARFCN or TAC of cell {c['lcrId']}.")
    clash = id_clash("eNB", nb.get("id"), nb.get("plmn"), instance(enb["dn"]), _plmn(enb))
    if clash:
        problems.append(clash)
    if problems:
        raise PlanError(problems)
    return nb


# Instance-id ranges (the dictionary). For LNADJ, LNADJL and LNREL it asks for
# "the lowest free" id, so planned objects don't collide with ones ANR creates.
ID_RANGE = {"LNADJ": (0, 255), "LNADJL": (0, 255), "LNREL": (0, 388), "IRFIM": (1, 16), "LNHOIF": (1, 16)}


class _Plan:
    def __init__(self, ctx: Context, doc: Doc, enb: dict, nb: dict):
        self.ctx, self.doc, self.site = ctx, doc, ctx.site
        self.enb, self.nb = enb, nb
        info = doc.class_info("LNBTS")
        self.prefix = (info[0] if info and ":" in info[0] else "NOKLTE:LNBTS").rsplit(":", 1)[0]
        self.notes: list[str] = []
        self.made: dict[str, int] = {}
        self.carriers: dict[tuple, list[str]] = {}  # (kind, EARFCN, donor) -> cells
        self.carriers_done: set[tuple[str, str]] = set()

    def plmn_row(self) -> list[tuple[str, str]]:
        p = self.nb["plmn"]
        return [("mcc", p["mcc"]), ("mnc", p["mnc"]), ("mncLength", p["mncLength"])]

    def free(self, parent: str, cls: str) -> Optional[str]:
        lo, hi = ID_RANGE[cls]
        inst = self.doc.next_free(parent, cls, lo).rsplit("-", 1)[-1]
        return inst if int(inst) <= hi else None

    def create(self, parent: str, cls: str, params: list[tuple[str, str]], w: dict) -> str:
        inst = self.free(parent, cls)
        if inst is None:
            raise PlanError([f"{label(parent)} has every {cls} id ({ID_RANGE[cls][0]}-{ID_RANGE[cls][1]}) in use."])
        first = not self.doc.of_class(cls)
        dn = self.doc.create(parent, cls, inst, params, full_class=f"{self.prefix}:{cls}" if first else None,
                             version=self.enb["version"] if first else None, w=w)
        self.made[cls] = self.made.get(cls, 0) + 1
        return dn

    def adj(self) -> str:
        nb, doc, enb = self.nb, self.doc, self.enb["dn"]
        src = f"from {nb['from']}" if nb["from"] else "as entered"
        existing = _existing(self.site.child(enb, "LNADJ"), nb["id"], nb["plmn"])
        if existing:
            dn = existing["dn"]
            if existing["p"].get("cPlaneIpAddr") != nb["ip"]:
                doc.set(dn, "cPlaneIpAddr", nb["ip"], why("neighbour", f"eNB {nb['id']}'s X2 C-plane address, {src}.",
                                                         "choice"))
                if existing["p"].get("cPlaneIpAddrCtrl") == "enbControlled":
                    doc.set(dn, "cPlaneIpAddrCtrl", "oamControlled",
                            why("neighbour", "A planned address: with enbControlled, ANR maintains it instead.",
                                "official", ("cPlaneIpAddrCtrl", None)))
            return dn
        rlf = nb["rlf"] if nb["rlf"] in ("true", "false") else "false"
        if nb["rlf"] not in ("true", "false"):
            self.notes.append(f"rlfBasedRCRsupported is false: it must match eNB {nb['id']}'s actRLFbasedRCR, "
                              "which isn't known. Set it to true if that eNB has RLF-based re-establishment on.")
        dn = self.create(enb, "LNADJ", [
            ("adjEnbId", nb["id"]), ("cPlaneIpAddr", nb["ip"]), ("cPlaneIpAddrCtrl", "oamControlled"),
            ("rlfBasedRCRsupported", rlf)],
            why("neighbour", f"eNB {nb['id']} at {nb['ip']}, {src}. oamControlled: the operator keeps the address "
                             "(ANR-learned neighbours are enbControlled). rlfBasedRCRsupported follows the "
                             "neighbour's actRLFbasedRCR.", "official", ("cPlaneIpAddrCtrl", None)))
        doc.add_item(dn, "plmnId", self.plmn_row(), why("neighbour", f"eNB {nb['id']}'s PLMN.", "choice"))
        return dn

    def adjl(self, lnadj: str, cell: dict) -> None:
        nb, doc = self.nb, self.doc
        existing = next((m for m in self.site.child(lnadj, "LNADJL") if m["p"].get("ecgiLcrId") == cell["lcrId"]),
                        None)
        values = {"fDlEarfcn": cell["earfcn"], "phyCellId": cell["pci"], "tac": cell["tac"]}
        if existing:
            for k, v in values.items():
                if existing["p"].get(k) != v:
                    doc.set(existing["dn"], k, v, why("neighbour", f"Cell {cell['lcrId']} of eNB {nb['id']} has "
                                                                   f"{k} {v}.", "choice"))
            return
        # The dictionary's Mandatory set; ecgiAdjEnbId, sourceOfData and the
        # bandwidths are "Value set by the system".
        dn = self.create(lnadj, "LNADJL", [
            ("ecgiLcrId", cell["lcrId"]), ("fDlEarfcn", cell["earfcn"]), ("phyCellId", cell["pci"]),
            ("tac", cell["tac"])],
            why("neighbour", f"{_cell_text(cell).capitalize()} of eNB {nb['id']}.", "official"))
        doc.add_item(dn, "bcPlmnIdList", self.plmn_row(), why("neighbour", "The PLMN the cell broadcasts.", "choice"))

    def rel(self, own: dict, cell: dict) -> None:
        nb = self.nb
        if any(m["p"].get("ecgiAdjEnbId") == nb["id"] and m["p"].get("ecgiLcrId") == cell["lcrId"]
               for m in self.site.child(own["dn"], "LNREL")):
            return
        dn = self.create(own["dn"], "LNREL", [
            ("amleAllowed", "false"), ("cellIndOffNeigh", "0dB"), ("ecgiAdjEnbId", nb["id"]),
            ("ecgiLcrId", cell["lcrId"]), ("handoverAllowed", "allowed"), ("nrControl", "automatic"),
            ("removeAllowed", "false")],
            why("neighbour", f"{label(own['dn'])} to cell {cell['lcrId']} of eNB {nb['id']}, handover allowed. "
                             "removeAllowed false so ANR keeps the planned relation, as on 385 of 494 planned "
                             "relations.", "files"))
        self.doc.add_item(dn, "ecgiPlmnId", self.plmn_row(), why("neighbour", "The PLMN of the target's ECGI.",
                                                                 "choice"))

    def carrier(self, own: dict, cell: dict) -> None:
        """IRFIM and LNHOIF for a neighbour on another EARFCN."""
        site, doc = self.site, self.doc
        mine, target = lte_cell(site, own)["earfcn"], cell["earfcn"]
        if not mine or target == mine or (own["dn"], target) in self.carriers_done:
            return
        self.carriers_done.add((own["dn"], target))
        cells = site.child(self.enb["dn"], "LNCEL")
        for cls, field in (("IRFIM", "dlCarFrqEut"), ("LNHOIF", "eutraCarrierInfo")):
            mine_objs = site.child(own["dn"], cls)
            if any(m["p"].get(field) == target for m in mine_objs):
                continue
            donor = (mine_objs or [m for c in cells for m in site.child(c["dn"], cls)] or [None])[0]
            if donor is None:
                if cls == "IRFIM":
                    self.carriers.setdefault(("none", target, ""), []).append(label(own["dn"]))
                continue
            inst = self.free(own["dn"], cls)
            if inst is None:
                self.carriers.setdefault(("full-" + cls, target, ""), []).append(label(own["dn"]))
                continue
            over = {field: target}
            nrb = NRB.get(cell.get("bw") or "")
            if nrb and cls == "IRFIM":
                over["measBdw"] = f"{nrb}mbw"
            elif nrb and donor["p"].get("measurementBandwidth"):
                over["measurementBandwidth"] = f"mbw{nrb}"
            doc.clone(donor["dn"], f"{own['dn']}/{cls}-{inst}",
                      why("neighbour", (f"Idle-mode reselection to EARFCN {target}" if cls == "IRFIM" else
                                        f"Inter-frequency handover to EARFCN {target}")
                          + f", copied from {label(donor['dn'])} of {label(donor['dn'].rsplit('/', 1)[0])}.",
                          "files"),
                      overrides={"": over})
            self.made[cls] = self.made.get(cls, 0) + 1
            if cls == "IRFIM":
                self.carriers.setdefault(("copied", target, f"{label(donor['dn'])} (EARFCN "
                                                            f"{donor['p'].get(field)})"), []).append(label(own["dn"]))

    def carrier_notes(self) -> None:
        for (kind, target, donor), cells in self.carriers.items():
            where = ", ".join(cells)
            if kind == "copied":
                self.notes.append(f"The new IRFIM for EARFCN {target} on {where} copies {donor}. Check its "
                                  "reselection priority (eutCelResPrio) and thresholds for the new carrier.")
            elif kind == "none":
                self.notes.append(f"No cell of this eNB has an IRFIM to copy, so {where} gets no carrier settings "
                                  f"for EARFCN {target}. Add an IRFIM for it, or idle UEs won't reselect to it.")
            else:
                self.notes.append(f"{where} already {'has' if len(cells) == 1 else 'have'} all 16 "
                                  f"{kind[5:]} ids in use, so EARFCN {target} gets none. Remove one for an unused "
                                  "carrier first.")

    def pci_checks(self, chosen: list[dict]) -> None:
        site, nb = self.site, self.nb
        adjl = {}
        for m in site.of("LNADJL", self.enb["dn"]):
            lnadj = site.by_dn.get(m["dn"].rsplit("/", 1)[0]) or {"p": {}}
            adjl[(m["p"].get("ecgiAdjEnbId") or lnadj["p"].get("adjEnbId"), m["p"].get("ecgiLcrId"))] = m
        for own in chosen:
            mine = lte_cell(site, own)
            for cell in nb["cells"]:
                if cell["earfcn"] == mine["earfcn"] and cell["pci"] == mine["pci"]:
                    self.notes.append(f"Cell {cell['lcrId']} of eNB {nb['id']} has PCI {cell['pci']} on EARFCN "
                                      f"{cell['earfcn']}, as {label(own['dn'])} does: UEs can't tell them apart "
                                      "(PCI collision).")
            known = {}
            for rel in site.child(own["dn"], "LNREL"):
                key = (rel["p"].get("ecgiAdjEnbId"), rel["p"].get("ecgiLcrId"))
                if key in adjl and key[0] != nb["id"]:
                    known[(adjl[key]["p"].get("fDlEarfcn"), adjl[key]["p"].get("phyCellId"))] = key
            for cell in nb["cells"]:
                other = known.get((cell["earfcn"], cell["pci"]))
                if other:
                    self.notes.append(f"{label(own['dn'])} already has a neighbour with PCI {cell['pci']} on EARFCN "
                                      f"{cell['earfcn']} (eNB {other[0]} cell {other[1]}): two neighbours with one "
                                      "PCI confuse handover (PCI confusion).")


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    if any(g["dn"] == inputs.get("target") for g in gnb_enb.gnbs(site)):
        return gnb_enb.plan(ctx, inputs)
    enb = next((m for m in _enbs(ctx) if m["dn"] == inputs.get("target")), None)
    if not enb:
        raise PlanError(["Pick this file's eNB or gNB."])
    nb = _neighbour(ctx, enb, inputs)
    cells = {c["dn"]: c for c in site.child(enb["dn"], "LNCEL") if c["p"].get("lcrId") not in (None, "")}
    chosen = picked(cells, inputs, "from")
    if not chosen:
        raise PlanError(["Pick at least one cell of this eNB to relate to the neighbour."])

    doc = Doc(ctx.raw)
    p = _Plan(ctx, doc, enb, nb)
    lnadj = p.adj()
    for cell in nb["cells"]:
        p.adjl(lnadj, cell)
    for own in chosen:
        for cell in nb["cells"]:
            p.rel(own, cell)
            p.carrier(own, cell)
    p.carrier_notes()
    p.pci_checks(chosen)
    problem, note = anr_budget(site, enb, p.made)
    if problem:
        raise PlanError([problem])
    if note:
        p.notes.append(note)
    how = reachable(site, nb["ip"])
    if how is None:
        p.notes.append(f"Nothing in this file reaches {nb['ip']}: it is on none of the BTS's subnets and no static "
                       "route covers it. Add a route, or the X2 link won't come up.")
    source = lte_cplane(site, enb["dn"], None)
    made = ", ".join(f"{n} {cls}" for cls, n in p.made.items())
    return finish(ctx, doc, {
        "label": f"Neighbour eNB {nb['id']} on {label(enb['dn'])}",
        "summary": f"eNB {nb['id']} with {len(nb['cells'])} cell{'s' if len(nb['cells']) != 1 else ''}"
                   + (f" ({made} new)" if made else ""),
        "notes": p.notes,
        "confirm": [f"eNB {nb['id']} at {nb['ip']} accepts X2 from this eNB" + (f" ({source})" if source else "")
                    + ", and has this eNB as its neighbour too, or handovers back here have no relation."]
                   + (["The cell you entered matches eNB " + nb["id"] + "'s own settings (lcrId, PCI, EARFCN, TAC)."]
                      if not nb["from"] else []),
        "focus": lnadj,
    })

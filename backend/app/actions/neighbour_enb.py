"""
Add an X2 neighbour eNB to an LTE eNB: an LNADJ for the other eNB, an
LNADJL per neighbour cell, an LNREL from each chosen cell of this eNB to
each neighbour cell, and the carrier settings an inter-frequency neighbour
needs.

The neighbour comes from another site's file in the tool (its eNB id,
PLMN, C-plane address and cells, from sites.summary) or is typed in, one
cell at a time. Taking the neighbour's identity from its own file is the
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

from . import Context, PlanError, finish
from .doc import Doc, instance, label, why
from .neighbours import (anr_budget, distinguish, from_text, lte_enbs, number, parse_plmn, plmn_text, same_node,
                         sources)
from .sites import NRB, lte_cell
from .transport import check_ip, lte_cplane, reachable

ID = "neighbour-enb"
TITLE = "Add a neighbour eNB (X2)"
GROUP = "Neighbours"
SUMMARY = "Add another LTE site as an X2 neighbour: its cells, and relations to them from this eNB's cells."
UI = "form"
KEYWORDS = "neighbour neighbor X2 adjacent eNodeB eNB cell relation handover LNADJ LNADJL LNREL IRFIM LNHOIF ANR"

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
    own = instance(enb["dn"])
    return sources(ctx, "enbs", lambda e: not e["cells"] or e["id"] == own, ("id", "plmn", "ip", "cells"))


def _existing(lnadjs: list[dict], enb_id: Optional[str], plmn: Optional[dict]) -> Optional[dict]:
    """The LNADJ for this neighbour: its eNB id and PLMN (the global eNB id)."""
    return next((m for m in lnadjs if m["p"].get("adjEnbId") == enb_id and same_node(m, "plmnId", plmn)), None)


def available(ctx: Context) -> Optional[str]:
    if _enbs(ctx):
        return None
    return "This file has no LTE eNB with cells (LNBTS and LNCEL)."


def setup(ctx: Context) -> dict:
    site = ctx.site
    targets, sources, nb_cells, own_cells, plmns, earfcns, tacs, bws, bw_opts = [], {}, {}, {}, {}, {}, {}, {}, {}
    for enb in _enbs(ctx):
        dn = enb["dn"]
        cells = [lte_cell(site, c) | {"dn": c["dn"]} for c in site.child(dn, "LNCEL")
                 if c["p"].get("lcrId") not in (None, "")]
        lnadjs = site.child(dn, "LNADJ")
        targets.append({"value": dn, "key": dn, "label": f"{label(dn)} · eNB {instance(dn)}"
                        + (f" · {enb['p']['enbName']}" if enb["p"].get("enbName") else ""),
                        "details": [f"{len(cells)} cell{'s' if len(cells) != 1 else ''}, {len(lnadjs)} neighbour "
                                    f"eNB{'s' if len(lnadjs) != 1 else ''}."]})
        opts, tails, found = [], [], _sources(ctx, enb)
        for e in found:
            have = _existing(lnadjs, e["id"], e["plmn"])
            details = [from_text(e), f"PLMN {plmn_text(e['plmn']) or '?'}, X2 C-plane {e['ip'] or 'not in that file'}."]
            details += [_cell_text(c).capitalize() + "." for c in e["cells"][:6]]
            if have:
                details.append(f"Already a neighbour ({label(have['dn'])}): what's missing is added.")
            opts.append({"value": e["key"], "key": e["key"], "group": "Sites in the tool", "details": details,
                         "label": f"eNB {e['id']}" + (f" {e['name']}" if e.get("name") else "")})
            tails.append(f"{len(e['cells'])} cell{'s' if len(e['cells']) != 1 else ''}"
                         + (" · already a neighbour" if have else ""))
            nb_cells[e["key"]] = [{"value": c["lcrId"], "label": _cell_text(c)} for c in e["cells"]]
        distinguish(opts, found, tails)
        opts.append({"value": MANUAL, "key": MANUAL, "group": "By hand", "label": "Enter the neighbour by hand",
                     "details": ["One cell at a time: run it again with the same eNB id to add another."]})
        sources[dn] = opts
        own_cells[dn] = [{"value": c["dn"], "label": f"{label(c['dn'])} · PCI {c['pci']} · EARFCN {c['earfcn']}"
                          + (f" · {c['name']}" if c.get("name") else "")} for c in cells]
        plmns[dn] = plmn_text({k: enb["p"].get(k) for k in ("mcc", "mnc", "mncLength")})
        earfcns[dn] = cells[0]["earfcn"] or ""
        tacs[dn] = cells[0]["tac"] or ""
        bw_opts[dn] = [{"value": b, "label": b} for b in BANDWIDTHS]
        bws[dn] = cells[0]["bw"] if cells[0]["bw"] in BANDWIDTHS else "20 MHz"
    manual = {"field": "source", "equals": MANUAL}
    return {
        "intro": "Adds the other eNB (LNADJ), its cells (LNADJL) and a relation (LNREL) from each cell you pick "
                 "here to each of its cells, with the carrier settings a neighbour on another EARFCN needs.",
        "fields": [
            {"id": "target", "label": "This eNB", "type": "select", "options": targets,
             "default": targets[0]["value"] if len(targets) == 1 else None},
            {"id": "source", "label": "Neighbour", "type": "select", "dependsOn": "target", "optionsByKey": sources},
            {"id": "cells", "label": "Its cells", "type": "checks", "dependsOn": "source", "optionsByKey": nb_cells},
            {"id": "enbId", "label": "Neighbour eNB id", "type": "text", "showIf": manual, "placeholder": "0-1048575"},
            {"id": "ip", "label": "Its X2 C-plane address", "type": "text", "showIf": manual,
             "placeholder": "10.0.1.47"},
            {"id": "plmn", "label": "Its PLMN (MCC-MNC)", "type": "text", "showIf": manual, "dependsOn": "target",
             "defaultByKey": plmns, "placeholder": "310-410"},
            {"id": "lcrId", "label": "Cell lcrId (the ECGI cell id)", "type": "text", "showIf": manual,
             "placeholder": "0-255"},
            {"id": "pci", "label": "Cell PCI", "type": "text", "showIf": manual, "placeholder": "0-503"},
            {"id": "earfcn", "label": "Cell DL EARFCN", "type": "text", "showIf": manual, "dependsOn": "target",
             "defaultByKey": earfcns},
            {"id": "tac", "label": "Cell TAC", "type": "text", "showIf": manual, "dependsOn": "target",
             "defaultByKey": tacs},
            {"id": "bw", "label": "Cell bandwidth", "type": "select", "showIf": manual, "dependsOn": "target",
             "optionsByKey": bw_opts, "defaultByKey": bws},
            {"id": "from", "label": "Relations from these cells", "type": "checks", "dependsOn": "target",
             "optionsByKey": own_cells},
        ],
    }


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
        match = next((e for e in _sources(ctx, enb) if e["key"] == src), None)
        if not match:
            raise PlanError(["Pick the neighbour eNB."])
        picked = set(inputs.get("cells") or [c["lcrId"] for c in match["cells"]])
        nb = {"id": match["id"], "plmn": match["plmn"], "ip": match["ip"], "rlf": match["rlf"],
              "cells": [c for c in match["cells"] if c["lcrId"] in picked], "from": match["file"]}
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
    if nb.get("id") == instance(enb["dn"]):
        problems.append(f"eNB {nb['id']} is this eNB.")
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
    enb = next((m for m in _enbs(ctx) if m["dn"] == inputs.get("target")), None)
    if not enb:
        raise PlanError(["Pick this file's eNB."])
    nb = _neighbour(ctx, enb, inputs)
    cells = {c["dn"]: c for c in site.child(enb["dn"], "LNCEL") if c["p"].get("lcrId") not in (None, "")}
    picked = inputs.get("from")
    chosen = [cells[d] for d in (picked if picked is not None else cells) if d in cells]
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

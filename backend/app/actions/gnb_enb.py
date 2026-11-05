"""
Add an LTE eNB to a 5G gNB as a neighbour: what the gNB needs to hand
over, reselect and redirect to the eNB's carriers, and, when picked, the
X2 link to it. The gNB side of "Add a neighbour eNB": neighbour_enb.py
hands a gNB here.

LTE neighbour cells aren't objects on the NR side: no file in the tool,
and no class in the catalog, has one. The gNB learns them from UE reports
(ANR), and its handover to LTE goes through the core (5GS to EPS handover
over N26, TS 23.502), not X2. The corpus splits cleanly: the 27 production
gNBs do all of it and the other 59 none of it, so what is written is
production's set.

Per EARFCN of the picked cells of the eNB, on the picked NR cells, through
the carrier action's planner (carrier.py: the cell's own object of the
kind, else another file's, else production's):
  - an NRHOIR for the EARFCN (the B2 measurement for handover to LTE),
    named in each cell's nrhoirDNList;
  - an NRLIM on the system information profile the cells broadcast (SIB5,
    idle-mode reselection), which then schedules SIB5; a cell without a
    profile gets production's, where its release has the class;
  - an NRREDRT for a cell that redirects to no LTE carrier yet, to the
    first EARFCN: each production cell redirects to one, the carrier its
    NRLIM and NRHOIR name. A cell redirecting elsewhere keeps it.
On the gNB (NRBTS), what the 27 have on and the 59 off: actInterRatHoSA
(inter-RAT handover in SA), actInterRatHoSADlDataForward (its downlink
data forwarding) and actSaUeBasedAnrEutra (UE-based ANR for LTE
neighbours, which is how the gNB learns the eNB's cells), each where its
release has the switch; carrier.py turns on actRedirect with an NRREDRT. ANR needs the gNB's NRANR:
a missing one is added as production's NRANR-1 (alike on all 27).

The X2 link, when picked (EN-DC with the eNB as master): an LTEENB with
eNodeBId, ipAddr (the eNB's X2 C-plane address), localCuIpAddr (this
gNB's own X2 C-plane address, as in all 3 files with an LTEENB),
x2LinkLock unlocked and enbPlmn. x2LinkStatus is the link's state (not
modifiable on LNADJ, by the dictionary), so it isn't written. None of the
27 production gNBs plans one, so it is off by default. Ids from 1; the
LTEENB with the eNB's address, else its id and PLMN, is updated instead.
"""
from __future__ import annotations

from typing import Optional

from . import Context, PlanError, carrier, finish
from .doc import Doc, instance, label, release_of, why
from .neighbours import (here, lookup, number, own_addresses, parse_plmn, picked, plmn_text, same_node, same_plmn,
                         sources)
from .sites import nr_cell, x2_address
from .transport import check_ip, reachable

MANUAL = "manual-nr"
X2 = "x2"
SWITCHES = (
    ("actInterRatHoSA", "inter-RAT handover in SA, which the NRHOIR measures for", "true"),
    ("actInterRatHoSADlDataForward", "downlink data forwarding on that handover", "true"),
    ("actSaUeBasedAnrEutra", "UE-based ANR for LTE neighbours: the gNB learns the eNB's cells from UE reports",
     "true"),
)
EVIDENCE = "on in all 27 production gNBs that hand over to LTE, off in all 59 that don't."
NRANR = {"actAutoEutraNbRemoval": "true", "actAutoNrNbRemoval": "true", "autoRecheckAttempts": "0",
         "autoRecheckInterval": "30", "consecHoFailThres": "1", "consecHoFailThresEutra": "3",
         "consecXnResolveFailThres": "3"}


def gnbs(site) -> list[dict]:
    """The gNBs with at least one cell."""
    return [m for m in site.of("NRBTS") if m["dn"].count("/") == 1
            and any(c["p"].get("lcrId") not in (None, "") for c in site.child(m["dn"], "NRCELL"))]


def enb_sources(ctx: Context) -> list[dict]:
    """eNBs to offer: this file's (co-sited) first, then the other files'."""
    skip = lambda e: not e["cells"]  # noqa: E731
    return here(ctx, "enbs", skip) + sources(ctx, "enbs", skip, ("id", "plmn", "ip", "cells"))


def _cells(site, gnb: dict) -> list[dict]:
    return [c for c in site.child(gnb["dn"], "NRCELL") if c["p"].get("lcrId") not in (None, "")]


def _lteenb(site, gnb: dict, ip: Optional[str], enb_id: Optional[str], plmn: Optional[dict]) -> Optional[dict]:
    """The LTEENB for this eNB: the one with its address, else the one with
    its id and PLMN."""
    for m in site.child(gnb["dn"], "LTEENB"):
        if ip and (m["p"].get("ipAddr") or "").lower() == ip.lower():
            return m
    for m in site.child(gnb["dn"], "LTEENB"):
        if enb_id and m["p"].get("eNodeBId") == enb_id and same_node(m, "enbPlmn", plmn):
            return m
    return None


def target(ctx: Context, gnb: dict) -> dict:
    site = ctx.site
    dn, cells = gnb["dn"], _cells(ctx.site, gnb)
    name = gnb["p"].get("btsName") or gnb["p"].get("nrBtsName")
    lims = sorted({m["p"].get("carrierFreq") for m in site.of("NRLIM", dn)} - {None}, key=int)
    hoirs = sorted({m["p"].get("earfcnValue") for m in site.child(dn, "NRHOIR")} - {None}, key=int)
    return {"value": dn, "key": dn, "group": "5G gNB", "label": f"{label(dn)} · gNB {instance(dn)}"
            + (f" · {name}" if name else ""),
            "details": [f"{len(cells)} NR cell{'s' if len(cells) != 1 else ''}. LTE carriers: "
                        + (f"handover to EARFCN {', '.join(hoirs)}" if hoirs else "no handover (NRHOIR)") + ", "
                        + (f"reselection to {', '.join(lims)}." if lims else "no reselection (NRLIM)."),
                        f"{len(site.child(dn, 'LTEENB'))} X2 link{'s' if len(site.child(dn, 'LTEENB')) != 1 else ''} "
                        "to eNBs (LTEENB)."]}


def setup_parts(ctx: Context, found: list[dict]) -> dict:
    """The gNB targets' share of the form: per gNB, its sources' state, its
    NR cells, the X2 default, its PLMN."""
    site = ctx.site
    out = {"targets": [], "states": {}, "nr_cells": {}, "x2": {}, "x2_default": {}, "x2_addresses": {}, "plmns": {},
           "earfcns": {}}
    lte_here = next((x["earfcn"] for e in here(ctx, "enbs", lambda e: not e["cells"]) for x in e["cells"]
                     if x.get("earfcn")), "")
    for gnb in gnbs(site):
        dn = gnb["dn"]
        out["targets"].append(target(ctx, gnb))
        hoirs = {m["p"].get("earfcnValue") for m in site.child(dn, "NRHOIR")}
        states = {}
        for e in found:
            have = _lteenb(site, gnb, e["ip"], e["id"], e["plmn"])
            earfcns = {c.get("earfcn") for c in e["cells"]} - {None, ""}
            states[e["key"]] = ("already a neighbour" if earfcns and earfcns <= hoirs else
                                "X2 link already" if have else None)
        out["states"][dn] = states
        out["nr_cells"][dn] = [{"value": c["dn"], "label": f"{label(c['dn'])} · PCI {c['p'].get('physCellId') or '?'}"
                                f" · NR-ARFCN {nr_cell(site, gnb, c)['arfcn'] or '?'}"
                                + (f" · {c['p']['cellName']}" if c["p"].get("cellName") else "")}
                               for c in _cells(site, gnb)]
        own = x2_address(site, gnb)
        out["x2"][dn] = [{"value": X2, "label": "An X2 link to it (LTEENB), for EN-DC with it as master",
                          "details": ["None of the 27 production gNBs plans one: handover to LTE doesn't use X2."
                                      + (f" This gNB's end is {own} (its X2 C-plane)." if own else "")]}]
        out["x2_default"][dn] = [X2] if site.child(dn, "LTEENB") else []
        out["x2_addresses"][dn] = own
        mine = next((p["p"] for p in site.child(dn, "NRPLMN") if p["p"].get("mcc")), None)
        out["plmns"][dn] = plmn_text(mine)
        out["earfcns"][dn] = lte_here
    return out


def _enb(ctx: Context, inputs: dict, want_x2: bool) -> dict:
    """The eNB as {id, plmn, ip, carriers, from}."""
    src = inputs.get("source") or ""
    problems: list[str] = []
    if src == MANUAL:
        nb = {"id": number(inputs.get("enbId"), 0, 1048575, "The eNB id", problems), "from": None}
        ip = (inputs.get("enbIp") or "").strip()
        problem = check_ip(ip)[0] if ip else None
        if problem:
            problems.append(problem)
        nb["ip"] = ip or None
        nb["plmn"] = parse_plmn(inputs.get("plmn") or "")
        if not nb["plmn"]:
            problems.append("Enter the PLMN as MCC-MNC, for example 310-410 or 001-01.")
        e = number(inputs.get("earfcn"), 0, carrier.EARFCN_MAX, "The EARFCN", problems)
        nb["carriers"] = [e] if e else []
    else:
        match = lookup(ctx, enb_sources(ctx), src, "enbs")
        if not match:
            raise PlanError(["Pick the neighbour eNB."])
        wanted = inputs.get("cells")
        wanted = {c["lcrId"] for c in match["cells"]} if wanted is None else set(wanted)
        cells = [c for c in match["cells"] if c["lcrId"] in wanted]
        if not cells:
            problems.append("Pick at least one of its cells: their EARFCNs are the carriers added.")
        nb = {"id": match["id"], "plmn": match["plmn"], "ip": match["ip"], "from": match["file"],
              "carriers": list(dict.fromkeys(c["earfcn"] for c in cells if c.get("earfcn")))}
        if cells and not nb["carriers"]:
            problems.append(f"{match['file']} doesn't say the EARFCN of eNB {match['id']}'s cells.")
        if want_x2 and not nb["ip"]:
            problems.append(f"{match['file']} has no C-plane address for eNB {match['id']}, which the X2 link needs. "
                            "Enter the eNB by hand, or leave the X2 link out.")
        if want_x2 and not nb["plmn"]:
            problems.append(f"{match['file']} doesn't say eNB {match['id']}'s PLMN (LNBTS mcc/mnc).")
    if want_x2 and src == MANUAL and not nb.get("ip"):
        problems.append("Enter the eNB's X2 C-plane address for the X2 link, or leave the X2 link out.")
    if problems:
        raise PlanError(problems)
    return nb


class _Gnb:
    def __init__(self, ctx: Context, doc: Doc, gnb: dict, nb: dict):
        self.ctx, self.doc, self.site, self.gnb, self.nb = ctx, doc, ctx.site, gnb, nb
        self.index = ctx.release_index()
        self.release = release_of(gnb["version"])
        self.notes: list[str] = []
        self.cp = carrier._Plan(ctx, doc, "ho-nr", {})
        self.focus: Optional[str] = None

    def has(self, cls: str, param: Optional[str] = None) -> Optional[bool]:
        """Whether some file of the gNB's release has the class (and sets the
        parameter); None when there is no release index."""
        if not self.index:
            return None
        known = self.index.get(self.release, {}).get(cls)
        return known is not None and (param is None or param in known)

    def carriers(self, cells: list[dict]) -> None:
        site, cp, nb = self.site, self.cp, self.nb
        who = f"eNB {nb['id']}"
        no_profile = []
        for e in nb["carriers"]:
            cp.inputs = {"earfcn": e}
            for c in cells:
                cp.add(c, "NRHOIR", e, f"handover to {who}'s EARFCN {e}")
            profiles = {}
            for c in cells:
                prof = cp.profile_of(c)
                if prof:
                    profiles.setdefault(prof["dn"], prof)
                elif label(c["dn"]) not in no_profile:
                    no_profile.append(label(c["dn"]))
            for prof in profiles.values():
                cp.add(prof, "NRLIM", e, f"reselection to {who}'s EARFCN {e}")
        if no_profile:
            self.notes.append(f"{', '.join(no_profile)} broadcast{'s' if len(no_profile) == 1 else ''} no system "
                              f"information profile, and no file of {self.release} has one (NRSYSINFO_PROFILE), so "
                              "none is added: idle UEs get no LTE carrier to reselect to (NRLIM).")
        first = nb["carriers"][0]
        cp.inputs = {"earfcn": first}
        for c in cells:
            have = [m["p"].get("redirFreqEutra") for m in site.child(c["dn"], "NRREDRT")]
            if not have:
                cp.add(c, "NRREDRT", first, f"redirect to {who}'s EARFCN {first}")
            elif not set(have) & set(nb["carriers"]):
                self.notes.append(f"{label(c['dn'])} keeps its redirect to EARFCN {', '.join(sorted(set(have)))} "
                                  "(NRREDRT): a cell redirects to one LTE carrier, as production's do.")
        self.focus = cp.focus

    def switches(self, switches: tuple, evidence: str) -> None:
        """NRBTS switches on, where the gNB's release has them."""
        dn, doc = self.gnb["dn"], self.doc
        missing = []
        for name, what, on in switches:
            if doc.get(dn, name) == on:
                continue
            if self.has("NRBTS", name) is False:
                missing.append(name)
                continue
            doc.set(dn, name, on, why("neighbour", f"{what[0].upper() + what[1:]}: {evidence}", "files"))
        if missing:
            self.notes.append(f"No file of {self.release} has {', '.join(missing)} on the NRBTS, so "
                              f"{'it is' if len(missing) == 1 else 'they are'} left out: check how this release "
                              "turns on handover to LTE.")

    def anr(self, param: str, what: str) -> None:
        """The gNB's NRANR, with `param` on: a missing one as production's."""
        site, doc, dn = self.site, self.doc, self.gnb["dn"]
        have = site.child(dn, "NRANR")
        if have:
            if have[0]["p"].get(param) not in (None, "true"):
                doc.set(have[0]["dn"], param, "true",
                        why("neighbour", f"ANR removes {what} it no longer sees, as production's NRANR does (27 of "
                                         "27).", "files"))
            return
        info = doc.class_info("NRBTS")
        prefix = (info[0] if info and ":" in info[0] else "com.nokia.srbts.nrbts:NRBTS").rsplit(":", 1)[0]
        first = not doc.of_class("NRANR")
        params = NRANR
        if self.has("NRANR"):
            known = self.index[self.release]["NRANR"]
            params = {k: v for k, v in NRANR.items() if k in known}
        doc.create(dn, "NRANR", "1", list(params.items()), full_class=f"{prefix}:NRANR" if first else None,
                   version=self.gnb["version"] if first else None,
                   w=why("neighbour", f"ANR, for the {what} the gNB learns from UE reports: production's NRANR-1 "
                                      "(alike on all 27 production gNBs).", "files"))
        if self.has("NRANR") is False and self.release != "NRBTSCL25R2":
            self.notes.append(f"No file of {self.release} has an NRANR: it is written as production's (NRBTSCL25R2). "
                              "Check this release takes it.")

    def x2(self) -> str:
        nb, doc, gnb = self.nb, self.doc, self.gnb
        src = f"from {nb['from']}" if nb["from"] else "as entered"
        own = x2_address(self.site, gnb)
        existing = _lteenb(self.site, gnb, nb["ip"], nb["id"], nb["plmn"])
        if existing:
            dn, p = existing["dn"], existing["p"]
            if p.get("eNodeBId") not in (None, "", nb["id"]):
                raise PlanError([f"{label(dn)} has {p.get('ipAddr')} for eNB {p['eNodeBId']}, not eNB {nb['id']}. "
                                 "Check which eNB is at that address."])
            if (p.get("ipAddr") or "").lower() != nb["ip"].lower():
                doc.set(dn, "ipAddr", nb["ip"], why("neighbour", f"eNB {nb['id']}'s X2 C-plane address, {src}.",
                                                    "choice"))
            if p.get("x2LinkLock") == "locked":
                doc.set(dn, "x2LinkLock", "unlocked", why("neighbour", f"The X2 link to eNB {nb['id']} in use.",
                                                          "choice"))
            return dn
        info = doc.class_info("NRBTS")
        prefix = (info[0] if info and ":" in info[0] else "com.nokia.srbts.nrbts:NRBTS").rsplit(":", 1)[0]
        first = not doc.of_class("LTEENB")
        params = [("eNodeBId", nb["id"]), ("ipAddr", nb["ip"])] + ([("localCuIpAddr", own)] if own else []) + [
            ("x2LinkLock", "unlocked")]
        dn = doc.create(gnb["dn"], "LTEENB", doc.next_free(gnb["dn"], "LTEENB", 1), params,
                        full_class=f"{prefix}:LTEENB" if first else None, version=gnb["version"] if first else None,
                        w=why("neighbour", f"X2 to eNB {nb['id']} at {nb['ip']}, {src}, unlocked. localCuIpAddr is "
                                           "this gNB's own X2 C-plane address, as in all 3 files with an LTEENB.",
                              "files"))
        doc.add_item(dn, "enbPlmn", [("mcc", nb["plmn"]["mcc"]), ("mnc", nb["plmn"]["mnc"]),
                                     ("mncLength", nb["plmn"]["mncLength"])],
                     why("neighbour", f"eNB {nb['id']}'s PLMN.", "choice"))
        if not own:
            self.notes.append("This gNB's X2 C-plane address isn't in the file (NRBTS x2Cplane), so localCuIpAddr "
                              "isn't written: set it to the gNB's own end of the link.")
        if self.has("LTEENB") is False and self.release != "NRBTSCL25R2":
            self.notes.append(f"No file of {self.release} has an LTEENB: it is written as the NRBTSCL25R2 files do. "
                              "Check this release takes it.")
        return dn


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    gnb = next((m for m in gnbs(site) if m["dn"] == inputs.get("target")), None)
    if not gnb:
        raise PlanError(["Pick this file's gNB."])
    want_x2 = X2 in (inputs.get("x2") or [])
    nb = _enb(ctx, inputs, want_x2)
    if want_x2 and nb["ip"].lower() in own_addresses(site):
        raise PlanError([f"{nb['ip']} is one of this BTS's own addresses, so no X2 link to it is planned: leave the "
                         "X2 link out" + (" (the eNB is co-sited)." if (nb["from"] or "") == "this file" else ".")])
    by_dn = {c["dn"]: c for c in _cells(site, gnb)}
    cells = picked(by_dn, inputs, "nrCells")
    if nb["carriers"] and not cells:
        raise PlanError(["Pick at least one cell of this gNB to hand over and reselect to the eNB's carriers."])
    who = f"eNB {nb['id']}"

    doc = Doc(ctx.raw)
    p = _Gnb(ctx, doc, gnb, nb)
    if nb["carriers"]:
        p.carriers(cells)
        if p.cp.skipped.get("no NRHOIR to copy in any file") or p.cp.skipped.get("no NRREDRT to copy in any file"):
            raise PlanError([f"No {cls} to copy in any file." for cls in ("NRHOIR", "NRREDRT")
                             if p.cp.skipped.get(f"no {cls} to copy in any file")])
        p.switches(SWITCHES, EVIDENCE)
        p.anr("actAutoEutraNbRemoval", "LTE neighbours")
    lteenb = p.x2() if want_x2 else None
    notes = carrier.notes(p.cp) + p.notes
    mine = next((m["p"] for m in site.child(gnb["dn"], "NRPLMN") if m["p"].get("mcc")), None)
    if mine and nb["plmn"] and not same_plmn(mine, nb["plmn"]):
        notes.append(f"{who}'s PLMN is {plmn_text(nb['plmn'])}, this gNB's {plmn_text(mine)}.")
    if want_x2 and reachable(site, nb["ip"]) is None:
        notes.append(f"Nothing in this file reaches {nb['ip']}: it is on none of the BTS's subnets and no static "
                     "route covers it. Add a route, or the X2 link won't come up.")
    carriers = ", ".join(nb["carriers"])
    confirm = []
    if nb["carriers"]:
        confirm.append(f"The AMF has N26 to the MME of {who}, or handover to it fails (UEs are then redirected "
                       "instead).")
    if want_x2:
        confirm.append(f"{who} at {nb['ip']} has this gNB as an EN-DC gNB (LNADJGNB), on SCTP port 36422.")
    if not nb["from"]:
        confirm.append(f"EARFCN {carriers or '?'} is {who}'s own carrier.")
    return finish(ctx, doc, {
        "label": f"Neighbour eNB {nb['id']} on {label(gnb['dn'])}",
        "summary": (f"Handover, reselection and redirect to EARFCN {carriers}" if carriers else "")
                   + (" and " if carriers and want_x2 else "") + ("the X2 link" if want_x2 else ""),
        "notes": notes,
        "confirm": confirm,
        "focus": lteenb or p.focus,
    })

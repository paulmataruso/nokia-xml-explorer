"""
Add a neighbour gNB, to a 5G gNB or an LTE eNB. To an eNB: the X2 link,
relations to its cells, and the cells' reselection and redirect to its
NR carriers (endc_gnb.py, which this hands an eNB to). To a gNB, over Xn,
as follows.

An XNLINK naming the other gNB's Xn C-plane address. NR neighbour cells
aren't objects in these files: no file in the tool, and no class in the
catalog, has one. The gNB learns them over Xn and from UEs (NRANR).

The other gNB comes from another site's file in the tool (its Xn-C plane
and cells, sites.summary) or its address is typed in, with its carrier if
known.

In a run (run.py), "More neighbour gNBs" adds others the same way, with
all their cells, and "Their end" adds this site to each neighbour's own
file: a gNB gets this gNB's Xn link (here), an eNB's gNB its eNB
(neighbour_enb), relating the cells each end picked here.

What is written (no dictionary in the tool covers XNLINK; the corpus is 27
production 25R2 SA gNBs with 15 XNLINKs each):
  - cPlaneIpAddr and cPlaneIpAddrCtrl oamControlled. 270 of the 405 links
    are oamControlled, the planned ones; the gnbControlled ones carry ids
    above 100, the way ANR-learned LTE neighbours do. A learned link to the
    same address is made oamControlled instead of adding a second.
  - Not localCuIpAddr: it is this gNB's own end of the link (SERVEDAMF and
    LTEENB carry the gNB's own address there in all 16 objects that write
    it), which the gNB fills in.
  - Ids: the lowest free from 2, as in every file with XNLINKs.
  - For a neighbour carrier this gNB neither serves nor lists, an NRIRFIM
    (SIB4 reselection) on the profile its cells broadcast, through the
    carrier action's planner (carrier.py: SIB4 scheduled, and production's
    profile for cells with none).
  - On the gNB, what the 27 production gNBs with Xn links have on and the
    59 without off: actIntraFreqHoSA (handover between the gNBs) and
    actSaUeBasedAnrNr (UE-based ANR, how the gNB learns the neighbour's
    cells), each where its release has it, and the NRANR that ANR needs
    (production's NRANR-1 when missing). Handover to another NR carrier
    (actInterFreqHoSA) is off in every file, so it isn't turned on, and a
    note says so.
"""
from __future__ import annotations

from typing import Optional

from . import Context, PlanError, carrier, endc_gnb, finish, gnb_enb
from .doc import Doc, instance, label, why
from .links import Site
from .neighbours import (BOTH, distinguish, far, from_text, group, here, id_clash, lcr_ids, lookup, lte_enbs, nearby,
                         number, own_addresses, plmn_text, run_fields, same_plmn, sources)
from .sites import nr_cell, xn_address
from .transport import check_ip, reachable

ID = "neighbour-gnb"
TITLE = "Add a neighbour gNB"
GROUP = "Neighbours"
SUMMARY = ("Add a 5G site as a neighbour: to a gNB over Xn (its cells are then learned), or to an eNB (the X2 link, "
           "relations, and reselection and redirect to its NR carriers).")
UI = "form"
KEYWORDS = ("neighbour neighbor Xn X2 5G NR gNB gNodeB adjacent handover reselection redirect XNLINK NRIRFIM SA "
            "EN-DC ENDC NSA eNB eNodeB LTE LNADJGNB LNRELGNBCELL NRFIM SIB24 REDRT "
            "neighbour cell roam roaming mobility idle")

MANUAL = "manual-xn"
FIRST_ID = 2
SWITCHES = (
    ("actIntraFreqHoSA", "handover in SA to the neighbour gNB's cells on this gNB's carrier", "true"),
    ("actSaUeBasedAnrNr", "UE-based ANR for NR: the gNB learns the neighbour's cells from UE reports", "true"),
)
EVIDENCE = "on in all 27 production gNBs with Xn links, off in all 59 without."


def _gnbs(site: Site) -> list[dict]:
    return [m for m in site.of("NRBTS") if m["dn"].count("/") == 1]


def _cell_text(c: dict) -> str:
    return (f"cell {c['lcrId']} · PCI {c.get('pci') or '?'} · NR-ARFCN {c.get('arfcn') or '?'}"
            + (f" · {c['name']}" if c.get("name") else ""))


def _sources(ctx: Context, gnb: dict) -> list[dict]:
    own, mine = instance(gnb["dn"]), own_addresses(ctx.site)
    empty = lambda e: not e["cells"] and not e["xn"]  # noqa: E731
    # As for eNBs: at this BTS's own address is this BTS in another export; its id alone is another BTS.
    return (here(ctx, "gnbs", lambda e: e["id"] == own or empty(e))
            + sources(ctx, "gnbs", lambda e: empty(e) or (e.get("xn") or "").strip().lower() in mine,
                      ("id", "plmn", "xn", "cells")))


def _link(site: Site, gnb: dict, ip: Optional[str]) -> Optional[dict]:
    return next((m for m in site.child(gnb["dn"], "XNLINK")
                 if ip and (m["p"].get("cPlaneIpAddr") or "").lower() == ip.lower()), None)


def _plmn(site: Site, gnb: dict) -> Optional[dict]:
    return next((m["p"] for m in site.child(gnb["dn"], "NRPLMN") if m["p"].get("mcc")), None)


def available(ctx: Context) -> Optional[str]:
    if _gnbs(ctx.site) or lte_enbs(ctx.site):
        return None
    return "This file has no 5G gNB (NRBTS) or LTE eNB with cells."


def setup(ctx: Context) -> dict:
    site = ctx.site
    lte = endc_gnb.setup_parts(ctx)
    both = bool(_gnbs(site)) and bool(lte["targets"])
    targets, srcs = [], dict(lte["sources"])
    for gnb in _gnbs(site):
        dn = gnb["dn"]
        links = site.child(dn, "XNLINK")
        planned = sum(1 for m in links if m["p"].get("cPlaneIpAddrCtrl") == "oamControlled")
        ncells = len(site.child(dn, "NRCELL"))
        name = gnb["p"].get("btsName") or gnb["p"].get("nrBtsName")
        targets.append({"value": dn, "key": dn, "label": f"{label(dn)} · gNB {instance(dn)}"
                        + (f" · {name}" if name else ""),
                        "details": [f"{ncells} cell{'s' if ncells != 1 else ''}, {len(links)} Xn link"
                                    f"{'s' if len(links) != 1 else ''}"
                                    + (f" ({planned} planned, {len(links) - planned} learned)." if links else "."),
                                    f"Xn C-plane {xn_address(site, gnb) or 'not in this file'}."]}
                       | ({"group": "5G gNB"} if both else {}))
        opts, tails, found = [], [], nearby(site, xn_address(site, gnb), _sources(ctx, gnb), address="xn")
        for e in found:
            have = _link(site, gnb, e["xn"])
            details = [from_text(e), f"PLMN {plmn_text(e['plmn']) or '?'}, Xn C-plane {e['xn'] or 'not in that file'}."]
            details += [_cell_text(c).capitalize() + "." for c in e["cells"][:6]]
            if have:
                details.append(f"Already an Xn neighbour ({label(have['dn'])}, {have['p'].get('cPlaneIpAddrCtrl')}).")
            clash = id_clash("gNB", e["id"], e["plmn"], instance(gnb["dn"]), _plmn(site, gnb))
            if clash:
                details.append(clash)
            opts.append({"value": e["key"], "key": e["key"], "details": details, "group": group(e),
                         "label": f"gNB {e['id']}" + (f" {e['name']}" if e.get("name") else "")})
            tails.append(f"{len(e['cells'])} cell{'s' if len(e['cells']) != 1 else ''}"
                         + (" · already a neighbour" if have else "") + (" · same gNB id" if clash else ""))
        distinguish(opts, found, tails, address="xn")
        opts.append({"value": MANUAL, "key": MANUAL, "group": "By hand", "label": "Enter its address by hand",
                     "details": ["The other gNB's Xn C-plane address, and its carrier if this gNB doesn't serve it."]})
        srcs[dn] = opts
    targets += [t | ({"group": "LTE eNB"} if both else {}) for t in lte["targets"]]
    x2 = {"field": "source", "equals": endc_gnb.MANUAL}
    typed = {"field": "source", "in": [endc_gnb.MANUAL, MANUAL]}
    return {
        "intro": "On a gNB: adds an Xn link (XNLINK) to the other gNB, which exchanges its cells over Xn, and "
                 "reselection to its carrier where this gNB lacks it. On an eNB: adds the X2 link to the gNB "
                 "(LNADJGNB), a relation (LNRELGNBCELL) from each LTE cell you pick to each of its NR cells, and "
                 "the cells' reselection and redirect to its NR carriers.",
        "fields": [
            {"id": "target", "label": "This site", "type": "select", "options": targets,
             "default": targets[0]["value"] if len(targets) == 1 else None},
            {"id": "source", "label": "Neighbour gNB", "type": "select", "dependsOn": "target", "optionsByKey": srcs},
            {"id": "cells", "label": "Relations to its cells", "type": "checks", "dependsOn": "source",
             "optionsByKey": lte["nb_cells"], "optional": True},
            {"id": "gnbId", "label": "gNB id", "type": "text", "showIf": x2, "placeholder": "500078"},
            {"id": "idLength", "label": "gNB id length (bits)", "type": "text", "showIf": x2,
             "dependsOn": "target", "defaultByKey": lte["lengths"], "placeholder": "22-32",
             "hint": "The gNB's own gNbIdLength (NRBTS). The NR cell identity is built from it."},
            {"id": "ip", "label": "Its X2 C-plane address", "type": "text", "showIf": x2, "placeholder": "10.0.1.48"},
            {"id": "xnIp", "label": "Its Xn C-plane address", "type": "text",
             "showIf": {"field": "source", "equals": MANUAL}, "placeholder": "10.0.1.48"},
            {"id": "plmn", "label": "Its PLMN (MCC-MNC)", "type": "text", "showIf": x2, "dependsOn": "target",
             "defaultByKey": lte["plmns"], "placeholder": "310-410"},
            {"id": "lcrIds", "label": "Relations to its cells (lcrIds)", "type": "text", "showIf": x2,
             "optional": True, "placeholder": "1, 2, 3",
             "hint": "Leave empty to add the X2 link only: UE-based ANR then learns the relations."},
            {"id": "ssb", "label": "Its carrier: SSB NR-ARFCN", "type": "text", "showIf": typed, "optional": True,
             "placeholder": "502110",
             "hint": "Where its SSB is (TS 38.331 SIB4 dl-CarrierFreq), for reselection to it. Leave empty to add "
                     "none."},
            {"id": "band", "label": "Its NR band", "type": "text", "showIf": typed, "optional": True,
             "placeholder": "41"},
            {"id": "scs", "label": "Its SSB subcarrier spacing", "type": "select", "showIf": typed, "optional": True,
             "options": [{"value": s, "label": s} for s in carrier.SCS]},
            {"id": "from", "label": "Relations from these cells", "type": "checks", "dependsOn": "target",
             "optionsByKey": lte["own_cells"]},
            *run_fields(srcs, "gNB"),
        ],
    }


def legs(ctx: Context, inputs: dict) -> list[dict]:
    """The run's other changes: the more neighbours on this file, then, with
    "Their end", this site on each neighbour's file: on an eNB, relating its
    picked cells ("from") and the gNB's ("cells")."""
    site, target, src = ctx.site, inputs.get("target") or "", inputs.get("source") or ""
    on_enb = any(e["dn"] == target for e in lte_enbs(site))
    more = [k for k in dict.fromkeys(inputs.get("more") or []) if far(k) and k != src]
    out = [{"file": None, "action": ID, "inputs": {**inputs, "source": k, "cells": None},
            "what": f"gNB {instance(far(k)[1])} as a neighbour too"} for k in more]
    if BOTH not in (inputs.get("both") or []):
        return out
    me = f"{'eNB' if on_enb else 'gNB'} {instance(target)}"
    mine = lcr_ids(site, inputs.get("from"), target, "LNCEL") if on_enb else None
    for k in [src] + more:
        there = far(k)
        if not there:
            continue
        back = {"target": there[1], "source": f"{ctx.key}|{target}"}
        if on_enb:
            back.update(cells=mine, nrCellsLcr=inputs.get("cells") if k == src else None)
        out.append({"file": there[0], "action": "neighbour-enb" if on_enb else ID, "inputs": back,
                    "what": f"{me} as gNB {instance(there[1])}'s neighbour"})
    return out


def _typed_carrier(inputs: dict, problems: list[str]) -> list[dict]:
    ssb = (inputs.get("ssb") or "").strip()
    if not ssb:
        return []
    ssb = number(ssb, 0, carrier.NR_ARFCN_MAX, "The SSB NR-ARFCN", problems)
    band = number(inputs.get("band"), 1, 1024, "The NR band", problems)
    if inputs.get("scs") not in carrier.SCS:
        problems.append("Pick its SSB subcarrier spacing.")
        return []
    return [{"ssb": ssb, "band": band, "scs": inputs["scs"]}] if ssb and band else []


def _neighbour(ctx: Context, gnb: dict, inputs: dict) -> dict:
    """The other gNB as {id, plmn, ip, cells, carriers, from}; id and cells
    are None when typed in."""
    src = inputs.get("source") or ""
    if src == MANUAL:
        problems: list[str] = []
        ip = (inputs.get("xnIp") or "").strip()
        problem = check_ip(ip)[0] if ip else "Enter the other gNB's Xn C-plane address."
        if problem:
            problems.append(problem)
        carriers = _typed_carrier(inputs, problems)
        if problems:
            raise PlanError(problems)
        return {"id": None, "plmn": None, "ip": ip, "cells": None, "carriers": carriers, "from": None}
    match = lookup(ctx, _sources(ctx, gnb), src, "gnbs")
    if not match:
        raise PlanError(["Pick the neighbour gNB."])
    if not match["xn"]:
        raise PlanError([f"{match['file']} has no address on gNB {match['id']}'s planes (NRBTS xnCplane). Enter its "
                         "address by hand instead."])
    carriers = {(c["ssb"], c["band"], c["scs"]): {"ssb": c["ssb"], "band": c["band"], "scs": c["scs"]}
                for c in match["cells"] if c.get("ssb") and c.get("band") and c.get("scs")}
    return {"id": match["id"], "plmn": match["plmn"], "ip": match["xn"], "cells": match["cells"],
            "carriers": list(carriers.values()), "from": match["file"]}


def _reselection(ctx: Context, p: gnb_enb._Gnb, nb: dict, who: str) -> tuple[list[str], list[str]]:
    """An NRIRFIM for each of the neighbour's carriers this gNB neither
    serves nor lists, on the profiles its cells broadcast. Returns the
    carriers it serves and the ones it doesn't."""
    site, gnb = ctx.site, p.gnb
    cells = [c for c in site.child(gnb["dn"], "NRCELL")]
    own = {nr_cell(site, gnb, c)["ssb"] for c in cells} - {None}
    same, other = [], []
    for c in nb["carriers"]:
        if c["ssb"] in own:
            same.append(c["ssb"])
        else:
            other.append(c["ssb"])
    profiles = {}
    for c in cells if other else []:
        prof = p.cp.profile_of(c)
        if prof:
            profiles.setdefault(prof["dn"], prof)
    for c in nb["carriers"]:
        if c["ssb"] in other:
            p.cp.inputs = c
            for prof in profiles.values():
                p.cp.add(prof, "NRIRFIM", c["ssb"], f"reselection to {who}'s carrier, SSB {c['ssb']}")
    if other and not profiles:
        p.notes.append(f"{who}'s cells are on SSB {', '.join(other)}, which this gNB doesn't serve, and its cells "
                       f"broadcast no system information profile, which no file of {p.release} has "
                       "(NRSYSINFO_PROFILE): idle UEs won't reselect to it.")
    return same, other


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    if any(e["dn"] == inputs.get("target") for e in lte_enbs(site)):
        return endc_gnb.plan(ctx, inputs)
    gnb = next((m for m in _gnbs(site) if m["dn"] == inputs.get("target")), None)
    if not gnb:
        raise PlanError(["Pick this file's gNB or eNB."])
    nb = _neighbour(ctx, gnb, inputs)
    clash = id_clash("gNB", nb["id"], nb["plmn"], instance(gnb["dn"]), _plmn(site, gnb))
    if clash:
        raise PlanError([clash])
    if nb["ip"].lower() in own_addresses(site):
        raise PlanError([f"{nb['ip']} is one of this BTS's own addresses."])
    who = f"gNB {nb['id']}" if nb["id"] else nb["ip"]
    src = f"from {nb['from']}" if nb["from"] else "as entered"

    doc = Doc(ctx.raw)
    p = gnb_enb._Gnb(ctx, doc, gnb, nb)
    existing = _link(site, gnb, nb["ip"])
    if existing:
        dn = existing["dn"]
        if existing["p"].get("cPlaneIpAddrCtrl") != "oamControlled":
            doc.set(dn, "cPlaneIpAddrCtrl", "oamControlled",
                    why("xn", f"A planned link to {who}: {existing['p'].get('cPlaneIpAddrCtrl')} is how the gNB marks "
                              "the links it learned.", "files"))
    else:
        inst = doc.next_free(gnb["dn"], "XNLINK", FIRST_ID)
        first = not doc.of_class("XNLINK")
        info = doc.class_info("NRBTS")
        prefix = (info[0] if info and ":" in info[0] else "com.nokia.srbts.nrbts:NRBTS").rsplit(":", 1)[0]
        dn = doc.create(gnb["dn"], "XNLINK", inst, [("cPlaneIpAddr", nb["ip"]), ("cPlaneIpAddrCtrl", "oamControlled")],
                        full_class=f"{prefix}:XNLINK" if first else None, version=gnb["version"] if first else None,
                        w=why("xn", f"Xn to {who + ' at ' + nb['ip'] if nb['id'] else 'the gNB at ' + nb['ip']}, "
                                    f"{src}. oamControlled: the operator keeps the address, as on 270 of the "
                                    "405 links in the files this was built from (the others the gNBs learned).",
                              "files"))
    same, other = _reselection(ctx, p, nb, who)
    p.switches(SWITCHES, EVIDENCE)
    p.anr("actAutoNrNbRemoval", "NR neighbours")
    notes = carrier.notes(p.cp) + p.notes
    if other:
        notes.append(f"Handover to {who}'s cells on SSB {', '.join(other)}, another carrier, needs inter-frequency "
                     "handover (actInterFreqHoSA), which is off in every file in the tool: it isn't turned on, so "
                     "UEs reach them by reselection.")
    mine = _plmn(site, gnb)
    if mine and nb["plmn"] and not same_plmn(mine, nb["plmn"]):
        notes.append(f"gNB {nb['id']}'s PLMN is {plmn_text(nb['plmn'])}, this gNB's {plmn_text(mine)}.")
    if reachable(site, nb["ip"]) is None:
        notes.append(f"Nothing in this file reaches {nb['ip']}: it is on none of the BTS's subnets and no static route "
                     "covers it. Add a route, or the Xn link won't come up.")
    source = xn_address(site, gnb)
    return finish(ctx, doc, {
        "label": f"Xn neighbour {who} on {label(gnb['dn'])}",
        "summary": f"Xn link to {who}" + (f" ({nb['ip']})" if nb["id"] else ""),
        "notes": notes,
        "confirm": [(f"{who} at {nb['ip']}" if nb["id"] else f"The gNB at {nb['ip']}") + " accepts Xn from this gNB"
                    + (f" ({source})" if source else "") + ", on SCTP port 38422, and has an Xn link back."],
        "focus": dn,
    })

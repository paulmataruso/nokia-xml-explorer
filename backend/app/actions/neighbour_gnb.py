"""
Add an Xn neighbour to a 5G gNB: an XNLINK naming the other gNB's Xn
C-plane address. NR neighbour cells aren't objects in these files: no file
in the tool, and no class in the catalog, has one. The gNB learns them over
Xn and from UEs (NRANR).

The other gNB comes from another site's file in the tool (its Xn-C plane,
sites.summary) or its address is typed in.

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
"""
from __future__ import annotations

from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, instance, label, why
from .links import Site
from .neighbours import distinguish, from_text, own_addresses, plmn_text, same_plmn, sources
from .sites import nr_cell, xn_address
from .transport import check_ip, reachable

ID = "neighbour-gnb"
TITLE = "Add a neighbour gNB (Xn)"
GROUP = "Neighbours"
SUMMARY = "Add an Xn link from this gNB to another gNB; their NR cells are then learned over Xn."
UI = "form"
KEYWORDS = "neighbour neighbor Xn 5G NR gNB gNodeB adjacent handover XNLINK SA"

MANUAL = "manual"
FIRST_ID = 2


def _gnbs(site: Site) -> list[dict]:
    return [m for m in site.of("NRBTS") if m["dn"].count("/") == 1]


def _cell_text(c: dict) -> str:
    return (f"cell {c['lcrId']} · PCI {c.get('pci') or '?'} · NR-ARFCN {c.get('arfcn') or '?'}"
            + (f" · {c['name']}" if c.get("name") else ""))


def _sources(ctx: Context, gnb: dict) -> list[dict]:
    own = instance(gnb["dn"])
    return sources(ctx, "gnbs", lambda e: e["id"] == own or (not e["cells"] and not e["xn"]),
                   ("id", "plmn", "xn", "cells"))


def _link(site: Site, gnb: dict, ip: Optional[str]) -> Optional[dict]:
    return next((m for m in site.child(gnb["dn"], "XNLINK")
                 if ip and (m["p"].get("cPlaneIpAddr") or "").lower() == ip.lower()), None)


def _plmn(site: Site, gnb: dict) -> Optional[dict]:
    return next((m["p"] for m in site.child(gnb["dn"], "NRPLMN") if m["p"].get("mcc")), None)


def available(ctx: Context) -> Optional[str]:
    if _gnbs(ctx.site):
        return None
    return "This file has no 5G gNB (NRBTS)."


def setup(ctx: Context) -> dict:
    site = ctx.site
    targets, srcs = [], {}
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
                                    f"Xn C-plane {xn_address(site, gnb) or 'not in this file'}."]})
        opts, tails, found = [], [], _sources(ctx, gnb)
        for e in found:
            have = _link(site, gnb, e["xn"])
            details = [from_text(e), f"PLMN {plmn_text(e['plmn']) or '?'}, Xn C-plane {e['xn'] or 'not in that file'}."]
            details += [_cell_text(c).capitalize() + "." for c in e["cells"][:6]]
            if have:
                details.append(f"Already an Xn neighbour ({label(have['dn'])}, {have['p'].get('cPlaneIpAddrCtrl')}).")
            opts.append({"value": e["key"], "key": e["key"], "group": "Sites in the tool", "details": details,
                         "label": f"gNB {e['id']}" + (f" {e['name']}" if e.get("name") else "")})
            tails.append(f"{len(e['cells'])} cell{'s' if len(e['cells']) != 1 else ''}"
                         + (" · already a neighbour" if have else ""))
        distinguish(opts, found, tails, address="xn")
        opts.append({"value": MANUAL, "key": MANUAL, "group": "By hand", "label": "Enter its address by hand",
                     "details": ["The other gNB's Xn C-plane address."]})
        srcs[dn] = opts
    return {
        "intro": "Adds an Xn link (XNLINK) to another gNB. The two gNBs exchange their cells over Xn, so no "
                 "neighbour cell is entered here.",
        "fields": [
            {"id": "target", "label": "This gNB", "type": "select", "options": targets,
             "default": targets[0]["value"] if len(targets) == 1 else None},
            {"id": "source", "label": "Neighbour gNB", "type": "select", "dependsOn": "target", "optionsByKey": srcs},
            {"id": "ip", "label": "Its Xn C-plane address", "type": "text", "showIf": {"field": "source",
                                                                                     "equals": MANUAL},
             "placeholder": "10.0.1.48"},
        ],
    }


def _neighbour(ctx: Context, gnb: dict, inputs: dict) -> dict:
    """The other gNB as {id, plmn, ip, cells, from}; id and cells are None
    when typed in."""
    src = inputs.get("source") or ""
    if src == MANUAL:
        ip = (inputs.get("ip") or "").strip()
        problem, _ = check_ip(ip) if ip else ("Enter the other gNB's Xn C-plane address.", [])
        if problem:
            raise PlanError([problem])
        return {"id": None, "plmn": None, "ip": ip, "cells": None, "from": None}
    match = next((e for e in _sources(ctx, gnb) if e["key"] == src), None)
    if not match:
        raise PlanError(["Pick the neighbour gNB."])
    if not match["xn"]:
        raise PlanError([f"{match['file']} has no address on gNB {match['id']}'s planes (NRBTS xnCplane). Enter its "
                         "address by hand instead."])
    return {"id": match["id"], "plmn": match["plmn"], "ip": match["xn"], "cells": match["cells"],
            "from": match["file"]}


def _frequency_note(site: Site, gnb: dict, nb: dict) -> Optional[str]:
    """Neighbour carriers this gNB neither serves nor lists for idle-mode
    reselection (NRSYSINFO_PROFILE NRIRFIM), when it has such a profile."""
    if not nb["cells"] or not site.of("NRSYSINFO_PROFILE", gnb["dn"]):
        return None
    known = {nr_cell(site, gnb, c)["arfcn"] for c in site.child(gnb["dn"], "NRCELL")}
    known |= {m["p"].get("dlCarrierFreq") for m in site.of("NRIRFIM", gnb["dn"])}
    missing = sorted({c["arfcn"] for c in nb["cells"] if c.get("arfcn")} - known, key=lambda a: int(a))
    if not missing:
        return None
    return (f"gNB {nb['id']}'s cells are on NR-ARFCN {', '.join(missing)}, which this gNB doesn't serve and no NRIRFIM "
            "lists: idle UEs won't reselect to them. Add an NRIRFIM for "
            + ("it" if len(missing) == 1 else "each") + " if they should.")


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    gnb = next((m for m in _gnbs(site) if m["dn"] == inputs.get("target")), None)
    if not gnb:
        raise PlanError(["Pick this file's gNB."])
    nb = _neighbour(ctx, gnb, inputs)
    if nb["ip"].lower() in own_addresses(site):
        raise PlanError([f"{nb['ip']} is one of this BTS's own addresses."])
    who = f"gNB {nb['id']}" if nb["id"] else nb["ip"]
    src = f"from {nb['from']}" if nb["from"] else "as entered"

    doc = Doc(ctx.raw)
    notes: list[str] = []
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
    mine = _plmn(site, gnb)
    if mine and nb["plmn"] and not same_plmn(mine, nb["plmn"]):
        notes.append(f"gNB {nb['id']}'s PLMN is {plmn_text(nb['plmn'])}, this gNB's {plmn_text(mine)}.")
    note = _frequency_note(site, gnb, nb)
    if note:
        notes.append(note)
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

"""
Add a VLAN interface with an address (TNLSVC transport): a VLANIF under
an Ethernet interface, an IPIF pointing at it, and an IPADDRESSV4 (or
IPADDRESSV6) under the IPIF. With a gateway, the subnet gets its default
route; the planes picked move onto the new address.

The default route follows the files: where a BTS has several IP
interfaces, 27 of the 36 such files in the corpus give each its own
routing table (IPRT) with a default route, and an RTPOL routing policy
sends the interface's source address to it. So when the main table
already has a default route, the new one goes into a table of its own (an
empty one no policy names, else a new one) with a policy row; otherwise
into the main table.

Refused: a VLAN ID the Ethernet interface already carries (the dictionary:
"For each VLAN interface the VLAN ID must be uniquely defined"; 7 files
repeat one on another ETHIF), an address another interface holds, a
gateway off the new subnet. Noted: a subnet overlapping another
interface's (one production file has two interfaces on one /22). Flexi
Zone (FTM) transport keeps its VLAN address in IVIF, which this action
doesn't build.
"""
from __future__ import annotations

import collections
import ipaddress
from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, instance, label, parent_dn, why
from .ip_address import USES, _parse_prefix, addresses
from .links import Site, _runtime
from .static_route import _rows, route_row, tables
from .transport import subnets

ID = "ip-interface"
TITLE = "Add a VLAN interface"
GROUP = "Transport"
SUMMARY = "A VLAN on an Ethernet interface with an IP address, its default route, and the planes that use it."
UI = "form"
KEYWORDS = "VLAN VLANIF IPIF IPADDRESSV4 IPADDRESSV6 interface subnet address OAM M-plane separation RTPOL ETHIF"

# The address fields a plane can point with, by IP version.
V6_FIELD = {"mPlaneIpv4AddressDN": "mPlaneIpv6AddressDN", "ipV4AddressDN1": "ipV6AddressDN1"}
# Fields the dictionary lets name an IPADDRESSV4 or an IPADDRESSV6.
EITHER = {"sourceIpAddressDN", "twampReflectorLocalIpAddressDN", "ntpSourceIpAddressDN", "sPlaneIpAddressDN"}


def _ip(value: Optional[str]):
    try:
        return ipaddress.ip_address((value or "").strip())
    except ValueError:
        return None


def _ethifs(site: Site) -> list[dict]:
    return [m for m in site.of("ETHIF") if not _runtime(m["dn"]) and "/TNLSVC-" in m["dn"]]


def _ipno(site: Site, ethif: str) -> Optional[str]:
    """The IPNO of the Ethernet interface's TNL."""
    tnl = ethif.split("/ETHSVC-")[0]
    return next((m["dn"] for m in site.of("IPNO") if parent_dn(m["dn"]) == tnl and not _runtime(m["dn"])), None)


def uses(site: Site) -> list[dict]:
    """Every value pointing at one of the BTS's address objects: (holder,
    list, field) with the address it names, one option per holder field."""
    own = {m["dn"]: m for m in site.of("IPADDRESSV4") + site.of("IPADDRESSV6") if not _runtime(m["dn"])}
    found = collections.OrderedDict()
    for m in site.mos:
        if _runtime(m["dn"]) or m["cls"] in ("IPRT", "IPRTV6", "RTPOL"):
            continue
        for k, v in m["p"].items():
            if v in own:
                found.setdefault((m["dn"], "", k), v)
        for ln, rows in (m.get("lists") or {}).items():
            if ln in (m.get("simple") or {}):
                continue
            for r in rows:
                for k, v in r.items():
                    if v in own:
                        found.setdefault((m["dn"], ln, k), v)
    out = []
    for (dn, ln, k), target in found.items():
        name = USES.get(ln or k) or (ln or k)
        where = label(dn) if ln else f"{label(dn)}.{k}"
        out.append({"value": f"{dn}|{ln}|{k}", "dn": dn, "list": ln, "field": k, "target": target,
                    "label": f"{name} · {where}" + (f".{ln}" if ln else "")
                             + f" · now {own[target]['p'].get('localIpAddr')}"})
    return out


def available(ctx: Context) -> Optional[str]:
    site = ctx.site
    if _ethifs(site) and any(_ipno(site, m["dn"]) for m in _ethifs(site)):
        return None
    if site.of("IEIF") or site.of("IVIF"):
        return ("This is Flexi Zone (FTM) transport: its VLAN address lives in IVIF under IEIF, which this action "
                "doesn't build.")
    return "This file has no Ethernet interface (ETHIF) with an IPNO to add an IP interface to."


def setup(ctx: Context) -> dict:
    site = ctx.site
    ethifs = []
    for m in _ethifs(site):
        if not _ipno(site, m["dn"]):
            continue
        vlans = [v["p"].get("vlanId") for v in site.child(m["dn"], "VLANIF")]
        link = label(m["p"].get("linkSelectorDN") or "")
        tnls = {e["dn"].split("/ETHSVC-")[0] for e in _ethifs(site)}
        where = f"{label(m['dn'].split('/ETHSVC-')[0])} " if len(tnls) > 1 else ""
        ethifs.append({"value": m["dn"], "key": m["dn"],
                       "label": f"{where}{label(m['dn'])}" + (f" · on {link}" if link else "")
                                + (f" · VLAN{'s' if len(vlans) > 1 else ''} {', '.join(vlans)}" if vlans else
                                   " · no VLAN")})
    mtus = collections.Counter(m["p"].get("ipMtu") for m in site.of("IPIF") if m["p"].get("ipMtu"))
    return {
        "intro": "Adds a VLAN with its own IP interface and address. A gateway gives the subnet its default route; "
                 "the planes you pick move onto the new address.",
        "fields": [
            {"id": "ethif", "label": "Ethernet interface", "type": "select", "options": ethifs,
             "default": ethifs[0]["value"] if len(ethifs) == 1 else None},
            {"id": "vlan", "label": "VLAN ID", "type": "text", "placeholder": "1-4094"},
            {"id": "name", "label": "Name", "type": "text", "optional": True, "placeholder": "OAM",
             "hint": "Written as the userLabel of the VLAN interface, and of the IP interface and routing table "
                     "where the file labels those."},
            {"id": "address", "label": "Address", "type": "text", "placeholder": "10.20.30.4/29",
             "hint": "The BTS's address on the VLAN, with its prefix length."},
            {"id": "gateway", "label": "Gateway", "type": "text", "optional": True,
             "hint": "The router on the new subnet. Leave it empty if nothing leaves the subnet."},
            {"id": "planes", "label": "Move onto it", "type": "checks", "options": uses(site), "default": [],
             "optional": True},
            {"id": "mtu", "label": "IP MTU", "type": "text",
             "default": mtus.most_common(1)[0][0] if mtus else "1500",
             "hint": "The file's other IP interfaces use this. The dictionary: at least four octets below the "
                     "Ethernet MTU on a VLAN."},
        ],
    }


def _field_for(site: Site, use: dict, version: int) -> Optional[str]:
    """The field that points `use` at an address of `version`: its own
    when the address it names is of that version, else its counterpart."""
    now = 6 if site.by_dn[use["target"]]["cls"] == "IPADDRESSV6" else 4
    if now == version or use["field"] in EITHER:
        return use["field"]
    return (V6_FIELD if version == 6 else {b: a for a, b in V6_FIELD.items()}).get(use["field"])


def _labelled(site: Site, cls: str) -> bool:
    return any("userLabel" in m["p"] for m in site.of(cls))


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    problems, notes = [], []
    ethif = site.by_dn.get(inputs.get("ethif") or "")
    if not ethif or ethif["cls"] != "ETHIF":
        raise PlanError(["Pick the Ethernet interface."])
    ipno = _ipno(site, ethif["dn"])
    vlan = (inputs.get("vlan") or "").strip()
    if not (vlan.isdigit() and 1 <= int(vlan) <= 4094):
        problems.append(f"{vlan!r} isn't a VLAN ID (1-4094)." if vlan else "Enter the VLAN ID.")
    elif any(v["p"].get("vlanId") == str(int(vlan)) for v in site.child(ethif["dn"], "VLANIF")):
        problems.append(f"{label(ethif['dn'])} already carries VLAN {int(vlan)}; the dictionary wants each VLAN "
                        "ID once.")
    text = (inputs.get("address") or "").strip()
    addr, _, pfx = text.partition("/")
    ip = _ip(addr)
    if ip is None:
        raise PlanError(problems + [f"{text!r} isn't an address with a prefix (10.20.30.4/29)." if text
                                    else "Enter the address."])
    prefix = _parse_prefix(pfx, ip.version) if pfx else None
    if prefix is None:
        problems.append(f"Give the prefix length after the address ({ip}/29)." if not pfx else
                        f"{pfx!r} isn't a prefix length (1-{32 if ip.version == 4 else 128}).")
    if problems:
        raise PlanError(problems)
    net = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
    if ip.is_unspecified or ip.is_multicast or ip.is_loopback or ip.is_link_local or \
            (ip.version == 4 and ip == ipaddress.ip_address("255.255.255.255")):
        problems.append(f"{ip} can't be a BTS address: unspecified, broadcast, multicast, loopback and link-local "
                        "are reserved.")
    elif ip.version == 6 and not (ip in ipaddress.ip_network("fc00::/7") or ip in ipaddress.ip_network("2000::/3")):
        problems.append(f"{ip} isn't unique-local (FC00::/7) or global unicast (2000::/3), the ranges the "
                        "dictionary allows (IPADDRESSV6 localIpAddr).")
    if ip.version == 4 and net.num_addresses > 2 and ip in (net.network_address, net.broadcast_address):
        problems.append(f"{ip} is the {'network' if ip == net.network_address else 'broadcast'} address of {net}; "
                        "pick a host address.")
    for m in addresses(site):
        if _ip(m["p"].get("localIpAddr")) == ip:
            problems.append(f"{label(m['dn'])} already has {ip}.")
    for dn, other in subnets(site):
        if other.version == net.version and other.overlaps(net):
            notes.append(f"{net} overlaps {label(dn)}'s subnet {other}. One production file puts two interfaces on "
                         "one subnet; otherwise which one a packet leaves through is ambiguous.")
    mtu = (inputs.get("mtu") or "").strip()
    if not (mtu.isdigit() and 200 <= int(mtu) <= 9500):
        problems.append(f"{mtu!r} isn't an IP MTU (200-9500 octets)." if mtu else "Enter the IP MTU.")
    gw_text = (inputs.get("gateway") or "").strip()
    gw = _ip(gw_text) if gw_text else None
    if gw_text and gw is None:
        problems.append(f"{gw_text!r} isn't an IP address.")
    elif gw is not None:
        if gw.version != ip.version or gw not in net:
            problems.append(f"The gateway {gw} isn't on the new subnet {net}.")
        elif gw == ip:
            problems.append("The gateway can't be the address itself.")
        elif net.num_addresses > 2 and gw in (net.network_address, net.broadcast_address):
            problems.append(f"{gw} is the {'lowest' if gw == net.network_address else 'highest'} address of {net}; "
                            "the dictionary doesn't allow either as a gateway.")
    picked = [u for u in uses(site) if u["value"] in (inputs.get("planes") or [])]
    stuck = [u for u in picked if _field_for(site, u, ip.version) is None]
    if stuck:
        problems.append(f"{', '.join(u['label'].split(' · ')[0] for u in stuck)} can't move to an IPv{ip.version} "
                        f"address: the dictionary gives {'it' if len(stuck) == 1 else 'them'} no field for one.")
    if problems:
        raise PlanError(problems)

    name = (inputs.get("name") or "").strip()
    doc = Doc(ctx.raw)
    w = lambda reason, basis="choice": why("interface", reason, basis)
    vdn = doc.create(ethif["dn"], "VLANIF", doc.next_free(ethif["dn"], "VLANIF"),
                     ([("userLabel", name)] if name else []) + [("vlanId", str(int(vlan)))],
                     w=w(f"VLAN {int(vlan)} on {label(ethif['dn'])}."))
    idn = doc.create(ipno, "IPIF", doc.next_free(ipno, "IPIF"),
                     [("interfaceDN", vdn), ("ipMtu", mtu)] + ([("userLabel", name)] if name and _labelled(site, "IPIF")
                                                              else []),
                     w=w(f"The IP interface on VLAN {int(vlan)}."))
    acls = "IPADDRESSV4" if ip.version == 4 else "IPADDRESSV6"
    # As typed: IPv6 files write "::" for a single zero group, which Python's spelling doesn't.
    adn = doc.create(idn, acls, "1", [("ipAddressAllocationMethod", "MANUAL"), ("localIpAddr", addr.strip()),
                                      ("localIpPrefixLength", str(prefix))],
                     w=w(f"The BTS's address {ip}/{prefix}; MANUAL, as every address in the files this was built "
                         "from is."))

    # The default route.
    if gw is not None:
        v = ip.version
        cls, lname = ("IPRT", "staticRoutes") if v == 4 else ("IPRTV6", "staticIpv6Routes")
        ts = [t for t in tables(site, v) if parent_dn(t["dn"]) == ipno]
        policies = [m for m in site.of("RTPOL") if parent_dn(m["dn"]) == ipno]
        rows = [r for m in policies for r in (m.get("lists") or {}).get("routingPolicies", [])]
        main = next((t for t in ts if instance(t["dn"]) == "1"), ts[0] if ts else None)
        main_default = main and any(_ip(r.get("destIpAddr") or r.get("destIpv6Addr")) is not None
                                    and _ip(r.get("destIpAddr") or r.get("destIpv6Addr")).is_unspecified
                                    for r in _rows(main))
        default = ipaddress.ip_network("0.0.0.0/0" if v == 4 else "::/0")
        named = {r.get("routingTableDN") or r.get("routingTablePtr") for r in rows}
        spare = next((t["dn"] for t in ts if t is not main and not _rows(t) and t["dn"] not in named), None)
        if main is None or not main_default:
            table = main["dn"] if main else doc.create(ipno, cls, "1", [], w=w(f"The main routing table; the file "
                                                                               f"has no {cls}."))
            why_table = "the main table, which has no default route yet"
            set_source = False
        else:
            if spare:
                table = spare
                if name and _labelled(site, cls) and not site.by_dn[spare]["p"].get("userLabel"):
                    doc.set(spare, "userLabel", name, w("The interface's name."))
            else:
                table = doc.create(ipno, cls, doc.next_free(ipno, cls),
                                   [("userLabel", name)] if name and _labelled(site, cls) else [],
                                   w=w(f"A routing table of its own for {net}: the routing policy sends its source "
                                       "address here, as the files with several IP interfaces do (27 of 36)."))
            set_source = True
            why_table = (f"a table of its own, {label(table)}" + (" (it had no routes and no policy)" if spare else "")
                         + f", picked by the routing policy for packets from {ip}; {label(main['dn'])} keeps its "
                           "default route for the other addresses")
            pol = policies[0]["dn"] if policies else doc.create(ipno, "RTPOL", "1", [], w=w(
                "The routing policies; the file has none yet."))
            spell = rows[0] if rows else {}
            order = max([int(r.get("orderNumber") or 0) for r in rows] + [0]) + 1
            prow = [("orderNumber", str(order)),
                    ("routingTablePtr" if "routingTablePtr" in spell else "routingTableDN", table),
                    ("srcIPAddress" if "srcIPAddress" in spell else "srcIpAddress", str(ip)),
                    ("srcIpPrefixLength", str(prefix))]
            if name and (not rows or "userLabel" in spell):
                prow.append(("userLabel", name))
            doc.add_item(pol, "routingPolicies", prow,
                         w(f"Packets from {ip} use {label(table)}. orderNumber {order}: the policies' order numbers "
                           "must differ (RTPOL orderNumber).", "official"))
        row, reasons, row_notes = route_row(site, table, default, gw, str(ip), "1", "", set_source=set_source)
        notes += row_notes
        doc.add_item(table, lname, row, w(f"The default route of {net} via {gw}"
                                          + (f": {', '.join(reasons)}." if reasons else ".")))
        notes.append(f"The default route goes into {why_table}.")

    # The planes.
    for u in picked:
        field = _field_for(site, u, ip.version)
        reason = w(f"{u['label'].split(' · ')[0]} moves to {ip}.")
        if not u["list"]:
            if field != u["field"]:
                doc.unset(u["dn"], u["field"], reason)
            doc.set(u["dn"], field, adn, reason)
            continue
        for i, r in enumerate(site.by_dn[u["dn"]]["lists"][u["list"]]):
            if r.get(u["field"]) == u["target"]:
                if field != u["field"]:
                    doc.unset_item(u["dn"], u["list"], i, u["field"], reason)
                doc.set_item(u["dn"], u["list"], i, field, adn, reason)
    moved = {p["value"] for p in picked}
    by_target = collections.defaultdict(list)
    for u in uses(site):
        by_target[u["target"]].append(u["value"])
    for t in sorted(t for t, vals in by_target.items() if all(v in moved for v in vals) and moved & set(vals)):
        notes.append(f"Nothing uses {label(parent_dn(t))}'s {site.by_dn[t]['p'].get('localIpAddr')} any more. "
                     "It stays; delete it if the old subnet goes.")
    if any(m["cls"] == "FSTSCH" for m in site.mos):
        notes.append("The file shapes some IP interfaces with a scheduler (QOS FSTSCH); the new one isn't in it.")
    if gw is None and picked:
        notes.append(f"No gateway: the planes moved to {ip} reach only {net}.")

    confirm = [f"VLAN {int(vlan)} reaches the BTS on the port behind {label(ethif['dn'])}"
               + (f", and {gw} routes {net}." if gw else ".")]
    if any("M-plane" in u["label"] for u in picked):
        confirm.append(f"NetAct (or whatever manages the BTS) reaches it on {ip} after loading.")
    return finish(ctx, doc, {
        "label": f"VLAN {int(vlan)} {ip}/{prefix}",
        "summary": f"VLAN {int(vlan)} on {label(ethif['dn'])} with {ip}/{prefix}"
                   + (f", default route via {gw}" if gw else "")
                   + (f"; {len(picked)} plane{'s' if len(picked) != 1 else ''} moved" if picked else ""),
        "notes": notes,
        "confirm": confirm,
        "focus": adn,
    })

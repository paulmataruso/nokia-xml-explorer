"""
Change one of the BTS's own IP addresses (its M-, C-, U- or S-plane
address), with everything that repeats it.

The two transport models (actions/transport.py) keep the address in
different places:
  - TNLSVC: an IPADDRESSV4/V6 (localIpAddr + localIpPrefixLength). The
    planes point at the object by DN (MPLANENW, TRSNW cPlane/uPlane, the
    NRBTS plane lists), so they follow on their own. Literal copies remain:
    IPRT preSrcIpv4Addr (68 files) and RTPOL srcIpAddress (54).
  - FTM (Flexi Zone): an IVIF or IEIF (localIpAddr + netmask), with IPNO
    holding each plane's address as a literal copy (mPlaneIpAddress,
    cPlaneIpAddress, uPlaneIpAddress, sPlaneIpAddress in all 47 files), and
    srcIpForCmpCrl, INTP, TWAMP, IPsec selectors and route sources repeating
    it. An IEIF of 0.0.0.0 is unconfigured (44 files) and isn't offered.

Every configured value equal to the old address is the BTS itself (a peer
can't share it), so all of them change. Runtime objects (_R) keep the old
address until the BTS reports again. Routes whose gateway is on the old
subnet are the ones leaving through this address; their gateway changes
when the subnet does.

Refused: an address of the other IP version, a reserved address, the
subnet's network or broadcast address, an address another interface holds,
and a gateway off the new subnet. Noted: an overlap with another
interface's subnet, and peers (MME, AMF, NetAct, timing, DNS) the file
reached before and doesn't after.
"""
from __future__ import annotations

import ipaddress
from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, why
from .links import Site, _runtime
from .transport import reachable, unset_address

ID = "ip"
TITLE = "Change a BTS IP address"
GROUP = "Transport"
SUMMARY = "Change the M-plane, C-plane or U-plane address of the BTS, with its subnet and gateway."
UI = "form"
KEYWORDS = "IP address M-plane C-plane U-plane S-plane subnet netmask prefix gateway route VLAN IPADDRESSV4 IVIF IPNO"

ADDRESS_CLASSES = ("IPADDRESSV4", "IPADDRESSV6", "IVIF", "IEIF")

# What an address is used for, by the field that points at or repeats it.
USES = {
    "mPlaneIpv4AddressDN": "M-plane", "mPlaneIpv6AddressDN": "M-plane", "mPlaneIpAddress": "M-plane",
    "cPlane": "S1/X2 C-plane", "uPlane": "S1/X2 U-plane",
    "cPlaneIpAddress": "C-plane", "uPlaneIpAddress": "U-plane", "sPlaneIpAddress": "S-plane",
    "cPlaneIpAddressSec": "secondary C-plane", "uPlane2IpAddress": "secondary U-plane",
    "ngCplane": "NG-C", "ngUplane": "NG-U", "x2Cplane": "X2-C", "x2Uplane": "X2-U", "xnCplane": "Xn-C",
    "xnUplane": "Xn-U", "s1Uplane": "S1-U", "e2Plane": "E2", "xgUplane": "Xg-U",
    "sPlaneIpAddressDN": "S-plane", "localIpAddressDN": "PTP", "ntpSourceIpAddressDN": "NTP",
    "ntpSourceIpAddress": "NTP", "sourceIpAddressDN": "TWAMP", "sourceIpAddress": "TWAMP",
    "twampIpAddress": "TWAMP", "twampReflectorLocalIpAddressDN": "TWAMP",
    "cmpCrlSrcIpv4AddressDN": "CMP/CRL", "srcIpForCmpCrl": "CMP/CRL",
}

# The dictionary's rules for fields that must equal an interface address.
MUST_MATCH = {
    "sPlaneIpAddress": "The IP address has to collapse with a network interface IP address.",
    "twampIpAddress": "Must be identical with one of the configured eNB application or interface IP addresses.",
    "ntpSourceIpAddress": "The BTS NTP client must collapse with either U, C, M or S-plane.",
}

# Peers whose reachability a subnet change can break: (class, field, what).
PEERS = (
    ("LNMME", "ipAddrPrim", "MME"), ("SERVEDAMF", "amfIPAddress", "AMF"), ("IPNO", "oamIpAddr", "NetAct (OMS)"),
    ("IPNO", "secOmsIpAddr", "secondary OMS"), ("MPLANENW", "nmsIntegrationIpAddress", "NetAct"),
    ("DNS", "serverIpAddressPrimary", "DNS server"), ("IDNS", "serverIpAddress", "DNS server"),
    ("LNADJGNB", "cPlaneIpAddr", "X2 neighbour gNB"), ("LNADJ", "cPlaneIpAddr", "X2 neighbour eNB"),
)


def _ip(value: Optional[str]):
    try:
        return ipaddress.ip_address((value or "").strip())
    except ValueError:
        return None


def _text(ip, like: str = "") -> str:
    """An address the way the file writes them. The dictionary says IPv6
    "has to be defined always in full length" (eight groups), but the IPv6
    files in the corpus use "::"; follow the value being replaced."""
    if ip.version == 4 or "::" in like:
        return str(ip)
    return ":".join(f"{int(g, 16):x}" for g in ip.exploded.split(":"))


def _short(dn: str) -> str:
    parts = dn.split("/")
    return "/".join(parts[-2:]) if parts[-1].startswith("IPADDRESSV") else parts[-1]


def _net(m: dict):
    p = m["p"]
    try:
        if m["cls"].startswith("IPADDRESSV"):
            return ipaddress.ip_network(f"{p['localIpAddr']}/{p.get('localIpPrefixLength')}", strict=False)
        return ipaddress.ip_network(f"{p['localIpAddr']}/{p.get('netmask')}", strict=False)
    except (KeyError, ValueError, TypeError):
        return None


def addresses(site: Site) -> list[dict]:
    """The BTS's own configured addresses."""
    return [m for cls in ADDRESS_CLASSES for m in site.of(cls)
            if not _runtime(m["dn"]) and not unset_address(m["p"].get("localIpAddr")) and _ip(m["p"].get("localIpAddr"))]


def _values(m: dict):
    """(kind, list, index, field, value) for every value an object holds."""
    for k, v in m["p"].items():
        yield "p", None, None, k, v
    for ln, vs in (m.get("simple") or {}).items():
        for i, v in enumerate(vs):
            yield "simple", ln, i, None, v
    for ln, rows in (m.get("lists") or {}).items():
        if ln in (m.get("simple") or {}):
            continue
        for i, row in enumerate(rows):
            for k, v in row.items():
                yield "row", ln, i, k, v


def uses(site: Site, target: dict) -> list[str]:
    """What the address is used for: the fields pointing at the object, and
    the fields repeating its value."""
    ip = _ip(target["p"]["localIpAddr"])
    out = []
    for m in site.mos:
        if _runtime(m["dn"]) or m["dn"] == target["dn"]:
            continue
        for kind, ln, _, field, v in _values(m):
            if v == target["dn"] or (v and _ip(v) == ip):
                name = USES.get(ln if ln and field and field.startswith("ipV") else field or ln)
                if name and name not in out:
                    out.append(name)
    return out


def _routes_via(site: Site, net) -> list[tuple[str, str, int, str, str]]:
    """(route object, list, row, gateway field, gateway) for the static
    routes whose gateway is on `net`: the ones leaving through it."""
    out = []
    for cls, ln, gw_field in (("IPRT", "staticRoutes", "gateway"), ("IPRTV6", "staticIpv6Routes", "gatewayIpv6Addr")):
        for m in site.of(cls):
            if _runtime(m["dn"]):
                continue
            for i, row in enumerate((m.get("lists") or {}).get(ln, [])):
                gw = _ip(row.get(gw_field))
                if gw is not None and net is not None and gw.version == net.version and gw in net:
                    out.append((m["dn"], ln, i, gw_field, row.get(gw_field)))
    return out


def _gateway(site: Site, m: dict) -> str:
    """The gateway routes through this address use: the default route's,
    else the most common one."""
    via = _routes_via(site, _net(m))
    if not via:
        return ""
    for dn, ln, i, _, gw in via:
        row = site.by_dn[dn]["lists"][ln][i]
        dest = row.get("destIpAddr") or row.get("destIpv6Addr")
        if _ip(dest) is not None and _ip(dest).is_unspecified:
            return gw
    gws = [gw for *_, gw in via]
    return max(gws, key=gws.count)


def _prefix_of(m: dict) -> str:
    net = _net(m)
    return str(net.prefixlen) if net else ""


def available(ctx: Context) -> Optional[str]:
    if addresses(ctx.site):
        return None
    return "This file sets no IP address of the BTS (no IPADDRESSV4, IPADDRESSV6, IVIF or IEIF with an address)."


def setup(ctx: Context) -> dict:
    site = ctx.site
    options, ips, prefixes, gateways = [], {}, {}, {}
    copies: dict[str, list[dict]] = {}
    for m in addresses(site):
        copies.setdefault(m["dn"], []).append(m)
    for dn, ms in copies.items():
        m = ms[0]
        if len(ms) > 1:
            # Listed once, so the select has one option per value; plan() refuses it.
            options.append({"value": dn, "key": dn, "group": "Addresses",
                            "label": f"{_short(dn)} · {len(ms)} copies "
                                     f"({', '.join(x['p']['localIpAddr'] for x in ms)})",
                            "details": [f"The file has {len(ms)} objects named {dn}; delete the extra one first."]})
            ips[dn], prefixes[dn], gateways[dn] = m["p"]["localIpAddr"], _prefix_of(m), ""
            continue
        net = _net(m)
        used = uses(site, m)
        details = [f"Used for {', '.join(used)}." if used else "No plane uses it."]
        iface = site.by_dn.get(site.by_dn.get(dn.rsplit("/", 1)[0], {}).get("p", {}).get("interfaceDN", ""))
        vlan = (iface or m)["p"].get("vlanId")
        if vlan:
            details.append(f"VLAN {vlan}.")
        gw = _gateway(site, m)
        if gw:
            details.append(f"Routes leave through gateway {gw}.")
        options.append({"value": dn, "key": dn, "group": "Addresses", "details": details,
                        "label": f"{_short(dn)} · {m['p']['localIpAddr']}/{net.prefixlen if net else '?'}"
                                 + (f" · {', '.join(used[:3])}{'…' if len(used) > 3 else ''}" if used else "")})
        ips[dn], prefixes[dn], gateways[dn] = m["p"]["localIpAddr"], _prefix_of(m), gw
    return {
        "intro": "Changes one of the BTS's own addresses. The planes that use it, the routes leaving through it "
                 "and every other copy of the address in the file change with it.",
        "fields": [
            {"id": "target", "label": "Address", "type": "select", "options": options,
             "default": options[0]["value"] if len(options) == 1 else None},
            {"id": "ip", "label": "New address", "type": "text", "dependsOn": "target", "defaultByKey": ips},
            {"id": "prefix", "label": "Prefix length or netmask", "type": "text", "dependsOn": "target",
             "defaultByKey": prefixes, "placeholder": "24"},
            {"id": "gateway", "label": "Gateway", "type": "text", "dependsOn": "target", "defaultByKey": gateways,
             "optional": True, "hint": "The next hop of the routes that leave through this address. Leave it empty "
                                       "if no route does."},
        ],
    }


def _parse_prefix(value: str, version: int) -> Optional[int]:
    v = (value or "").strip().lstrip("/")
    if v.isdigit():
        n = int(v)
        return n if 1 <= n <= (32 if version == 4 else 128) else None
    if version == 4:
        try:
            return ipaddress.ip_network(f"0.0.0.0/{v}").prefixlen or None
        except ValueError:
            return None
    return None


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    own = {m["dn"]: m for m in addresses(site)}
    target = own.get(inputs.get("target") or "")
    if not target:
        raise PlanError(["Pick an address."])
    copies = [m for m in site.mos if m["dn"] == target["dn"]]
    if len(copies) > 1:
        raise PlanError([f"The file has {len(copies)} objects named {target['dn']} ("
                         + ", ".join(m["p"].get("localIpAddr") or "no address" for m in copies)
                         + "). Delete the extra one first; the site check lists it."])
    old_ip = _ip(target["p"]["localIpAddr"])
    old_net = _net(target)
    problems, notes = [], []

    new_ip = _ip(inputs.get("ip"))
    if new_ip is None:
        raise PlanError([f"{(inputs.get('ip') or '').strip()!r} isn't an IP address." if inputs.get("ip")
                         else "Enter the new address."])
    if new_ip.version != old_ip.version:
        problems.append(f"{_short(target['dn'])} holds an IPv{old_ip.version} address; enter one.")
    elif new_ip.is_unspecified or new_ip.is_multicast or new_ip.is_loopback or \
            (new_ip.version == 4 and new_ip == ipaddress.ip_address("255.255.255.255")):
        problems.append(f"{new_ip} can't be a BTS address: 0.0.0.0, broadcast, multicast and loopback are reserved.")
    prefix = _parse_prefix(inputs.get("prefix") or "", old_ip.version)
    if prefix is None:
        problems.append(f"{(inputs.get('prefix') or '').strip()!r} isn't a prefix length "
                        f"(1-{32 if old_ip.version == 4 else 128}){' or netmask' if old_ip.version == 4 else ''}.")
    if problems:
        raise PlanError(problems)
    new_net = ipaddress.ip_network(f"{new_ip}/{prefix}", strict=False)
    if new_ip.version == 4 and prefix <= 30 and new_ip in (new_net.network_address, new_net.broadcast_address):
        problems.append(f"{new_ip} is the {'network' if new_ip == new_net.network_address else 'broadcast'} "
                        f"address of {new_net}; pick a host address.")
    for dn, m in own.items():
        if dn != target["dn"] and _ip(m["p"]["localIpAddr"]) == new_ip:
            problems.append(f"{_short(dn)} already has {new_ip}.")
    gw_in = (inputs.get("gateway") or "").strip()
    old_gw = _gateway(site, target)
    new_gw = _ip(gw_in) if gw_in else _ip(old_gw)
    if gw_in and new_gw is None:
        problems.append(f"{gw_in!r} isn't an IP address.")
    elif new_gw is not None:
        if new_gw.version != new_ip.version or new_gw not in new_net:
            problems.append(f"The gateway {new_gw} isn't on the new subnet {new_net}. Enter the gateway for it.")
        elif new_gw == new_ip:
            problems.append("The gateway can't be the address itself.")
    if problems:
        raise PlanError(problems)
    if new_ip == old_ip and new_net == old_net and (new_gw is None or _ip(old_gw) == new_gw):
        raise PlanError([f"{_short(target['dn'])} already has {new_ip}/{prefix}"
                         + (f" with gateway {new_gw}." if new_gw else ".")])
    for dn, m in own.items():
        net = _net(m)
        if dn != target["dn"] and net is not None and net.version == new_net.version and net.overlaps(new_net):
            notes.append(f"The new subnet {new_net} overlaps {_short(dn)}'s {net}. Two interfaces on overlapping "
                         "subnets make it ambiguous which one a packet leaves through.")

    doc = Doc(ctx.raw)
    tdn, new_text = target["dn"], _text(new_ip, target["p"]["localIpAddr"])
    what = _short(tdn)
    doc.set(tdn, "localIpAddr", new_text, why("ip", "The new address.", "choice"))
    if target["cls"].startswith("IPADDRESSV"):
        doc.set(tdn, "localIpPrefixLength", str(prefix), why("ip", f"The new subnet {new_net}.", "choice"))
    else:
        doc.set(tdn, "netmask", str(new_net.netmask), why("ip", f"The new subnet {new_net}.", "choice"))

    # Every other copy of the old address.
    runtime_copies = 0
    for m in site.mos:
        if m["dn"] == tdn:
            continue
        for kind, ln, i, field, v in _values(m):
            if not v or _ip(v) != old_ip:
                continue
            if _runtime(m["dn"]):
                runtime_copies += 1
                continue
            name = field or ln
            rule = MUST_MATCH.get(name)
            used = USES.get(name)
            w = why("ip", (f"Repeats {what}'s address" + (f" ({used})" if used else "") + "; it moves with it."
                           + (f" {rule}" if rule else "")),
                    "official" if rule else "choice", (name, None) if rule else None)
            if kind == "p":
                doc.set(m["dn"], field, new_text, w)
            elif kind == "row":
                doc.set_item(m["dn"], ln, i, field, new_text, w)
            else:
                values = doc.values(m["dn"], ln)
                doc.set_values(m["dn"], ln, [new_text if _ip(x) == old_ip else x for x in values], w)
    if runtime_copies:
        notes.append(f"Runtime objects (_R) still show the old address {old_ip} in {runtime_copies} place"
                     f"{'s' if runtime_copies != 1 else ''}; the BTS reports the new one once loaded.")

    # The routes leaving through this address.
    if new_gw is not None:
        for dn, ln, i, gw_field, gw in _routes_via(site, old_net):
            if _ip(gw) == _ip(old_gw) and _ip(gw) != new_gw:
                doc.set_item(dn, ln, i, gw_field, _text(new_gw, gw),
                             why("ip", f"The gateway of the routes leaving through {what}.", "choice"))
            elif _ip(gw) != _ip(old_gw) and _ip(gw) not in new_net:
                row = site.by_dn[dn]["lists"][ln][i]
                dest = row.get("destIpAddr") or row.get("destIpv6Addr")
                notes.append(f"The route to {dest} uses gateway {gw}, which isn't on the new subnet. Change it in "
                             f"the tree ({dn.rsplit('/', 1)[-1]} {ln}[{i + 1}]).")

    # Peers the change cuts off.
    after = Context(doc.raw(), ctx.filename, ctx.source).site
    lost = []
    for cls, field, peer in PEERS:
        for m in site.of(cls):
            v = m["p"].get(field)
            if v and not unset_address(v) and reachable(site, v) and not reachable(after, v):
                lost.append(f"the {peer} at {v}")
    if lost:
        notes.append("Nothing in the file reaches " + ", ".join(dict.fromkeys(lost)) + " any more: no subnet or "
                     "static route covers it on the new subnet. Add a route, or those links won't come up.")

    used = uses(site, target)
    confirm = [f"{new_ip}/{prefix} is free on the site's network"
               + (f", and the router at {new_gw} serves {new_net}." if new_gw else ".")]
    if "M-plane" in used and new_ip != old_ip:
        confirm.append(f"NetAct (or whatever manages the BTS) reaches it on {new_ip} after loading: the old "
                       f"address {old_ip} stops answering.")
    if any(u for u in used if u != "M-plane") and new_ip != old_ip:
        confirm.append(f"The core and the neighbouring eNBs/gNBs accept connections from {new_ip}: firewalls, "
                       "IPsec policies and peer X2/Xn settings that name the old address are outside this file.")
    return finish(ctx, doc, {
        "label": f"IP {what} {new_ip}/{prefix}",
        "summary": f"{what} from {old_ip}/{old_net.prefixlen if old_net else '?'} to {new_ip}/{prefix}",
        "notes": notes,
        "confirm": confirm,
        "focus": f"{tdn}::p::localIpAddr",
    })

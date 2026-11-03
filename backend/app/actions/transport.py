"""
What the file says about its IP transport, for the actions that point the
BTS at another node (MME, AMF, neighbours): the addresses it owns, the
subnets and static routes it can reach, and the C-plane address a core
sees it on.

Two transport models (PROJECT_STATE §9.9):
  - TNLSVC (SBTS/SRAN): IPADDRESSV4/V6 localIpAddr + localIpPrefixLength
    under IPIF; IPRT staticRoutes rows with destIpAddr +
    destinationIpPrefixLength (or netmask on older releases), IPRTV6
    staticIpv6Routes; planes point at an address object by DN (MPLANENW,
    TRSNW cPlane/uPlane, the NRBTS plane lists).
  - FTM (Flexi Zone): IEIF/IVIF localIpAddr + netmask; IPNO cPlaneIpAddress.

Pure: reads a links.Site, never the disk.
"""
from __future__ import annotations

import ipaddress
from typing import Optional

from .links import Site


def check_ip(value: str) -> tuple[Optional[str], list[str]]:
    """(problem, notes) for an address a core node will be reached on,
    after the LNMME ipAddrPrim rules (the same ranges apply to any peer)."""
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return f"{value!r} isn't an IPv4 or IPv6 address.", []
    if ip.version == 4:
        if ip == ipaddress.ip_address("0.0.0.0") or ip == ipaddress.ip_address("255.255.255.255") \
                or ip.is_multicast or ip.is_loopback:
            return (f"{ip} can't be a peer address: Nokia doesn't allow 0.0.0.0, 255.255.255.255, multicast "
                    "(224.0.0.0-239.255.255.255) or loopback (127.0.0.0/8)."), []
        return None, []
    if not (ip in ipaddress.ip_network("fc00::/7") or ip in ipaddress.ip_network("2000::/3")):
        return None, [f"{ip} is neither unique-local (FC00::/7) nor global unicast (2000::/3), the ranges Nokia "
                      "recommends for IPv6 peers."]
    return None, []


def _network(addr: Optional[str], prefix: Optional[str] = None, netmask: Optional[str] = None):
    if not addr:
        return None
    try:
        if prefix not in (None, ""):
            return ipaddress.ip_network(f"{addr}/{prefix}", strict=False)
        if netmask:
            return ipaddress.ip_network(f"{addr}/{netmask}", strict=False)
    except ValueError:
        return None
    return None


def unset_address(value: Optional[str]) -> bool:
    """0.0.0.0 (or ::) is how a file leaves an address unconfigured: an
    unused Flexi Zone IEIF holds 0.0.0.0 with netmask 0.0.0.0 in 44 files,
    with the address on its VLAN interface (IVIF)."""
    try:
        return not value or ipaddress.ip_address(value.strip()).is_unspecified
    except ValueError:
        return False


def subnets(site: Site) -> list[tuple[str, object]]:
    """(owning object, network) for every address the BTS has."""
    out = []
    for m in site.of("IPADDRESSV4") + site.of("IPADDRESSV6"):
        if not unset_address(m["p"].get("localIpAddr")):
            net = _network(m["p"].get("localIpAddr"), m["p"].get("localIpPrefixLength"))
            if net:
                out.append((m["dn"], net))
    for cls in ("IEIF", "IVIF"):
        for m in site.of(cls):
            if not unset_address(m["p"].get("localIpAddr")):
                net = _network(m["p"].get("localIpAddr"), netmask=m["p"].get("netmask"))
                if net:
                    out.append((m["dn"], net))
    return out


def routes(site: Site) -> list[tuple[str, object, Optional[str]]]:
    """(IPRT or IPRTV6, destination network, gateway) for every static
    route: IPRT staticRoutes, IPRTV6 staticIpv6Routes."""
    out = []
    for m in site.of("IPRT"):
        for row in (m.get("lists") or {}).get("staticRoutes", []):
            net = _network(row.get("destIpAddr"), row.get("destinationIpPrefixLength"), row.get("netmask"))
            if net:
                out.append((m["dn"], net, row.get("gateway")))
    for m in site.of("IPRTV6"):
        for row in (m.get("lists") or {}).get("staticIpv6Routes", []):
            net = _network(row.get("destIpv6Addr"), row.get("destinationIpv6PrefixLength"))
            if net:
                out.append((m["dn"], net, row.get("gatewayIpv6Addr")))
    return out


def reachable(site: Site, value: str) -> Optional[str]:
    """How the BTS reaches `value` ("on IPADDRESSV4-1's subnet", "via the
    static route to 10.0.0.0/8"), or None when nothing in the file does.
    A file with no addresses at all (a partial export) counts as reachable:
    there is nothing to judge by."""
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    nets, rts = subnets(site), routes(site)
    if not nets and not rts:
        return "no transport in this file to check against"
    for dn, net in nets:
        if net.version == ip.version and ip in net:
            return f"on {dn.rsplit('/', 1)[-1]}'s subnet {net}"
    best = None
    for dn, net, gw in rts:
        if net.version == ip.version and ip in net and (best is None or net.prefixlen > best[1].prefixlen):
            best = (dn, net, gw)
    if best:
        return f"via the static route to {best[1]}" + (f" (gateway {best[2]})" if best[2] else "")
    return None


def address(site: Site, dn: Optional[str]) -> Optional[str]:
    """The address an IPADDRESSV4 (or IPADDRESSV6) distName holds."""
    m = site.by_dn.get(dn or "")
    if not m:
        return None
    return m["p"].get("localIpAddr") or m["p"].get("localIpv6Addr")


def lte_cplane(site: Site, enb: str, transport_nw: Optional[str]) -> Optional[str]:
    """The S1 C-plane address of an eNB on a transport network: TRSNW's
    cPlane (TNLSVC) or IPNO's cPlaneIpAddress (FTM)."""
    for t in site.child(enb, "TRSNW"):
        if transport_nw is None or t["p"].get("transportNwId", "0") == transport_nw:
            for row in (t.get("lists") or {}).get("cPlane", []):
                a = address(site, row.get("ipV4AddressDN1") or row.get("ipV6AddressDN1"))
                if a:
                    return a
    for m in site.of("IPNO"):
        if m["p"].get("cPlaneIpAddress"):
            return m["p"]["cPlaneIpAddress"]
    return None


NR_PLANES = ("ngCplane", "x2Cplane", "xnCplane", "s1Uplane", "ngUplane")


def nr_cplane(site: Site, gnb: str) -> Optional[str]:
    """The NG-C address of a gNB: NRBTS ngCplane, else the address its
    other planes use. 18 SA gNBs in the corpus (on-air lab ones among them)
    have no ngCplane and a single address for everything."""
    m = site.by_dn.get(gnb) or {}
    for plane in NR_PLANES:
        for row in (m.get("lists") or {}).get(plane, []):
            a = address(site, row.get("ipV4AddressDN1") or row.get("ipV6AddressDN1"))
            if a:
                return a
    return None


def plane_refs(site: Site, dn: str, planes) -> list[str]:
    """The address objects the plane lists of `dn` point at, present or not."""
    m = site.by_dn.get(dn) or {}
    return [ref for plane in planes for row in (m.get("lists") or {}).get(plane, [])
            for ref in (row.get("ipV4AddressDN1"), row.get("ipV6AddressDN1")) if ref]


def has_transport(site: Site) -> bool:
    """Whether the file carries IP transport at all. Flexi Zone BTS
    commissioning files often don't (33 LTE files in the corpus); their
    addresses are set outside the file."""
    return any(site.of(cls) for cls in ("IPADDRESSV4", "IPNO", "IEIF", "TRSNW", "IPRT"))

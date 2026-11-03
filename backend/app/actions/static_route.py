"""
Add a static route: a row of IPRT staticRoutes (IPv4) or IPRTV6
staticIpv6Routes (IPv6).

Which table: IPRT-1 is the main routing table. A file with several IPRTs
(source-based routing, SR000403) picks a table by the packet's source
address through RTPOL routingPolicies. The route goes to the table whose
routes already leave through the gateway's subnet, else the one RTPOL
sends that subnet's address to, else the main table; the form can name
one instead. A file with an IPNO and no table gets IPRT-1 (IPRTV6-1).

The row is written the way the table's other rows are: prefix length or
netmask (FTM), preferred source (the BTS's address on the gateway's
subnet, or unset, as the file's other routes do; with none, set on Flexi
Zone and where several tables route by source), bfdId on Flexi Zone, MTU
only when given.

Refused, after the dictionary's gateway rules (IPRT gateway,
IPRTV6 gatewayIpv6Addr): a gateway on none of the BTS's subnets, the
lowest or highest address of its subnet, a reserved address, a BTS
address in the main table, an IPv6 gateway outside FC00::/7 and 2000::/3;
and a route the table already has with that gateway. Noted: a second path
to the same destination (the lower preference wins), and the peers the
file reaches only with the route.
"""
from __future__ import annotations

import collections
import ipaddress
from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, instance, label, parent_dn, why
from .ip_address import PEERS, _text
from .links import Site, _runtime
from .transport import reachable, subnets, unset_address

ID = "static-route"
TITLE = "Add a static route"
GROUP = "Transport"
SUMMARY = "Route a destination subnet through a gateway on one of the BTS's subnets (IPRT, IPRTV6)."
UI = "form"
KEYWORDS = "static route IPRT IPRTV6 staticRoutes gateway next hop default route destination subnet RTPOL routing table"

TABLES = {4: ("IPRT", "staticRoutes"), 6: ("IPRTV6", "staticIpv6Routes")}
FIELDS = {
    4: {"dest": "destIpAddr", "prefix": "destinationIpPrefixLength", "gw": "gateway", "src": "preSrcIpv4Addr"},
    6: {"dest": "destIpv6Addr", "prefix": "destinationIpv6PrefixLength", "gw": "gatewayIpv6Addr",
        "src": "preSrcIpv6Addr"},
}
# A row's fields when the file has no route to follow: the commonest shapes
# in the files this was built from (TNLSVC 138 of 274 rows, FTM all 27).
SHAPES = {
    ("TNLSVC", 4): ("destIpAddr", "destinationIpPrefixLength", "gateway", "preSrcIpv4Addr", "preference"),
    ("FTM", 4): ("bfdId", "destIpAddr", "gateway", "netmask", "preSrcIpv4Addr", "preference"),
    ("TNLSVC", 6): ("destinationIpv6PrefixLength", "destIpv6Addr", "gatewayIpv6Addr", "preference", "preSrcIpv6Addr"),
}
# IPv4 gateways the dictionary rules out (IPRT gateway, rule 3).
RESERVED = (("127.0.0.0/8", "loopback"), ("192.168.253.0/24", "Nokia-internal"), ("192.168.254.0/23", "Nokia-internal"),
            ("169.254.0.0/16", "link-local"))
AUTO = "auto"


def _ip(value: Optional[str]):
    try:
        return ipaddress.ip_address((value or "").strip())
    except ValueError:
        return None


def _model(dn: str) -> str:
    return "FTM" if "/FTM-" in dn else "TNLSVC"


def tables(site: Site, version: int) -> list[dict]:
    cls, _ = TABLES[version]
    return [m for m in site.of(cls) if not _runtime(m["dn"])]


def _rows(m: dict) -> list[dict]:
    return (m.get("lists") or {}).get(TABLES[6 if m["cls"] == "IPRTV6" else 4][1], [])


def _row_net(row: dict, version: int):
    f = FIELDS[version]
    try:
        if row.get(f["prefix"]) not in (None, ""):
            return ipaddress.ip_network(f"{row.get(f['dest'])}/{row[f['prefix']]}", strict=False)
        if row.get("netmask"):
            return ipaddress.ip_network(f"{row.get(f['dest'])}/{row['netmask']}", strict=False)
    except ValueError:
        return None
    return None


def _leaves_through(rows: list[dict], version: int, net) -> bool:
    """Whether any of the rows' gateways is on `net`."""
    gws = [_ip(r.get(FIELDS[version]["gw"])) for r in rows]
    return any(g is not None and g.version == net.version and g in net for g in gws)


def _subnet_of(site: Site, ip) -> Optional[tuple[str, object]]:
    """(address object, network) of the BTS subnet holding `ip`."""
    best = None
    for dn, net in subnets(site):
        if net.version == ip.version and ip in net and (best is None or net.prefixlen > best[1].prefixlen):
            best = (dn, net)
    return best


def _own(site: Site, dn: str) -> Optional[str]:
    return (site.by_dn.get(dn) or {}).get("p", {}).get("localIpAddr")


def _policy_table(site: Site, src) -> Optional[str]:
    """The table RTPOL sends packets from `src` to, by the lowest orderNumber."""
    hits = []
    for m in site.of("RTPOL"):
        for row in (m.get("lists") or {}).get("routingPolicies", []):
            addr = row.get("srcIpAddress") or row.get("srcIPAddress")
            try:
                net = ipaddress.ip_network(f"{addr}/{row.get('srcIpPrefixLength') or 0}", strict=False)
            except ValueError:
                continue
            if net.version == src.version and src in net:
                hits.append((int(row.get("orderNumber") or 0), row.get("routingTableDN") or row.get("routingTablePtr")))
    return min(hits)[1] if hits else None


def pick_table(site: Site, gw) -> Optional[str]:
    """The table a route through `gw` belongs in (see the module doc).
    Where several tables leave through the subnet, the one the routing
    policy sends the subnet's address to, else the main table."""
    ts = tables(site, gw.version)
    if not ts:
        return None
    main = next((m["dn"] for m in ts if instance(m["dn"]) == "1"), ts[0]["dn"])
    sub = _subnet_of(site, gw)
    if sub:
        src = _ip(_own(site, sub[0]))
        policy = _policy_table(site, src) if src else None
        via = [m["dn"] for m in ts if _leaves_through(_rows(m), gw.version, sub[1])]
        if via:
            return policy if policy in via else main if main in via else via[0]
        if policy in {m["dn"] for m in ts}:
            return policy
    return main


def _ipno(site: Site, version: int) -> Optional[str]:
    """Where a first table goes: the IPNO next to the BTS's addresses."""
    ipnos = [m["dn"] for m in site.of("IPNO") if not _runtime(m["dn"])]
    for dn, _ in subnets(site):
        hit = next((i for i in ipnos if dn.startswith(parent_dn(i) + "/")), None)
        if hit and (version == 4 or _model(hit) == "TNLSVC"):
            return hit
    return None


def _mtu(m: Optional[dict]) -> str:
    """The MTU the table's routes share, if they all set the same one."""
    vals = {r.get("routeIpMtu") for r in _rows(m)} if m else set()
    return next(iter(vals)) if len(vals) == 1 and None not in vals else ""


def _describe(site: Site, m: dict) -> str:
    rows = _rows(m)
    bits = [label(m["dn"])]
    if m["p"].get("userLabel"):
        bits.append(m["p"]["userLabel"])
    bits.append(f"{len(rows)} route{'s' if len(rows) != 1 else ''}" if rows else "no routes")
    v = 6 if m["cls"] == "IPRTV6" else 4
    gws = list(dict.fromkeys(r.get(FIELDS[v]["gw"]) for r in rows if r.get(FIELDS[v]["gw"])))
    if gws:
        bits.append("via " + ", ".join(gws[:2]) + ("…" if len(gws) > 2 else ""))
    return " · ".join(bits)


def route_row(site: Site, table: str, net, gw, src_own: Optional[str], pref: str = "", mtu: str = "",
              set_source: bool = False) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    """(row, reasons, notes) for a route in `table`, written the way the
    file's other routes are. `set_source` sets the preferred source to
    `src_own` whatever they do (a table of its own, picked by source)."""
    v = net.version
    f = FIELDS[v]
    by = {m["dn"]: m for m in tables(site, v)}
    rows = _rows(by[table]) if table in by else []
    notes = []
    # Follow the table's rows, else another table's, else the commonest shape.
    siblings = rows or [r for t in by.values() for r in _rows(t)]
    shape = list(siblings[0]) if siblings else list(SHAPES.get((_model(table), v)) or SHAPES[("TNLSVC", v)])
    # The preferred source follows the other routes. With none to follow, it is set on Flexi Zone (all 27 FTM
    # routes in the files this was built from) and where several tables route by source address (73 of 81),
    # and left unset on a single TNLSVC table (116 of 166).
    sets_src = [r for r in siblings if r.get(f["src"]) is not None]
    src_like_siblings = set_source or (any(not unset_address(r.get(f["src"])) for r in sets_src) if sets_src
                                       else _model(table) == "FTM" or len(by) > 1)
    spelled = next((r.get(f["gw"]) for r in siblings if r.get(f["gw"])), "")
    values = {
        f["dest"]: _text(net.network_address, spelled), f["prefix"]: str(net.prefixlen),
        "netmask": str(net.netmask) if v == 4 else None, f["gw"]: _text(gw, spelled),
        f["src"]: (src_own if src_like_siblings and src_own else ("0.0.0.0" if v == 4 else "::")),
        "preference": pref or None, "bfdId": "0",
        "routeIpMtu": mtu or None,
    }
    if f["src"] not in shape and set_source:
        shape.append(f["src"])
    if "netmask" in shape and f["prefix"] in shape:
        shape.remove("netmask")
    if pref and "preference" not in shape:
        shape.append("preference")
    if mtu and "routeIpMtu" not in shape:
        if _model(table) == "FTM":
            notes.append("Flexi Zone (FTM) routes have no MTU setting; it isn't written.")
        else:
            shape.append("routeIpMtu")
    row = [(k, values[k]) for k in shape if values.get(k) is not None]
    reasons = []
    if any(k == f["src"] for k, _ in row):
        reasons.append(f"preferred source {dict(row)[f['src']]}"
                       + (" (the BTS's address on the gateway's subnet)" if dict(row)[f["src"]] == src_own else
                          " (unset, like the file's other routes)" if sets_src else " (unset: a single routing table)"))
    if any(k == "bfdId" for k, _ in row):
        reasons.append("bfdId 0, not protected by a BFD session")
    return row, reasons, notes


def available(ctx: Context) -> Optional[str]:
    site = ctx.site
    if not subnets(site):
        return "This file sets no IP address of the BTS, so there is no subnet a gateway could be on."
    if not (tables(site, 4) or tables(site, 6) or _ipno(site, 4)):
        return "This file has no routing table (IPRT) and no IPNO to put one in."
    return None


def setup(ctx: Context) -> dict:
    site = ctx.site
    table_opts = [{"value": AUTO, "key": AUTO, "label": "Pick from the gateway",
                   "details": ["The table whose routes already leave through the gateway's subnet, else the one "
                               "the routing policy (RTPOL) sends that subnet's address to, else the main table."]}]
    mtus = {AUTO: ""}
    # A table of an IP version the BTS has no address in can't take a route.
    versions = [v for v in (4, 6) if any(n.version == v for _, n in subnets(site))]
    for v in versions:
        for m in tables(site, v):
            table_opts.append({"value": m["dn"], "key": m["dn"], "group": f"IPv{v} tables",
                               "label": _describe(site, m)})
            mtus[m["dn"]] = _mtu(m)
    gws = collections.OrderedDict()
    for v in versions:
        for m in tables(site, v):
            for r in _rows(m):
                g = r.get(FIELDS[v]["gw"])
                net = _row_net(r, v)
                # A gateway the dictionary rules out (the site check warns of it) isn't one to reuse.
                if g and _ip(g) and g not in gws and not _gateway_problems(site, _ip(g), m["dn"]):
                    sub = _subnet_of(site, _ip(g))
                    gws[g] = {"value": g, "group": "Gateways the file's routes use",
                              "label": f"{g} · {label(m['dn'])}" + (f" · on {sub[1]}" if sub else "")
                                       + (" · default route" if net is not None and net.prefixlen == 0 else "")}
    return {
        "intro": "Adds a static route. The gateway must be on one of the BTS's subnets; the route goes into the "
                 "routing table whose routes already leave through that subnet.",
        "fields": [
            {"id": "destination", "label": "Destination", "type": "text",
             "placeholder": "10.20.0.0/16, or 0.0.0.0/0 for a default route",
             "hint": "A subnet with its prefix length (or netmask). An address alone is a host route (/32, /128)."},
            {"id": "gateway", "label": "Gateway", "type": "combo", "options": list(gws.values()),
             "placeholder": "The next hop's address",
             "hint": "The router the BTS hands these packets to, on one of its own subnets."},
            {"id": "table", "label": "Routing table", "type": "select", "options": table_opts, "default": AUTO},
            {"id": "preference", "label": "Preference", "type": "text", "default": "1",
             "hint": "Lower wins (the dictionary: a lower preference value means a lower cost). Give a backup "
                     "route a higher one."},
            {"id": "mtu", "label": "Route MTU", "type": "text", "optional": True, "dependsOn": "table",
             "defaultByKey": mtus, "placeholder": "Not set",
             "hint": "The IP MTU toward the destination (355-8982). Most routes in the files this was built from "
                     "leave it unset."},
        ],
    }


def _destination(text: str):
    t = (text or "").strip()
    if t.lower() == "default":
        t = "0.0.0.0/0"
    t = " ".join(t.split())
    if " " in t:
        t = t.replace(" ", "/", 1)
    try:
        exact = ipaddress.ip_network(t, strict=True)
        return exact, None
    except ValueError:
        pass
    try:
        net = ipaddress.ip_network(t, strict=False)
    except ValueError:
        return None, None
    return net, f"{t} has host bits set; the route is to {net}."


def _gateway_problems(site: Site, gw, table: Optional[str]) -> list[str]:
    rule = "IPRT gateway" if gw.version == 4 else "IPRTV6 gatewayIpv6Addr"
    out = []
    sub = _subnet_of(site, gw)
    if gw.version == 4:
        if gw.is_unspecified or gw == ipaddress.ip_address("255.255.255.255"):
            out.append(f"{gw} can't be a gateway ({rule}: not 0.0.0.0 or 255.255.255.255).")
        for net, what in RESERVED:
            if gw in ipaddress.ip_network(net):
                out.append(f"{gw} is in the {what} range {net}, which the dictionary rules out for a gateway "
                           f"({rule}).")
    elif not (gw in ipaddress.ip_network("fc00::/7") or gw in ipaddress.ip_network("2000::/3")):
        out.append(f"{gw} isn't unique-local (FC00::/7) or global unicast (2000::/3), the ranges the dictionary "
                   f"allows for a gateway ({rule}).")
    if out:
        return out
    if not sub:
        nets = ", ".join(str(n) for _, n in subnets(site) if n.version == gw.version) or "none"
        return [f"{gw} is on none of the BTS's IPv{gw.version} subnets ({nets}). The dictionary requires the "
                f"gateway to be on one ({rule}); the BTS can't reach a next hop off its own links."]
    net = sub[1]
    if net.num_addresses > 2 and gw in (net.network_address, net.broadcast_address):
        out.append(f"{gw} is the {'lowest' if gw == net.network_address else 'highest'} address of {net}; the "
                   f"dictionary doesn't allow either as a gateway ({rule}).")
    own = {_ip(_own(site, dn)) for dn, _ in subnets(site)}
    if gw in own and (table is None or instance(table) == "1"):
        out.append(f"{gw} is one of the BTS's own addresses. A route in the main table can't use it as its "
                   f"gateway ({rule}).")
    return out


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    problems, notes = [], []
    net, host_note = _destination(inputs.get("destination") or "")
    if net is None:
        raise PlanError([f"{(inputs.get('destination') or '').strip()!r} isn't a subnet (10.20.0.0/16) or an "
                         "address." if (inputs.get("destination") or "").strip() else "Enter the destination."])
    if host_note:
        notes.append(host_note)
    gw_text = (inputs.get("gateway") or "").strip()
    gw = _ip(gw_text)
    if gw is None:
        raise PlanError([f"{gw_text!r} isn't an IP address." if gw_text else "Enter the gateway."])
    if gw.version != net.version:
        raise PlanError([f"The destination {net} is IPv{net.version} and the gateway {gw} IPv{gw.version}."])
    v = net.version
    cls, lname = TABLES[v]
    f = FIELDS[v]

    pick = inputs.get("table") or AUTO
    by = {m["dn"]: m for m in tables(site, v)}
    if pick != AUTO and pick not in by:
        other = {m["dn"] for m in tables(site, 10 - v)}
        raise PlanError([f"{label(pick)} holds IPv{10 - v} routes; pick an IPv{v} table." if pick in other
                         else "Pick a routing table."])
    table = pick if pick != AUTO else pick_table(site, gw)
    problems += _gateway_problems(site, gw, table)

    pref = (inputs.get("preference") or "").strip()
    if pref and not (pref.isdigit() and int(pref) <= 4294967295):
        problems.append(f"{pref!r} isn't a preference (0-4294967295).")
    mtu = (inputs.get("mtu") or "").strip()
    if mtu and not (mtu.isdigit() and 355 <= int(mtu) <= 8982):
        problems.append(f"{mtu!r} isn't a route MTU (355-8982).")
    if problems:
        raise PlanError(problems)

    m = by.get(table)
    rows = _rows(m) if m else []
    for r in rows:
        if _row_net(r, v) == net and _ip(r.get(f["gw"])) == gw:
            raise PlanError([f"{label(table)} already routes {net} via {gw}."])
    for t in by.values():
        for r in _rows(t):
            if _row_net(r, v) == net and _ip(r.get(f["gw"])) != gw:
                same = (r.get("preference") or "") == pref
                notes.append(f"{label(t['dn'])} already routes {net} via {r.get(f['gw'])} (preference "
                             f"{r.get('preference') or 'unset'}). "
                             + ("With the same preference, which path the BTS takes isn't defined by the file; "
                                "give the backup a higher one." if same and t["dn"] == table else
                                "The lower preference wins; the other is the backup." if t["dn"] == table else
                                "That table serves other source addresses."))
    sub = _subnet_of(site, gw)
    for dn, own_net in subnets(site):
        if own_net.version == v and own_net.overlaps(net) and net.prefixlen > 0 and own_net.prefixlen >= net.prefixlen:
            notes.append(f"{net} covers the BTS's own subnet {own_net}; packets for that subnet stay on it "
                         "(the connected route is more specific).")
            break

    doc = Doc(ctx.raw)
    w = why("route", f"The route to {net} via {gw}.", "choice")
    if m is None:
        if table:
            raise PlanError([f"{label(table)} isn't in the file."])
        ipno = _ipno(site, v)
        if not ipno:
            raise PlanError([f"The file has no {cls} and no IPNO to put one in."])
        table = doc.create(ipno, cls, "1", [], w=why("route", f"The main routing table; the file has no {cls}.",
                                                     "choice"))
        notes.append(f"The file had no {cls}; the route goes into a new {label(table)}, the main routing table.")

    row, reasons, row_notes = route_row(site, table, net, gw, sub and _own(site, sub[0]), pref, mtu)
    notes += row_notes
    index = doc.add_item(table, lname, row,
                         why("route", f"The route to {net} via {gw}" + (f": {', '.join(reasons)}." if reasons else "."),
                             "choice"))

    if pick == AUTO and len(by) > 1:
        notes.append(f"It goes into {label(table)}: " + (
            "its routes already leave through the gateway's subnet." if _leaves_through(rows, v, sub[1]) else
            "the routing policy sends the gateway subnet's address to it." if sub and table == _policy_table(
                site, _ip(_own(site, sub[0])) or gw) else "it is the main table."))

    after = Context(doc.raw(), ctx.filename, ctx.source).site
    gained = []
    for c, field, peer in PEERS:
        for o in site.of(c):
            val = o["p"].get(field)
            if val and not unset_address(val) and _ip(val) and _ip(val).version == v and _ip(val) in net:
                if not reachable(site, val) and reachable(after, val):
                    gained.append(f"the {peer} at {val}")
    if gained:
        notes.append("With this route the file reaches " + ", ".join(dict.fromkeys(gained)) + ".")

    return finish(ctx, doc, {
        "label": f"Route {net} via {gw}",
        "summary": f"{label(table)}: {net} via {gw}" + (f", preference {pref}" if pref else ""),
        "notes": notes,
        "confirm": [f"The router at {gw} forwards traffic for {net}, and the far end routes replies back to the "
                    f"BTS's {sub[1] if sub else 'subnet'}."],
        "focus": f"{table}::list::{lname}::item::{index}",
    })

#!/usr/bin/env python3
"""
Corpus check for the VLAN interface action (backend/app/actions/ip_interface.py).

Sweep: on every Ethernet interface the form offers, a new VLAN with
198.51.100.10/29 (TEST-NET-2, RFC 5737; 203.0.113.10/29 where that
overlaps) and gateway .9, once with no plane moved and once with every
plane moved: no crash; the site check finds no new error or warning; the
same again on the result is refused.
Round trip: in files with several IP interfaces, each VLAN interface with
its IPIF, address, default route, own routing table and policy is
removed, the planes on it moved to another address, and it is added again
through the action with its VLAN, name, address, gateway, MTU and planes.
It must come back with the same values: the VLAN, the interface, the
address, the default route's gateway in a table of the same kind (its own
with a policy, or the main one), and the planes on it.

Usage: python3 scripts/interface_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if anything fails. Run from the repo root; no server needed.
"""
import collections
import ipaddress
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from app.actions import Context, PlanError, ip_interface  # noqa: E402
from app.actions.doc import Doc, instance, label, parent_dn, why  # noqa: E402
from app.actions.links import Site, _runtime  # noqa: E402
from app.actions.static_route import TABLES, _row_net, _rows, tables  # noqa: E402
from app.actions.transport import subnets  # noqa: E402
from app.ca import _load  # noqa: E402
from cell_check import load  # noqa: E402

W = why("check", "round trip", "choice")


def new_findings(plan):
    return [f["title"] for f in plan["check"]["new"] if f["severity"] in ("error", "warning")]


def _free_vlan(site, ethif):
    used = {v["p"].get("vlanId") for v in site.child(ethif, "VLANIF")}
    return next(str(v) for v in range(3999, 0, -1) if str(v) not in used)


def sweep(name, source, raw, counts, failures):
    ctx = Context(raw, name, source)
    if ip_interface.available(ctx):
        counts[("unavailable", "")] += 1
        return
    f = {x["id"]: x for x in ip_interface.setup(ctx)["fields"]}
    taken = [n for _, n in subnets(ctx.site)]
    base = next(b for b in ("198.51.100.0/29", "203.0.113.0/29", "192.0.2.0/29")
                if not any(n.version == 4 and n.overlaps(ipaddress.ip_network(b)) for n in taken))
    host = ipaddress.ip_network(base).network_address
    for e in f["ethif"]["options"]:
        for planes in ([], [o["value"] for o in f["planes"]["options"]]):
            inputs = {"ethif": e["value"], "vlan": _free_vlan(ctx.site, e["value"]), "name": "Check",
                      "address": f"{host + 2}/29", "gateway": str(host + 1), "planes": planes, "mtu": f["mtu"]["default"]}
            kind = "all planes" if planes else "no plane"
            where = f"{name} {e['label']} {kind}"
            try:
                out, plan = ip_interface.plan(ctx, inputs)
            except PlanError as ex:
                counts[(kind, "refused")] += 1
                failures.append(f"{where}: refused: {ex.problems}")
                continue
            except Exception:
                failures.append(f"{where}: crashed\n{traceback.format_exc()}")
                continue
            counts[(kind, "ok")] += 1
            # A file with no address before hides the gateway rule; what it then says of old routes isn't new.
            new = [t for t in new_findings(plan) if not ("off the BTS's subnets" in t and inputs["gateway"] not in t)]
            if new:
                failures.append(f"{where}: new findings {new[:3]}")
            try:
                ip_interface.plan(Context(out, name, source), inputs)
                failures.append(f"{where}: repeat not refused")
            except PlanError:
                pass
            except Exception:
                failures.append(f"{where}: repeat crashed\n{traceback.format_exc()}")


def _default_via(rows, net):
    for i, r in enumerate(rows):
        gw = r.get("gateway") or r.get("gatewayIpv6Addr")
        dest = _row_net(r, net.version)
        try:
            if dest is not None and dest.prefixlen == 0 and ipaddress.ip_address(gw) in net:
                return i, gw
        except ValueError:
            continue
    return None, None


def round_trip(name, source, raw, failures, skipped):
    site = Site(_load(raw))
    ipifs = [m for m in site.of("IPIF") if not _runtime(m["dn"])]
    if len(ipifs) < 2:
        return 0
    done = 0
    for ipif in ipifs:
        vdn = ipif["p"].get("interfaceDN") or ""
        vlan = site.by_dn.get(vdn)
        addrs = [m for m in site.child(ipif["dn"], "IPADDRESSV4") + site.child(ipif["dn"], "IPADDRESSV6")]
        if not vlan or vlan["cls"] != "VLANIF" or len(addrs) != 1:
            skipped["not one VLAN and one address"] += 1
            continue
        addr = addrs[0]
        others = [m for m in site.of(addr["cls"]) if m["dn"] != addr["dn"] and not _runtime(m["dn"])]
        if not others:
            skipped["no other address to park the planes on"] += 1
            continue
        try:
            net = ipaddress.ip_network(f"{addr['p']['localIpAddr']}/{addr['p']['localIpPrefixLength']}", strict=False)
        except (KeyError, ValueError):
            continue
        ip = addr["p"]["localIpAddr"]
        uses = [u for u in ip_interface.uses(site) if u["target"] == addr["dn"]]
        doc = Doc(raw)
        for u in uses:
            if u["list"]:
                for i, r in enumerate(site.by_dn[u["dn"]]["lists"][u["list"]]):
                    if r.get(u["field"]) == addr["dn"]:
                        doc.set_item(u["dn"], u["list"], i, u["field"], others[0]["dn"], W)
            else:
                doc.set(u["dn"], u["field"], others[0]["dn"], W)
        # Its routes: a table of its own goes; a default route in a shared table comes out.
        gw, own_table = None, None
        pols = [(p["dn"], i, r) for p in site.of("RTPOL") for i, r in enumerate(p["lists"].get("routingPolicies", []))
                if (r.get("srcIpAddress") or r.get("srcIPAddress")) == ip]
        for t in tables(site, net.version):
            if parent_dn(t["dn"]) != parent_dn(ipif["dn"]):
                continue
            i, g = _default_via(_rows(t), net)
            if g is None:
                continue
            gw = gw or g
            named = any((r.get("routingTableDN") or r.get("routingTablePtr")) == t["dn"] for _, _, r in pols)
            if instance(t["dn"]) != "1":
                own_table = t["dn"]
            if named and instance(t["dn"]) != "1" and len(_rows(t)) == 1:
                doc.delete(t["dn"], W)
            else:
                doc.remove_item(t["dn"], TABLES[net.version][1], i, W)
        for pdn, i, _ in sorted(pols, key=lambda x: -x[1]):
            doc.remove_item(pdn, "routingPolicies", i, W)
        for m in site.mos:
            for ln, vals in (m.get("simple") or {}).items():
                if ipif["dn"] in vals:
                    doc.remove_value(m["dn"], ln, ipif["dn"], W)
        doc.delete(ipif["dn"], W)
        doc.delete(vdn, W)
        stripped = doc.raw()
        ctx = Context(stripped, name, source)
        options = {o["value"] for o in ip_interface.uses(ctx.site)}
        planes = [u["value"] for u in uses if u["value"] in options]
        label_ = vlan["p"].get("userLabel") or ipif["p"].get("userLabel") or ""
        inputs = {"ethif": parent_dn(vdn), "vlan": vlan["p"].get("vlanId"), "name": label_,
                  "address": f"{ip}/{addr['p']['localIpPrefixLength']}", "gateway": gw or "", "planes": planes,
                  "mtu": ipif["p"].get("ipMtu") or "1500"}
        where = f"{name} {label(ipif['dn'])} VLAN {vlan['p'].get('vlanId')} {ip}"
        try:
            out, plan = ip_interface.plan(ctx, inputs)
        except PlanError as e:
            failures.append(f"{where}: round trip refused: {e.problems}")
            continue
        except Exception:
            failures.append(f"{where}: round trip crashed\n{traceback.format_exc()}")
            continue
        again = Site(_load(out))
        new_addr = plan["focus"]
        diff = []
        new_ipif = again.by_dn.get(parent_dn(new_addr), {})
        new_vlan = again.by_dn.get(new_ipif.get("p", {}).get("interfaceDN", ""), {})
        if new_vlan.get("p", {}).get("vlanId") != vlan["p"].get("vlanId"):
            diff.append("vlanId")
        if (new_vlan.get("p", {}).get("userLabel") or "") != (vlan["p"].get("userLabel") or ""):
            diff.append("VLANIF userLabel")
        if new_ipif.get("p", {}).get("ipMtu") != ipif["p"].get("ipMtu"):
            diff.append("ipMtu")
        if again.by_dn.get(new_addr, {}).get("p") != addr["p"]:
            diff.append("address")
        if gw:
            homes = [t for t in tables(again, net.version) if _default_via(_rows(t), net)[1]]
            if not homes:
                diff.append("default route")
            elif bool(own_table) != any(instance(t["dn"]) != "1" for t in homes):
                diff.append("default route's table")
        for u in uses:
            m = again.by_dn.get(u["dn"], {})
            vals = [r.get(u["field"]) for r in m.get("lists", {}).get(u["list"], [])] if u["list"] else \
                [m.get("p", {}).get(u["field"])]
            if new_addr not in vals:
                diff.append(f"plane {u['label'].split(' · ')[0]}")
        if diff:
            failures.append(f"{where}: differs in {diff}")
        done += 1
    return done


def main(folders):
    _, raws = load(folders)
    counts, skipped, failures = collections.Counter(), collections.Counter(), []
    done = 0
    for (source, name), raw in raws.items():
        sweep(name, source, raw, counts, failures)
        done += round_trip(name, source, raw, failures, skipped)
    print(f"{len(raws)} files")
    for (kind, result), n in sorted(counts.items()):
        print(f"  {kind:12} {result:8} {n}")
    print(f"round trip: {done} interfaces rebuilt")
    for reason, n in skipped.most_common():
        print(f"  skipped {n}: {reason}")
    print(f"{len(failures)} failures")
    for f in failures[:25]:
        print("  " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    folders = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(folders))

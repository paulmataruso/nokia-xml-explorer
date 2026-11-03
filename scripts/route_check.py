#!/usr/bin/env python3
"""
Corpus check for the static route action (backend/app/actions/static_route.py).

Sweep: on every file the action is available on, a route to 198.51.100.0/24
(TEST-NET-2, RFC 5737; 2001:db8:100::/48 for IPv6, RFC 3849) through each
gateway the form suggests, else through the first free host of each BTS
subnet: no crash; the site check finds no new error or warning; the same
again on the result is refused.
Round trip: every route in the files is removed and added again with its
destination, gateway, preference and MTU, once into its own table and once
with "Pick from the gateway". The row must come back with the same fields
and values (the preferred source and bfdId are the action's to choose), and
the automatic pick must find the table it was in when the table keeps
other routes or a routing policy names it. Picks that differ are counted,
and so are preferred sources that differ from the file's.

Usage: python3 scripts/route_check.py [folder ...]
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

from app.actions import Context, PlanError, static_route  # noqa: E402
from app.actions.doc import Doc, label, why  # noqa: E402
from app.actions.links import Site  # noqa: E402
from app.actions.static_route import AUTO, FIELDS, TABLES, _row_net, _rows, tables  # noqa: E402
from app.actions.transport import subnets  # noqa: E402
from app.ca import _load  # noqa: E402
from cell_check import load  # noqa: E402

W = why("check", "round trip", "choice")
TEST = {4: "198.51.100.0/24", 6: "2001:db8:100::/48"}


def new_findings(plan):
    return [f["title"] for f in plan["check"]["new"] if f["severity"] in ("error", "warning")]


def _free_host(site, net):
    own = {(site.by_dn.get(dn) or {}).get("p", {}).get("localIpAddr") for dn, _ in subnets(site)}
    for host in (net.hosts() if net.num_addresses > 2 else iter(net)):
        if str(host) not in own:
            return str(host)
    return None


def sweep(name, source, raw, counts, failures):
    ctx = Context(raw, name, source)
    if static_route.available(ctx):
        counts[("unavailable", "")] += 1
        return
    f = {x["id"]: x for x in static_route.setup(ctx)["fields"]}
    gws = [o["value"] for o in f["gateway"]["options"]]
    if not gws:
        gws = [g for g in (_free_host(ctx.site, n) for _, n in subnets(ctx.site)) if g]
    for gw in gws:
        v = ipaddress.ip_address(gw).version
        inputs = {"destination": TEST[v], "gateway": gw, "table": AUTO, "preference": "1", "mtu": ""}
        where = f"{name} via {gw}"
        try:
            out, plan = static_route.plan(ctx, inputs)
        except PlanError as e:
            counts[(f"sweep v{v}", "refused")] += 1
            if gw in [o["value"] for o in f["gateway"]["options"]]:
                failures.append(f"{where}: a suggested gateway refused: {e.problems}")
            continue
        except Exception:
            failures.append(f"{where}: crashed\n{traceback.format_exc()}")
            continue
        counts[(f"sweep v{v}", "ok")] += 1
        if new_findings(plan):
            failures.append(f"{where}: new findings {new_findings(plan)[:3]}")
        try:
            static_route.plan(Context(out, name, source), inputs)
            failures.append(f"{where}: repeat not refused")
        except PlanError:
            pass
        except Exception:
            failures.append(f"{where}: repeat crashed\n{traceback.format_exc()}")


def _same(a, b):
    try:
        return ipaddress.ip_address(a) == ipaddress.ip_address(b)
    except ValueError:
        return a == b


def round_trip(name, source, raw, picks, sources, repeats, failures):
    site = Site(_load(raw))
    done = 0
    for v in (4, 6):
        cls, lname = TABLES[v]
        fl = FIELDS[v]
        ts = tables(site, v)
        for t in ts:
            for i, row in enumerate(_rows(t)):
                prefix = row.get(fl["prefix"]) or row.get("netmask")
                if not (row.get(fl["dest"]) and row.get(fl["gw"]) and prefix):
                    continue
                # A route the table already has (host bits under a /0 make several rows one route) comes back
                # refused: the action takes it for a repeat.
                if any(j != i and _row_net(r, v) == _row_net(row, v) and _same(r.get(fl["gw"]) or "", row[fl["gw"]])
                       for j, r in enumerate(_rows(t))):
                    repeats[0] += 1
                    continue
                doc = Doc(raw)
                doc.remove_item(t["dn"], lname, i, W)
                stripped = doc.raw()
                ctx = Context(stripped, name, source)
                where = f"{name} {label(t['dn'])}[{i + 1}] {row.get(fl['dest'])}/{prefix} via {row[fl['gw']]}"
                for pick in (t["dn"], AUTO):
                    inputs = {"destination": f"{row[fl['dest']]}/{prefix}", "gateway": row[fl["gw"]],
                              "table": pick, "preference": row.get("preference") or "",
                              "mtu": row.get("routeIpMtu") or ""}
                    try:
                        out, plan = static_route.plan(ctx, inputs)
                    except PlanError as e:
                        if pick == t["dn"]:
                            # A gateway the dictionary rules out is refused; the site check warns of it too.
                            if not any("none of the BTS's" in p or "lowest" in p or "highest" in p
                                       for p in e.problems):
                                failures.append(f"{where}: round trip refused: {e.problems}")
                        break
                    except Exception:
                        failures.append(f"{where}: round trip crashed\n{traceback.format_exc()}")
                        break
                    table = plan["focus"].split("::list::")[0]
                    if pick == AUTO:
                        if table != t["dn"]:
                            picks[(name, t["dn"], table)] += 1
                            # With the table's other routes, or a policy of its own, left to go by, the pick
                            # must find it. Policies that send one source to several tables leave it open.
                            pols = [(r.get("srcIpAddress") or r.get("srcIPAddress"), r.get("srcIpPrefixLength"),
                                     r.get("routingTableDN") or r.get("routingTablePtr"))
                                    for p in site.of("RTPOL") for r in p["lists"].get("routingPolicies", [])]
                            own = [x for x in pols if x[2] == t["dn"]]
                            if len(_rows(t)) > 1 or (own and all(sum(1 for y in pols if y[:2] == x[:2]) == 1
                                                                 for x in own)):
                                failures.append(f"{where}: picked {label(table)}")
                        continue
                    got = _rows(Site(_load(out)).by_dn[table])[-1]
                    if not _same(row.get(fl["src"]) or "", got.get(fl["src"]) or ""):
                        sources[(row.get(fl["src"]) in (None, "0.0.0.0", "::"), got.get(fl["src"]) in ("0.0.0.0", "::"))] += 1
                    # A destination written with host bits comes back as its network.
                    diff = [k for k in set(row) | set(got) if k not in (fl["src"], "bfdId", fl["dest"])
                            and not _same(row.get(k) or "", got.get(k) or "")]
                    if _row_net(row, v) != _row_net(got, v):
                        diff.append(fl["dest"])
                    if diff:
                        failures.append(f"{where}: differs in {sorted(diff)}: {row} -> {got}")
                    done += 1
    return done


def main(folders):
    _, raws = load(folders)
    counts, picks, sources, failures = collections.Counter(), collections.Counter(), collections.Counter(), []
    repeats = [0]
    done = 0
    for (source, name), raw in raws.items():
        sweep(name, source, raw, counts, failures)
        done += round_trip(name, source, raw, picks, sources, repeats, failures)
    print(f"{len(raws)} files")
    for (kind, result), n in sorted(counts.items()):
        print(f"  {kind:14} {result:8} {n}")
    print(f"round trip: {done} routes rebuilt" + (f", {repeats[0]} the file repeats skipped" if repeats[0] else ""))
    if picks:
        print(f"  automatic pick differs on {sum(picks.values())} routes in {len({k[0] for k in picks})} files")
    for (was_unset, now_unset), n in sorted(sources.items()):
        print(f"  preferred source differs on {n} routes: {'unset' if was_unset else 'an address'} in the file, "
              f"{'unset' if now_unset else 'an address'} from the action")
    print(f"{len(failures)} failures")
    for f in failures[:25]:
        print("  " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    folders = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(folders))

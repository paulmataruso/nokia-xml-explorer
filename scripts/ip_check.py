#!/usr/bin/env python3
"""
Corpus check for the IP address action (backend/app/actions/ip_address.py).

For every address of the BTS in the given folders:
  1. Move it to the next host address on its subnet, then to a new subnet
     with a new gateway. A crash fails; a refusal is counted with its
     reason.
  2. The result must parse, and the site check must find no new error.
  3. No configured value may still hold the old address (runtime _R
     objects aside), and on a new subnet no route may still use the old
     gateway.
  4. Planning the same change on the result must be refused as unchanged,
     and taking another interface's address must be refused.

Usage: python3 scripts/ip_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if any file fails. Run from the repo root; no server needed.
"""
import collections
import ipaddress
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.actions import Context, PlanError, ip_address as action  # noqa: E402
from app.actions.links import _runtime  # noqa: E402
from app.parser import XmlParseError, parse_file  # noqa: E402

NEW_SUBNET = {4: ("172.31.99.10", "24", "172.31.99.1"), 6: ("fd00:99::10", "64", "fd00:99::1")}


def leftovers(site, old):
    """Configured values that still hold `old`."""
    out = []
    for m in site.mos:
        if _runtime(m["dn"]):
            continue
        for kind, ln, i, field, v in action._values(m):
            if v and action._ip(v) == old:
                out.append(f"{m['dn'].rsplit('/', 1)[-1]} {field or ln}")
    return out


def main(folders):
    paths = sorted(os.path.join(d, f) for d in folders for f in os.listdir(d) if f.lower().endswith(".xml"))
    ctx = lambda raw, name: Context(raw, name, "upload")
    counts, refusals, notes, failures = collections.Counter(), collections.Counter(), collections.Counter(), []

    def refused(c, inputs):
        try:
            action.plan(c, inputs)
        except PlanError:
            return True
        return False

    for path in paths:
        raw = open(path, "rb").read()
        name = os.path.basename(path)
        try:
            parse_file(raw, name)
        except XmlParseError:
            continue
        c = ctx(raw, name)
        try:
            if action.available(c):
                continue
            fields = {f["id"]: f for f in action.setup(c)["fields"]}
        except Exception:
            failures.append(f"{name}: setup crashed\n{traceback.format_exc()}")
            continue
        own = {m["dn"]: m for m in action.addresses(c.site)}
        for target in fields["target"]["options"]:
            dn = target["value"]
            old = action._ip(fields["ip"]["defaultByKey"][dn])
            prefix = fields["prefix"]["defaultByKey"][dn]
            gateway = fields["gateway"]["defaultByKey"][dn]
            net = action._net(own[dn])
            bump = next((h for h in (old + 1, old - 1) if h in net and h not in (net.network_address,
                         getattr(net, "broadcast_address", None)) and str(h) != gateway), None)
            ip6, p6, gw6 = NEW_SUBNET[old.version]
            cases = [("same subnet", {"ip": str(bump), "prefix": prefix, "gateway": gateway})] if bump else []
            cases.append(("new subnet", {"ip": ip6, "prefix": p6, "gateway": gw6 if gateway else ""}))
            for case, over in cases:
                inputs = {"target": dn, **over}
                where = f"{name} {target['label']} [{case}]"
                kind = (own[dn]["cls"], case)
                try:
                    out, plan = action.plan(c, inputs)
                except PlanError as e:
                    counts[(*kind, "refused")] += 1
                    for p in e.problems:
                        refusals[p[:90]] += 1
                    continue
                except Exception:
                    failures.append(f"{where}: plan crashed\n{traceback.format_exc()}")
                    continue
                counts[(*kind, "ok")] += 1
                for n in plan["notes"]:
                    notes[n.split(":")[0][:70]] += 1
                try:
                    parse_file(out, name)
                except XmlParseError as e:
                    failures.append(f"{where}: result doesn't parse: {e}")
                    continue
                broken = [f["title"] for f in plan["check"]["new"] if f["severity"] == "error"]
                if broken:
                    failures.append(f"{where}: new site-check errors: {broken}")
                after = ctx(out, name)
                left = leftovers(after.site, old)
                if left:
                    failures.append(f"{where}: still holds the old address in {left[:5]}")
                if gateway and case == "new subnet":
                    stale = [r for r in action._routes_via(after.site, net) if action._ip(r[4]) == action._ip(gateway)]
                    if stale:
                        failures.append(f"{where}: {len(stale)} route(s) still use the old gateway {gateway}")
                if not refused(after, inputs):
                    failures.append(f"{where}: the same change planned again isn't refused")
            for other, m in own.items():
                if other != dn and action._ip(m["p"]["localIpAddr"]).version == old.version:
                    if not refused(c, {"target": dn, "ip": m["p"]["localIpAddr"], "prefix": prefix,
                                       "gateway": gateway}):
                        failures.append(f"{name} {target['label']}: taking {other}'s address isn't refused")
                    break

    for key, n in sorted(counts.items()):
        print(f"{' / '.join(key)}: {n}")
    for reason, n in refusals.most_common():
        print(f"  refused {n}x: {reason}")
    for note, n in notes.most_common():
        print(f"  note {n}x: {note}")
    for f in failures:
        print("FAIL", f)
    print(f"{len(failures)} failure{'s' if len(failures) != 1 else ''}")
    return 1 if failures else 0


if __name__ == "__main__":
    args = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(args))

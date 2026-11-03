#!/usr/bin/env python3
"""
Corpus check for the NTP and DNS action (backend/app/actions/ntp_dns.py).

Sweep: on every file the action is available on, two NTP servers and two
DNS servers (TEST-NET addresses, RFC 5737; DNS only where the file has no
CLOCK to hold NTP): no crash; the site check
finds no new error or warning; the same again on the result is refused
(nothing to change).
Round trip: every file's NTP servers are removed and typed back in, and
its DNS servers likewise (the DNS object deleted, or the Flexi Zone IDNS
set to 0.0.0.0). They must come back in the same list (by release), with
the same values in the same object.

Usage: python3 scripts/ntp_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if anything fails. Run from the repo root; no server needed.
"""
import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from app.actions import Context, PlanError, ntp_dns  # noqa: E402
from app.actions.doc import Doc, why  # noqa: E402
from app.actions.links import Site  # noqa: E402
from app.ca import _load  # noqa: E402
from cell_check import load  # noqa: E402

W = why("check", "round trip", "choice")
SWEEP = {"ntp": "192.0.2.123, 198.51.100.123", "dns1": "192.0.2.53", "dns2": "198.51.100.53", "source": "keep"}


def new_findings(plan):
    return [f["title"] for f in plan["check"]["new"] if f["severity"] in ("error", "warning")]


def sweep(name, source, raw, counts, failures):
    ctx = Context(raw, name, source)
    if ntp_dns.available(ctx):
        counts["unavailable"] += 1
        return
    inputs = SWEEP if ntp_dns._ntp_home(ctx.site) else {**SWEEP, "ntp": ""}
    try:
        out, plan = ntp_dns.plan(ctx, inputs)
    except PlanError as e:
        failures.append(f"{name}: sweep refused: {e.problems}")
        return
    except Exception:
        failures.append(f"{name}: sweep crashed\n{traceback.format_exc()}")
        return
    counts["sweep ok"] += 1
    if new_findings(plan):
        failures.append(f"{name}: new findings {new_findings(plan)[:3]}")
    try:
        ntp_dns.plan(Context(out, name, source), inputs)
        failures.append(f"{name}: repeat not refused")
    except PlanError:
        pass


def _ntp(site):
    m = ntp_dns._one(site, "NTP") or ntp_dns._one(site, "INTP")
    if not m:
        return None, None, []
    lname = next((k for k in ("ntpServerIpAddrOrFqdnList", "ntpServerIpAddrList", "ntpServers") if k in m["simple"]),
                 None)
    return m["dn"], lname, list(m["simple"].get(lname, [])) if lname else []


def _dns(site):
    m = ntp_dns._one(site, "DNS") or ntp_dns._one(site, "IDNS")
    return (m["dn"], dict(m["p"])) if m else (None, {})


def round_trip(name, source, raw, counts, failures):
    site = Site(_load(raw))
    now = ntp_dns.current(site)
    model = ntp_dns._model(site)
    dn, lname, servers = _ntp(site)
    if servers:
        doc = Doc(raw)
        doc.set_values(dn, lname, [], W)
        ctx = Context(doc.raw(), name, source)
        try:
            out, _ = ntp_dns.plan(ctx, {"ntp": ", ".join(servers), "dns1": "", "dns2": "", "source": "keep"})
            got = _ntp(Site(_load(out)))
            if got != (dn, lname, servers):
                failures.append(f"{name}: NTP came back as {got}, was {(dn, lname, servers)}")
            counts["NTP rebuilt"] += 1
        except PlanError as e:
            failures.append(f"{name}: NTP round trip refused: {e.problems}")
        except Exception:
            failures.append(f"{name}: NTP round trip crashed\n{traceback.format_exc()}")
    ddn, dparams = _dns(site)
    if ddn and not ntp_dns._unset(now["dns1"]):
        doc = Doc(raw)
        if model == "FTM":
            doc.set(ddn, "serverIpAddress", "0.0.0.0", W)
            doc.set(ddn, "serverIpAddress2", "0.0.0.0", W)
        elif set(dparams) <= {"serverIpAddressPrimary", "serverIpAddressSecondary"}:
            doc.delete(ddn, W)
        else:
            counts["DNS skipped (other settings)"] += 1
            return
        ctx = Context(doc.raw(), name, source)
        d2 = "" if ntp_dns._unset(now["dns2"]) else now["dns2"]
        try:
            out, _ = ntp_dns.plan(ctx, {"ntp": "", "dns1": now["dns1"], "dns2": d2, "source": "keep"})
            got = _dns(Site(_load(out)))
            if got != (ddn, dparams):
                failures.append(f"{name}: DNS came back as {got}, was {(ddn, dparams)}")
            counts["DNS rebuilt"] += 1
        except PlanError as e:
            failures.append(f"{name}: DNS round trip refused: {e.problems}")
        except Exception:
            failures.append(f"{name}: DNS round trip crashed\n{traceback.format_exc()}")


def main(folders):
    _, raws = load(folders)
    counts, failures = collections.Counter(), []
    for (source, name), raw in raws.items():
        sweep(name, source, raw, counts, failures)
        round_trip(name, source, raw, counts, failures)
    print(f"{len(raws)} files")
    for k, n in sorted(counts.items()):
        print(f"  {k:30} {n}")
    print(f"{len(failures)} failures")
    for f in failures[:25]:
        print("  " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    folders = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(folders))

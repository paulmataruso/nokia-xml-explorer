#!/usr/bin/env python3
"""
Corpus check for the PLMN action (backend/app/actions/plmn.py).

Sweep: on every eNB and gNB, the test PLMN 001-01 (and 999-99 where that
is taken) on every cell and slice the form offers: no crash; the site
check finds no new error or warning; the same again on the result is
refused. Refusals by the dictionary's rules are counted.
Round trip: every further PLMN of every LTE cell, and every NRPLMN but a
gNB's first, is removed and added again with the cells, slices and
reservation it had. It must come back with the same rows and the same
lists.

Usage: python3 scripts/plmn_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if anything fails. Run from the repo root; no server needed.
"""
import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from app.actions import Context, PlanError, delete, plmn  # noqa: E402
from app.actions.doc import Doc, label, why  # noqa: E402
from app.actions.links import Site  # noqa: E402
from app.ca import _load  # noqa: E402
from cell_check import load  # noqa: E402

W = why("check", "round trip", "choice")


def new_findings(plan):
    return [f["title"] for f in plan["check"]["new"] if f["severity"] in ("error", "warning")]


def sweep(name, source, raw, counts, refusals, failures):
    ctx = Context(raw, name, source)
    if plmn.available(ctx):
        return
    f = {x["id"]: x for x in plmn.setup(ctx)["fields"]}
    for t in f["target"]["options"]:
        for mcc, mnc in (("001", "01"), ("999", "99")):
            inputs = {"target": t["value"], "mcc": mcc, "mnc": mnc,
                      "cells": [o["value"] for o in f["cells"]["optionsByKey"].get(t["value"], [])],
                      "slices": [o["value"] for o in f["slices"]["optionsByKey"].get(t["value"], [])],
                      "reserved": f["reserved"]["defaultByKey"].get(t["value"])}
            where = f"{name} {label(t['value'])} {mcc}-{mnc}"
            kind = "gNB" if "/NRBTS-" in t["value"] else "eNB"
            try:
                out, plan_ = plmn.plan(ctx, inputs)
            except PlanError as e:
                counts[(kind, "refused")] += 1
                for p in e.problems:
                    refusals[p.split(":")[0][-60:] if "dictionary" not in p else p[p.find("("):][:60]] += 1
                continue
            except Exception:
                failures.append(f"{where}: crashed\n{traceback.format_exc()}")
                break
            counts[(kind, "ok")] += 1
            if new_findings(plan_):
                failures.append(f"{where}: new findings {new_findings(plan_)[:3]}")
            try:
                plmn.plan(Context(out, name, source), inputs)
                failures.append(f"{where}: repeat not refused")
            except PlanError:
                pass
            break


def round_trip(name, source, raw, counts, failures):
    site = Site(_load(raw))
    # LTE: one further PLMN at a time, from every cell that has it.
    for enb in plmn._enbs(site):
        cells = site.child(enb["dn"], "LNCEL")
        further = {}
        for c in cells:
            for i, r in enumerate(c["lists"].get("furtherPlmnIdL", [])):
                further.setdefault(plmn._plmn(r), []).append((c["dn"], i, r))
        for key, where_ in further.items():
            doc = Doc(raw)
            for dn, i, _ in sorted(where_, key=lambda x: -x[1]):
                doc.remove_item(dn, "furtherPlmnIdL", i, W)
            ctx = Context(doc.raw(), name, source)
            mcc, mnc = f"{int(key[0]):03d}", f"{int(key[1]):0{int(key[2])}d}"
            inputs = {"target": enb["dn"], "mcc": mcc, "mnc": mnc, "cells": [dn for dn, _, _ in where_],
                      "reserved": where_[0][2].get("cellReserve")}
            at = f"{name} {label(enb['dn'])} further {mcc}-{mnc}"
            try:
                out, _ = plmn.plan(ctx, inputs)
            except PlanError as e:
                failures.append(f"{at}: round trip refused: {e.problems}")
                continue
            again = Site(_load(out))
            for dn, _, row in where_:
                got = [r for r in again.by_dn[dn]["lists"].get("furtherPlmnIdL", []) if plmn._plmn(r) == key]
                if got != [row]:
                    failures.append(f"{at}: {label(dn)} came back as {got}, was {row}")
            counts["further PLMNs rebuilt"] += 1
    # 5G: every NRPLMN but the first, with the sets and slices that list it.
    for gnb in plmn._gnbs(site):
        g = gnb["dn"]
        for p in site.child(g, "NRPLMN")[1:]:
            sets = [s for c in site.child(g, "NRCELL") for cls in ("NRPLMNSET_SA", "NRPLMNSET_NSA")
                    for s in site.child(c["dn"], cls) if p["dn"] in s["simple"].get("nrPlmnDNList", [])]
            slices = [s["dn"] for s in site.child(g, "SNSSAI") if p["dn"] in s["simple"].get("nrPlmnDNList", [])]
            doc = Doc(raw)
            for s in sets + [site.by_dn[x] for x in slices]:
                doc.remove_value(s["dn"], "nrPlmnDNList", p["dn"], W)
            for prof in site.child(g, "NRRESOURCEGROUP_PROFILE"):
                for ln in ("defaultRgSaList", "defaultRgNsaList"):
                    for i in reversed([i for i, r in enumerate(prof["lists"].get(ln, [])) if r.get("nrPlmnDN") == p["dn"]]):
                        doc.remove_item(prof["dn"], ln, i, W)
            doc.delete(p["dn"], W)
            ctx = Context(doc.raw(), name, source)
            key = plmn._plmn(p["p"])
            inputs = {"target": g, "mcc": f"{int(key[0]):03d}", "mnc": f"{int(key[1]):0{int(key[2])}d}",
                      "cells": sorted({s["dn"].rsplit("/", 1)[0] for s in sets}), "slices": slices,
                      "reserved": plmn.NOT_RESERVED}
            at = f"{name} {label(p['dn'])} {inputs['mcc']}-{inputs['mnc']}"
            try:
                out, plan_ = plmn.plan(ctx, inputs)
            except PlanError as e:
                failures.append(f"{at}: round trip refused: {e.problems}")
                continue
            again = Site(_load(out))
            new = plan_["focus"]
            if again.by_dn.get(new, {}).get("p") != p["p"]:
                failures.append(f"{at}: came back as {again.by_dn.get(new, {}).get('p')}")
            for s in sets:
                if new not in again.by_dn[s["dn"]]["simple"].get("nrPlmnDNList", []):
                    failures.append(f"{at}: {label(s['dn'])} doesn't list it")
            for s in slices:
                if new not in again.by_dn[s]["simple"].get("nrPlmnDNList", []):
                    failures.append(f"{at}: {label(s)} doesn't list it")
            counts["NRPLMNs rebuilt"] += 1


def main(folders):
    _, raws = load(folders)
    counts, refusals, failures = collections.Counter(), collections.Counter(), []
    for (source, name), raw in raws.items():
        sweep(name, source, raw, counts, refusals, failures)
        round_trip(name, source, raw, counts, failures)
    print(f"{len(raws)} files")
    for k, n in sorted(counts.items(), key=str):
        print(f"  {str(k):40} {n}")
    for k, n in refusals.most_common(8):
        print(f"  refused {n:4}: {k}")
    print(f"{len(failures)} failures")
    for f in failures[:25]:
        print("  " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    folders = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(folders))

#!/usr/bin/env python3
"""
Corpus check for the slice action (backend/app/actions/slice.py) and the
slice rules of dependents.py.

Sweep: on every gNB, a slice of SST 2 with SD 4660 in all its PLMNs and
tracking areas: no crash; the site check finds no new error or warning;
the same again on the result is refused.
Round trip: every slice is deleted through the delete action (its rows in
tracking areas, 5QI mappings and resource groups go with it) and added
again with its SST, SD, PLMNs and tracking areas, and the 5QI mappings it
had. It must come back with the same values, in the same lists, with a
resource group where it had one (quotas from a slice of its SST).

Usage: python3 scripts/slice_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if anything fails. Run from the repo root; no server needed.
"""
import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from app.actions import Context, PlanError, delete, slice as slice_action  # noqa: E402
from app.actions.doc import label  # noqa: E402
from app.actions.links import Site  # noqa: E402
from app.ca import _load  # noqa: E402
from cell_check import load  # noqa: E402


def new_findings(plan):
    return [f["title"] for f in plan["check"]["new"] if f["severity"] in ("error", "warning")]


def sweep(name, source, raw, counts, failures):
    ctx = Context(raw, name, source)
    if slice_action.available(ctx):
        return
    f = {x["id"]: x for x in slice_action.setup(ctx)["fields"]}
    for g in f["gnb"]["options"]:
        inputs = {"gnb": g["value"], "sst": "2", "sd": "4660",
                  "plmns": [o["value"] for o in f["plmns"]["optionsByKey"].get(g["value"], [])],
                  "tas": [o["value"] for o in f["tas"]["optionsByKey"].get(g["value"], [])], "mappings": []}
        where = f"{name} {label(g['value'])}"
        try:
            out, plan = slice_action.plan(ctx, inputs)
        except PlanError as e:
            failures.append(f"{where}: refused: {e.problems}")
            continue
        except Exception:
            failures.append(f"{where}: crashed\n{traceback.format_exc()}")
            continue
        counts["sweep ok"] += 1
        if new_findings(plan):
            failures.append(f"{where}: new findings {new_findings(plan)[:3]}")
        try:
            slice_action.plan(Context(out, name, source), inputs)
            failures.append(f"{where}: repeat not refused")
        except PlanError:
            pass


def _ties(site, gnb, dn):
    """Where a slice is named: tracking areas, 5QI mappings, resource groups."""
    tas = sorted(t["dn"] for t in site.child(gnb, "TRACKINGAREA")
                 if any(slice_action._rel(gnb, r.get("snssaiDN")) == dn for r in t["lists"].get("snssaiList", [])))
    maps = sorted(slice_action._served_by(site, gnb, dn))
    groups = [grp for p in site.child(gnb, "NRRESOURCEGROUP_PROFILE") for grp in site.child(p["dn"], "NRRESOURCEGROUP")
              if any(slice_action._rel(gnb, r.get("resourceDN")) == dn for r in grp["lists"].get("nrResourceList", []))]
    return tas, maps, groups


def round_trip(name, source, raw, counts, failures):
    site = Site(_load(raw))
    for gnb in slice_action._gnbs(site):
        g = gnb["dn"]
        for s in slice_action._slices(site, g):
            tas, maps, groups = _ties(site, g, s["dn"])
            ctx = Context(raw, name, source)
            try:
                stripped, _ = delete.plan(ctx, {"object": s["dn"]})
            except PlanError as e:
                failures.append(f"{name} {label(s['dn'])}: delete refused: {e.problems}")
                continue
            # Some lab exports name the PLMNs relative to the gNB; the action writes full distNames.
            plmns = [slice_action._rel(g, p) for p in s["simple"].get("nrPlmnDNList", [])]
            # A mapping that served only this slice goes with it; the rest must get it back.
            after = Site(_load(stripped))
            maps_left = [m for m in maps if m in after.by_dn]
            inputs = {"gnb": g, "sst": s["p"].get("sst"), "sd": s["p"].get("sd") or "",
                      "plmns": plmns, "tas": tas, "mappings": maps_left}
            where = f"{name} {label(s['dn'])} {slice_action._name(inputs['sst'], s['p'].get('sd'))}"
            try:
                out, plan = slice_action.plan(Context(stripped, name, source), inputs)
            except PlanError as e:
                failures.append(f"{where}: round trip refused: {e.problems}")
                continue
            except Exception:
                failures.append(f"{where}: round trip crashed\n{traceback.format_exc()}")
                continue
            again = Site(_load(out))
            new = again.by_dn.get(plan["focus"])
            diff = []
            if not new or new["p"] != s["p"] and {k: v for k, v in new["p"].items()} != \
                    {k: v for k, v in s["p"].items() if k != "operationalState"}:
                diff.append("params")
            if new and new["simple"].get("nrPlmnDNList", []) != plmns:
                diff.append("nrPlmnDNList")
            t2, m2, g2 = _ties(again, g, plan["focus"])
            if t2 != tas:
                diff.append("tracking areas")
            if m2 != maps_left:
                diff.append("5QI mappings")
            if bool(g2) != bool(groups):
                diff.append("resource group")
            elif groups and {k: v for k, v in g2[0]["lists"].items() if k != "nrResourceList"} != \
                    {k: v for k, v in groups[0]["lists"].items() if k != "nrResourceList"}:
                counts["resource group quotas from another slice of its SST"] += 1
            if diff:
                failures.append(f"{where}: differs in {diff}")
            counts["rebuilt"] += 1


def main(folders):
    _, raws = load(folders)
    counts, failures = collections.Counter(), []
    for (source, name), raw in raws.items():
        sweep(name, source, raw, counts, failures)
        round_trip(name, source, raw, counts, failures)
    print(f"{len(raws)} files")
    for k, n in sorted(counts.items()):
        print(f"  {k:55} {n}")
    print(f"{len(failures)} failures")
    for f in failures[:25]:
        print("  " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    folders = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(folders))

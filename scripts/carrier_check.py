#!/usr/bin/env python3
"""
Corpus check for the carrier action (backend/app/actions/carrier.py).

Sweep: every kind the form offers on every file, on all its cells, with a
carrier another file uses (else the first suggestion): no crash; the site
check finds no new error or warning; the same again on the result is
refused (every cell has it).
Round trip: every carrier object in the files (IRFIM with its LNHOIF,
NRFIM and REDRT rows, NRIRFIM, NRLIM, NRREDRT) is removed and added again
through the action, with the band and SCS it had. The copy must name the
carrier as the removed one did (the same values and ssbScs spellings) and
hold its template's values everywhere else.

Usage: python3 scripts/carrier_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if anything fails. Run from the repo root; no server needed.
"""
import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from app.actions import Context, PlanError, carrier  # noqa: E402
from app.actions.carrier import KINDS, OBJECTS, _carriers, _objects  # noqa: E402
from app.actions.doc import Doc, label, why  # noqa: E402
from app.actions.links import Site  # noqa: E402
from app.ca import _load  # noqa: E402
from cell_check import load  # noqa: E402

W = why("check", "round trip", "choice")
MAIN = {"lte-lte": "IRFIM", "nr-lte": "NRFIM", "redirect-lte": "REDRT:eutra", "redirect-lte-nr": "REDRT:nr",
        "nr-nr": "NRIRFIM", "lte-nr": "NRLIM", "redirect-nr": "NRREDRT"}


def new_findings(plan):
    return [f["title"] for f in plan["check"]["new"] if f["severity"] in ("error", "warning")]


def sweep(name, source, raw, corpus, counts, refusals, failures):
    ctx = Context(raw, name, source, corpus=lambda: corpus)
    if carrier.available(ctx):
        return
    f = {x["id"]: x for x in carrier.setup(ctx)["fields"]}
    for k in f["kind"]["options"]:
        kind = k["value"]
        inp = KINDS[kind]["input"]
        sugg = f[inp]["optionsByKey"].get(kind, [])
        if not sugg:
            continue
        o = next((o for o in sugg if o["group"] == "Other files"), sugg[0])
        inputs = {"kind": kind, "targets": [t["value"] for t in f["targets"]["optionsByKey"][kind]], inp: o["value"],
                  "band": f["band"]["defaultByKey"].get(o["key"]) or "41",
                  "scs": f["scs"]["defaultByKey"].get(o["key"]) or "30 kHz"}
        where = f"{name} {kind} {inp} {o['value']}"
        try:
            out, plan = carrier.plan(ctx, inputs)
        except PlanError as e:
            counts[(kind, "refused")] += 1
            for p in e.problems:
                refusals[(kind, p.split("(")[-1][:60])] += 1
            continue
        except Exception:
            failures.append(f"{where}: crashed\n{traceback.format_exc()}")
            continue
        counts[(kind, "ok")] += 1
        if new_findings(plan):
            failures.append(f"{where}: new findings {new_findings(plan)[:3]}")
        try:
            carrier.plan(Context(out, name, source, corpus=lambda: corpus), inputs)
            failures.append(f"{where}: repeat not refused")
        except PlanError:
            pass
        except Exception:
            failures.append(f"{where}: repeat crashed\n{traceback.format_exc()}")


def facts(m, key, value):
    """The inputs that describe the carrier an object (or its row) names."""
    p = m["p"]
    row = next((r for r in m["lists"].get(OBJECTS[key].get("row", ("", ""))[0], [])
                if r.get(OBJECTS[key]["row"][1]) == value), {}) if "row" in OBJECTS[key] else {}
    scs = "".join(ch for ch in (p.get("ssbScs") or row.get("ssbScsNr") or row.get("ssbSubcarrierSpacing") or "")
                  if ch.isdigit())
    return {"band": p.get("freqBandIndicatorNR") or row.get("nrMultiBandInfo1"),
            "scs": f"{scs} kHz" if scs else None, "row": row}


def round_trip(name, source, raw, corpus, failures):
    site = Site(_load(raw))
    done = 0
    for kind, key in MAIN.items():
        spec = KINDS[kind]
        for parent in site.of(spec["parent"]):
            for m in _objects(site, parent["dn"], key):
                for value in _carriers(m, key):
                    if not value:
                        continue
                    fx = facts(m, key, value)
                    doc = Doc(raw)
                    removed = {}
                    for k in spec["objects"]:
                        for o in _objects(site, parent["dn"], k):
                            if value not in _carriers(o, k):
                                continue
                            removed[k] = o
                            if "row" in OBJECTS[k] and len(o["lists"].get(OBJECTS[k]["row"][0], [])) > 1:
                                rows = o["lists"][OBJECTS[k]["row"][0]]
                                doc.remove_item(o["dn"], OBJECTS[k]["row"][0],
                                                next(i for i, r in enumerate(rows) if r.get(OBJECTS[k]["row"][1]) == value), W)
                            else:
                                doc.delete(o["dn"], W)
                    stripped = doc.raw()
                    ctx = Context(stripped, name, source, corpus=lambda: corpus)
                    inputs = {"kind": kind, "targets": [parent["dn"]], spec["input"]: value,
                              "band": fx["band"] or "41", "scs": fx["scs"] or "30 kHz"}
                    where = f"{name} {label(parent['dn'])} {key} {value}"
                    try:
                        out, plan = carrier.plan(ctx, inputs)
                    except PlanError as e:
                        # Its own carrier (a profile's cells are on it), or nothing left to copy.
                        if not any("own carrier" in p or "to copy" in p for p in e.problems):
                            failures.append(f"{where}: round trip refused: {e.problems}")
                        continue
                    except Exception:
                        failures.append(f"{where}: round trip crashed\n{traceback.format_exc()}")
                        continue
                    again = Site(_load(out))
                    plan_ = carrier._Plan(ctx, Doc(stripped), kind, inputs)
                    for k, old in removed.items():
                        new = next((o for o in _objects(again, parent["dn"], k) if value in _carriers(o, k)), None)
                        if not new:
                            failures.append(f"{where}: {k} not rebuilt")
                            continue
                        t = plan_.template(ctx.site.by_dn[parent["dn"]], k)
                        row = "row" in OBJECTS[k]
                        if row:
                            lname, field = OBJECTS[k]["row"]
                            want = next(r for r in old["lists"][lname] if r.get(field) == value)
                            got = next(r for r in new["lists"][lname] if r.get(field) == value)
                            mine = next((o for o in _objects(ctx.site, parent["dn"], k)), None)
                            base = ((mine or t)["lists"].get(lname) or [{}])[0]
                        else:
                            want, got, base = old["p"], new["p"], t["p"]
                        # The carrier's own fields come back exactly, in the file's spelling; the rest is the template's.
                        named = plan_.overrides(k, {"p": old["p"], "lists": old["lists"]})[1 if row else 0]
                        diff = [x for x in named if want.get(x) != got.get(x)]
                        diff += [x for x in base if x not in named and got.get(x) != base[x]]
                        if diff:
                            failures.append(f"{where}: {k} differs in {diff[:6]}")
                    done += 1
    return done


def main(folders):
    corpus, raws = load(folders)
    counts, refusals, failures = collections.Counter(), collections.Counter(), []
    done = 0
    for (source, name), raw in raws.items():
        sweep(name, source, raw, corpus, counts, refusals, failures)
        done += round_trip(name, source, raw, corpus, failures)
    print(f"{len(raws)} files")
    for (kind, result), n in sorted(counts.items()):
        print(f"  {kind:18} {result:8} {n}")
    for reason, n in refusals.most_common(8):
        print(f"  refused {n:4}: {reason}")
    print(f"round trip: {done} carriers rebuilt")
    print(f"{len(failures)} failures")
    for f in failures[:25]:
        print("  " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    folders = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(folders))

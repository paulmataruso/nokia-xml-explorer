#!/usr/bin/env python3
"""
Corpus check for the EN-DC action (backend/app/actions/endc.py).

Every eNB gets the 4G side once per kind of NR carrier offered (keep what
it measures, its own gNB's, another site's, one typed in) and once per kind
of X2 offered (leave it, automatic setup, a planned link); every gNB gets
the 5G side. A crash fails; a refusal is counted with its reason. The
result must parse, add no site-check error and pass the dictionary's EN-DC
rules (actLteNrDualConnectivity 1.1, 1.2, 1.2.1 and 2.1); every change must
be in the manual steps; planning it again must change nothing. Nothing the
feature needs may be left out (the owner's rule: add everything it needs):
after the 4G side qciTab6-9 are EN-DC-eligible, QCI 5 isn't, and the B1
measurement of the carrier picked is there; after the 5G side the gNB has
its X2 planes, every cell an NSA PLMN set (or the gNB its own mcc), and
QCI 6-9 are mapped to NR bearers.

Usage: python3 scripts/endc_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if any file fails. Run from the repo root; no server needed.
"""
import collections
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from neighbour_check import load  # noqa: E402

from app.actions import Context, PlanError, endc  # noqa: E402
from app.parser import XmlParseError, parse_file  # noqa: E402

CATALOG = os.path.join(os.path.dirname(__file__), "..", "backend", "app", "data", "class_catalog.json")
TYPED = {"ssb": "633312", "band": "78", "scs": "30kHz"}


def main(folders):
    corpus, raws = load(folders)
    index = {}
    for f in corpus:
        for (release, cls), names in f["params"].items():
            index.setdefault(release, {}).setdefault(cls, set()).update(names)
    kb = {"catalog": json.load(open(CATALOG)) if os.path.exists(CATALOG) else {}}
    ctx = lambda raw, src, name: Context(raw, name, src, corpus=lambda: corpus, release_index=lambda: index, kb=kb)
    counts, refusals, failures = collections.Counter(), collections.Counter(), []
    notes, todos = collections.Counter(), collections.Counter()

    def check(c, src, name, inputs, where, kind):
        try:
            out, plan = endc.plan(c, inputs)
        except PlanError as e:
            counts[(inputs["side"], kind, "refused")] += 1
            for p in e.problems:
                refusals[p[:90]] += 1
            return
        except Exception:
            failures.append(f"{where}: plan crashed\n{traceback.format_exc()}")
            return
        counts[(inputs["side"], kind, "ok")] += 1
        for n in plan["notes"]:
            notes[n.split(":")[0][:70]] += 1
        for t in plan["todo"]:
            todos[t.split(":")[0][:70]] += 1
        try:
            parse_file(out, name)
        except XmlParseError as e:
            failures.append(f"{where}: result doesn't parse: {e}")
            return
        bad = [f["title"] for f in plan["check"]["new"] if f["severity"] == "error"]
        if bad:
            failures.append(f"{where}: new site-check errors: {bad}")
        stepped = {s["dn"] for s in plan["steps"]}
        lost = sorted({x["dn"] for x in plan["changes"]} - stepped
                      - {d for d in (x["dn"] for x in plan["changes"]) if any(d.startswith(s + "/") for s in stepped)})
        if lost:
            failures.append(f"{where}: changes missing from the manual steps: {lost[:4]}")
        if (plan["changes"] or plan["todo"]) and not plan["stepsText"].strip():
            failures.append(f"{where}: no steps text")
        after = ctx(out, src, name)
        again = endc.plan(after, inputs)[1]["changes"]
        if again:
            failures.append(f"{where}: not idempotent: {[(x['op'], x['dn'], x.get('param')) for x in again[:4]]}")
        rules = rules_4g(after.site, inputs["enb"], inputs) if inputs["side"] == "4g" else \
            rules_5g(after.site, inputs["gnb"])
        failures.extend(f"{where}: {r}" for r in rules)

    for (src, name), raw in raws.items():
        c = ctx(raw, src, name)
        try:
            if endc.available(c):
                continue
            fields = {f["id"]: f for f in endc.setup(c)["fields"]}
        except Exception:
            failures.append(f"{name}: setup crashed\n{traceback.format_exc()}")
            continue
        sides = {o["value"] for o in fields["side"]["options"]}
        if "4g" in sides:
            for enb in fields["enb"]["options"]:
                where = f"{name} {enb['label']}"
                carriers = fields["carrier"]["optionsByKey"][enb["key"]]
                x2s = fields["x2"]["optionsByKey"][enb["key"]]
                carrier = {}
                for o in carriers:
                    carrier.setdefault(o.get("group") or o["value"], o["value"])
                x2 = {}
                for o in x2s:
                    x2.setdefault(o["value"] if o["value"] in (endc.KEEP, endc.AUTO) else "planned", o["value"])
                first_x2 = x2.get(endc.KEEP) or x2.get(endc.AUTO) or next(iter(x2.values()))
                first_carrier = next(v for k, v in carrier.items() if k != endc.MANUAL)
                base = {"side": "4g", "enb": enb["value"]}
                for kind, value in carrier.items():
                    inputs = {**base, "carrier": value, "x2": first_x2, **(TYPED if value == endc.MANUAL else {})}
                    check(c, src, name, inputs, f"{where} carrier {kind}", f"carrier: {kind}")
                for kind, value in x2.items():
                    check(c, src, name, {**base, "carrier": first_carrier, "x2": value},
                          f"{where} X2 {kind}", f"X2: {kind}")
        if "5g" in sides:
            for gnb in fields["gnb"]["options"]:
                check(c, src, name, {"side": "5g", "gnb": gnb["value"]}, f"{name} {gnb['label']}", "gNB")

    for key, n in sorted(counts.items()):
        print(f"{' / '.join(key)}: {n}")
    for reason, n in refusals.most_common():
        print(f"  refused {n}x: {reason}")
    for note, n in notes.most_common():
        print(f"  note {n}x: {note}")
    for todo, n in todos.most_common():
        print(f"  by hand {n}x: {todo}")
    for f in failures:
        print("FAIL", f)
    print(f"{len(failures)} failure{'s' if len(failures) != 1 else ''}")
    return 1 if failures else 0


def rules_4g(site, dn, inputs):
    """The dictionary's rules on actLteNrDualConnectivity, and the template, after the plan."""
    enb = site.by_dn[dn]
    p, lists = enb["p"], enb.get("lists") or {}
    out = []
    if p.get("actLteNrDualConnectivity") != "true":
        out.append("EN-DC isn't on")
    if p.get("actSatBackhaul") == "true":
        out.append("rule 1.1: actSatBackhaul is on")
    if not p.get("tLteNrDualConnectPrep") or not site.child(dn, "NRDCDPR"):
        out.append("rule 1.2: tLteNrDualConnectPrep or NRDCDPR missing")
    for name, rows in lists.items():
        if name.startswith("qciTab") and isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("lteNrDualConnectSupport") == "EN-DC":
                    if not row.get("nrPdcpProfIdx"):
                        out.append(f"rule 1.2.1: {name} is EN-DC without nrPdcpProfIdx")
                    elif not lists.get(f"pdcpProf{row['nrPdcpProfIdx']}"):
                        out.append(f"{name} names pdcpProf{row['nrPdcpProfIdx']}, which isn't there")
    for fdd in site.child(dn, "LNBTS_FDD"):
        if fdd["p"].get("actProSeComm") == "true":
            out.append("rule 2.1: actProSeComm is on")
    for q in endc.QCIS:
        rows = lists.get(f"qciTab{q}") or []
        if not rows or rows[0].get("lteNrDualConnectSupport") != "EN-DC":
            out.append(f"qciTab{q} isn't EN-DC-eligible")
    if (lists.get("qciTab5") or [{}])[0].get("lteNrDualConnectSupport") == "EN-DC":
        out.append("qciTab5 is still EN-DC-eligible")
    carrier = inputs.get("ssb") or (inputs["carrier"].split(":")[1] if inputs["carrier"].startswith("nr:") else None)
    if carrier and carrier not in endc._measured(site, enb):
        out.append(f"no B1 measurement of NR-ARFCN {carrier}")
    return out


def rules_5g(site, dn):
    gnb = site.by_dn[dn]
    out = []
    for plane in ("x2Cplane", "x2Uplane"):
        if not (gnb.get("lists") or {}).get(plane):
            out.append(f"{plane} missing")
    own = not site.child(dn, "NRPLMN") and gnb["p"].get("mcc")
    for cell in site.child(dn, "NRCELL"):
        if not own and not site.child(cell["dn"], "NRPLMNSET_NSA"):
            out.append(f"{cell['dn']} has no NSA PLMN set")
    qcis = {v for m in site.of("NRDRB_QCI", dn) for v in (m.get("simple") or {}).get("qciValueList", [])}
    if set(map(str, endc.QCIS)) - qcis:
        out.append(f"QCI {sorted(set(map(str, endc.QCIS)) - qcis)} not mapped")
    return out


if __name__ == "__main__":
    args = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(args))

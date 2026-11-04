#!/usr/bin/env python3
"""
Corpus check for the QoS action (backend/app/actions/qos.py).

Sweep: every gNB (SA 5QI and EN-DC QCI) and every eNB (QCI table) in the
given folders, every value the form offers, with its default template:
  1. Plan it. A crash fails; a refusal is counted with its reason.
  2. The result must parse, and the site check must find no new error.
  3. No new NRDRB_5QI or NRDRB_QCI may be instance 1 but the mapping of
     value 1.
  4. Planning it again on the result must be refused (a gNB value is mapped
     now) or change nothing (an eNB row is as the template now).
  5. On a gNB, the same with the gNB's first bearer shared instead.
Replace, on every gNB side (in the sweep): a production gNB (its mappings
name slices) must be refused as production's already; anywhere else no new
site-check error or warning, a repeat refused, and tidy must find nothing
to move among the side's mappings and the bearers they name. With every
value production doesn't map picked under Keep, those stay mapped. Keep,
on every lab gNB (SA): 5QI 69, which production doesn't map, added and
the set replaced without Keep (69 must go) and keeping 69 (it must stay).
Round trip: on every gNB whose mappings all have bearers of their own
(production), each mapping is removed with whatever only it used, then
planned again from production's template with the same slices. The rebuilt
mapping, bearer and profiles must hold the same values as the removed ones.

Usage: python3 scripts/qos_check.py [--round-trip] [folder ...]
       (default: example/ and scp/, whichever exist; --round-trip skips
       the sweep, which takes about half an hour over both)
Exit status 1 if anything fails. Run from the repo root; no server needed.
"""
import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.actions import Context, PlanError, qos, tidy  # noqa: E402
from app.actions.renumber import MAPPINGS  # noqa: E402
from app.actions.corpus import profile  # noqa: E402
from app.actions.doc import Doc, label, why  # noqa: E402
from app.actions.qos_files import bearer_signature, summary  # noqa: E402
from app.actions.qos_templates import TEMPLATES  # noqa: E402
from app.ca import _load  # noqa: E402
from app.parser import XmlParseError  # noqa: E402

W = why("check", "round trip", "choice")


def load(folders):
    corpus, raws = [], {}
    for d in folders:
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(".xml"):
                continue
            raw = open(os.path.join(d, f), "rb").read()
            try:
                entry = profile(raw)
            except XmlParseError:
                continue
            source = os.path.basename(os.path.normpath(d))
            corpus.append({"name": f, "source": source, "key": f"{source}:{f}", "mtime": 0, **entry})
            raws[(source, f)] = raw
    index = {}
    for f in corpus:
        for (release, cls), names in f["params"].items():
            index.setdefault(release, {}).setdefault(cls, set()).update(names)
    return corpus, raws, index


def new_errors(plan):
    return [f["title"] for f in plan["check"]["new"] if f["severity"] == "error"]


def new_findings(plan):
    return [f["title"] for f in plan["check"]["new"] if f["severity"] in ("error", "warning")]


def created_one(plan, out):
    doc = Doc(out)
    return [c["dn"] for c in plan["changes"] if c["op"] == "create" and c["class"] in MAPPINGS
            and c["dn"].endswith("-1") and doc.values(c["dn"], MAPPINGS[c["class"]]) != ["1"]]


def production(mos):
    return {g["dn"] for g in summary(mos)["gnbs"] if any(p["slices"] for p in g["profiles"])}


def replaced(ctx, c, target, keep, counts, failures, where):
    """The replace checks for one gNB side."""
    side, gnb = target["value"].split("|", 1)
    inp = {"target": target["value"], "value": qos.REPLACE, "keep": [o["value"] for o in keep]}
    kind = f"{side} replace" + (" keep" if keep else "")
    try:
        out, plan = qos.plan(c, inp)
    except PlanError as e:
        counts[(kind, "refused")] += 1
        if gnb in production(c.mos) and not any("production's already" in p for p in e.problems):
            failures.append(f"{where}: production gNB refused for another reason: {e.problems}")
        elif gnb not in production(c.mos):
            failures.append(f"{where}: refused {e.problems}")
        return
    except Exception:
        failures.append(f"{where}: plan crashed\n{traceback.format_exc()}")
        return
    counts[(kind, "ok")] += 1
    if gnb in production(c.mos):
        failures.append(f"{where}: changed a production gNB: {[label(x['dn']) for x in plan['changes'][:4]]}")
    if new_findings(plan):
        failures.append(f"{where}: new findings {new_findings(plan)[:3]}")
    try:
        qos.plan(ctx(out), inp)
        failures.append(f"{where}: repeat not refused")
    except PlanError:
        pass
    doc = Doc(out)
    cls, values = qos.MAPPING[side]
    maps = doc.children(gnb, cls)
    named = {doc.get(m, "nrDrbDN") for m in maps}
    moved = [label(o) for k, m in tidy.plan_numbers(ctx(out), doc).items() if k.startswith(gnb + "|")
             for o in m if o in maps or o in named]
    if moved:
        failures.append(f"{where}: tidy would still move {moved[:4]}")
    mapped = {v for m in maps for v in doc.values(m, values)}
    lost = [o["value"] for o in keep if o["value"] not in mapped]
    if lost:
        failures.append(f"{where}: kept values not mapped afterwards: {lost}")


def keep_check(corpus, raws, index, counts, failures):
    for (source, name), raw in raws.items():
        ctx = lambda r: Context(r, name, source, corpus=lambda: corpus, release_index=lambda: index)
        c = ctx(raw)
        if qos.available(c):
            continue
        fields = {f["id"]: f for f in qos.setup(c)["fields"]}
        for target in fields["target"]["options"]:
            side, gnb = target["value"].split("|", 1)
            if side != qos.SA or gnb in production(c.mos):
                continue
            v = next((o for o in fields["value"]["optionsByKey"][target["key"]] if o["value"] == "69"), None)
            templates = fields["template"]["optionsByKey"].get(v["key"], []) if v else []
            if not templates:
                continue
            where = f"{name} {target['label']} keep"
            try:
                out, _ = qos.plan(c, {"target": target["value"], "value": "69", "template": templates[0]["value"],
                                      "drb": qos.OWN, "slices": []})
            except PlanError:
                continue
            c2 = ctx(out)
            f2 = {f["id"]: f for f in qos.setup(c2)["fields"]}
            key = next(o["key"] for o in f2["value"]["optionsByKey"][target["key"]] if o["value"] == qos.REPLACE)
            keep = f2["keep"]["optionsByKey"].get(key, [])
            if [o["value"] for o in keep] != ["69"]:
                failures.append(f"{where}: Keep offers {[o['value'] for o in keep]}, not 69")
                continue
            for kept in ([], keep):
                try:
                    o2, plan = qos.plan(c2, {"target": target["value"], "value": qos.REPLACE,
                                             "keep": [o["value"] for o in kept]})
                except Exception as e:
                    failures.append(f"{where}: replace {'keeping 69' if kept else 'without Keep'} failed: {e}")
                    continue
                mapped = {x for m in Doc(o2).children(gnb, "NRDRB_5QI") for x in Doc(o2).values(m, "fiveqiValueList")}
                if ("69" in mapped) != bool(kept):
                    failures.append(f"{where}: 69 {'lost' if kept else 'left'} by the replace")
                if new_findings(plan):
                    failures.append(f"{where}: new findings {new_findings(plan)[:3]}")
                counts[("5qi replace keep" if kept else "5qi replace extra", "ok")] += 1


def sweep(corpus, raws, index, counts, refusals, failures):
    for (source, name), raw in raws.items():
        ctx = lambda r: Context(r, name, source, corpus=lambda: corpus, release_index=lambda: index)
        c = ctx(raw)
        try:
            if qos.available(c):
                continue
            fields = {f["id"]: f for f in qos.setup(c)["fields"]}
        except Exception:
            failures.append(f"{name}: setup crashed\n{traceback.format_exc()}")
            continue
        for target in fields["target"]["options"]:
            side = target["value"].split("|")[0]
            for value in fields["value"]["optionsByKey"][target["key"]]:
                if value["value"] == qos.REPLACE:
                    where = f"{name} {target['label']} replace"
                    replaced(ctx, c, target, [], counts, failures, where)
                    keep = fields["keep"]["optionsByKey"].get(value["key"], [])
                    if keep:
                        replaced(ctx, c, target, keep, counts, failures, where + " keeping " +
                                 ", ".join(o["value"] for o in keep))
                    continue
                if value["value"] == qos.OTHER:
                    continue
                drbs = fields["drb"]["optionsByKey"].get(value["key"], [])
                templates = fields["template"]["optionsByKey"].get(value["key"], [])
                inputs = {"target": target["value"], "value": value["value"],
                          "template": templates[0]["value"] if templates else None, "drb": qos.OWN, "slices": []}
                variants = [("own", inputs)]
                if side != qos.LTE and len(drbs) > 1:
                    variants.append(("shared", {**inputs, "drb": drbs[1]["value"]}))
                for variant, inp in variants:
                    kind = f"{side} {variant}" + (" preset" if value["value"] == qos.PRESET else "")
                    where = f"{name} {target['label']} {value['label']} ({variant})"
                    try:
                        out, plan = qos.plan(c, inp)
                    except PlanError as e:
                        counts[(kind, "refused")] += 1
                        for p in e.problems:
                            refusals[p[:100]] += 1
                        continue
                    except Exception:
                        failures.append(f"{where}: plan crashed\n{traceback.format_exc()}")
                        continue
                    counts[(kind, "ok")] += 1
                    if new_errors(plan):
                        failures.append(f"{where}: new site-check errors {new_errors(plan)}")
                    if created_one(plan, out):
                        failures.append(f"{where}: created instance 1: {created_one(plan, out)}")
                    try:
                        _, again = qos.plan(ctx(out), inp)
                    except PlanError:
                        continue
                    except Exception:
                        failures.append(f"{where}: repeat crashed\n{traceback.format_exc()}")
                        continue
                    if side != qos.LTE or again["changes"]:
                        failures.append(f"{where}: repeat not refused ({len(again['changes'])} changes)")


def strip(values):
    return {k: v for k, v in values.items() if k != "inst"}


def builtin(p):
    """The built-in template key for a production mapping: the variant with
    its bearer if there is one (production maps 5QI 6 twice), else the
    value's first template."""
    built = TEMPLATES[p["kind"]].get(p["values"][0]) or {}
    sig = bearer_signature(p["bearer"])
    i = next((i for i, t in enumerate(built.get("variants") or [], 1) if bearer_signature(t["bearer"]) == sig), None)
    return f"builtin|{p['kind']}|{p['values'][0]}" + (f"|{i}" if i else "")


def round_trip(corpus, raws, index, failures):
    done = 0
    for (source, name), raw in raws.items():
        mos = _load(raw)
        for g in summary(mos)["gnbs"]:
            maps = [p for p in g["profiles"] if p["bearer"]]
            if not maps or not all(p["slices"] for p in maps if p["kind"] == "5qi"):
                continue
            for p in maps:
                if len(p["values"]) != 1 or p["values"][0] not in qos.TEMPLATES[p["kind"]]:
                    continue
                doc = Doc(raw)
                dn, gnb = p["dn"], g["dn"]
                drb = doc.get(dn, "nrDrbDN")
                users = lambda d, name: [m for m in doc.mos if doc.get(m, name) == d]
                parts = {n: doc.get(drb, n) for n in ("nrDrbMacDN", "nrDrbPdcpDN", "nrDrbRlcAmDN", "nrDrbRlcUmDN")}
                slices = [r.get("snssaiDN") for r in doc.items(dn, "snssaiList")]
                doc.delete(dn, W)
                if not users(drb, "nrDrbDN"):
                    doc.delete(drb, W)
                    for n, d in parts.items():
                        if d and doc.exists(d) and not users(d, n):
                            doc.delete(d, W)
                stripped = doc.raw()
                side = qos.SA if p["kind"] == "5qi" else qos.NSA
                ctx = Context(stripped, name, source, corpus=lambda: corpus, release_index=lambda: index)
                v = p["values"][0]
                where = f"{name} {label(dn)}"
                try:
                    out, plan = qos.plan(ctx, {"target": f"{side}|{gnb}", "value": v, "template": builtin(p),
                                               "drb": qos.OWN, "slices": slices})
                except Exception as e:
                    failures.append(f"{where}: round trip failed: {e}")
                    continue
                if new_errors(plan):
                    failures.append(f"{where}: round trip new errors {new_errors(plan)}")
                again = next((x for x in summary(_load(out))["gnbs"] if x["dn"] == gnb), None)
                rebuilt = next((x for x in again["profiles"] if x["kind"] == p["kind"] and x["values"] == p["values"]
                                and sorted(x["slices"], key=str) == sorted(p["slices"], key=str)), None) if again else None
                if not rebuilt:
                    failures.append(f"{where}: round trip lost the mapping")
                    continue
                want, got = p["bearer"], rebuilt["bearer"]
                diff = [k for k in ("p", "simple", "rows") if want["drb"][k] != got["drb"][k]]
                diff += [n for n in want["parts"] if strip(want["parts"][n]) != strip(got["parts"].get(n) or {})]
                if rebuilt["p"] != p["p"]:
                    diff.append("mapping")
                if diff:
                    failures.append(f"{where}: round trip differs in {diff}")
                done += 1
    return done


def main(folders, flags=()):
    corpus, raws, index = load(folders)
    counts, refusals, failures = collections.Counter(), collections.Counter(), []
    done = round_trip(corpus, raws, index, failures)
    if "--round-trip" not in flags:
        sweep(corpus, raws, index, counts, refusals, failures)
        keep_check(corpus, raws, index, counts, failures)
    print(f"{len(raws)} files")
    for (kind, result), n in sorted(counts.items()):
        print(f"  {kind:22} {result:8} {n}")
    for reason, n in refusals.most_common(12):
        print(f"  refused {n:4}: {reason}")
    print(f"round trip: {done} mappings rebuilt")
    print(f"{len(failures)} failures")
    for f in failures[:25]:
        print("  " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    folders = [a for a in sys.argv[1:] if not a.startswith("--")] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(folders, flags))

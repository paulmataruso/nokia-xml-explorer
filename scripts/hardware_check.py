#!/usr/bin/env python3
"""
Corpus check for the hardware and delete actions
(backend/app/actions/add_radio.py, remove_module.py, delete.py and the
rules in dependents.py).

Add a radio: every template the form offers (this file's radios, kinds
from other files) with its default card and ports: no crash; the site
check finds no new error or warning; the same again on the result is
refused (the id and ports are taken).
Remove a module: every radio and baseband card: no crash; a plan adds no
site-check error or warning (one that is refused says why).
Delete: every cell, neighbour, slice, bearer and route: a plan adds no
site-check error.
Round trip: every radio cabled to one card is stripped with its cells,
then added again with its old id on its old ports, from a sibling of the
same code, else from the radio of that code the form offers from another
file. The copy must hold the template's values (the removed radio's where
they matched) and the same cables.

Usage: python3 scripts/hardware_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if anything fails. Run from the repo root; no server needed.
"""
import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from app.actions import Context, PlanError, add_radio, delete, remove_module  # noqa: E402
from app.actions.cells import cell_mapping, radios  # noqa: E402
from app.actions.dependents import apply_removal, plan_removal  # noqa: E402
from app.actions.doc import Doc, label, why  # noqa: E402
from app.actions.hardware import PLACE_PARAMS, base, cables, modules  # noqa: E402
from app.actions.links import Site  # noqa: E402
from app.ca import _load  # noqa: E402
from cell_check import load  # noqa: E402

DELETE_CLASSES = ("LNCEL", "NRCELL", "LNADJ", "LNADJGNB", "SNSSAI", "NRDRB", "IPRT")
W = why("check", "round trip", "choice")


def new_findings(plan, severities=("error", "warning")):
    return [f["title"] for f in plan["check"]["new"] if f["severity"] in severities]


def sweep_add(name, ctx, counts, failures):
    fields = {f["id"]: f for f in add_radio.setup(ctx)["fields"]}
    for t in fields["template"]["options"]:
        card = fields["card"]["defaultByKey"].get(t["key"])
        ports = fields["ports"]["defaultByKey"].get(f"{t['key']}|{card}", [])
        inputs = {"template": t["value"], "rmod": fields["rmod"]["default"], "card": card, "ports": ports}
        where = f"{name} add {t['label']}"
        kind = f"add {t['group'].lower()}"
        try:
            out, plan = add_radio.plan(ctx, inputs)
        except PlanError as e:
            counts[(kind, "refused")] += 1
            failures.append(f"{where}: refused with the form's defaults: {e.problems}")
            continue
        except Exception:
            failures.append(f"{where}: crashed\n{traceback.format_exc()}")
            continue
        counts[(kind, "ok")] += 1
        # Cabling a radio where the file's others have none brings out the rule
        # that every radio is cabled; those findings are about the others.
        new = [f["title"] for f in plan["check"]["new"] if f["severity"] in ("error", "warning")
               and not (f["title"].endswith("has no cable") and not f["title"].startswith(label(plan["focus"]) + " "))]
        if new:
            failures.append(f"{where}: new findings {new[:3]}")
        try:
            add_radio.plan(Context(out, ctx.filename, ctx.source, corpus=ctx.corpus, read=ctx.read), inputs)
            failures.append(f"{where}: repeat not refused")
        except PlanError:
            pass
        except Exception:
            failures.append(f"{where}: repeat crashed\n{traceback.format_exc()}")


def sweep_remove(name, ctx, counts, refusals, failures):
    for o in {f["id"]: f for f in remove_module.setup(ctx)["fields"]}["module"]["options"]:
        where = f"{name} remove {o['label']}"
        try:
            out, plan = remove_module.plan(ctx, {"module": o["value"]})
        except PlanError as e:
            counts[("remove", "refused")] += 1
            for p in e.problems:
                refusals[" ".join(w for w in p.split() if not any(ch.isdigit() for ch in w))[:70]] += 1
            continue
        except Exception:
            failures.append(f"{where}: crashed\n{traceback.format_exc()}")
            continue
        counts[("remove", "ok")] += 1
        if new_findings(plan):
            failures.append(f"{where}: new findings {new_findings(plan)[:3]}")


def sweep_delete(name, ctx, counts, failures):
    for m in ctx.mos:
        if m["cls"] not in DELETE_CLASSES:
            continue
        try:
            out, plan = delete.plan(ctx, {"object": m["dn"]})
        except PlanError:
            counts[(f"delete {m['cls']}", "refused")] += 1
            continue
        except Exception:
            failures.append(f"{name} delete {m['dn']}: crashed\n{traceback.format_exc()}")
            continue
        counts[(f"delete {m['cls']}", "ok")] += 1
        if new_findings(plan, ("error",)):
            failures.append(f"{name} delete {m['dn']}: new errors {new_findings(plan, ('error',))[:3]}")


def radio_values(site, dn):
    """A radio's values as the action copies them, and its cables' settings
    with the RMOD end replaced."""
    m = site.by_dn[dn]
    kids = sorted((label(k["dn"]), tuple(sorted((n, v) for n, v in k["p"].items()
                                               if n not in PLACE_PARAMS.get(k["cls"], ()))))
                  for k in site.kids.get(dn, []) if k["cls"] in add_radio.KIDS)
    cabs = [tuple(sorted((n, v) for n, v in c["p"].items() if n not in ("firstEndpointDN", "secondEndpointDN")))
            for c in cables(site, dn)]
    return {"p": {k: v for k, v in m["p"].items() if k not in PLACE_PARAMS["RMOD"]}, "lists": m["lists"],
            "kids": kids, "cables": sorted(cabs)}


def round_trip(name, source, raw, corpus, read, failures):
    site = Site(_load(raw))
    by_code = collections.defaultdict(list)
    for mod in modules(site):
        if mod["class"] == "RMOD" and mod["code"]:
            by_code[base(mod["code"])].append(mod)
    done = 0
    for code, mods in by_code.items():
        for mod in mods:
            sibling = next((m for m in mods if m is not mod), None)
            r = mod["dn"]
            mine = cables(site, r)
            cards = {c["p"].get("firstEndpointDN") for c in mine}
            if len(cards) != 1 or not all(c["p"].get("secondEndpointDN") == r for c in mine):
                continue
            ports = [f"{c['p'].get('firstEndpointLabel')}|{c['p'].get('firstEndpointPortId')}" for c in mine]
            # Strip the radio with the cells on it.
            cells = [c["dn"] for c in site.of("LNCEL") + site.of("NRCELL")
                     if r in radios(site, cell_mapping(site, c))]
            removal = plan_removal(site, cells + [r])
            if removal.blockers:
                continue
            doc = Doc(raw)
            apply_removal(doc, removal, lambda d, reason: W)
            stripped = doc.raw()
            ctx = Context(stripped, name, source, corpus=lambda: corpus, read=read)
            if sibling:
                template, template_site = sibling["dn"], site
            else:
                # The only radio of its kind: the form then offers one from another file.
                fields = {f["id"]: f for f in add_radio.setup(ctx)["fields"]}
                shape = f"file|{code}|{mod['antl']}|{mod['phyant']}|{len(mine)}"
                template = next((o["value"] for o in fields["template"]["options"] if o["key"] == shape), None)
                if not template:
                    continue
                _, key, dn = template.split("|", 2)
                f = next(f for f in corpus if f["key"] == key)
                template_site = Site(_load(read(f["name"], f["source"])))
                sibling = {"dn": dn}
            where = f"{name} {label(r)} from {label(sibling['dn'])}" + ("" if template_site is site else " elsewhere")
            try:
                out, plan = add_radio.plan(ctx, {"template": template, "rmod": r.rsplit("-", 1)[1],
                                                 "card": next(iter(cards)), "ports": ports})
            except PlanError as e:
                failures.append(f"{where}: round trip refused: {e.problems}")
                continue
            except Exception:
                failures.append(f"{where}: round trip crashed\n{traceback.format_exc()}")
                continue
            again = Site(_load(out))
            if r not in again.by_dn:
                failures.append(f"{where}: round trip put the radio elsewhere ({plan['focus']})")
                continue
            want, sib, got = radio_values(site, r), radio_values(template_site, sibling["dn"]), radio_values(again, r)
            diff = [k for k in want["p"] if want["p"].get(k) != got["p"].get(k) and want["p"].get(k) == sib["p"].get(k)]
            if want["cables"] != got["cables"] and sib["cables"] == want["cables"]:
                diff.append("cables")
            if want["kids"] != got["kids"] and sib["kids"] == want["kids"]:
                diff.append("antennas")
            if diff:
                failures.append(f"{where}: round trip differs in {diff[:6]}")
            done += 1
    return done


def main(folders):
    corpus, raws = load(folders)
    read = lambda n, s: raws[(s, n)]
    counts, refusals, failures = collections.Counter(), collections.Counter(), []
    done = 0
    for (source, name), raw in raws.items():
        ctx = Context(raw, name, source, corpus=lambda: corpus, read=read)
        if not add_radio.available(ctx):
            sweep_add(name, ctx, counts, failures)
        if not remove_module.available(ctx):
            sweep_remove(name, ctx, counts, refusals, failures)
        sweep_delete(name, ctx, counts, failures)
        done += round_trip(name, source, raw, corpus, read, failures)
    print(f"{len(raws)} files")
    for (kind, result), n in sorted(counts.items()):
        print(f"  {kind:28} {result:8} {n}")
    for reason, n in refusals.most_common(8):
        print(f"  remove refused {n:4}: {reason}")
    print(f"round trip: {done} radios rebuilt")
    print(f"{len(failures)} failures")
    for f in failures[:25]:
        print("  " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    folders = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(folders))

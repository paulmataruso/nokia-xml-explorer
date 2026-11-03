#!/usr/bin/env python3
"""
Corpus check for the cell actions (backend/app/actions/nr_cell.py and
lte_cell.py).

Sweep: every NR and LTE cell of the given folders as the template, with
the form's suggestions:
  1. On a radio with no cell where there is one, on the template's carrier.
  2. On the template's own radio, on another carrier (NR: the next channel
     up, with an SSB inside it; LTE: 50 EARFCNs up), LTE with relations
     both ways to every cell of the eNB.
  Each: no crash; the result parses; the site check finds no new error;
  planning the same again on the result is refused (the lcrId is taken).
Round trip: on every site with three or more cells, each cell is removed
with its channel mapping (and NR cell group, LTE relations to it), then
added again from a sibling with its old identity on its old radio. The
copy must hold the removed cell's values where they matched the sibling, and
the same channel mapping.

Usage: python3 scripts/cell_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if anything fails. Run from the repo root; no server needed.
"""
import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.actions import Context, PlanError, lte_cell, nr_cell  # noqa: E402
from app.actions.cells import antennas, cell_mapping, move_antennas, radios, root_limit  # noqa: E402
from app.actions.corpus import profile  # noqa: E402
from app.actions.doc import Doc, instance, label, why  # noqa: E402
from app.actions.links import Site  # noqa: E402
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
    return corpus, raws


def gscn_near(mhz):
    """The GSCN nearest a frequency (TS 38.104 Table 5.4.3.1-1)."""
    if mhz < 3000:
        return 3 * round(mhz / 1.2)
    if mhz < 24250:
        return 7499 + round((mhz - 3000) / 1.44)
    return 22256 + round((mhz - 24250.08) / 17.28)


def defaults(fields, key):
    return {i: fields[i].get("defaultByKey", {}).get(key) for i in fields if fields[i].get("dependsOn") == "template"}


def free_root(site, cell):
    """A PRACH root no cell of the site uses, where the form suggests none
    (a carrier with one cell has no spacing to follow)."""
    if cell["cls"] == "NRCELL":
        used = [c["p"].get("prachRootSequenceIndex") for c in site.of("NRCELL")]
    else:
        used = [(lte_cell._sub(site, c) or {"p": {}})["p"].get("rootSeqIndex") for c in site.of("LNCEL")]
    used = [int(u) for u in used if (u or "").isdigit()]
    return str(next(v for v in range(root_limit(used), -1, -1) if v not in used))


def new_errors(plan):
    return [f["title"] for f in plan["check"]["new"] if f["severity"] == "error"]


def sweep(action, corpus, raws, counts, refusals, failures):
    for (source, name), raw in raws.items():
        ctx = lambda r: Context(r, name, source, corpus=lambda: corpus)
        c = ctx(raw)
        try:
            if action.available(c):
                continue
            fields = {f["id"]: f for f in action.setup(c)["fields"]}
        except Exception:
            failures.append(f"{name}: {action.ID} setup crashed\n{traceback.format_exc()}")
            continue
        site = c.site
        for t in fields["template"]["options"]:
            cell = site.by_dn[t["value"]]
            base = {"template": t["value"], **defaults(fields, t["key"])}
            base["cellName"] = base.get("cellName") or "CHECK_CELL"
            base["root"] = base.get("root") or free_root(site, cell)
            own_radio = radios(site, cell_mapping(site, cell))[0]
            variants = []
            if base.get("radio") and base["radio"] != own_radio:
                variants.append(("free radio", {**base, "relations": []}))
            if action is nr_cell:
                if not site.child(cell["dn"], "NRCELL_FDD") and (cell["p"].get("nrarfcn") or "").isdigit():
                    bw = int("".join(ch for ch in cell["p"].get("chBw") or "" if ch.isdigit()) or 20)
                    arfcn = int(cell["p"]["nrarfcn"])
                    step = bw / (0.015 if arfcn >= 600000 else 0.005)
                    new = int(arfcn + step)
                    centre = nr_cell._mhz(new)
                    variants.append(("other carrier", {**base, "radio": own_radio, "arfcn": str(new),
                                                       "gscn": str(gscn_near(centre))}))
            else:
                earfcn = lte_cell.lte_cell(site, cell)["earfcn"]
                rel = [o["value"] for o in fields["relations"]["optionsByKey"].get(t["key"], [])]
                variants.append(("other carrier", {**base, "radio": own_radio, "earfcn": str(int(earfcn) + 50),
                                                   "relations": rel}))
            for variant, inputs in variants:
                kind = f"{action.ID} {variant}"
                where = f"{name} {t['label']} ({variant})"
                try:
                    out, plan = action.plan(c, inputs)
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
                    failures.append(f"{where}: new site-check errors {new_errors(plan)[:3]}")
                try:
                    action.plan(ctx(out), inputs)
                    failures.append(f"{where}: repeat not refused")
                except PlanError:
                    pass
                except Exception:
                    failures.append(f"{where}: repeat crashed\n{traceback.format_exc()}")


def values(doc, dn):
    return {"p": doc.params(dn), "kids": sorted((d[len(dn):], tuple(sorted(doc.params(d).items())))
                                                for d in doc.subtree(dn) if d != dn)}


IDENTITY = {"lcrId", "cellName", "physCellId", "phyCellId", "prachRootSequenceIndex", "nrCellIdentity", "eutraCelId"}


def round_trip(corpus, raws, failures):
    done = 0
    for (source, name), raw in raws.items():
        site = Site(_load(raw))
        for cls, action, parent in (("NRCELL", nr_cell, "NRBTS"), ("LNCEL", lte_cell, "LNBTS")):
            for node in site.of(parent):
                cells = [c for c in site.child(node["dn"], cls) if cell_mapping(site, c)]
                if len(cells) < 3:
                    continue
                for cell in cells:
                    mapping = cell_mapping(site, cell)
                    count = len(antennas(site, mapping))
                    sibling = next((c for c in cells if c is not cell and len(antennas(site, cell_mapping(site, c))) == count),
                                   None)
                    if not sibling:
                        continue
                    doc = Doc(raw)
                    radio = radios(site, mapping)[0]
                    want_cell = values(doc, cell["dn"])
                    inputs = {"template": sibling["dn"], "radio": radio, "lcrId": cell["p"].get("lcrId"),
                              "cellName": cell["p"].get("cellName") or "X", "relations": []}
                    lcr = cell["p"].get("lcrId")
                    if cls == "NRCELL":
                        inputs.update(pci=cell["p"].get("physCellId"), root=cell["p"].get("prachRootSequenceIndex"))
                        if cell["p"].get("nrarfcn") != sibling["p"].get("nrarfcn"):
                            inputs.update(arfcn=cell["p"].get("nrarfcn"), gscn=cell["p"].get("gscnOrSsPbchArfcn"))
                        for g in site.child(node["dn"], "NRCELLGRP"):
                            if instance(cell["dn"]) in g["simple"].get("nrCellList", []):
                                doc.delete(g["dn"], W)
                                for du in site.child(node["dn"], "NRDU"):
                                    doc.remove_value(du["dn"], "refNrCellGroup", instance(g["dn"]), W)
                    else:
                        sub = lte_cell._sub(site, cell) or {"p": {}}
                        inputs.update(pci=cell["p"].get("phyCellId"), root=sub["p"].get("rootSeqIndex"))
                        earfcn = lte_cell.lte_cell(site, cell)["earfcn"]
                        if earfcn != lte_cell.lte_cell(site, sibling)["earfcn"]:
                            inputs["earfcn"] = earfcn
                        for rel in site.of("LNREL", node["dn"]):
                            if rel["p"].get("ecgiLcrId") == lcr and rel["p"].get("ecgiAdjEnbId") == instance(node["dn"]):
                                doc.delete(rel["dn"], W)
                    doc.delete(cell["dn"], W)
                    doc.delete(mapping["dn"], W)
                    where = f"{name} {label(cell['dn'])} from {label(sibling['dn'])}"
                    try:
                        out, plan = action.plan(Context(doc.raw(), name, source, corpus=lambda: corpus), inputs)
                    except PlanError as e:
                        if not any("PCI" in p or "PRACH" in p or "rootSeq" in p or "carries" in p for p in e.problems):
                            failures.append(f"{where}: round trip refused: {e.problems}")
                        continue
                    except Exception:
                        failures.append(f"{where}: round trip crashed\n{traceback.format_exc()}")
                        continue
                    if new_errors(plan):
                        failures.append(f"{where}: round trip new errors {new_errors(plan)[:3]}")
                    again = Doc(out)
                    new_dn = plan["focus"]
                    got_cell = values(again, new_dn)
                    new_map = f"{mapping['dn'].rsplit('/', 1)[0]}/{label(mapping['dn'])}"
                    got_map = values(again, new_map) if again.exists(new_map) else None
                    # The action promises the sibling's mapping moved to the radio (cells of one radio can order
                    # their channels differently, so the removed cell's own mapping needn't come back).
                    sib_map = cell_mapping(site, sibling)
                    moves = sorted({sib_map["dn"]: new_map, **move_antennas(site, sib_map, radio)[0]}.items(),
                                   key=lambda kv: -len(kv[0]))
                    move = lambda v: next((n + v[len(o):] for o, n in moves if v and (v == o or v.startswith(o + "/"))), v)
                    want_map = values(doc, sib_map["dn"])
                    want_map = {"p": want_map["p"], "kids": [(k, tuple((n, move(v)) for n, v in ps))
                                                            for k, ps in want_map["kids"]]}
                    if got_map != want_map:
                        failures.append(f"{where}: channel mapping isn't the sibling's moved to {label(radio)}")
                    same_sib = values(Doc(raw), sibling["dn"])
                    # The copy holds the sibling's settings: only where the removed cell matched its sibling
                    # (cells of one carrier do) must the copy match the removed cell.
                    diff = sorted(k for k in set(want_cell["p"]) | set(got_cell["p"])
                                  if k not in IDENTITY and want_cell["p"].get(k) != got_cell["p"].get(k)
                                  and want_cell["p"].get(k) == same_sib["p"].get(k))
                    if diff:
                        failures.append(f"{where}: round trip differs in {diff[:6]}")
                    done += 1
    return done


def main(folders):
    corpus, raws = load(folders)
    counts, refusals, failures = collections.Counter(), collections.Counter(), []
    for action in (nr_cell, lte_cell):
        sweep(action, corpus, raws, counts, refusals, failures)
    done = round_trip(corpus, raws, failures)
    print(f"{len(raws)} files")
    for (kind, result), n in sorted(counts.items()):
        print(f"  {kind:28} {result:8} {n}")
    for reason, n in refusals.most_common(10):
        print(f"  refused {n:4}: {reason}")
    print(f"round trip: {done} cells rebuilt")
    print(f"{len(failures)} failures")
    for f in failures[:25]:
        print("  " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    folders = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(folders))

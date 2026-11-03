#!/usr/bin/env python3
"""
Round-trip test for the CA wizard (backend/app/ca_wizard.py).

For every working CA export in the given folders (downlink CA on, CAREL
relations, no errors in the CA check):
  1. Strip its CA setup: CA switches off, and every CA object under the eNB
     (CAGENB and its children, CADPR*, CAREL, CAPR) deleted. Cell
     parameters are left alone, as they would be in a real non-CA file.
  2. Put CA back with the wizard, asking for the original relations and
     using the original file as the donor.
  3. Compare with the original: relations and their priorities, CAREL
     parameters, CAPR carrier coverage per PCell, the eNB-wide CA objects
     and the CA switches. The rebuilt file must have no errors in the CA
     check.
Then it repeats step 2 with the best-ranked *other* donor, which is how the
wizard is normally used, and expects no errors there either.

Usage: python3 scripts/ca_wizard_roundtrip.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if any file fails. Run from the repo root; no server needed.
"""
import hashlib
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.ca import _load  # noqa: E402
from app.ca_wizard import PlanError, plan_ca, profile, rank_donors, wizard_setup  # noqa: E402
from app.parser import _local, _serialize, _short_class, _strip_leading_junk  # noqa: E402

_STRIP = ("CAGENB", "CADPR", "CADPRCBRS", "CADPRLAA", "CAREL", "CAPR")


def strip_ca(raw: bytes, enb: str) -> bytes:
    root = ET.fromstring(_strip_leading_junk(raw))
    cmdata = next(el for el in root.iter() if _local(el.tag) == "cmData")
    gone = set()
    for el in list(cmdata):
        dn = el.get("distName") or ""
        if not dn.startswith(enb + "/"):
            continue
        cls = _short_class(el.get("class"))
        if cls in _STRIP or any(dn.startswith(g + "/") for g in gone):
            gone.add(dn)
            cmdata.remove(el)
    lnbts = next(el for el in cmdata if el.get("distName") == enb)
    for p in lnbts:
        if p.get("name") == "actDLCAggr":
            p.text = "false"
        if p.get("name") == "actULCAggr" and p.text not in (None, "false"):
            p.text = "false"
    return _serialize(root)


def ca_view(raw: bytes, enb: str) -> dict:
    mos = _load(raw)
    by_dn = {m["dn"]: m for m in mos}
    lcr = {m["p"].get("lcrId"): m["dn"] for m in mos if m["cls"] == "LNCEL" and m["dn"].startswith(enb + "/")}
    rels, carels, caprs, objects = {}, {}, {}, {}
    for m in mos:
        if not m["dn"].startswith(enb + "/"):
            continue
        parent = m["dn"].rsplit("/", 1)[0]
        if m["cls"] == "CAREL":
            scell = lcr.get(m["p"].get("lcrId"))
            rels[(parent, scell)] = m["p"].get("scellPrio")
            carels[(parent, scell)] = m["p"]
        elif m["cls"] == "CAPR":
            caprs.setdefault(parent, set()).add(m["p"].get("earfcnDL"))
        elif m["cls"] in ("CAGENB", "CADPR", "CADPRCBRS", "CADPRLAA") and parent == enb:
            objects[m["cls"]] = m["p"]
    lnbts = by_dn[enb]["p"]
    return {"rels": rels, "carels": carels, "caprs": caprs, "objects": objects,
            "switches": {k: lnbts.get(k) for k in ("actDLCAggr", "actULCAggr", "actEnhAcAndGbrServices")}}


def diff_params(a: dict, b: dict) -> list[str]:
    return [f"{k}: {a.get(k)} -> {b.get(k)}" for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]


def main() -> int:
    folders = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    raws, seen = {}, set()
    for folder in folders:
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith(".xml"):
                continue
            raw = open(os.path.join(folder, name), "rb").read()
            digest = hashlib.sha1(raw).hexdigest()
            if digest not in seen:
                seen.add(digest)
                raws[os.path.join(folder, name)] = raw

    profiles, release_params = {}, {}
    for path, raw in raws.items():
        try:
            profiles[path] = profile(raw)
        except Exception as e:  # unreadable files are the parser's problem, not this test's
            print(f"skip {path}: {e}")
            continue
        for (release, cls), names in profiles[path]["params"].items():
            release_params.setdefault(release, {}).setdefault(cls, set()).update(names)
    donors = [{**p["donor"], "name": os.path.basename(path), "path": path}
              for path, p in profiles.items() if p["donor"]]
    print(f"{len(raws)} files, {len(donors)} working CA exports\n")

    failures = 0
    for d in donors:
        path, raw = d["path"], raws[d["path"]]
        enb_setup = max(wizard_setup(raw)["enbs"], key=lambda e: sum(len(r["scells"]) for r in e["current"]))
        enb = enb_setup["id"]
        stripped = strip_ca(raw, enb)
        request = {"enb": enb, "relations": enb_setup["current"], "ul": enb_setup["ulOn"]}
        problems, notes = [], []
        try:
            rebuilt, plan = plan_ca(stripped, raw, d["name"], request, release_params)
        except PlanError as e:
            print(f"FAIL {d['name']}: {e.problems}")
            failures += 1
            continue
        before, after = ca_view(raw, enb), ca_view(rebuilt, enb)
        if set(before["rels"]) != set(after["rels"]):
            problems.append(f"relations differ: {sorted(set(before['rels']) ^ set(after['rels']))}")
        elif before["rels"] != after["rels"]:
            notes.append("scellPrio renumbered: " + ", ".join(
                f"{k[0].rsplit('/', 1)[1]}->{k[1].rsplit('/', 1)[1]} {before['rels'][k]}->{after['rels'][k]}"
                for k in before["rels"] if before["rels"][k] != after["rels"][k]))
        for key in before["carels"].keys() & after["carels"].keys():
            ds = [x for x in diff_params(before["carels"][key], after["carels"][key]) if not x.startswith("scellPrio")]
            if ds:
                notes.append(f"CAREL {key[0].rsplit('/', 1)[1]}->{key[1].rsplit('/', 1)[1]}: {'; '.join(ds)}")
        if before["caprs"] != after["caprs"]:
            problems.append(f"CAPR coverage differs: {before['caprs']} vs {after['caprs']}")
        for cls in before["objects"].keys() | after["objects"].keys():
            ds = diff_params(before["objects"].get(cls, {}), after["objects"].get(cls, {}))
            if ds:
                notes.append(f"{cls}: {'; '.join(ds)}")
        if before["switches"] != after["switches"]:
            problems.append(f"switches differ: {diff_params(before['switches'], after['switches'])}")
        if plan["after"]["errors"]:
            problems.append("errors after: " + "; ".join(f["title"] for f in plan["after"]["findings"]
                                                          if f["severity"] == "error"))
        cell_changes = [c for c in plan["changes"] if c["group"] in ("cells", "fill", "tuning", "cleanup")]
        if cell_changes:
            notes.append("cell changes: " + "; ".join(f"{c['dn'].rsplit('/', 1)[1]}.{c.get('param')} {c.get('old')}->"
                                                     f"{c.get('new')}" for c in cell_changes))
        # The usual case: another file as the donor.
        others = rank_donors(enb_setup, [o for o in donors if o["path"] != path], want_ul=enb_setup["ulOn"])
        others = [o for o in others if o["ul"] or not enb_setup["ulOn"]]
        if others:
            o = others[0]
            try:
                _, cross = plan_ca(stripped, raws[o["path"]], o["name"], request, release_params)
                if cross["after"]["errors"]:
                    problems.append(f"errors with donor {o['name']}: " + "; ".join(
                        f["title"] for f in cross["after"]["findings"] if f["severity"] == "error"))
                else:
                    notes.append(f"with donor {o['name']}: {len(cross['changes'])} changes, "
                                 f"{len(cross['skipped'])} skipped, 0 errors, {cross['after']['warnings']} warnings")
            except PlanError as e:
                problems.append(f"donor {o['name']}: {e.problems}")
        status = "FAIL" if problems else "ok  "
        failures += bool(problems)
        print(f"{status} {d['name']} ({enb_setup['release']}, {len(before['rels'])} relations, "
              f"{len(plan['changes'])} changes, {plan['after']['warnings']} warnings after)")
        for line in problems:
            print(f"     ! {line}")
        for line in notes:
            print(f"       {line}")
    print(f"\n{failures} failed" if failures else "\nall passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

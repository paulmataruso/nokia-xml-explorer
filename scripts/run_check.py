#!/usr/bin/env python3
"""
Corpus check for runs (backend/app/actions/run.py: one action's change on
this file and the ones it implies in the other sites' files).

For every eNB and gNB:
  - each neighbour action (neighbour_enb.py, neighbour_gnb.py) with the
    first site offered from another file, "Their end" ticked and one more
    neighbour picked, and with a co-sited one from this file, if any;
  - EN-DC (endc.py) with the other side's file: on an eNB the 4G side with
    "The gNB's file" ticked, on a gNB the 5G side with the first eNB
    offered.
A crash fails; a refusal of the run or of one file's leg is counted with
its reason. Every file the run writes must parse and gain no site-check
error, and the run planned again on the files as it left them must change
nothing in any of them (a file whose leg was refused may be refused again).

Usage: python3 scripts/run_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if any file fails. Run from the repo root; no server needed.
"""
import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from neighbour_check import load  # noqa: E402

from app.actions import Context, PlanError, endc, neighbour_enb, neighbour_gnb  # noqa: E402
from app.actions.neighbours import BOTH  # noqa: E402
from app.actions.registry import ACTIONS  # noqa: E402
from app.actions.run import plan_run  # noqa: E402
from app.parser import XmlParseError, parse_file  # noqa: E402


def main(folders):
    corpus, raws = load(folders)
    index = {}
    for f in corpus:
        for (release, cls), names in f["params"].items():
            index.setdefault(release, {}).setdefault(cls, set()).update(names)

    def opener(files):
        def ctx(key):
            src, _, name = key.partition(":")
            if (src, name) not in files:
                raise FileNotFoundError(key)
            return Context(files[(src, name)], name, src, corpus=lambda: corpus, release_index=lambda: index)
        return ctx

    counts, refusals, failures, notes = collections.Counter(), collections.Counter(), [], collections.Counter()

    def check(action, src, name, inputs, where, kind):
        kind = (action.ID, kind)
        try:
            files = plan_run(opener(raws)(f"{src}:{name}"), action, inputs, ACTIONS, opener(raws))
        except PlanError as e:
            counts[kind + ("refused",)] += 1
            for p in e.problems:
                refusals[(action.ID, p[:90])] += 1
            return
        except Exception:
            failures.append(f"{where}: run crashed\n{traceback.format_exc()}")
            return
        counts[kind + ("ok",)] += 1
        after = dict(raws)
        for f in files:
            counts[kind + (f"{len(files)} files",)] += f is files[0]
            if f["problems"]:
                counts[kind + ("leg refused",)] += 1
                for p in f["problems"]:
                    refusals[(action.ID, "leg: " + p[:85])] += 1
                continue
            if not f["plan"]["changes"]:
                counts[kind + ("file already has it",)] += 1
                continue
            try:
                parse_file(f["new"], f["name"])
            except XmlParseError as e:
                failures.append(f"{where}: {f['name']} doesn't parse: {e}")
                continue
            bad = [x["title"] for x in f["plan"]["check"]["new"] if x["severity"] == "error"]
            if bad:
                failures.append(f"{where}: {f['name']} gets site-check errors: {bad}")
            for n in f["plan"]["notes"]:
                notes[(action.ID, n.split(":")[0][:70])] += 1
            after[(f["source"], f["name"])] = f["new"]
        try:
            again = plan_run(opener(after)(f"{src}:{name}"), action, inputs, ACTIONS, opener(after))
        except Exception as e:
            failures.append(f"{where}: the repeat fails: {e}")
            return
        refused = {f["key"] for f in files if f["problems"]}
        for f in again:
            changed = f["key"] not in refused and (f["problems"] or (f["plan"] and f["plan"]["changes"]))
            if changed:
                failures.append(f"{where}: the repeat changes {f['name']}: "
                                + str(f["problems"] or [(x["op"], x["dn"], x.get("param")) for x in changed[:4]]))

    for (src, name), raw in raws.items():
        c = opener(raws)(f"{src}:{name}")
        for action in (neighbour_enb, neighbour_gnb):
            try:
                if action.available(c):
                    continue
                fields = {f["id"]: f for f in action.setup(c)["fields"]}
            except Exception:
                failures.append(f"{name}: {action.ID} setup crashed\n{traceback.format_exc()}")
                continue
            for target in fields["target"]["options"]:
                opts = [o for o in fields["source"]["optionsByKey"].get(target["key"], []) if "|" in o["value"]]
                far = [o for o in opts if not o["value"].startswith("here|")]
                here = [o for o in opts if o["value"].startswith("here|")]
                if far:
                    more = [o["value"] for o in fields["more"]["optionsByKey"].get(target["key"], [])
                            if o["value"] != far[0]["value"]][:1]
                    check(action, src, name, {"target": target["value"], "source": far[0]["value"], "both": [BOTH],
                                              "more": more},
                          f"{name} {target['label']} <- {far[0]['label']}", "other files")
                if here:
                    check(action, src, name, {"target": target["value"], "source": here[0]["value"], "both": [BOTH]},
                          f"{name} {target['label']} <- {here[0]['label']}", "co-sited")
        try:
            if endc.available(c):
                continue
            fields = {f["id"]: f for f in endc.setup(c)["fields"]}
        except Exception:
            failures.append(f"{name}: endc setup crashed\n{traceback.format_exc()}")
            continue
        for side in fields["side"]["options"]:
            if side["value"] == "4g":
                for enb in fields["enb"]["options"]:
                    carriers = [o["value"] for o in fields["carrier"]["optionsByKey"][enb["key"]]
                                if o["value"] != endc.MANUAL]
                    carrier = fields["carrier"]["defaultByKey"].get(enb["key"]) or (carriers or [None])[0]
                    if not carrier:
                        continue
                    x2s = [o["value"] for o in fields["x2"]["optionsByKey"][enb["key"]]]
                    x2 = fields["x2"]["defaultByKey"].get(enb["key"]) or (endc.AUTO if endc.AUTO in x2s else x2s[0])
                    check(endc, src, name, {"side": "4g", "enb": enb["value"], "carrier": carrier, "x2": x2,
                                            "also5g": [endc.ALSO]},
                          f"{name} {enb['label']} 4G side", "4g")
            else:
                for gnb in fields["gnb"]["options"]:
                    picks = [o["value"] for o in fields["enbs"]["optionsByKey"].get(gnb["key"], [])][:1]
                    if picks:
                        check(endc, src, name, {"side": "5g", "gnb": gnb["value"], "enbs": picks},
                              f"{name} {gnb['label']} 5G side", "5g")

    for k in sorted(counts):
        print(" / ".join(k) + f": {counts[k]}")
    for (a, p), n in refusals.most_common():
        print(f"  {a} refused {n}x: {p}")
    for (a, n), k in sorted(notes.items(), key=lambda x: -x[1])[:25]:
        print(f"  {a} note {k}x: {n}")
    for f in failures:
        print("FAIL", f)
    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    here = os.path.join(os.path.dirname(__file__), "..")
    folders = sys.argv[1:] or [d for d in (os.path.join(here, "example"), os.path.join(here, "scp")) if os.path.isdir(d)]
    sys.exit(main(folders))

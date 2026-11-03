#!/usr/bin/env python3
"""
Corpus check for the MME/AMF action (backend/app/actions/core.py).

For every MME and AMF in the given folders, and every "New MME/AMF" target:
  1. Plan a new address. A crash fails; a refusal is counted with its reason.
  2. The result must parse, and the site check must find no new error.
  3. The node must hold the new address afterwards, with nothing the old
     core reported left on it.
  4. Planning the same address again must be refused (unchanged, or a
     duplicate of the node just added).
  5. A new node with the address of the first existing one on the same
     transport network must be refused.

Usage: python3 scripts/core_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if any file fails. Run from the repo root; no server needed.
"""
import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.actions import Context, PlanError, core  # noqa: E402
from app.actions.corpus import profile  # noqa: E402
from app.parser import XmlParseError, parse_file  # noqa: E402

TEST_IP = "10.250.250.1"


def main(folders):
    paths = sorted(os.path.join(d, f) for d in folders for f in os.listdir(d) if f.lower().endswith(".xml"))
    index, raws = {}, {}
    for path in paths:
        raw = open(path, "rb").read()
        try:
            for (release, cls), names in profile(raw)["params"].items():
                index.setdefault(release, {}).setdefault(cls, set()).update(names)
        except XmlParseError:
            continue
        raws[path] = raw
    ctx = lambda raw, name: Context(raw, name, "upload", release_index=lambda: index)

    counts, refusals, notes, failures = collections.Counter(), collections.Counter(), collections.Counter(), []

    def refused(c, inputs):
        try:
            core.plan(c, inputs)
        except PlanError:
            return True
        return False

    for path, raw in raws.items():
        name = os.path.basename(path)
        c = ctx(raw, name)
        try:
            if core.available(c):
                continue
            fields = {f["id"]: f for f in core.setup(c)["fields"]}
        except Exception:
            failures.append(f"{name}: setup crashed\n{traceback.format_exc()}")
            continue
        for target in fields["target"]["options"]:
            new_node = target["value"].startswith(core.NEW)
            kind = ("MME" if target["group"].startswith("MMEs") else "AMF") + (" new" if new_node else " change")
            inputs = {"target": target["value"], "ip": TEST_IP}
            where = f"{name} {target['label']}"
            try:
                out, plan = core.plan(c, inputs)
            except PlanError as e:
                counts[(kind, "refused")] += 1
                for p in e.problems:
                    refusals[p[:90]] += 1
                continue
            except Exception:
                failures.append(f"{where}: plan crashed\n{traceback.format_exc()}")
                continue
            counts[(kind, "ok")] += 1
            for n in plan["notes"]:
                notes[n.split(":")[0][:60]] += 1
            try:
                parse_file(out, name)
            except XmlParseError as e:
                failures.append(f"{where}: result doesn't parse: {e}")
                continue
            broken = [f["title"] for f in plan["check"]["new"] if f["severity"] == "error"]
            if broken:
                failures.append(f"{where}: new site-check errors: {broken}")
            after = ctx(out, name)
            dn = plan["focus"].split("::p::")[0]
            m = after.site.by_dn.get(dn)
            if not m or core._ip_of(m) != TEST_IP:
                failures.append(f"{where}: {dn} doesn't hold {TEST_IP} afterwards")
                continue
            learned = (core.MME_LEARNED if m["cls"] == "LNMME" else core.AMF_LEARNED)
            lists = (core.MME_LEARNED_LISTS if m["cls"] == "LNMME" else core.AMF_LEARNED_LISTS)
            left = [k for k in learned if m["p"].get(k) is not None] + \
                [k for k in lists if (m.get("lists") or {}).get(k)]
            if left:
                failures.append(f"{where}: {dn} still has what the old core reported: {left}")
            again = {"target": target["value"] if new_node else dn, "ip": TEST_IP}
            if not refused(after, again):
                failures.append(f"{where}: the same address planned again isn't refused")
            if new_node:
                parent = target["value"][len(core.NEW):]
                cls = "LNMME" if kind.startswith("MME") else "SERVEDAMF"
                first = next((s for s in c.site.child(parent, cls) if core._ip_of(s)), None)
                if first and not refused(c, {"target": target["value"], "ip": core._ip_of(first)}):
                    failures.append(f"{where}: a new node with {label(first)}'s address isn't refused")

    for key, n in sorted(counts.items()):
        print(f"{' / '.join(key)}: {n}")
    for reason, n in refusals.most_common():
        print(f"  refused {n}x: {reason}")
    for note, n in notes.most_common():
        print(f"  note {n}x: {note}")
    for f in failures:
        print("FAIL", f)
    print(f"{len(failures)} failure{'s' if len(failures) != 1 else ''}")
    return 1 if failures else 0


def label(m):
    return m["dn"].rsplit("/", 1)[-1]


if __name__ == "__main__":
    args = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(args))

#!/usr/bin/env python3
"""
Corpus check for the DRX action (backend/app/actions/drx.py).

For every eNB and gNB in the given folders, and every preset:
  1. Plan it. A crash fails; a refusal is counted with its reason (runtime
     exports with no DRX objects are refused on purpose).
  2. The result must parse, and the site check must find no new error.
  3. Planning the same preset on the result must change nothing.
  4. "off" after "on" must leave no DRX switch on in the picked cells.

Usage: python3 scripts/drx_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if any file fails. Run from the repo root; no server needed.
"""
import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.actions import Context, PlanError, drx  # noqa: E402
from app.actions.corpus import profile  # noqa: E402
from app.parser import XmlParseError, parse_file  # noqa: E402


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

    counts, refusals, failures = collections.Counter(), collections.Counter(), []
    for path, raw in raws.items():
        name = os.path.basename(path)
        c = ctx(raw, name)
        try:
            if drx.available(c):
                continue
            fields = {f["id"]: f for f in drx.setup(c)["fields"]}
        except Exception:
            failures.append(f"{name}: setup crashed\n{traceback.format_exc()}")
            continue
        for target in fields["target"]["options"]:
            kind = target["group"]
            for preset in fields["preset"]["optionsByKey"][target["value"]]:
                inputs = {"target": target["value"], "preset": preset["value"]}
                where = f"{name} {target['label']} {preset['value']}"
                try:
                    new, plan = drx.plan(c, inputs)
                except PlanError as e:
                    counts[(kind, preset["value"], "refused")] += 1
                    for p in e.problems:
                        refusals[p.split(": ", 1)[-1].split(". ")[0][:80]] += 1
                    continue
                except Exception:
                    failures.append(f"{where}: plan crashed\n{traceback.format_exc()}")
                    continue
                counts[(kind, preset["value"], "ok")] += 1
                try:
                    parse_file(new, name)
                except XmlParseError as e:
                    failures.append(f"{where}: result doesn't parse: {e}")
                    continue
                broken = [f["title"] for f in plan["check"]["new"] if f["severity"] == "error"]
                if broken:
                    failures.append(f"{where}: new site-check errors: {broken}")
                again = drx.plan(ctx(new, name), inputs)[1]["changes"]
                if again:
                    failures.append(f"{where}: not idempotent, a second run changes "
                                    f"{[(x['dn'], x.get('param')) for x in again[:5]]}")
                if preset["value"] == "on":
                    off, _ = drx.plan(ctx(new, name), {**inputs, "preset": "off"})
                    after = ctx(off, name)
                    for cell in fields["cells"]["optionsByKey"][target["value"]]:
                        p = after.site.by_dn[cell["value"]]["p"]
                        left = [k for k in ("actDrx", "actSmartDrx", "actCDrx", "actCDrxVoNR") if p.get(k) == "true"]
                        if left:
                            failures.append(f"{where}: {cell['label']} still has {left} after off")

    for key, n in sorted(counts.items()):
        print(f"{' / '.join(key)}: {n}")
    for reason, n in refusals.most_common():
        print(f"  refused {n}x: {reason}")
    for f in failures:
        print("FAIL", f)
    print(f"{len(failures)} failure{'s' if len(failures) != 1 else ''}")
    return 1 if failures else 0


if __name__ == "__main__":
    args = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(args))

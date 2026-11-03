#!/usr/bin/env python3
"""
Calibration for the link rules (backend/app/actions/links.py): runs the
site check on every file in the given folders and reports, per rule, how
many findings it raised and on how many files. Production and working files
should have no errors; a rule that fires there is too strict.

Usage: python3 scripts/link_rules_check.py [-v] [folder ...]
       (default: example/ and scp/, whichever exist)
-v lists every finding, not just the counts.
Exit status 1 if any file has an error. Run from the repo root; no server
needed.
"""
import hashlib
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.actions.site_check import check_site  # noqa: E402
from app.parser import XmlParseError  # noqa: E402


def main() -> int:
    args = sys.argv[1:]
    verbose = "-v" in args
    folders = [a for a in args if a != "-v"] or [d for d in ("example", "scp") if os.path.isdir(d)]
    seen, per_rule, files_per_rule, error_files = set(), defaultdict(Counter), defaultdict(set), {}
    total = 0
    for folder in folders:
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith(".xml"):
                continue
            raw = open(os.path.join(folder, name), "rb").read()
            digest = hashlib.sha1(raw).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            try:
                result = check_site(raw)
            except XmlParseError as e:
                print(f"skip {name}: {e}")
                continue
            total += 1
            for f in result["findings"]:
                per_rule[f["ruleId"]][f["severity"]] += 1
                files_per_rule[f["ruleId"]].add(name)
                if verbose:
                    print(f"  {f['severity']:7} {name[:48]:48} {f['title']}")
            if result["summary"]["errors"]:
                error_files[name] = [f["title"] for f in result["findings"] if f["severity"] == "error"]
    print(f"\n{total} files")
    for rid in sorted(per_rule):
        c = per_rule[rid]
        print(f"  {rid:16} {c['error']:5} errors {c['warning']:5} warnings {c['info']:5} notes"
              f"   on {len(files_per_rule[rid])} files")
    for name, titles in sorted(error_files.items()):
        print(f"ERRORS {name}: " + "; ".join(titles[:4]) + (f" (+{len(titles) - 4})" if len(titles) > 4 else ""))
    print(f"\n{len(error_files)} files with errors" if error_files else "\nno errors")
    return 1 if error_files else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Phase 2 of the 3GPP-reference work (see scripts/build_3gpp_class_refs.py
for phase 1 and PROJECT_STATE.md §8.7 for the full story): gives every
parameter in backend/app/data/parameters.json a `threeGpp` field too.

Run standalone, AFTER build_3gpp_class_refs.py (reads its `threeGpp`
output on classes.json). Only ever adds/overwrites the `threeGpp` key on
parameters that don't already carry a real `threeGppRef` -- never touches
description/confidence/dataType/anything else, and never touches the 526
parameters whose `threeGppRef` came straight from Nokia's own official
dictionary (scripts/merge_official_reference.py) -- that data is more
authoritative than anything this script could produce and is left alone.

THE HONESTY PROBLEM THIS SCRIPT EXISTS TO SOLVE: individually researching
each of the ~5,130 remaining parameters against actual 3GPP spec text
(the way build_3gpp_class_refs.py's 297 classes were each individually
reasoned about) is not a "run a script" task -- it would mean reading
thousands of spec sections by hand. What IS honest and tractable at this
scale: a parameter's own managed-object class(es) now have a real,
individually-reasoned 3GPP status (phase 1). Inheriting from that is a
STRICTLY WEAKER claim than "this exact parameter is defined at TS X
clause Y" -- so it gets its own status, `unverified`, distinct from the
class-level `standardized`, rather than borrowing that label. This is the
whole point: never let an inherited, lower-confidence signal wear the
same badge as something actually reasoned through.

Combining rule per parameter, across every class it's observed under
(from class_catalog.json, which -- unlike classes.json's 297 corpus-
grounded classes -- also includes ~260 official-dictionary-only classes,
many of them Nokia's own reserved "*SPARE" padding slots that were never
worth individually researching in phase 1; those default to
vendor-specific here, same as an unlisted class would):
  - any owning class is "standardized"   -> parameter status "unverified"
    (shows the class's own spec links for reference, clearly captioned as
    class-level, not parameter-verified)
  - else any owning class is "other-standard" -> parameter inherits that
    class's note (e.g. "this lives on an AISG-governed RET class")
  - else (all owning classes vendor-specific, unknown, or no class found
    at all) -> "vendor-specific"
"""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "backend" / "app" / "data"


def load(name):
    return json.loads((DATA_DIR / name).read_text())


def build():
    params = load("parameters.json")
    classes = load("classes.json")
    class_catalog = load("class_catalog.json")

    param_to_classes: dict[str, set[str]] = {}
    for cls, entry in class_catalog.items():
        for pname in entry.get("params", {}):
            param_to_classes.setdefault(pname, set()).add(cls)

    counts = {"skipped_has_ref": 0, "unverified": 0, "other-standard": 0, "vendor-specific": 0}

    for name, entry in params.items():
        if entry.get("threeGppRef"):
            counts["skipped_has_ref"] += 1
            continue

        owning = sorted(param_to_classes.get(name, []))
        statuses = [classes.get(c, {}).get("threeGpp", {}).get("status", "vendor-specific") for c in owning]

        standardized_classes = [c for c, s in zip(owning, statuses) if s == "standardized"]
        other_standard_classes = [c for c, s in zip(owning, statuses) if s == "other-standard"]

        if standardized_classes:
            # Union the specs from every standardized owning class, dedup by spec number.
            specs_by_number = {}
            for c in standardized_classes:
                for s in classes[c]["threeGpp"]["specs"]:
                    specs_by_number[s["spec"]] = s
            class_list = ", ".join(standardized_classes)
            entry["threeGpp"] = {
                "status": "unverified",
                "specs": list(specs_by_number.values()),
                "note": (
                    f"Not individually checked against spec text. This parameter's managed-object "
                    f"class ({class_list}) is 3GPP-standardized (see the spec(s) above), but Nokia's "
                    f"own dictionary didn't carry a parameter-specific 3GPP reference for it, and "
                    f"individually verifying every such parameter against the actual spec text was "
                    f"beyond this pass's scope -- this could be a standardized IE, or a Nokia OAM "
                    f"knob layered on top of a standardized object. Treat this as a starting point "
                    f"for manual lookup, not a confirmed citation."
                ),
            }
            counts["unverified"] += 1
        elif other_standard_classes:
            # Reuse the first owning other-standard class's note verbatim -- they're
            # already written to stand alone, and a parameter under e.g. an AISG-governed
            # RET class inherits that exact same governing body.
            note = classes[other_standard_classes[0]]["threeGpp"]["note"]
            entry["threeGpp"] = {"status": "other-standard", "specs": [], "note": note}
            counts["other-standard"] += 1
        else:
            note = (
                "Nokia-proprietary parameter; no 3GPP reference in Nokia's own dictionary, and its "
                "managed-object class isn't part of the 3GPP model either."
                if owning
                else "Nokia-proprietary parameter with no managed-object class association found in "
                "the generator's catalog to check against."
            )
            entry["threeGpp"] = {"status": "vendor-specific", "specs": [], "note": note}
            counts["vendor-specific"] += 1

    (DATA_DIR / "parameters.json").write_text(json.dumps(params, indent=1, sort_keys=True))

    print(f"Parameters processed: {len(params)}")
    print(f"  already had Nokia-sourced threeGppRef (untouched): {counts['skipped_has_ref']}")
    print(f"  unverified (owning class standardized, param itself not checked): {counts['unverified']}")
    print(f"  other-standard (non-3GPP body governs it):          {counts['other-standard']}")
    print(f"  vendor-specific (no reference at all):               {counts['vendor-specific']}")


if __name__ == "__main__":
    build()

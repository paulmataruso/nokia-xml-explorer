#!/usr/bin/env python3
"""
Merges curated research output (written by the research subagents + a few
hand-written entries for edge cases) with a deterministic heuristic fallback
for anything not curated, into the two files the backend actually serves:

    backend/app/data/classes.json
    backend/app/data/parameters.json

Run scripts/extract_inventory.py first (or after adding new sample files)
to refresh research/input/final_inventory.json / final_param_stats.json.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.heuristics import generate as heuristic_generate  # noqa: E402

RESEARCH_INPUT = ROOT / "research" / "input"
RESEARCH_OUTPUT = ROOT / "research" / "output"
DATA_DIR = ROOT / "backend" / "app" / "data"

VALID_CONFIDENCE = {"high", "medium", "low", "heuristic"}
VALID_CATEGORY = {
    "Equipment", "Transport-Networking", "LTE-Radio-Cell", "NR-Radio-Cell",
    "Mobility-Neighbor-Relations", "Core-Network-Interface", "Synchronization",
    "Security", "QoS", "Feature-Function-Config", "Site-Common", "Other",
    # a couple of loose synonyms some agents may have used
    "File Format",
}


def load_json(path: Path):
    return json.loads(path.read_text())


def main():
    final_inventory = load_json(RESEARCH_INPUT / "final_inventory.json")
    final_stats = load_json(RESEARCH_INPUT / "final_param_stats.json")

    # ---- Merge curated classes ----
    curated_classes = {}
    for i in (1, 2, 3):
        chunk = load_json(RESEARCH_OUTPUT / f"classes_chunk_{i}.json")
        curated_classes.update(chunk)
    extra_classes_path = RESEARCH_OUTPUT / "classes_extra_manual.json"
    if extra_classes_path.exists():
        curated_classes.update(load_json(extra_classes_path))

    # ---- Merge curated params ----
    curated_params = {}
    for i in range(1, 7):
        chunk = load_json(RESEARCH_OUTPUT / f"params_chunk_{i}.json")
        curated_params.update(chunk)
    extra_params_path = RESEARCH_OUTPUT / "params_extra_manual.json"
    if extra_params_path.exists():
        curated_params.update(load_json(extra_params_path))

    # ---- Build final classes.json: every class in final_inventory gets an
    # entry, curated where available, generic heuristic otherwise. ----
    final_classes = {}
    uncurated_classes = []
    for short, meta in final_inventory.items():
        entry = curated_classes.get(short)
        if entry and entry.get("description"):
            conf = entry.get("confidence", "medium")
            if conf not in VALID_CONFIDENCE:
                conf = "medium"
            cat = entry.get("category", "Other")
            if cat not in VALID_CATEGORY:
                cat = "Other"
            final_classes[short] = {
                "description": entry["description"],
                "category": cat,
                "confidence": conf,
                "fullNames": meta["fullNames"],
                "occurrences": meta["occurrences"],
            }
        else:
            uncurated_classes.append(short)
            final_classes[short] = {
                "description": (
                    f"No curated description is available for managed object class \"{short}\". "
                    "It did not appear in the researched sample set. Based on Nokia RAN naming "
                    "conventions, it is a managed object class in the SBTS/AirScale or Flexi Zone "
                    "data model; the sample parameters it configures are listed below for context."
                ),
                "category": "Other",
                "confidence": "heuristic",
                "fullNames": meta["fullNames"],
                "occurrences": meta["occurrences"],
                "sampleParams": meta["sampleParams"][:10],
            }

    # ---- Build final parameters.json: every param name in final_param_stats
    # gets an entry, curated where available, heuristic-generated otherwise. ----
    final_params = {}
    heuristic_count = 0
    freq = final_stats["freq"]
    examples = final_stats["examples"]
    classes_for_param = final_stats["classes_for_param"]

    for name in freq:
        entry = curated_params.get(name)
        if entry and entry.get("description"):
            conf = entry.get("confidence", "medium")
            if conf not in VALID_CONFIDENCE:
                conf = "medium"
            final_params[name] = {
                "description": entry["description"],
                "confidence": conf,
                "dataType": entry.get("dataType") or "string",
                "unit": entry.get("unit"),
                "notes": entry.get("notes"),
            }
        else:
            heuristic_count += 1
            generated = heuristic_generate(
                name,
                classes_for_param.get(name, []),
                examples.get(name, []),
            )
            final_params[name] = generated

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "classes.json").write_text(json.dumps(final_classes, indent=1, sort_keys=True))
    (DATA_DIR / "parameters.json").write_text(json.dumps(final_params, indent=1, sort_keys=True))

    print(f"Classes: {len(final_classes)} total, {len(uncurated_classes)} uncurated (heuristic)")
    if uncurated_classes:
        print("  uncurated:", ", ".join(sorted(uncurated_classes)))
    print(f"Params: {len(final_params)} total, {heuristic_count} heuristic-generated "
          f"({100 * (len(final_params) - heuristic_count) / len(final_params):.1f}% curated)")


if __name__ == "__main__":
    main()

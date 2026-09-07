#!/usr/bin/env python3
"""
Upgrades backend/app/data/{parameters,classes}.json with the official Nokia
parameter dictionaries extracted from ref/ (see extract_official_reference.py
and extract_sbts18a_reference.py):

  - LTE18 (2018): built for the older `com.nokia.mrbts:*` / `NOKLTE:*`
    (Flexi Zone / BTS Site Manager) naming convention.
  - SBTS18A (2019): the current, unified SingleRAN AirScale dictionary
    covering the `com.nokia.srbts:*` namespace -- the newest/most relevant
    convention for this tool, including 5G NR.

For every parameter name that actually appears in our XML corpus AND has a
match in either dictionary, the curated/heuristic entry is replaced with a
new "official" entry carrying the real Nokia description plus the rich
structured fields (range, default, modification rules, required-on-creation,
license/feature requirement, 3GPP reference). Non-matching entries (names
newer than both dictionaries, or too obscure to be documented) are left
untouched.

Class entries get non-destructive enrichment only: officialFullName and
officialHierarchy, without touching the existing curated description.

Run AFTER scripts/build_knowledge.py (this reads its output and upgrades it
in place) and AFTER both extract_*.py scripts (produce the ref/extracted/*.json
this script consumes). Requires only the stdlib.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED_DIR = ROOT / "ref" / "extracted"
DATA_DIR = ROOT / "backend" / "app" / "data"
STATS_PATH = ROOT / "research" / "input" / "final_param_stats.json"

DATA_TYPE_MAP = {
    "String": "string",
    "Boolean": "boolean",
    "Enumeration": "enum",
    "Structure": "other",
    "Bitmask": "other",
}

SOURCE_LABELS = {
    "SBTS18A": "Nokia SBTS 18A official SingleRAN AirScale parameter dictionary",
    "LTE18-FDD": "Nokia LTE18 official BTS parameter dictionary (FDD)",
    "LTE18-TDD": "Nokia LTE18 official BTS parameter dictionary (TDD)",
}

_STEP_DECIMAL_RE = re.compile(r"step\s+(-?\d+\.\d+)", re.I)


def load(path: Path):
    return json.loads(path.read_text())


def dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1, sort_keys=True))


def _s(value) -> str:
    """A handful of source cells are numeric (e.g. a bare 'Range and step' of
    42) even though the column is normally free text -- coerce defensively
    rather than letting a stray float blow up string operations downstream."""
    if value is None:
        return ""
    return str(value)


def normalize_data_type(entry: dict) -> str:
    raw = entry.get("Data Type")
    if raw == "Number":
        return "decimal" if _STEP_DECIMAL_RE.search(_s(entry.get("Range and step"))) else "integer"
    return DATA_TYPE_MAP.get(raw, "string")


def extract_unit(range_and_step) -> str | None:
    range_and_step = _s(range_and_step)
    if not range_and_step:
        return None
    # e.g. "-500...18000 m, step 1 m" -> "m" ; "0...360 degrees, step 1 degrees" -> "degrees"
    m = re.search(r"\d(?:\.\d+)?\s+([A-Za-z%][A-Za-z%/°\s]{0,15}?)(?:,|$)", range_and_step)
    if m:
        unit = m.group(1).strip()
        if unit and unit.lower() not in ("step",):
            return unit
    return None


def load_all_param_rows() -> list[dict]:
    rows = []
    for fname, tag in (
        ("sbts18a_parameters.json", "SBTS18A"),
        ("lte18_parameters_fdd.json", "LTE18-FDD"),
        ("lte18_parameters_tdd.json", "LTE18-TDD"),
    ):
        path = EXTRACTED_DIR / fname
        if not path.exists():
            continue
        for row in load(path):
            row["_source_doc"] = tag
            rows.append(row)
    return rows


def pick_best_entry(candidates: list[dict], our_classes: set[str]) -> dict:
    """Nokia reuses many abbreviated names (administrativeState, name, prodCode...)
    across dozens of unrelated MO classes. Our knowledge base is keyed by name
    alone (not (class, name)), so picking one class's description to represent
    ALL uses of the name needs care:

    - If every candidate has the same description, it doesn't matter -- use it.
    - If our corpus only ever uses this name under a single class, prefer the
      official entry for exactly that class (most precise), regardless of
      which dictionary it came from.
    - Otherwise the name is genuinely used generically across our own corpus
      too, so a highly class-specific essay (e.g. the ETHLK-only lock/unlock
      rules for "administrativeState") would be actively misleading when shown
      for, say, an RMOD or BBMOD instance. Prefer the SHORTEST reasonably
      substantial description as a safer generic proxy, favoring SBTS18A
      (the current, most relevant dictionary for this tool) when it has one.
    """
    distinct_descriptions = {c.get("Description", "") for c in candidates}
    if len(distinct_descriptions) <= 1:
        return max(candidates, key=lambda c: len(c.get("Description") or ""))

    if len(our_classes) <= 1:
        for c in candidates:
            last_seg = _s(c.get("MO Class")).rsplit("/", 1)[-1]
            if last_seg in our_classes:
                return c

    substantial = [c for c in candidates if len(c.get("Description") or "") >= 15] or candidates
    sbts_substantial = [c for c in substantial if c.get("_source_doc") == "SBTS18A"]
    pool = sbts_substantial or substantial
    return min(pool, key=lambda c: len(c.get("Description") or ""))


def build_official_param_entry(row: dict) -> dict:
    entry = {
        "description": row.get("Description") or row.get("Full Name") or "",
        "confidence": "official",
        "dataType": normalize_data_type(row),
        "unit": extract_unit(row.get("Range and step", "")),
        "source": SOURCE_LABELS.get(row.get("_source_doc"), "Nokia official parameter dictionary"),
        "fullName": row.get("Full Name"),
        "moClass": row.get("MO Class"),
    }
    if row.get("Range and step") not in (None, ""):
        entry["range"] = _s(row["Range and step"])
    if "Default Value" in row:
        dv = row["Default Value"]
        entry["defaultValue"] = str(dv)
        if row.get("Default Value Notes"):
            entry["defaultValue"] += f" ({row['Default Value Notes']})"
    if row.get("Modification"):
        entry["modification"] = row["Modification"]
    if row.get("Required on Creation"):
        entry["requiredOnCreation"] = row["Required on Creation"]
    if row.get("Related Features"):
        entry["relatedFeatures"] = row["Related Features"]
    if row.get("References"):
        entry["threeGppRef"] = row["References"]
    if row.get("3GPP Name"):
        entry["threeGppName"] = row["3GPP Name"]
    notes_bits = []
    if row.get("Related Functions"):
        notes_bits.append(f"Related functions: {row['Related Functions']}")
    if row.get("Related Parameters"):
        notes_bits.append(f"Related parameters: {row['Related Parameters']}")
    if row.get("Parameter Relationships"):
        notes_bits.append(row["Parameter Relationships"])
    if notes_bits:
        entry["notes"] = " ".join(notes_bits)
    return entry


def merge_parameters(our_stats: dict) -> tuple[int, int]:
    params_path = DATA_DIR / "parameters.json"
    params = load(params_path)

    by_name: dict[str, list[dict]] = {}
    for row in load_all_param_rows():
        by_name.setdefault(row["Abbreviated Name"], []).append(row)

    classes_for_param = our_stats["classes_for_param"]

    upgraded = 0
    for name in params:
        candidates = by_name.get(name)
        if not candidates:
            continue
        our_classes = set(classes_for_param.get(name, []))
        best = pick_best_entry(candidates, our_classes)
        params[name] = build_official_param_entry(best)
        upgraded += 1

    dump(params_path, params)
    return upgraded, len(params)


def merge_classes() -> int:
    classes_path = DATA_DIR / "classes.json"
    classes = load(classes_path)

    by_short: dict[str, dict] = {}
    # Load lowest-priority first so later loads override on conflict.
    for fname in ("lte18_mo_classes_tdd.json", "lte18_mo_classes_fdd.json", "sbts18a_mo_classes.json"):
        path = EXTRACTED_DIR / fname
        if not path.exists():
            continue
        for row in load(path):
            by_short[row["shortName"]] = row

    enriched = 0
    for short, entry in classes.items():
        official = by_short.get(short)
        if not official:
            continue
        entry["officialFullName"] = official["fullName"]
        entry["officialHierarchy"] = official["parentChain"] + [official["shortName"]]
        enriched += 1

    dump(classes_path, classes)
    return enriched


def main():
    our_stats = load(STATS_PATH)
    upgraded, total = merge_parameters(our_stats)
    enriched = merge_classes()
    print(f"Parameters upgraded to 'official': {upgraded} / {total} "
          f"({100 * upgraded / total:.1f}%)")
    print(f"Classes enriched with official full name/hierarchy: {enriched}")


if __name__ == "__main__":
    main()

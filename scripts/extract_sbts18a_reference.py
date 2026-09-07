#!/usr/bin/env python3
"""
Extracts the official Nokia SBTS 18A parameter dictionary -- the modern,
unified (2G/3G/4G/5G) SingleRAN AirScale dictionary, covering the
`com.nokia.srbts:*` namespace that the older LTE18 dictionary (built for
the `com.nokia.mrbts:*`/`NOKLTE:*` convention) doesn't -- into clean JSON:

  ref/extracted/sbts18a_parameters.json
  ref/extracted/sbts18a_mo_classes.json

Source is the old binary .xls format (requires `xlrd`, not `openpyxl`).
Same schema as extract_official_reference.py's LTE18 extraction, except the
Parameter List here is a single unified sheet (no FDD/TDD split) with an
extra "Technology" column.
"""
import json
from pathlib import Path

import xlrd

ROOT = Path(__file__).resolve().parent.parent
XLS_PATH = (
    ROOT / "ref" / "SRAN18AISSUE03HTML" / "htm" / "docs" / "sbts_parameters_18a" / "SBTS_Parameters_18A.xls"
)
OUT_DIR = ROOT / "ref" / "extracted"


def find_header_row(sh, marker_col_idx, marker_value, max_scan=10):
    for r in range(min(max_scan, sh.nrows)):
        if sh.cell_value(r, marker_col_idx) == marker_value:
            return r
    raise ValueError(f"Could not find header row with {marker_value!r} in column {marker_col_idx}")


def extract_param_sheet(wb, sheet_name):
    sh = wb.sheet_by_name(sheet_name)
    header_idx = find_header_row(sh, 3, "Abbreviated Name")
    header_row = [sh.cell_value(header_idx, c) for c in range(sh.ncols)]

    col_map = {}
    for idx, label in enumerate(header_row):
        if label and "in release" not in str(label) and "in issue" not in str(label):
            col_map[str(label)] = idx

    results = []
    name_idx = col_map["Abbreviated Name"]
    for r in range(header_idx + 1, sh.nrows):
        name = sh.cell_value(r, name_idx)
        if not name:
            continue
        entry = {}
        for label, idx in col_map.items():
            if idx >= sh.ncols:
                continue
            v = sh.cell_value(r, idx)
            if v not in (None, ""):
                entry[label] = v.strip() if isinstance(v, str) else v
        results.append(entry)
    return results


def extract_mo_class_tree(wb, sheet_name):
    sh = wb.sheet_by_name(sheet_name)
    results = []
    stack = []
    for r in range(sh.nrows):
        depth = None
        short_name = None
        for c in range(8):
            v = sh.cell_value(r, c)
            if v not in (None, ""):
                depth = c
                short_name = str(v).strip()
                break
        if depth is None or short_name == "Managed Object Class Tree":
            continue
        full_name = sh.cell_value(r, 8) if sh.ncols > 8 else None
        stack = stack[:depth]
        stack.append(short_name)
        results.append({
            "shortName": short_name,
            "fullName": str(full_name).strip() if full_name else None,
            "depth": depth,
            "parentChain": list(stack[:-1]),
        })
    return results


def dump_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1, default=str))


def main():
    wb = xlrd.open_workbook(str(XLS_PATH), formatting_info=False)

    params = extract_param_sheet(wb, "Parameter List")
    classes = extract_mo_class_tree(wb, "MO Class Tree")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dump_json(OUT_DIR / "sbts18a_parameters.json", params)
    dump_json(OUT_DIR / "sbts18a_mo_classes.json", classes)

    print(f"SBTS18A params: {len(params)}")
    print(f"SBTS18A classes: {len(classes)}")
    unique_moc = {p["MO Class"].rsplit("/", 1)[-1] for p in params if "MO Class" in p}
    print(f"Unique MO classes referenced by params: {len(unique_moc)}")


if __name__ == "__main__":
    main()

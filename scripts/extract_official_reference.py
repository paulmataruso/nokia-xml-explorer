#!/usr/bin/env python3
"""
Extracts the official Nokia LTE18 BTS parameter dictionary from
ref/ref_bts_parameters_lte18.xlsx into clean JSON:

  ref/extracted/lte18_parameters.json   -- one entry per (MO Class, Abbreviated Name) row
  ref/extracted/lte18_mo_classes.json   -- MO class hierarchy + full names

Run with a Python that has openpyxl installed (not a runtime dependency of
the app itself -- this is an offline data-prep script, like build_knowledge.py).
"""
import datetime
import json
from pathlib import Path

import openpyxl


def _json_default(o):
    if isinstance(o, (datetime.time, datetime.date, datetime.datetime)):
        return o.isoformat()
    return str(o)


def dump_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1, default=_json_default))

ROOT = Path(__file__).resolve().parent.parent
XLSX_PATH = ROOT / "ref" / "ref_bts_parameters_lte18.xlsx"
OUT_DIR = ROOT / "ref" / "extracted"


def find_header_row(ws, marker_col_idx, marker_value, max_scan=10):
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan, values_only=True), start=1):
        if len(row) > marker_col_idx and row[marker_col_idx] == marker_value:
            return i, row
    raise ValueError(f"Could not find header row with {marker_value!r} in column {marker_col_idx}")


def extract_param_sheet(wb, sheet_name, duplex):
    ws = wb[sheet_name]
    header_idx, header_row = find_header_row(ws, 3, "Abbreviated Name")

    col_map = {}
    for idx, label in enumerate(header_row):
        if label and "in release" not in str(label):
            col_map[str(label)] = idx

    results = []
    for row in ws.iter_rows(min_row=header_idx + 1, values_only=True):
        name_idx = col_map["Abbreviated Name"]
        if name_idx >= len(row) or not row[name_idx]:
            continue
        entry = {}
        for label, idx in col_map.items():
            v = row[idx] if idx < len(row) else None
            if v is not None and str(v).strip():
                entry[label] = v if not isinstance(v, str) else v.strip()
        entry["_duplex"] = duplex
        results.append(entry)
    return results


def extract_mo_class_tree(wb, sheet_name, duplex):
    ws = wb[sheet_name]
    # Rows encode hierarchy depth by *which* of columns 1..8 holds the class
    # short name; column 9 holds the human-readable full name.
    results = []
    stack = []  # list of short names at each depth, index = depth
    for row in ws.iter_rows(min_row=1, values_only=True):
        depth = None
        short_name = None
        for i in range(8):
            if row[i] not in (None, ""):
                depth = i
                short_name = str(row[i]).strip()
                break
        if depth is None:
            continue
        full_name = row[8] if len(row) > 8 else None
        if short_name in ("Managed Object Class Tree",):
            continue
        stack = stack[:depth]
        stack.append(short_name)
        results.append({
            "shortName": short_name,
            "fullName": str(full_name).strip() if full_name else None,
            "depth": depth,
            "parentChain": list(stack[:-1]),
            "_duplex": duplex,
        })
    return results


def main():
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)

    fdd_params = extract_param_sheet(wb, "FDD Parameter List", "FDD")
    tdd_params = extract_param_sheet(wb, "TDD Parameter List", "TDD")
    fdd_classes = extract_mo_class_tree(wb, "FDD MO Class Tree", "FDD")
    tdd_classes = extract_mo_class_tree(wb, "TDD MO Class Tree", "TDD")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dump_json(OUT_DIR / "lte18_parameters_fdd.json", fdd_params)
    dump_json(OUT_DIR / "lte18_parameters_tdd.json", tdd_params)
    dump_json(OUT_DIR / "lte18_mo_classes_fdd.json", fdd_classes)
    dump_json(OUT_DIR / "lte18_mo_classes_tdd.json", tdd_classes)

    print(f"FDD params: {len(fdd_params)}  TDD params: {len(tdd_params)}")
    print(f"FDD classes: {len(fdd_classes)}  TDD classes: {len(tdd_classes)}")

    unique_moc = {p["MO Class"] for p in fdd_params if "MO Class" in p} | {
        p["MO Class"] for p in tdd_params if "MO Class" in p
    }
    print(f"Unique MO classes referenced by params: {len(unique_moc)}")


if __name__ == "__main__":
    main()

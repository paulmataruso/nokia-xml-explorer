#!/usr/bin/env python3
"""
Canonical, authoritative extraction of every managed-object class and every
parameter name that actually appears in /scp, using the *same* parser the
running application uses (backend/app/parser.py) -- so the knowledge base
we build is guaranteed to cover exactly what the tree view will ever ask
about (including list/table names, which get a generic explanation rather
than a curated one).

Writes:
  research/input/final_inventory.json  -- {classes: {short: {fullNames, occurrences, sampleParams}}}
  research/input/final_param_stats.json -- {freq, examples, classes_for_param}
"""
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.parser import parse_file  # noqa: E402

SCP_DIR = ROOT / "scp"
OUT_DIR = ROOT / "research" / "input"


def walk(node, class_freq, class_fullnames, class_sample_params,
         param_freq, param_examples, param_classes, current_class):
    kind = node.get("kind")
    if kind in ("mo", "mo-placeholder"):
        short = node.get("class") or ""
        if short:
            class_freq[short] += 1
            full = node.get("fullClass")
            if full:
                class_fullnames[short].add(full)
        current_class = short
    elif kind in ("param", "list"):
        name = node["label"]
        param_freq[name] += 1
        if current_class:
            param_classes[name].add(current_class)
            if len(class_sample_params[current_class]) < 25:
                class_sample_params[current_class].add(name)
        if kind == "param":
            val = node.get("value")
            if val and len(param_examples[name]) < 4:
                param_examples[name].add(val)

    for child in node.get("children", []):
        walk(child, class_freq, class_fullnames, class_sample_params,
             param_freq, param_examples, param_classes, current_class)


def main():
    class_freq = Counter()
    class_fullnames = defaultdict(set)
    class_sample_params = defaultdict(set)
    param_freq = Counter()
    param_examples = defaultdict(set)
    param_classes = defaultdict(set)

    files = sorted(glob.glob(str(SCP_DIR / "*.xml")))
    errors = []
    for path in files:
        raw = Path(path).read_bytes()
        try:
            tree = parse_file(raw, Path(path).name)
        except Exception as e:  # noqa: BLE001
            errors.append((path, str(e)))
            continue
        for child in tree["children"]:
            walk(child, class_freq, class_fullnames, class_sample_params,
                 param_freq, param_examples, param_classes, None)

    print(f"Parsed {len(files) - len(errors)}/{len(files)} files OK")
    for p, e in errors:
        print("  PARSE ERROR:", p, e)

    classes_out = {}
    for short, freq in class_freq.items():
        classes_out[short] = {
            "fullNames": sorted(class_fullnames[short]),
            "occurrences": freq,
            "sampleParams": sorted(class_sample_params[short]),
        }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "final_inventory.json").write_text(json.dumps(classes_out, indent=1, sort_keys=True))

    stats_out = {
        "freq": dict(param_freq),
        "examples": {k: sorted(v) for k, v in param_examples.items()},
        "classes_for_param": {k: sorted(v) for k, v in param_classes.items()},
    }
    (OUT_DIR / "final_param_stats.json").write_text(json.dumps(stats_out, indent=1, sort_keys=True))

    print(f"classes: {len(classes_out)}")
    print(f"params (incl. list names): {len(param_freq)}")


if __name__ == "__main__":
    main()

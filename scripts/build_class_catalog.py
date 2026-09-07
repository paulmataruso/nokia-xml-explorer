#!/usr/bin/env python3
"""
Builds backend/app/data/class_catalog.json: for every MO class Nokia's
official dictionaries define (not just the ones your sample files happen to
use), its parent class and its scalar-parameter catalog.

Each class's parameter list combines two sources:
  1. Parameters actually observed in scp/ ("observed": true) -- data type,
     description, and *actual* distinct values seen in real files. Why this
     matters more than the official doc's numeric enum codes: Nokia's LTE18/
     SBTS18A references document an enum like administrativeState as
     "1: unlocked, 2: shutting down, 3: locked", but real commissioning XML
     in this corpus actually contains the text "Unlocked" / "Locked".
     Suggestions always come from what's actually in scp/, never from the
     official range text alone (that's shown only as human-readable help).
  2. Parameters from the official Nokia dictionaries that are valid for this
     class but weren't exercised by any sample file ("observed": false) --
     included so the "Add Object" generator can offer the *complete* known
     parameter set for a class, not just whatever happened to appear in our
     limited corpus.

Classes are handled the same way: every class actually seen in scp/ gets its
real observed parent + parameter set; every OTHER class either official
dictionary defines also gets a full entry ("observedInCorpus": false), with
its parent taken from the official MO Class Tree instead. Without this, the
"Add Object" picker could only ever offer the ~256 classes your corpus
happened to use, not the ~490 Nokia actually documents -- which defeats the
point of a generator meant to create things you don't already have samples of.

Run after build_knowledge.py and merge_official_reference.py.
"""
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.parser import parse_file  # noqa: E402

SCP_DIR = ROOT / "scp"
DATA_DIR = ROOT / "backend" / "app" / "data"
EXTRACTED_DIR = ROOT / "ref" / "extracted"

MAX_EXAMPLES = 12

DATA_TYPE_MAP = {"String": "string", "Boolean": "boolean", "Enumeration": "enum", "Structure": "other", "Bitmask": "other"}
_STEP_DECIMAL_RE = re.compile(r"step\s+(-?\d+\.\d+)", re.I)


def _s(v) -> str:
    return "" if v is None else str(v)


def official_data_type(row: dict) -> str:
    raw = row.get("Data Type")
    if raw == "Number":
        return "decimal" if _STEP_DECIMAL_RE.search(_s(row.get("Range and step"))) else "integer"
    return DATA_TYPE_MAP.get(raw, "string")


def is_truly_required(official: dict) -> bool:
    """The dictionaries' own field description for 'Required on Creation'
    says: 'Mandatory parameters with no default value defined must be
    filled in.' So 'Mandatory' alone overstates it -- most Mandatory
    parameters have a system default and are fine left unset. Only
    Mandatory-with-no-default genuinely must be supplied for a valid object."""
    return official.get("Required on Creation") == "Mandatory" and official.get("Default Value") in (None, "")


def resolve_default_for_xml(data_type: str, official_default, example_values: list[str]):
    """The value to actually WRITE when auto-filling a Mandatory parameter's
    default -- NOT the bare documented default. Nokia's docs encode
    enum/boolean defaults as codes (administrativeState's official default
    is "locked (3)"; a boolean default is a bare 0.0/1.0), but real XML in
    this corpus uses text ("Locked", "unlocked", "true"/"false"). Returns
    None (leave the parameter unset, same as before) whenever we can't
    confidently resolve a representation that matches what real files
    actually contain -- guessing wrong here would silently write XML that
    doesn't match what real Nokia tools emit, which is worse than omitting
    the parameter and letting the target system apply its own default.
    """
    if official_default in (None, ""):
        return None

    def match_case(label: str):
        for ex in example_values:
            if ex.lower() == label.lower():
                return ex
        return None

    if data_type in ("integer", "decimal"):
        if isinstance(official_default, float) and official_default.is_integer():
            return str(int(official_default))
        return str(official_default)

    if data_type == "string":
        return str(official_default)

    if data_type == "boolean":
        d = str(official_default).strip().lower()
        if d in ("1", "1.0", "true"):
            label = "true"
        elif d in ("0", "0.0", "false"):
            label = "false"
        else:
            return None
        if example_values:
            return match_case(label)
        return label

    if data_type == "enum":
        text = str(official_default)
        label = text.rsplit("(", 1)[0].strip() if "(" in text else text.strip()
        if not label:
            return None
        if example_values:
            return match_case(label)
        return label  # no corpus grounding either way -- best-effort label

    return None


def official_param_entry(official: dict) -> dict:
    """An official-only (never observed in scp/) scalar parameter entry."""
    data_type = official_data_type(official)
    return {
        "dataType": data_type,
        "description": official.get("Description") or official.get("Full Name") or "",
        "confidence": "official",
        "unit": None,
        "exampleValues": [],
        "occurrences": 0,
        "observed": False,
        "officialRange": official.get("Range and step"),
        "officialDefault": official.get("Default Value"),
        "requiredOnCreation": official.get("Required on Creation"),
        "trulyRequired": is_truly_required(official),
        "resolvedDefault": resolve_default_for_xml(data_type, official.get("Default Value"), []),
        "fullName": official.get("Full Name"),
    }


def walk(node, parent_class, class_parent_counter, class_params, class_lists, class_child_sets):
    kind = node.get("kind")
    if kind in ("mo", "mo-placeholder"):
        short = node.get("class") or ""
        if short and parent_class:
            class_parent_counter[short][parent_class] += 1
        new_parent = short
        # The set of direct child classes under THIS ONE instance -- used
        # after the full corpus walk to infer which child classes are
        # "required in practice" (present under every observed instance of
        # this class). Nokia's docs have no class-cardinality data at all
        # (verified: neither dictionary's MO Class Tree sheet, nor any XSD,
        # records min/max child-instance counts) -- this corpus heuristic is
        # the only grounded signal available, so it's surfaced with an
        # explicit sample size rather than presented as fact.
        if short:
            direct_child_classes = {
                c.get("class")
                for c in node.get("children", [])
                if c.get("kind") in ("mo", "mo-placeholder") and c.get("class")
            }
            class_child_sets[short].append(direct_child_classes)
        for child in node.get("children", []):
            walk(child, new_parent, class_parent_counter, class_params, class_lists, class_child_sets)
        return
    if kind == "param":
        name = node["label"]
        val = node.get("value")
        if parent_class:
            entry = class_params[parent_class][name]
            entry["count"] += 1
            if val:
                entry["values"][val] += 1
        return
    if kind == "list":
        name = node["label"]
        if parent_class:
            class_lists[parent_class].add(name)
        # still walk into items so we don't crash on nested structure, but
        # item-level sub-params aren't attributed to the outer class for v1
        return
    for child in node.get("children", []):
        walk(child, parent_class, class_parent_counter, class_params, class_lists, class_child_sets)


def load_official_rows() -> list[dict]:
    rows = []
    for fname in ("sbts18a_parameters.json", "lte18_parameters_fdd.json", "lte18_parameters_tdd.json"):
        path = EXTRACTED_DIR / fname
        if path.exists():
            rows.extend(json.loads(path.read_text()))
    return rows


def index_official_params(rows: list[dict]):
    """by_class_param: (class, name) -> row, for precise per-(class,param)
    lookups. by_class: class -> {name: row} for scalar params only (rows
    with Data Type == "Structure" are list/table containers, not settable
    values, and go in by_class_lists instead)."""
    by_class_param: dict[tuple[str, str], dict] = {}
    by_class: dict[str, dict[str, dict]] = defaultdict(dict)
    by_class_lists: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        cls = _s(row.get("MO Class")).rsplit("/", 1)[-1]
        name = row.get("Abbreviated Name")
        if not cls or not name:
            continue
        key = (cls, name)
        if key not in by_class_param:
            by_class_param[key] = row
        if row.get("Data Type") == "Structure":
            by_class_lists[cls].add(name)
        elif name not in by_class[cls]:
            by_class[cls][name] = row
    return by_class_param, by_class, by_class_lists


def load_official_classes() -> dict[str, dict]:
    """shortName -> {fullName, parentChain} across both dictionaries. Loaded
    lowest-priority first so SBTS18A (most current) wins on conflicts."""
    by_short: dict[str, dict] = {}
    for fname in ("lte18_mo_classes_tdd.json", "lte18_mo_classes_fdd.json", "sbts18a_mo_classes.json"):
        path = EXTRACTED_DIR / fname
        if path.exists():
            for row in json.loads(path.read_text()):
                by_short[row["shortName"]] = row
    return by_short


def main():
    params_kb = json.loads((DATA_DIR / "parameters.json").read_text())
    official_by_class_param, official_by_class, official_by_class_lists = index_official_params(load_official_rows())
    official_classes = load_official_classes()

    class_parent_counter = defaultdict(Counter)
    class_params = defaultdict(lambda: defaultdict(lambda: {"count": 0, "values": Counter()}))
    class_lists = defaultdict(set)
    class_child_sets = defaultdict(list)

    files = sorted(glob.glob(str(SCP_DIR / "*.xml")))
    for path in files:
        raw = Path(path).read_bytes()
        try:
            tree = parse_file(raw, Path(path).name)
        except Exception:
            continue
        for child in tree["children"]:
            walk(child, None, class_parent_counter, class_params, class_lists, class_child_sets)

    # A child class is "required in practice" only if it shows up under
    # EVERY observed instance of the parent class -- not merely common.
    # There's no official source for this at all (see the note in walk()),
    # so childSampleSize is carried alongside it: a class inferred from 1
    # instance is a much weaker signal than one inferred from 50, and the
    # frontend/README should treat it accordingly, not as settled fact.
    class_required_children: dict[str, list[str]] = {}
    class_child_sample_size: dict[str, int] = {}
    for cls, instance_sets in class_child_sets.items():
        class_child_sample_size[cls] = len(instance_sets)
        if not instance_sets:
            continue
        common = set.intersection(*instance_sets)
        if common:
            class_required_children[cls] = sorted(common)

    catalog = {}

    # --- Pass 1: classes actually observed in scp/ ---
    for cls, params in class_params.items():
        parent_counts = class_parent_counter.get(cls, Counter())
        observed_parent_list = [p for p, _ in parent_counts.most_common()]
        # Prefer the officially-documented parent as canonical when we have
        # one (verified against ref/extracted/*_mo_classes*.json), rather
        # than whichever parent happened to be most common in this corpus --
        # a handful of classes (ETHLK, IPSECC, PMTNL, TWAMP, and others tied
        # to older/legacy transport object placement) showed a mismatch on
        # cross-check. Every parent actually seen in scp/ is still kept as a
        # valid alternate so the "Add Object" picker doesn't reject real,
        # working file structures.
        official_parent_chain = official_classes.get(cls, {}).get("parentChain") or []
        official_parent = official_parent_chain[-1] if official_parent_chain else None
        if official_parent:
            direct_parent = official_parent
            all_parents = [official_parent] + [p for p in observed_parent_list if p != official_parent]
        else:
            direct_parent = observed_parent_list[0] if observed_parent_list else None
            all_parents = observed_parent_list

        param_entries = {}
        for name, info in params.items():
            kb_entry = params_kb.get(name, {})
            official = official_by_class_param.get((cls, name))
            examples = [v for v, _ in info["values"].most_common(MAX_EXAMPLES)]
            entry = {
                "dataType": kb_entry.get("dataType", "string"),
                "description": kb_entry.get("description", ""),
                "confidence": kb_entry.get("confidence", "heuristic"),
                "unit": kb_entry.get("unit"),
                "exampleValues": examples,
                "occurrences": info["count"],
                "observed": True,
            }
            if official:
                entry["officialRange"] = official.get("Range and step")
                entry["officialDefault"] = official.get("Default Value")
                entry["requiredOnCreation"] = official.get("Required on Creation")
                entry["trulyRequired"] = is_truly_required(official)
                entry["resolvedDefault"] = resolve_default_for_xml(
                    entry["dataType"], official.get("Default Value"), examples
                )
                entry["fullName"] = official.get("Full Name")
            param_entries[name] = entry

        # Widen with official-only scalar parameters never exercised by our
        # sample files, so "Add Object" can offer the complete known set.
        for name, official in official_by_class.get(cls, {}).items():
            if name not in param_entries:
                param_entries[name] = official_param_entry(official)

        lists = set(class_lists.get(cls, set())) | official_by_class_lists.get(cls, set())

        catalog[cls] = {
            "directParent": direct_parent,
            "observedParents": all_parents,
            "observedInCorpus": True,
            "officialFullName": official_classes.get(cls, {}).get("fullName"),
            "params": param_entries,
            "lists": sorted(lists),
            # Corpus heuristic, NOT an official Nokia fact (no dictionary or
            # schema in ref/ records MO-class cardinality at all) -- child
            # classes present under every single observed instance of this
            # class, so "+ Add Object" can cascade-create them too. See the
            # note in walk() above for why this is the only signal available.
            "requiredChildClasses": class_required_children.get(cls, []),
            "childSampleSize": class_child_sample_size.get(cls, 0),
        }

    # --- Pass 2: every other class either official dictionary defines,
    # never seen in scp/ at all, so the generator isn't limited to what your
    # sample files happened to include. ---
    for short, official_cls in official_classes.items():
        if short in catalog:
            continue
        parent_chain = official_cls.get("parentChain") or []
        param_entries = {
            name: official_param_entry(official)
            for name, official in official_by_class.get(short, {}).items()
        }
        catalog[short] = {
            "directParent": parent_chain[-1] if parent_chain else None,
            "observedParents": [],
            "observedInCorpus": False,
            "officialFullName": official_cls.get("fullName"),
            "params": param_entries,
            "lists": sorted(official_by_class_lists.get(short, set())),
            # Never observed in scp/ at all, so there's no corpus signal to
            # infer required children from.
            "requiredChildClasses": [],
            "childSampleSize": 0,
        }

    out_path = DATA_DIR / "class_catalog.json"
    out_path.write_text(json.dumps(catalog, indent=1, sort_keys=True))

    print(f"Classes cataloged: {len(catalog)}")
    observed_classes = sum(1 for c in catalog.values() if c["observedInCorpus"])
    print(f"  {observed_classes} observed in scp/, {len(catalog) - observed_classes} official-only")
    total_params = sum(len(c["params"]) for c in catalog.values())
    observed_params = sum(1 for c in catalog.values() for p in c["params"].values() if p["observed"])
    print(f"Total (class, param) scalar entries: {total_params} ({observed_params} observed, "
          f"{total_params - observed_params} official-only)")


if __name__ == "__main__":
    main()

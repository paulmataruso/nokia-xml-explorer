"""
Change a product code: sets the planned code of a radio (RMOD), baseband
(BBMOD), system module (SMOD) or antenna-line device (ALD).

Only the code changes. The review says what else usually differs for that
code in the corpus (ANTL or PHYANT antennas, link protocol, SFPs), because
a different module type often needs different objects around it; adding or
removing those is the hardware actions' job.

Refused: codes that aren't product codes, core-board codes (BBMOD_R
reports the core board inside a module as coreHwBoardProductCode; it is
not the module's code), and catalog codes of another kind of module.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, why
from .hardware import CLASS_KINDS, KIND, KIND_LABELS, NOKIA_CODE, base, corpus_view, modules

ID = "product-code"
TITLE = "Change a product code"
GROUP = "Hardware"
SUMMARY = "Set the planned code of a radio, baseband, system module or antenna-line device."
UI = "form"
KEYWORDS = "hardware module RMOD BBMOD SMOD ALD prodCodePlanned productCode"


def available(ctx: Context) -> Optional[str]:
    if not modules(ctx.site):
        return "This file has no radio, baseband, system module or antenna-line device."
    return None


def _name(code: str, products: dict, view: dict) -> Optional[str]:
    """The BTS's own name for the code (productName on the *_R objects,
    "ABIL AirScale Capacity") if a file has it, else the catalog's."""
    name = view["names"].get(code) or (products.get(code) or {}).get("name")
    return name if name != code else None


def _catalog_hint(entry: dict) -> str:
    hint = entry.get("description") or ""
    if len(entry.get("sources", [])) == 1:
        hint += (" · " if hint else "") + "one web source"
    return hint


def _module_details(mod: dict, products: dict, view: dict) -> list[str]:
    out = []
    if mod["detected"] and mod["detected"]["code"]:
        d = mod["detected"]
        out.append(f"The BTS reported {d['code']}" + (f" ({d['name']})" if d["name"] else "")
                   + (f", core board {d['coreBoard']}" if d["coreBoard"] else "") + ".")
    if mod["class"] == "RMOD":
        bits = []
        if mod["phyant"]:
            bits.append(f"{mod['phyant']} PHYANT")
        if mod["antl"]:
            bits.append(f"{mod['antl']} ANTL")
        if mod["links"]:
            bits.append(f"{mod['links']} link{'s' if mod['links'] != 1 else ''}"
                        + (f" ({', '.join(mod['protocols'])})" if mod["protocols"] else ""))
        if bits:
            out.append("Has " + ", ".join(bits) + ".")
        if mod["cells"]:
            out.append("Cells on it: " + ", ".join(mod["cells"]) + ".")
    elif mod["class"] == "BBMOD" and (mod["sfp"] or mod["config"]):
        out.append(f"{mod['sfp']} SFP" + (f", board config {mod['config']}" if mod["config"] else "") + ".")
    elif mod["class"] == "SMOD" and mod["eacIn"]:
        out.append(f"{mod['eacIn']} external alarm inputs.")
    return out


def _code_options(cls: str, products: dict, view: dict) -> list[dict]:
    seen: Counter = view["seen"].get(cls, Counter())
    out = []
    for code, n in seen.most_common():
        entry = products.get(code) or {}
        out.append({"value": code, "label": code, "name": _name(code, products, view),
                    "hint": (entry.get("description") or "") + (" · " if entry.get("description") else "")
                    + f"in {n} {cls}{'s' if n != 1 else ''} in your files",
                    "group": "In your files"})
    for code, entry in sorted(products.items(), key=lambda kv: (kv[1].get("name") or "", kv[0])):
        if code in seen or entry.get("kind") not in CLASS_KINDS.get(cls, ()):
            continue
        out.append({"value": code, "label": code, "name": entry.get("name"),
                    "hint": _catalog_hint(entry), "group": "Nokia catalog (public web sources)"})
    return out


def setup(ctx: Context) -> dict:
    products = ctx.kb.get("products") or {}
    view = corpus_view(ctx.corpus())
    mods = modules(ctx.site)
    targets = []
    for mod in mods:
        b = base(mod["code"])
        name = _name(b, products, view) if b else None
        targets.append({
            "value": mod["dn"],
            "label": f"{mod['label']} · {mod['code'] or 'no code'}" + (f" · {name}" if name else ""),
            "group": f"{KIND[mod['class']].capitalize()}s ({mod['class']})",
            "key": mod["class"],
            "details": _module_details(mod, products, view),
            "current": mod["code"],
        })
    return {
        "intro": "Sets the module's planned product code (prodCodePlanned, or productCode on an ALD). The BTS uses "
                 "it before commissioning; after that it uses the code it detects. The code is six digits and a "
                 "letter, optionally with a revision (474020A or 474020A.102).",
        "fields": [
            {"id": "target", "label": "Module", "type": "select", "options": targets,
             "default": targets[0]["value"] if len(targets) == 1 else None},
            {"id": "code", "label": "New product code", "type": "combo", "dependsOn": "target",
             "optionsByKey": {cls: _code_options(cls, products, view) for cls in {m["class"] for m in mods}},
             "placeholder": "474020A or 474020A.102"},
        ],
    }


def _consequences(mod: dict, code: str, view: dict) -> list[str]:
    usual = view["usual"].get((mod["class"], code))
    cls = mod["class"]
    if usual is None:
        return [f"No {cls} in your files uses {code}, so there is nothing to compare its antennas and links with."]
    out = []
    n = f"{usual['count']} {cls}{'s' if usual['count'] != 1 else ''} with {code} in your files"
    if cls == "RMOD":
        if usual["phyant"] and not mod["phyant"]:
            out.append(f"The {n} have a PHYANT (one integrated antenna array) instead of ANTL objects; this radio has "
                       f"{mod['antl']} ANTL. Its antenna objects and channels need changing to match.")
        elif mod["phyant"] and not usual["phyant"]:
            out.append(f"The {n} have {usual['antl']} ANTL objects instead of a PHYANT. This radio's antenna objects "
                       "and channels need changing to match.")
        elif usual["antl"] != mod["antl"]:
            out.append(f"The {n} have {usual['antl']} ANTL; this radio has {mod['antl']}.")
        # "They" only after a sentence that names them.
        if usual["protocols"] and mod["protocols"] and set(usual["protocols"]) != set(mod["protocols"]):
            out.append(f"{'Their links' if out else f'The links of the {n}'} use {', '.join(usual['protocols'])}; "
                       f"this radio's links use {', '.join(mod['protocols'])}.")
        if bool(usual["rsl"]) != bool(mod["rsl"]):
            out.append(f"{'They' if out else f'The {n}'} {'have' if usual['rsl'] else 'have no'} RSL; this radio "
                       f"{'has one' if mod['rsl'] else 'has none'}.")
        if mod["cells"] and out:
            out.append(f"Cells on this radio ({', '.join(mod['cells'])}) may need radio-dependent settings changed "
                       "too, such as pMax and the MIMO mode.")
    elif cls == "BBMOD":
        if usual["sfp"] != mod["sfp"] or usual["config"] != mod["config"]:
            out.append(f"The {n} have {usual['sfp']} SFP" + (f" and board config {usual['config']}" if usual["config"] else "")
                       + f"; this one has {mod['sfp']}" + (f" and {mod['config']}" if mod["config"] else "") + ".")
    elif cls == "SMOD":
        if usual["eacIn"] != mod["eacIn"]:
            out.append(f"The {n} have {usual['eacIn']} external alarm inputs (EAC_IN); this one has {mod['eacIn']}.")
    if out and usual["majority"] < usual["count"]:
        out.append(f"(That is the most common layout, {usual['majority']} of {usual['count']}.)")
    return out


def _platform_notes(mod: dict, code: str, entry: Optional[dict], view: dict) -> list[str]:
    """A Flexi Zone small cell and a macro BTS take different files, so a
    code the corpus only ever has on the other platform is worth a warning;
    so is a catalog item the catalog doesn't classify."""
    out = []
    cls = mod["class"]
    plats = view["platforms"].get((cls, code))
    if plats and mod["fzm"] not in plats:
        there, here = ("macro (AirScale or Flexi Multiradio)", "Flexi Zone") if mod["fzm"] else \
            ("Flexi Zone", "macro (AirScale or Flexi Multiradio)")
        out.append(f"In your files {code} is only ever on {there} equipment, and this {KIND[cls]} is {here}. "
                   "The two take different files (release and object layout), so this usually needs another "
                   "file rather than another code.")
    if entry and entry.get("kind") not in KIND_LABELS and code not in view["seen"].get(cls, {}):
        out.append(f"The catalog doesn't say what kind of item {code} is ({entry.get('name')}"
                   + (f": {entry['description']}" if entry.get("description") else "")
                   + f"). Check that it is a {KIND[cls]}.")
    return out


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    products = ctx.kb.get("products") or {}
    view = corpus_view(ctx.corpus())
    mod = next((m for m in modules(ctx.site) if m["dn"] == inputs.get("target")), None)
    if mod is None:
        raise PlanError(["Pick a module."])
    code = (inputs.get("code") or "").strip()
    if not code:
        raise PlanError(["Enter a product code."])
    cls, b = mod["class"], base(code)
    problems = []
    if code == mod["code"]:
        problems.append(f"{mod['label']} already has {code}.")
    if cls != "ALD" and not NOKIA_CODE.match(code) and b not in view["seen"].get(cls, {}):
        problems.append(f"{code} doesn't look like a Nokia product code (six digits and a letter, such as 474020A, "
                        f"optionally with a revision such as .102), and no {cls} in your files uses it.")
    module = view["coreBoards"].get(b)
    if module or (products.get(b) or {}).get("kind") == "core-board":
        mname = _name(module, products, view) if module else None
        problems.append(f"{b} is the code of a core board inside a module, which the BTS reports as "
                        "coreHwBoardProductCode. A module's planned code is the module's own code"
                        + (f": {module}" + (f" ({mname})" if mname else "") + " for the module this board sits in."
                           if module else "."))
    entry = products.get(b)
    seen_here = b in view["seen"].get(cls, {})
    # A file that already uses the code on this class outranks the web
    # catalog's kind; "other" is unclassified, so it never refuses.
    if entry and entry.get("kind") in KIND_LABELS and entry["kind"] not in CLASS_KINDS.get(cls, ()) and not seen_here:
        problems.append(f"{b} is {entry.get('name') or 'a module'}, a {KIND_LABELS[entry['kind']]} in the catalog; "
                        f"{cls} takes a {KIND[cls]} code.")
    elif not entry and not seen_here:
        elsewhere = sorted(c for c, seen in view["seen"].items() if c != cls and b in seen)
        if elsewhere:
            name = _name(b, products, view)
            problems.append(f"{b}{f' ({name})' if name else ''} is a {' and '.join(KIND[c] for c in elsewhere)} code "
                            f"in your files, never a {KIND[cls]} one.")
    if problems:
        raise PlanError(problems)

    name = _name(b, products, view)
    doc = Doc(ctx.raw)
    doc.set(mod["dn"], mod["param"], code, why(
        "hardware", f"The {KIND[cls]}'s planned code" + (f": {name}." if name else ". It isn't in the catalog."),
        "choice"))
    notes = _platform_notes(mod, b, entry, view) + _consequences(mod, b, view)
    d = mod["detected"]
    if d and d["code"] and base(d["code"]) != b:
        notes.append(f"The BTS reported {d['code']}" + (f" ({d['name']})" if d["name"] else "") + " for this module. "
                     "It uses the planned code only before commissioning, then the code it detects.")
    return finish(ctx, doc, {
        "label": f"Product code of {mod['label']}: {mod['code'] or 'none'} -> {code}",
        "summary": f"{mod['label']} becomes {code}" + (f" ({name})" if name else ""),
        "notes": notes,
        "confirm": [f"The module installed at the site is {name + ' ' if name else ''}{b}."],
        "focus": f"{mod['dn']}::p::{mod['param']}",
    })

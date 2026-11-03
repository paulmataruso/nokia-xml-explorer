"""
What the cell actions (nr_cell.py, lte_cell.py) share: a new cell is a copy
of a sibling cell of the same site, with its own identity and radio.

A cell is more than its LNCEL or NRCELL (PROJECT_STATE §9.9, "Companions"):
- the cell and its children: the per-cell objects every sibling has, which
  come along, and the per-relation ones, which don't (a new cell has no
  neighbours yet; ANR learns them, or the neighbour actions plan them);
- its channel mapping, LCELL-{lcrId} or LCELNR-{lcrId} under CELLMAPPING,
  whose CHANNELs name the radio's antennas (ANTL, or PHYANT on a
  massive-MIMO radio);
- for NR, its own NRCELLGRP, listed in NRDU.refNrCellGroup.

Moving the copy to another radio moves every antenna it names to the same
antenna of that radio (RMOD-1/ANTL-2 to RMOD-3/ANTL-2). A radio without
one of them, but with as many antennas, takes them in order (with a note);
one with fewer is refused.

Suggestions (identity comes from the inputs; these only propose):
- lcrId: production numbers cells sector x 100 + carrier (111, 211, 311 on
  the first carrier), so the next free sector on the template's carrier;
  else the lowest free lcrId of the site (lcrIds are unique across LTE and
  NR on one MRBTS).
- PCI: the next free one after the site's cells on the same carrier.
- PRACH root: spaced from the site's cells on the carrier by their smallest
  spacing, within 0-837 (or 0-137 where every cell uses the short range).
"""
from __future__ import annotations

import re
from typing import Optional

from .doc import Doc, label, natural, parent_dn
from .hardware import modules
from .links import Site

ANTENNA = re.compile(r"^(.*?/RMOD-[^/]+)/(ANTL|PHYANT)-[^/]+$")
MAPPING = {"LNCEL": "LCELL", "NRCELL": "LCELNR"}


def root_of(dn: str) -> str:
    return dn.split("/", 1)[0]


def cell_mapping(site: Site, cell: dict) -> Optional[dict]:
    """The cell's LCELL or LCELNR (named by its lcrId), if the file has one."""
    want = f"{MAPPING[cell['cls']]}-{cell['p'].get('lcrId')}"
    root = root_of(cell["dn"])
    return next((m for m in site.of(MAPPING[cell["cls"]], root) if label(m["dn"]) == want), None)


def antennas(site: Site, mapping: dict) -> list[str]:
    """The antennas its CHANNELs name, in order."""
    out = []
    for ch in site.of("CHANNEL", mapping["dn"]):
        a = ch["p"].get("resourceDN") or ch["p"].get("antlDN")
        if a and a not in out:
            out.append(a)
    return out


def radios(site: Site, mapping: Optional[dict]) -> list[str]:
    out = []
    for a in antennas(site, mapping) if mapping else []:
        m = ANTENNA.match(a)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def lcr_ids(site: Site, root: str) -> set[int]:
    return {int(m["p"]["lcrId"]) for cls in ("LNCEL", "NRCELL") for m in site.of(cls, root)
            if (m["p"].get("lcrId") or "").isdigit()}


def suggest_lcr(site: Site, root: str, template: Optional[str], hi: int) -> Optional[str]:
    used = lcr_ids(site, root)
    t = int(template) if (template or "").isdigit() else None
    if t is not None and t >= 100:
        for sector in range(1, 10):
            v = sector * 100 + t % 100
            if v not in used and v <= hi:
                return str(v)
    return next((str(v) for v in range(0, hi + 1) if v not in used), None)


def suggest_pci(used: list[int], hi: int) -> Optional[str]:
    start = max(used) + 1 if used else 0
    for v in [*range(start, hi + 1), *range(0, start)]:
        if v not in used:
            return str(v)
    return None


def root_limit(used: list[int]) -> int:
    return 837 if not used or max(used) > 137 else 137


def suggest_root(used: list[int]) -> Optional[str]:
    """A PRACH root sequence index as far from the others as they are from
    each other."""
    if len(used) < 2:
        return None
    hi = root_limit(used)
    s = sorted(set(used))
    gap = min(b - a for a, b in zip(s, s[1:])) if len(s) > 1 else 0
    if gap <= 0:
        return None
    for v in [max(s) + gap, *range(0, hi + 1)]:
        if 0 <= v <= hi and all(abs(v - u) >= gap for u in s):
            return str(v)
    return None


def radio_options(site: Site, describe) -> list[dict]:
    """Every radio, for the radio select: its code and name, antennas and
    the cells it carries now. `describe(code)` names a code."""
    out = []
    for mod in modules(site):
        if mod["class"] != "RMOD":
            continue
        name = describe(mod["code"]) if mod["code"] else None
        bits = [f"{mod['phyant']} PHYANT" if mod["phyant"] else f"{mod['antl']} ANTL"]
        out.append({"value": mod["dn"], "key": mod["dn"],
                    "label": f"{mod['label']} · {mod['code'] or 'no code'}" + (f" {name}" if name else "")
                             + f" · {', '.join(bits)}",
                    "group": "Radios with cells" if mod["cells"] else "Radios with no cell",
                    "details": [f"Cells on it now: {', '.join(mod['cells'])}." if mod["cells"] else "No cell uses it yet."],
                    "cells": mod["cells"], "code": mod["code"]})
    return out


def move_antennas(site: Site, mapping: dict, radio: Optional[str]) -> tuple[dict[str, str], Optional[str], list[str]]:
    """The rewrite moving the mapping's antennas to `radio`, why it can't
    (or None), and how antennas were renumbered.

    Each antenna moves to the same antenna of the radio (RMOD-1/ANTL-2 to
    RMOD-3/ANTL-2). Where the radio lacks one but has as many antennas of
    the kind as the template uses, they map in order instead (ANTL-3, ANTL-4
    to ANTL-1, ANTL-2), and the renumbering is returned for a note."""
    from_radios = radios(site, mapping)
    if not radio or not from_radios or from_radios == [radio]:
        return {}, None, []
    if len(from_radios) > 1:
        return {}, (f"The template's channels use {len(from_radios)} radios ({', '.join(label(r) for r in from_radios)}): "
                    "keep the template's radio."), []
    old = from_radios[0]
    used = antennas(site, mapping)
    if all(radio + a[len(old):] in site.by_dn for a in used):
        return {old: radio}, None, []
    rewrite, moved = {}, []
    for kind in ("ANTL", "PHYANT"):
        mine = sorted((a for a in used if label(a).startswith(kind + "-")), key=natural)
        theirs = sorted((m["dn"] for m in site.child(radio, kind)), key=natural)
        if len(theirs) < len(mine):
            return {}, (f"{label(radio)} has {len(theirs)} {kind}, and the template's channels use {len(mine)} "
                        f"({', '.join(label(a) for a in mine)}): pick a template with as many antennas, or another "
                        "radio."), []
        for a, b in zip(mine, theirs):
            rewrite[a] = b
            if label(a) != label(b):
                moved.append(f"{label(a)} to {label(b)}")
    return {old: radio, **rewrite}, None, moved


def clone_mapping(doc: Doc, site: Site, mapping: dict, new_lcr: str, rewrite: dict, w: dict) -> str:
    """The template's channel mapping as {LCELL,LCELNR}-{new lcrId}."""
    dst = f"{parent_dn(mapping['dn'])}/{label(mapping['dn']).rsplit('-', 1)[0]}-{new_lcr}"
    doc.clone(mapping["dn"], dst, w, rewrite=rewrite)
    return dst


def free_instance(doc: Doc, parent: str, cls: str, prefer: str, start: int = 1) -> str:
    if not doc.exists(f"{parent}/{cls}-{prefer}"):
        return prefer
    return doc.next_free(parent, cls, start)

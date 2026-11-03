"""
Add a 5G cell to a gNB: a copy of one of its cells (the template), on a
radio of the site, with its own lcrId, name, PCI and PRACH root.

What a production NR cell is (38 objects on the 25R2 gNBs, all 1:1):
NRCELL with its NRDLMUMIMO, NRPLMNSET_NSA/_SA, NRREDRT, NRRIM_PROFILE and
NRULMUMIMO; its own NRCELLGRP (nrCellList = the cell), which
NRDU.refNrCellGroup lists; LCELNR-{lcrId} under CELLMAPPING with its
CHANNELGROUPs and CHANNELs on the radio's antennas. All of it is copied;
neighbour relations and CBRS registration aren't (cells.py).

Per cell, only cellName, physCellId, prachRootSequenceIndex and lcrId vary
over 118 production cells; nrCellIdentity, where a file writes it, follows
from the gNB id and lcrId (sites.nci). mMimoAntArrayMode,
numberOfRxBeamforming, numberOfRxPucch and pMax follow the radio: on a
radio of another product code they take the values the files' cells on
that code have, else the template's, with a note.

The new NRCELL is instance lcrId (156 of 167 cells), its NRCELLGRP too, as
production numbers them; the next free id where that is taken.
Refused: an lcrId the site uses, or one that doesn't fit the NR cell
identity (36 - gNbIdLength bits); a PCI or PRACH root another cell on the
same carrier has; a radio that already carries a cell on the same carrier;
a radio with fewer antennas than the template's channels use.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from . import Context, PlanError, finish
from .cells import (clone_mapping, free_instance, lcr_ids, move_antennas, radio_options, radios, root_limit,
                    suggest_lcr, suggest_pci, suggest_root, cell_mapping)
from .doc import Doc, instance, label, why
from .hardware import RADIO_PARAMS, base, corpus_view
from .neighbours import number
from .product_code import _name
from .sites import gscn_to_arfcn, nci, nr_cell

ID = "nr-cell"
TITLE = "Add a 5G cell"
GROUP = "Cells"
SUMMARY = "A new NR cell on a radio of the site, copied from one of the gNB's cells, with its cell group and channels."
UI = "form"
KEYWORDS = "5G NR cell NRCELL sector carrier add cell NRCELLGRP LCELNR channel radio PCI lcrId"

SKIP = frozenset({"NRREL", "NRRELE", "NRCBSDCELL"})


def _cells(ctx: Context) -> list[tuple[dict, dict, dict]]:
    """(gNB, cell, its channel mapping) for every cell that can be copied."""
    out = []
    for gnb in ctx.site.of("NRBTS"):
        for cell in ctx.site.child(gnb["dn"], "NRCELL"):
            mapping = cell_mapping(ctx.site, cell)
            if mapping and radios(ctx.site, mapping):
                out.append((gnb, cell, mapping))
    return out


def available(ctx: Context) -> Optional[str]:
    if _cells(ctx):
        return None
    if ctx.site.of("NRCELL"):
        return "No NR cell here has a channel mapping (LCELNR) on a radio to copy."
    return "This file has no 5G cell to copy. Add the first one in the WebUI or from a commissioning file."


def _carrier(site, gnb, cell) -> dict:
    return nr_cell(site, gnb, cell)


def _same_carrier(site, gnb, cell) -> list[dict]:
    want = _carrier(site, gnb, cell)["arfcn"]
    return [c for c in site.child(gnb["dn"], "NRCELL") if _carrier(site, gnb, c)["arfcn"] == want]


def _name_suggestion(cell: dict, new_lcr: Optional[str]) -> Optional[str]:
    """Production names a cell after its sector: "<site>_10n411" for lcrId
    111. The template's name with its sector digit moved, where it follows
    that pattern."""
    name, old = cell["p"].get("cellName") or "", cell["p"].get("lcrId") or ""
    if not (new_lcr and old.isdigit() and new_lcr.isdigit() and int(old) >= 100 and int(new_lcr) >= 100):
        return None
    marker = f"_{int(old) // 100}0"
    if name.count(marker) != 1:
        return None
    return name.replace(marker, f"_{int(new_lcr) // 100}0")


def setup(ctx: Context) -> dict:
    site = ctx.site
    products = ctx.kb.get("products") or {}
    view = corpus_view(ctx.corpus())
    describe = lambda code: _name(base(code), products, view)
    templates, radio_by, radio_default, lcr_by, name_by, pci_by, root_by = [], {}, {}, {}, {}, {}, {}
    for gnb, cell, mapping in _cells(ctx):
        x = _carrier(site, gnb, cell)
        root = cell["dn"].split("/", 1)[0]
        dn = cell["dn"]
        here = radios(site, mapping)
        templates.append({"value": dn, "key": dn, "group": f"gNB {instance(gnb['dn'])}",
                          "label": f"Like {label(dn)} · {x['name'] or 'no name'} · NR-ARFCN {x['arfcn'] or '?'}"
                                   + (f" · n{x['band']}" if x["band"] else ""),
                          "details": [f"On {', '.join(label(r) for r in here)}; PCI {x['pci']}, lcrId {x['lcrId']}. "
                                      "The new cell takes its carrier and settings."]})
        same = _same_carrier(site, gnb, cell)
        opts = [{k: v for k, v in r.items() if k not in ("cells", "code")} for r in radio_options(site, describe)]
        radio_by[dn] = opts
        radio_default[dn] = next((o["value"] for o in opts if o["group"] == "Radios with no cell"), here[0])
        lcr = suggest_lcr(site, root, x["lcrId"], 16383)
        if lcr:
            lcr_by[dn] = lcr
            name = _name_suggestion(cell, lcr)
            if name:
                name_by[dn] = name
        pcis = [int(c["p"]["physCellId"]) for c in same if (c["p"].get("physCellId") or "").isdigit()]
        roots = [int(c["p"]["prachRootSequenceIndex"]) for c in same
                 if (c["p"].get("prachRootSequenceIndex") or "").isdigit()]
        if suggest_pci(pcis, 1007):
            pci_by[dn] = suggest_pci(pcis, 1007)
        if suggest_root(roots):
            root_by[dn] = suggest_root(roots)
    return {
        "intro": "Copies one of the gNB's cells, with its cell group and channel mapping, onto a radio of the site. "
                 "Only the cell's identity is new: its lcrId, name, PCI and PRACH root.",
        "fields": [
            {"id": "template", "label": "Copy the settings of", "type": "select", "options": templates,
             "default": templates[0]["value"] if len(templates) == 1 else None},
            {"id": "radio", "label": "Radio", "type": "select", "dependsOn": "template", "optionsByKey": radio_by,
             "defaultByKey": radio_default},
            {"id": "arfcn", "label": "NR-ARFCN (empty: the template's carrier)", "type": "text", "optional": True,
             "placeholder": "520000",
             "hint": "Another carrier, for a second cell on a radio that has one. A TDD cell only; the bandwidth stays "
                     "the template's."},
            {"id": "gscn", "label": "SSB GSCN (with a new NR-ARFCN)", "type": "text", "optional": True,
             "placeholder": "6339",
             "hint": "Where the new carrier's SSB is (gscnOrSsPbchArfcn), inside the channel."},
            {"id": "lcrId", "label": "lcrId", "type": "text", "dependsOn": "template", "defaultByKey": lcr_by,
             "hint": "Unique across the site's LTE and NR cells. Production numbers them sector × 100 + carrier."},
            {"id": "cellName", "label": "Cell name", "type": "text", "dependsOn": "template", "defaultByKey": name_by},
            {"id": "pci", "label": "PCI (physCellId)", "type": "text", "dependsOn": "template", "defaultByKey": pci_by,
             "hint": "0 to 1007; not one another cell on this carrier uses."},
            {"id": "root", "label": "PRACH root sequence index", "type": "text", "dependsOn": "template",
             "defaultByKey": root_by,
             "hint": "Spaced like the site's other cells on the carrier, so their preamble ranges don't overlap."},
        ],
    }


def _radio_values(ctx: Context, code: Optional[str]) -> dict[str, str]:
    """The radio-dependent NRCELL values most cells on this radio code have."""
    seen: dict[str, Counter] = {}
    for f in ctx.corpus():
        for c in (f.get("hardware") or {}).get("cellRadios", []):
            if base(c["code"]) == base(code):
                for k, v in c["p"].items():
                    seen.setdefault(k, Counter())[v] += 1
    return {k: c.most_common(1)[0][0] for k, c in seen.items()}


def _mhz(arfcn: int) -> float:
    """An NR-ARFCN as MHz (TS 38.104 Table 5.4.2.1-1)."""
    if arfcn < 600000:
        return arfcn * 0.005
    if arfcn < 2016667:
        return 3000 + (arfcn - 600000) * 0.015
    return 24250.08 + (arfcn - 2016667) * 0.06


def _ssb_outside(arfcn: int, gscn: int, bw: Optional[str]) -> Optional[str]:
    width = int("".join(ch for ch in bw or "" if ch.isdigit()) or 0)
    if not width:
        return None
    centre, ssb = _mhz(arfcn), _mhz(gscn_to_arfcn(gscn))
    if abs(ssb - centre) > width / 2:
        return (f"The SSB at GSCN {gscn} ({ssb:.2f} MHz) is outside the {width} MHz channel at NR-ARFCN {arfcn} "
                f"({centre - width / 2:.2f} to {centre + width / 2:.2f} MHz).")
    return None


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    found = next(((g, c, m) for g, c, m in _cells(ctx) if c["dn"] == inputs.get("template")), None)
    if not found:
        raise PlanError(["Pick the cell to copy."])
    gnb, cell, mapping = found
    root = cell["dn"].split("/", 1)[0]
    radio = inputs.get("radio") or ""
    if site.by_dn.get(radio, {}).get("cls") != "RMOD" or radio.split("/", 1)[0] != root:
        raise PlanError(["Pick the radio the new cell transmits on."])
    problems: list[str] = []
    length = gnb["p"].get("gNbIdLength")
    hi = (1 << (36 - int(length))) - 1 if (length or "").isdigit() and 22 <= int(length) <= 32 else 16383
    lcr = number(inputs.get("lcrId"), 0, hi, "The lcrId", problems)
    pci = number(inputs.get("pci"), 0, 1007, "The PCI", problems)
    x = _carrier(site, gnb, cell)
    carrier = None
    if (inputs.get("arfcn") or "").strip() or (inputs.get("gscn") or "").strip():
        if site.child(cell["dn"], "NRCELL_FDD"):
            problems.append("The template is an FDD cell: its carrier is in NRCELL_FDD, which this doesn't change. "
                            "Leave the NR-ARFCN empty.")
        a = number(inputs.get("arfcn"), 0, 3279165, "The NR-ARFCN", problems)
        g = number(inputs.get("gscn"), 2, 26639, "The SSB GSCN", problems)
        if a and g:
            carrier = (a, g)
            problem = _ssb_outside(int(a), int(g), cell["p"].get("chBw"))
            if problem:
                problems.append(problem)
    target_arfcn = carrier[0] if carrier else x["arfcn"]
    same = [c for c in site.child(gnb["dn"], "NRCELL") if _carrier(site, gnb, c)["arfcn"] == target_arfcn]
    used_roots = [int(c["p"]["prachRootSequenceIndex"]) for c in same
                  if (c["p"].get("prachRootSequenceIndex") or "").isdigit()]
    prach = number(inputs.get("root"), 0, root_limit(used_roots), "The PRACH root sequence index", problems)
    name = (inputs.get("cellName") or "").strip()
    if not name:
        problems.append("Enter the cell name.")
    if problems:
        raise PlanError(problems)
    if int(lcr) in lcr_ids(site, root):
        problems.append(f"lcrId {lcr} is taken: lcrIds are unique across the site's LTE and NR cells.")
    for c in same:
        if c["p"].get("physCellId") == pci:
            problems.append(f"{label(c['dn'])} has PCI {pci} on the same carrier (NR-ARFCN {target_arfcn}).")
        if c["p"].get("prachRootSequenceIndex") == prach:
            problems.append(f"{label(c['dn'])} has PRACH root {prach} on the same carrier.")
        if radio in radios(site, cell_mapping(site, c) or {}):
            problems.append(f"{label(radio)} already carries {label(c['dn'])} on NR-ARFCN {target_arfcn}: a second "
                            "cell on the same radio needs another carrier (enter its NR-ARFCN and SSB GSCN), or "
                            "add a radio first (Add a radio).")
    lcelnr = f"{mapping['dn'].rsplit('/', 1)[0]}/LCELNR-{lcr}"
    if lcr and lcelnr in site.by_dn:
        problems.append(f"{label(lcelnr)} exists already, left over from a deleted cell: remove it first.")
    rewrite, unfit, renumbered = move_antennas(site, mapping, radio)
    if unfit:
        problems.append(unfit)
    if problems:
        raise PlanError(problems)

    doc = Doc(ctx.raw)
    notes, confirm = [], []
    if renumbered:
        notes.append(f"{label(radio)} lacks the template's antenna numbers, so its channels use {', '.join(renumbered)}: "
                     "check the ports the cell is cabled to.")
    w = why("nr-cell", f"A new cell like {label(cell['dn'])}: its carrier, profiles, PLMN sets and tracking area, with "
                       "its own identity.", "donor")
    inst = free_instance(doc, gnb["dn"], "NRCELL", lcr)
    dst = f"{gnb['dn']}/NRCELL-{inst}"
    over = {"lcrId": lcr, "cellName": name, "physCellId": pci, "prachRootSequenceIndex": prach}
    if carrier:
        over.update({"nrarfcn": carrier[0], "gscnOrSsPbchArfcn": carrier[1]})
        if cell["p"].get("arfcnSsbPbch") is not None:
            over["arfcnSsbPbch"] = str(gscn_to_arfcn(int(carrier[1])))
        notes.append(f"On NR-ARFCN {carrier[0]} with its SSB at GSCN {carrier[1]}; the band (n{x['band']}), "
                     f"bandwidth ({cell['p'].get('chBw')}) and SSB spacing stay the template's.")
    if cell["p"].get("nrCellIdentity") is not None:
        identity = nci(instance(gnb["dn"]), length, lcr)
        if identity:
            over["nrCellIdentity"] = identity
    codes = {r: base(site.by_dn[r]["p"].get("prodCodePlanned")) for r in [*radios(site, mapping), radio]}
    old_code, new_code = codes[radios(site, mapping)[0]], codes[radio]
    if new_code and old_code and new_code != old_code:
        values = _radio_values(ctx, new_code)
        changed = {k: v for k, v in values.items() if k in RADIO_PARAMS and cell["p"].get(k) != v}
        over.update(changed)
        kept = [k for k in RADIO_PARAMS if k in cell["p"] and k not in values]
        if changed:
            notes.append(f"{label(radio)} is a {new_code}, the template's radio a {old_code}: "
                         + ", ".join(f"{k} {v}" for k, v in sorted(changed.items()))
                         + f", as cells on {new_code} radios have in the files.")
        if kept:
            notes.append(f"No file has a cell on a {new_code} radio, so {', '.join(kept)} stay as on the template "
                         f"({old_code}): check them for this radio.")
    skipped = [label(d) for d in doc.subtree(cell["dn"]) if doc.cls(d) in SKIP]
    # The rewrite also moves frRefList, which names the cell's radio.
    doc.clone(cell["dn"], dst, w, rewrite=rewrite, overrides={"": over}, skip=SKIP)
    if skipped:
        notes.append(f"Not copied: {', '.join(skipped[:6])}" + (" and more" if len(skipped) > 6 else "")
                     + ". Relations are learned by ANR or planned with the neighbour actions; a CBRS cell registers "
                       "with its own id.")
    group = next((g for g in site.child(gnb["dn"], "NRCELLGRP") if instance(cell["dn"]) in g["simple"].get("nrCellList", [])),
                 None)
    if group:
        g_inst = free_instance(doc, gnb["dn"], "NRCELLGRP", inst)
        g_dst = f"{gnb['dn']}/NRCELLGRP-{g_inst}"
        doc.clone(group["dn"], g_dst, why("nr-cell", f"The new cell's own cell group, like {label(group['dn'])}: one "
                                                     "group per cell, as production.", "donor"))
        doc.set_values(g_dst, "nrCellList", [inst], why("nr-cell", "The group holds the new cell.", "files"))
        for du in site.child(gnb["dn"], "NRDU"):
            if instance(group["dn"]) in du["simple"].get("refNrCellGroup", []):
                doc.add_value(du["dn"], "refNrCellGroup", g_inst,
                              why("nr-cell", f"{label(du['dn'])} serves the new cell group, as it serves "
                                             f"{label(group['dn'])}.", "files"))
    clone_mapping(doc, site, mapping, lcr, rewrite,
                  why("nr-cell", f"The new cell's channels, like {label(mapping['dn'])}'s"
                      + (f", moved to {label(radio)}'s antennas" if rewrite else "") + ".", "donor"))
    others = [label(c["dn"]) for c in site.child(gnb["dn"], "NRCELL")
              if radio in radios(site, cell_mapping(site, c) or {})]
    if others:
        confirm.append(f"{label(radio)} can carry another carrier: it already transmits {', '.join(others)}.")
    if others and site.child(radio, "PHYANT"):
        notes.append("No file has two cells on one massive-MIMO radio: check the radio supports it.")
    confirm.append(f"{label(radio)} covers the band"
                   + (f" (n{x['band']}, NR-ARFCN {target_arfcn})" if x["band"] else "") + ", and the baseband has "
                   "capacity for another cell.")
    notes.append("Neighbours aren't copied: ANR learns them, or plan them with the neighbour actions. An LTE eNB that "
                 "anchors EN-DC learns the cell from UE measurements, or add it with the EN-DC gNB action.")
    return finish(ctx, doc, {
        "label": f"NR cell {name} ({label(dst)})",
        "summary": f"{label(dst)} · {name} · lcrId {lcr} · PCI {pci} on {label(radio)}",
        "notes": notes,
        "confirm": confirm,
        "focus": dst,
    })

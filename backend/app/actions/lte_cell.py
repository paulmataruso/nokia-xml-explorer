"""
Add an LTE cell to an eNB: a copy of one of its cells (the template), on a
radio of the site, with its own lcrId, name, PCI and PRACH root, and
optionally relations both ways with the eNB's other cells.

What a production LTE cell is (17 objects, PROJECT_STATE §9.9): LNCEL_FDD
or _TDD, APUCCH_FDD, BBPOOLALLOC, DRX, SDRX, SIB, GFIM/GNFL, LNHOG, LNHOW,
NRFIM, UFFIM, REDRT, the IRFIM/LNHOIF of the carriers it measures, and
LCELL-{lcrId} with its CHANNELGROUP and CHANNELs. All of it is copied;
neighbour relations, CA (CAREL, CAPR), CBRS registration (CBSDCEL) and
traces aren't.

Per cell, lcrId, phyCellId, cellName and the LNCEL_FDD/_TDD rootSeqIndex
vary; eutraCelId, where written, is the eNB id × 256 + lcrId (its
dictionary: the 20 leftmost bits are the eNB id, the 8 rightmost the local
cell id). The carrier can change: EARFCN (FDD: the UL EARFCN moves by the
same step, which keeps the band's duplex spacing).

Relations both ways with picked own cells: LNREL as the neighbour action
writes them (handover allowed, removeAllowed false). An own cell on
another carrier gets an IRFIM and LNHOIF for the new cell's carrier where
it lacks one (the neighbour action's code), and the new cell keeps the
template's IRFIMs, minus the one for its own carrier.

Refused: an lcrId the site uses (0-255), a PCI (0-503) or root another cell
of the eNB has on the same EARFCN, a radio already carrying a cell on the
same EARFCN, a radio with fewer antennas than the template's channels use.
"""
from __future__ import annotations

from typing import Optional

from . import Context, PlanError, finish
from .cells import (cell_mapping, clone_mapping, free_instance, lcr_ids, move_antennas, radio_options, radios,
                    root_limit, suggest_lcr, suggest_pci, suggest_root)
from .doc import Doc, instance, label, why
from .hardware import base, corpus_view
from .neighbour_enb import _Plan as _NeighbourPlan
from .neighbours import number
from .product_code import _name
from .sites import NRB, _plmn, lte_cell

ID = "lte-cell"
TITLE = "Add an LTE cell"
GROUP = "Cells"
SUMMARY = "A new LTE cell on a radio of the site, copied from one of the eNB's cells, with its channels and relations."
UI = "form"
KEYWORDS = "LTE cell LNCEL sector carrier add cell LCELL channel radio PCI lcrId EARFCN"

SKIP = frozenset({"LNREL", "LNRELG", "LNRELW", "LNRELX", "LNRELGNBCELL", "LNRELNRCELL", "CAREL", "CAPR", "CAIMLBS",
                  "CBSDCEL", "MFIRECEL", "MTRACE"})
CARRIERS = ("IRFIM", "LNHOIF")
LNREL_RANGE = 388


def _cells(ctx: Context) -> list[tuple[dict, dict, dict]]:
    out = []
    for enb in ctx.site.of("LNBTS"):
        for cell in ctx.site.child(enb["dn"], "LNCEL"):
            mapping = cell_mapping(ctx.site, cell)
            if mapping and radios(ctx.site, mapping) and lte_cell(ctx.site, cell)["earfcn"]:
                out.append((enb, cell, mapping))
    return out


def available(ctx: Context) -> Optional[str]:
    if _cells(ctx):
        return None
    if ctx.site.of("LNCEL"):
        return "No LTE cell here has a channel mapping (LCELL) on a radio to copy."
    return "This file has no LTE cell to copy."


def _sub(site, cell) -> Optional[dict]:
    return next((m for cls in ("LNCEL_FDD", "LNCEL_TDD") for m in site.child(cell["dn"], cls)), None)


def _name_suggestion(cell: dict, old_lcr: Optional[str], new_lcr: Optional[str]) -> Optional[str]:
    """The template's name with its lcrId swapped, where the name ends in it
    ("SITE_B66_1" for lcrId 1)."""
    name = cell["p"].get("cellName") or ""
    if old_lcr and new_lcr and name.endswith(old_lcr) and not name[: -len(old_lcr)][-1:].isdigit():
        return name[: -len(old_lcr)] + new_lcr
    return None


def setup(ctx: Context) -> dict:
    site = ctx.site
    products = ctx.kb.get("products") or {}
    view = corpus_view(ctx.corpus())
    describe = lambda code: _name(base(code), products, view)
    templates, radio_by, radio_default, lcr_by, name_by, pci_by, root_by, rel_by = [], {}, {}, {}, {}, {}, {}, {}
    for enb, cell, mapping in _cells(ctx):
        x = lte_cell(site, cell)
        root = cell["dn"].split("/", 1)[0]
        dn = cell["dn"]
        here = radios(site, mapping)
        templates.append({"value": dn, "key": dn, "group": f"eNB {instance(enb['dn'])}",
                          "label": f"Like {label(dn)} · {x['name'] or 'no name'} · EARFCN {x['earfcn']}"
                                   + (f" · {x['bw']}" if x["bw"] else ""),
                          "details": [f"On {', '.join(label(r) for r in here)}; PCI {x['pci']}, lcrId {x['lcrId']}. "
                                      "The new cell takes its carrier and settings."]})
        opts = [{k: v for k, v in r.items() if k not in ("cells", "code")} for r in radio_options(site, describe)]
        radio_by[dn] = opts
        radio_default[dn] = next((o["value"] for o in opts if o["group"] == "Radios with no cell"), here[0])
        same = [c for c in site.child(enb["dn"], "LNCEL") if lte_cell(site, c)["earfcn"] == x["earfcn"]]
        lcr = suggest_lcr(site, root, x["lcrId"], 255)
        if lcr:
            lcr_by[dn] = lcr
            name = _name_suggestion(cell, x["lcrId"], lcr)
            if name:
                name_by[dn] = name
        pcis = [int(c["p"]["phyCellId"]) for c in same if (c["p"].get("phyCellId") or "").isdigit()]
        roots = [int(r) for c in same for r in [(_sub(site, c) or {"p": {}})["p"].get("rootSeqIndex") or ""]
                 if r.isdigit()]
        if suggest_pci(pcis, 503):
            pci_by[dn] = suggest_pci(pcis, 503)
        if suggest_root(roots):
            root_by[dn] = suggest_root(roots)
        rel_by[dn] = [{"value": c["dn"], "label": f"{label(c['dn'])} · {lte_cell(site, c)['name'] or ''} · EARFCN "
                                                  f"{lte_cell(site, c)['earfcn']}"}
                      for c in site.child(enb["dn"], "LNCEL")]
    return {
        "intro": "Copies one of the eNB's cells, with its carrier settings and channel mapping, onto a radio of the "
                 "site. The cell's identity is new: its lcrId, name, PCI and PRACH root.",
        "fields": [
            {"id": "template", "label": "Copy the settings of", "type": "select", "options": templates,
             "default": templates[0]["value"] if len(templates) == 1 else None},
            {"id": "radio", "label": "Radio", "type": "select", "dependsOn": "template", "optionsByKey": radio_by,
             "defaultByKey": radio_default},
            {"id": "earfcn", "label": "EARFCN (empty: the template's carrier)", "type": "text", "optional": True,
             "placeholder": "66786",
             "hint": "Another carrier in the same band, for a second cell on a radio that has one. FDD: the UL EARFCN "
                     "moves by the same step."},
            {"id": "lcrId", "label": "lcrId", "type": "text", "dependsOn": "template", "defaultByKey": lcr_by,
             "hint": "0 to 255, unique across the site's LTE and NR cells."},
            {"id": "cellName", "label": "Cell name", "type": "text", "dependsOn": "template", "defaultByKey": name_by},
            {"id": "pci", "label": "PCI (phyCellId)", "type": "text", "dependsOn": "template", "defaultByKey": pci_by,
             "hint": "0 to 503; not one another cell of the eNB uses on this carrier."},
            {"id": "root", "label": "PRACH root (rootSeqIndex)", "type": "text", "dependsOn": "template",
             "defaultByKey": root_by,
             "hint": "Spaced like the eNB's other cells on the carrier, so their preamble ranges don't overlap."},
            {"id": "relations", "label": "Relations both ways with", "type": "checks", "dependsOn": "template",
             "optionsByKey": rel_by, "optional": True},
        ],
    }


def _relation(doc: Doc, src: str, enb_id: str, lcr: str, plmn: list[tuple[str, str]], what: str) -> Optional[str]:
    inst = doc.next_free(src, "LNREL", 0)
    if int(inst) > LNREL_RANGE:
        return None
    first = not doc.of_class("LNREL")
    info = doc.class_info("LNCEL")
    dn = doc.create(src, "LNREL", inst, [
        ("amleAllowed", "false"), ("cellIndOffNeigh", "0dB"), ("ecgiAdjEnbId", enb_id), ("ecgiLcrId", lcr),
        ("handoverAllowed", "allowed"), ("nrControl", "automatic"), ("removeAllowed", "false")],
        full_class=f"{info[0].rsplit(':', 1)[0]}:LNREL" if first and info and ":" in info[0] else None,
        w=why("lte-cell", f"{what}, handover allowed. removeAllowed false, so ANR keeps the planned relation.", "files"))
    if plmn:
        doc.add_item(dn, "ecgiPlmnId", plmn, why("lte-cell", "The eNB's PLMN, in the target's ECGI.", "choice"))
    return dn


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    found = next(((e, c, m) for e, c, m in _cells(ctx) if c["dn"] == inputs.get("template")), None)
    if not found:
        raise PlanError(["Pick the cell to copy."])
    enb, cell, mapping = found
    root = cell["dn"].split("/", 1)[0]
    radio = inputs.get("radio") or ""
    if site.by_dn.get(radio, {}).get("cls") != "RMOD" or radio.split("/", 1)[0] != root:
        raise PlanError(["Pick the radio the new cell transmits on."])
    x = lte_cell(site, cell)
    sub = _sub(site, cell)
    problems: list[str] = []
    lcr = number(inputs.get("lcrId"), 0, 255, "The lcrId", problems)
    pci = number(inputs.get("pci"), 0, 503, "The PCI", problems)
    earfcn = x["earfcn"]
    if (inputs.get("earfcn") or "").strip():
        earfcn = number(inputs.get("earfcn"), 0, 262143, "The EARFCN", problems) or earfcn
    same = [c for c in site.child(enb["dn"], "LNCEL") if lte_cell(site, c)["earfcn"] == earfcn]
    used_roots = [int(r) for c in same for r in [(_sub(site, c) or {"p": {}})["p"].get("rootSeqIndex") or ""]
                  if r.isdigit()]
    prach = number(inputs.get("root"), 0, root_limit(used_roots), "The PRACH root (rootSeqIndex)", problems)
    name = (inputs.get("cellName") or "").strip()
    if not name:
        problems.append("Enter the cell name.")
    if problems:
        raise PlanError(problems)
    if int(lcr) in lcr_ids(site, root):
        problems.append(f"lcrId {lcr} is taken: lcrIds are unique across the site's LTE and NR cells.")
    for c in same:
        if c["p"].get("phyCellId") == pci:
            problems.append(f"{label(c['dn'])} has PCI {pci} on EARFCN {earfcn}.")
        if (_sub(site, c) or {"p": {}})["p"].get("rootSeqIndex") == prach:
            problems.append(f"{label(c['dn'])} has rootSeqIndex {prach} on EARFCN {earfcn}.")
        if radio in radios(site, cell_mapping(site, c) or {}):
            problems.append(f"{label(radio)} already carries {label(c['dn'])} on EARFCN {earfcn}: a second cell on "
                            "the same radio needs another carrier (enter its EARFCN), or add a radio first (Add a "
                            "radio).")
    lcell = f"{mapping['dn'].rsplit('/', 1)[0]}/LCELL-{lcr}"
    if lcell in site.by_dn:
        problems.append(f"{label(lcell)} exists already, left over from a deleted cell: remove it first.")
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
    w = why("lte-cell", f"A new cell like {label(cell['dn'])}: its carrier settings, profiles and measurement "
                        "objects, with its own identity.", "donor")
    inst = free_instance(doc, enb["dn"], "LNCEL", lcr, 0)
    dst = f"{enb['dn']}/LNCEL-{inst}"
    over = {"": {"lcrId": lcr, "cellName": name, "phyCellId": pci}}
    eci = cell["p"].get("eutraCelId")
    if (eci or "").isdigit():
        over[""]["eutraCelId"] = str((int(eci) >> 8 << 8) | int(lcr))
    moved = earfcn != x["earfcn"]
    if sub:
        rel = sub["dn"][len(cell["dn"]) + 1:]
        over[rel] = {"rootSeqIndex": prach}
        if moved and sub["cls"] == "LNCEL_FDD":
            step = int(earfcn) - int(x["earfcn"])
            over[rel].update(earfcnDL=earfcn, earfcnUL=str(int(sub["p"].get("earfcnUL") or 0) + step))
            notes.append(f"On EARFCN {earfcn} (UL {over[rel]['earfcnUL']}, the template's duplex spacing); the "
                         f"bandwidth stays {x['bw']}.")
        elif moved:
            over[rel]["earfcn"] = earfcn
            notes.append(f"On EARFCN {earfcn}; the bandwidth stays {x['bw']}.")
    skip = SKIP | (frozenset(CARRIERS) if moved else frozenset())
    skipped = sorted({doc.cls(d) for d in doc.subtree(cell["dn"]) if doc.cls(d) in SKIP})
    doc.clone(cell["dn"], dst, w, overrides=over, skip=skip)
    if moved:
        # The template's carrier objects, minus the one for the new cell's own carrier.
        for cls, field in (("IRFIM", "dlCarFrqEut"), ("LNHOIF", "eutraCarrierInfo")):
            for m in site.child(cell["dn"], cls):
                if m["p"].get(field) != earfcn:
                    doc.clone(m["dn"], f"{dst}/{label(m['dn'])}", w)
    if skipped:
        notes.append(f"Not copied: {', '.join(skipped)}. Relations are added below or learned by ANR; carrier "
                     "aggregation needs the CA wizard; a CBRS cell registers with its own id.")
    clone_mapping(doc, site, mapping, lcr, rewrite,
                  why("lte-cell", f"The new cell's channels, like {label(mapping['dn'])}'s"
                      + (f", moved to {label(radio)}'s antennas" if rewrite else "") + ".", "donor"))

    picked = [c for c in site.child(enb["dn"], "LNCEL") if c["dn"] in (inputs.get("relations") or [])]
    plmn = _plmn(enb["p"])
    row = [("mcc", plmn["mcc"]), ("mnc", plmn["mnc"]), ("mncLength", plmn["mncLength"])] if plmn else []
    enb_id = instance(enb["dn"])
    if picked and not plmn:
        notes.append("The eNB has no PLMN (LNBTS mcc/mnc), so the relations carry no ecgiPlmnId.")
    full, added, none = [], {}, []
    nb = _NeighbourPlan(ctx, doc, enb, {"plmn": plmn or {}})
    for c in picked:
        cx = lte_cell(site, c)
        if not _relation(doc, dst, enb_id, cx["lcrId"], row, f"{label(dst)} to {label(c['dn'])}"):
            full.append(label(dst))
        if not _relation(doc, c["dn"], enb_id, lcr, row, f"{label(c['dn'])} to the new cell"):
            full.append(label(c["dn"]))
        if cx["earfcn"] != earfcn:
            nb.carrier(c, {"earfcn": earfcn, "bw": x["bw"]})
            for cls, field in (("IRFIM", "dlCarFrqEut"), ("LNHOIF", "eutraCarrierInfo")):
                mine = doc.children(dst, cls)
                if any(doc.get(d, field) == cx["earfcn"] for d in mine):
                    continue
                donor = (mine or [d for o in site.child(enb["dn"], "LNCEL") for d in doc.children(o["dn"], cls)]
                         or [None])[0]
                if donor is None:
                    none.append(f"{cls} for EARFCN {cx['earfcn']}")
                    continue
                i = doc.next_free(dst, cls, 1)
                if int(i) > 16:
                    none.append(f"{cls} for EARFCN {cx['earfcn']} (all 16 ids in use)")
                    continue
                o = {field: cx["earfcn"]}
                nrb = NRB.get(cx.get("bw") or "")
                if nrb and cls == "IRFIM":
                    o["measBdw"] = f"{nrb}mbw"
                elif nrb and doc.get(donor, "measurementBandwidth"):
                    o["measurementBandwidth"] = f"mbw{nrb}"
                doc.clone(donor, f"{dst}/{cls}-{i}",
                          why("lte-cell", f"{'Reselection' if cls == 'IRFIM' else 'Handover'} from the new cell to "
                                          f"EARFCN {cx['earfcn']}, copied from {label(donor)}.", "files"),
                          overrides={"": o})
                added.setdefault(cx["earfcn"], label(donor))
    nb.carrier_notes()
    notes += nb.notes
    if added:
        notes.append(f"The new cell's IRFIM and LNHOIF for EARFCN {', '.join(added)} copy "
                     f"{', '.join(sorted(set(added.values())))}: check their priorities and thresholds.")
    if none:
        notes.append(f"No cell has one to copy, so the new cell gets no {', '.join(none)}.")
    if full:
        notes.append(f"{', '.join(sorted(set(full)))} has every LNREL id in use, so some relations weren't added.")
    others = [label(c["dn"]) for c in site.child(enb["dn"], "LNCEL") if radio in radios(site, cell_mapping(site, c) or {})]
    if others:
        confirm.append(f"{label(radio)} can carry another carrier: it already transmits {', '.join(others)}.")
    confirm.append(f"{label(radio)} covers EARFCN {earfcn}, and the baseband has capacity for another cell.")
    if not picked:
        notes.append("No relations: ANR learns them, or plan them later with the neighbour actions.")
    return finish(ctx, doc, {
        "label": f"LTE cell {name} ({label(dst)})",
        "summary": f"{label(dst)} · {name} · lcrId {lcr} · PCI {pci} on {label(radio)}"
                   + (f" · {len(picked)} relation{'s' if len(picked) != 1 else ''} both ways" if picked else ""),
        "notes": notes,
        "confirm": confirm,
        "focus": dst,
    })

"""
What deleting objects takes with it (the delete and remove-module
actions; PROJECT_STATE §9.9, "Delete with dependents").

Deleting an object deletes everything under it. What points into that
subtree from outside, read from the reference map's links (refmap.py),
decides the rest:
- a link object goes too: a CABLINK or LOGLINK joins two modules and
  means nothing with one end gone, and a relation (LNREL, LNRELGNBCELL,
  CAREL) means nothing without its target;
- a cell's channel mapping (LCELL/LCELNR, by lcrId) goes with the cell;
- a value in a list of distNames or ids is taken out (SYNC.targetDNList,
  RETU.antlDNList, NRCELLGRP.nrCellList, NRDU.refNrCellGroup). A cell
  group left with no cell goes too, with its NRDU entry; a SYNC, RETU or
  NRDU list left empty is said in the plan; any other list left empty
  blocks;
- a list row that only names it (ROW_REFS: snssaiList {snssaiDN},
  nrResourceList) comes out. A 5QI mapping or resource group whose rows
  all name deleted objects goes too, since a mapping naming no slice would
  serve every slice; a tracking area left with none is said in the plan;
- a radio's CBRS (SAS) registration (OF_RADIO: CBSD, NRCBSD) goes with it;
- anything else blocks: a setting naming it (CHANNEL.antlDN: a cell uses
  the antenna; NRDRB_5QI.nrDrbDN; ETHLK.modDN), a row with other fields,
  or a list in BLOCK_LISTS (a cell's baseband and radio). The plan names
  each, to change first.
Runtime objects (_R, INVUNIT) are the BTS's report and are left alone.
References written relative to the parent ("NRDRB-2" in nrDrbDN) count as
the distName they name.

Pure: works on a Site and a Doc.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ..refmap import build
from .doc import Doc, instance, label, parent_dn
from .links import Site, _runtime

LINKS = {"CABLINK", "LOGLINK", "LNREL", "LNRELGNBCELL"}
# Objects that exist for one radio: a CBRS device's SAS registration (CBSD
# rmodDN, NRCBSD rModDN; nothing else in the files names them).
OF_RADIO = {"CBSD": "its CBRS (SAS) registration", "NRCBSD": "its CBRS (SAS) registration"}
BLOCK_LISTS = {("NRCELL", "modDNList"), ("NRCELL", "frRefList")}
EMPTY_OK = {("SYNC", "targetDNList"), ("RETU", "antlDNList"), ("NRDU", "refNrCellGroup")}
MAPPINGS = {"LNCEL": "LCELL", "NRCELL": "LCELNR"}
# Lists whose rows only name an object (snssaiList {snssaiDN}): the row
# comes out with it. A 5QI mapping left naming no slice would serve every
# slice, so one that served only the deleted ones goes too, as does a
# slice's resource group; a tracking area is only noted.
ROW_REFS = {("NRDRB_5QI", "snssaiList"): "drop", ("TRACKINGAREA", "snssaiList"): "keep",
            ("NRRESOURCEGROUP", "nrResourceList"): "drop"}

# A distName written relative to the object's parent ("NRDRB_MAC-1" on an
# NRDRB; one lab export does this).
_RELATIVE = re.compile(r"^[A-Z][A-Z0-9_]*-[^/\s]+(/[A-Za-z0-9_]+-[^/\s]+)*$")
_LIST_ITEM = re.compile(r"^(.*)::list::([^:]+)::item::(\d+)$")
_ROW_FIELD = re.compile(r"^(.*)::list::([^:]+)::item::(\d+)::p::(.+)$")


@dataclass
class Removal:
    roots: list[str] = field(default_factory=list)         # objects deleted (with their subtrees)
    values: list[tuple[str, str, str]] = field(default_factory=list)  # (dn, list, value) taken out
    rows: list[tuple[str, str, int]] = field(default_factory=list)    # (dn, list, row index) taken out
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    why: dict[str, str] = field(default_factory=dict)       # root -> why it goes


def where(dn: str) -> str:
    """A label that says where a generic object is ("LCELL-1/CHANNELGROUP-1/
    CHANNEL-3"), its own label otherwise."""
    parts = dn.split("/")
    if label(dn).split("-", 1)[0] in ("CHANNEL", "CHANNELGROUP") and len(parts) > 3:
        return "/".join(parts[-3:])
    return label(dn)


def _cell_of_mapping(site: Site, dn: str) -> Optional[dict]:
    """The cell whose channel mapping contains `dn`."""
    m = re.search(r"/(LCELL|LCELNR)-([^/]+)", dn)
    if not m:
        return None
    cls = "LNCEL" if m.group(1) == "LCELL" else "NRCELL"
    root = dn.split("/", 1)[0]
    return next((c for c in site.of(cls, root) if c["p"].get("lcrId") == m.group(2)), None)


def plan_removal(site: Site, start: list[str]) -> Removal:
    """Everything deleting `start` takes with it, or what blocks it."""
    edges = [e for e in build(site.mos)["edges"] if not e.get("missing") and not _runtime(e["s"])]
    for m in site.mos:
        for k, v in m["p"].items():
            if v and _RELATIVE.match(v) and not v.startswith("MRBTS-") and f"{parent_dn(m['dn'])}/{v}" in site.by_dn:
                edges.append({"s": m["dn"], "t": f"{parent_dn(m['dn'])}/{v}", "via": k, "at": f"{m['dn']}::p::{k}",
                              "kind": "ref"})
    inbound: dict[str, list[dict]] = {}
    for e in edges:
        inbound.setdefault(e["t"], []).append(e)
    out = Removal()
    gone: set[str] = set()
    under = {}

    def subtree(dn: str) -> list[str]:
        if dn not in under:
            under[dn] = [m["dn"] for m in site.mos if m["dn"] == dn or m["dn"].startswith(dn + "/")]
        return under[dn]

    def drop(dn: str, why: str) -> bool:
        if dn in gone:
            return False
        out.roots.append(dn)
        out.why[dn] = why
        gone.update(subtree(dn))
        return True

    for dn in start:
        drop(dn, "picked")

    # 1. What goes with them, to a fixpoint: companions, links, relations, and
    #    cell groups whose every cell goes.
    changed = True
    while changed:
        changed = False
        for dn in list(gone):
            m = site.by_dn.get(dn)
            if not m:
                continue
            if m["cls"] in MAPPINGS:
                lcr = m["p"].get("lcrId")
                root = dn.split("/", 1)[0]
                for cm in site.of(MAPPINGS[m["cls"]], root):
                    if instance(cm["dn"]) == lcr:
                        changed |= drop(cm["dn"], f"the channel mapping of {label(dn)}")
                if m["cls"] == "LNCEL":
                    enb = instance(parent_dn(dn))
                    for rel in site.of("CAREL", parent_dn(dn)):
                        if rel["p"].get("lcrId") == lcr and rel["p"].get("lnBtsId") in (None, enb):
                            changed |= drop(rel["dn"], f"a carrier aggregation relation to {label(dn)}")
            for e in inbound.get(dn, []):
                src = e["s"]
                if src in gone:
                    continue
                cls = site.by_dn[src]["cls"]
                if cls in LINKS and not _ROW_FIELD.match(e["at"]) and not _LIST_ITEM.match(e["at"]):
                    changed |= drop(src, f"a {cls} to {label(dn)}")
                elif cls in OF_RADIO and site.by_dn[dn]["cls"] == "RMOD" and not _LIST_ITEM.match(e["at"]):
                    changed |= drop(src, f"{OF_RADIO[cls]} of {label(dn)}")
                elif _ROW_FIELD.match(e["at"]) and ROW_REFS.get((cls, _ROW_FIELD.match(e["at"]).group(2))) == "drop":
                    lname = _ROW_FIELD.match(e["at"]).group(2)
                    if all(set(r.values()) <= gone for r in site.by_dn[src]["lists"].get(lname, [])):
                        changed |= drop(src, f"it served only {label(dn)}")
                elif cls == "NRCELLGRP" and _LIST_ITEM.match(e["at"]):
                    cells = site.by_dn[src]["simple"].get("nrCellList", [])
                    if all(f"{parent_dn(src)}/NRCELL-{c}" in gone for c in cells):
                        changed |= drop(src, "left with no cell")

    # 2. What points in from what stays: list values come out, the rest blocks.
    taken: dict[tuple[str, str], set[int]] = {}
    blocked: set[tuple] = set()
    listed: dict[tuple[str, str], str] = {}   # (cell, module) -> a BLOCK_LISTS message
    on_radio: set[tuple[str, str]] = set()     # (cell, radio) a channel block already names
    for dn in sorted(gone):
        for e in inbound.get(dn, []):
            src = e["s"]
            if src in gone:
                continue
            cls = site.by_dn[src]["cls"]
            row = _ROW_FIELD.match(e["at"])
            item = _LIST_ITEM.match(e["at"])
            if item:
                lname, i = item.group(2), int(item.group(3))
                if (cls, lname) in BLOCK_LISTS:
                    listed.setdefault((src, dn), f"{where(src)} lists {label(dn)} in {lname}: it runs on it. Delete "
                                                 f"or change {where(src)} first.")
                    continue
                hit = taken.setdefault((src, lname), set())
                if i in hit:
                    continue
                hit.add(i)
                values = site.by_dn[src]["simple"].get(lname, [])
                out.values.append((src, lname, values[i]))
                if len(hit) == len(values):
                    if (cls, lname) in EMPTY_OK:
                        out.notes.append(f"{where(src)}.{lname} is empty now.")
                    else:
                        out.blockers.append(f"{where(src)}.{lname} would be left empty. Change it first.")
                continue
            if cls == "CHANNEL":
                cell = _cell_of_mapping(site, src)
                radio = dn.split("/ANTL-")[0].split("/PHYANT-")[0]
                key = ("cell", cell["dn"] if cell else src, radio)
                if cell:
                    on_radio.add((cell["dn"], radio))
                if key not in blocked:
                    blocked.add(key)
                    out.blockers.append(f"{label(cell['dn']) if cell else where(src)} uses {label(dn)} (its channel "
                                        "mapping names it). Delete the cell first, or move it to another radio.")
                continue
            if (src, e["via"]) in blocked:
                continue
            blocked.add((src, e["via"]))
            if e["kind"] == "id" and e["via"] == "lcrId":
                out.blockers.append(f"{label(src)} uses {label(dn)} as its channel mapping. Delete the cell first.")
            elif row and (cls, row.group(2)) in ROW_REFS and len(site.by_dn[src]["lists"][row.group(2)][
                    int(row.group(3))]) == 1:
                lname = row.group(2)
                out.rows.append((src, lname, int(row.group(3))))
                if sum(1 for r in out.rows if r[:2] == (src, lname)) == len(site.by_dn[src]["lists"][lname]):
                    out.notes.append(f"{where(src)}.{lname} is empty now.")
            elif row:
                out.blockers.append(f"{where(src)}'s {row.group(2)} has a row naming {label(dn)}. Change that row "
                                    "first.")
            elif cls == "ETHLK":
                out.blockers.append(f"{label(dn)} carries the Ethernet link {where(src)} (its {e['via']}): the "
                                    "backhaul runs on it. Move the link to another card first.")
            else:
                out.blockers.append(f"{where(src)}.{e['via']} names {label(dn)}. Change it first.")
    # A cell listing the radio its channels already block on needn't be said twice.
    out.blockers += [msg for (cell, mod), msg in listed.items() if (cell, mod) not in on_radio]
    # Values in objects that go anyway needn't be taken out.
    out.values = [v for v in out.values if v[0] not in gone]
    out.rows = [r for r in out.rows if r[0] not in gone]
    return out


def apply_removal(doc: Doc, removal: Removal, w_for) -> None:
    """Writes a removal: values out first, then the objects (parents after
    the objects inside them are covered by the parent's delete). `w_for(dn,
    why)` gives each change its reason."""
    for dn, lname, value in removal.values:
        doc.remove_value(dn, lname, value, w_for(dn, f"{lname} names an object that is deleted"))
    for dn, lname, i in sorted(set(removal.rows), key=lambda r: (r[0], r[1], -r[2])):
        doc.remove_item(dn, lname, i, w_for(dn, f"its {lname} row names an object that is deleted"))
    roots = [r for r in removal.roots if not any(r != o and r.startswith(o + "/") for o in removal.roots)]
    for dn in roots:
        doc.delete(dn, w_for(dn, removal.why.get(dn, "")))

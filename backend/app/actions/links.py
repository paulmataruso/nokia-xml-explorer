"""
What ties one managed object to another, as rules. The site check
(site_check.py) runs them on a file, and the actions follow them when they
add or remove objects ("if you add A you need B"). PROJECT_STATE §9.9 has
the measurements behind each rule.

Kinds of link:
- reference: a parameter or list value holding another object's distName.
  One generic rule covers them all: a value shaped like a distName of this
  site must name an object in the file.
- id: two objects agree on an id that isn't a distName (NRCELL.lcrId and
  LCELNR-{lcrId}, NRCELLGRP.nrCellList and NRCELL ids, ...).
- value: a value has to reappear elsewhere (an inter-frequency LNREL needs
  an IRFIM for the target carrier).
- companion: objects every sibling has (a cell's SIB, DRX, ...), compared
  within the file, so a hand-added cell missing one stands out.

`basis` is as in ca.py's findings: official (dictionary rules), files
(patterns calibrated on the corpus) or general. `evidence` records what the
rule was calibrated on. scripts/link_rules_check.py re-runs every rule over
the corpus; production and working files must have no errors.

Pure: works on ca._load() output.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Callable, Iterator, Optional

from ..ca import _instance, _int, _label, _parent

_DN = re.compile(r"^MRBTS-[^/\s]+(/[A-Za-z0-9_]+-[^/\s]+)*$")


class Site:
    """ca._load() output with the lookups the rules need."""

    def __init__(self, mos: list[dict]):
        self.mos = mos
        self.by_dn = {m["dn"]: m for m in mos}
        self.kids: dict[str, list[dict]] = defaultdict(list)
        self.by_cls: dict[str, list[dict]] = defaultdict(list)
        for m in mos:
            self.kids[_parent(m["dn"])].append(m)
            self.by_cls[m["cls"]].append(m)
        self.roots = {m["dn"].split("/", 1)[0] for m in mos if m["dn"].startswith("MRBTS-")}

    def of(self, cls: str, under: Optional[str] = None) -> list[dict]:
        return [m for m in self.by_cls.get(cls, []) if under is None or m["dn"].startswith(under + "/")]

    def child(self, dn: str, cls: str) -> list[dict]:
        return [m for m in self.kids.get(dn, []) if m["cls"] == cls]


Finding = dict  # {"title", "detail", "targets": [(id, label)], optional "severity"}

RULES: list[dict] = []


def rule(rid: str, title: str, kind: str, severity: str, basis: str, evidence: str):
    def register(fn: Callable[[Site], Iterator[Finding]]):
        RULES.append({"id": rid, "title": title, "kind": kind, "severity": severity, "basis": basis,
                      "evidence": evidence, "check": fn})
        return fn
    return register


def _pid(dn: str, name: str) -> str:
    return f"{dn}::p::{name}"


def _values(m: dict) -> Iterator[tuple[str, str, Optional[str]]]:
    """(node id, label, value) for every value an object holds."""
    for k, v in m["p"].items():
        yield _pid(m["dn"], k), k, v
    for ln, vs in m["simple"].items():
        for i, v in enumerate(vs):
            yield f"{m['dn']}::list::{ln}::item::{i}", f"{ln}[{i + 1}]", v
    for ln, rows in m["lists"].items():
        if ln in m["simple"]:
            continue
        for i, row in enumerate(rows):
            for k, v in row.items():
                yield f"{m['dn']}::list::{ln}::item::{i}::p::{k}", f"{ln}[{i + 1}].{k}", v


# --- Reference ---------------------------------------------------------------

def _runtime(dn: str) -> bool:
    """Runtime objects, and INVUNIT inventory records, which point at both
    configuration and runtime objects."""
    return any(c.endswith("_R") or c == "INVUNIT" for c in (part.split("-", 1)[0] for part in dn.split("/")))


@rule("reference", "A reference points at a missing object", "reference", "error", "general",
      "0 dangling references across the production files (about 60 kinds of reference). Runtime (_R) objects "
      "and INVUNIT are left out: a runtime export doesn't carry the configuration they point at.")
def _references(site: Site) -> Iterator[Finding]:
    for m in site.mos:
        if _runtime(m["dn"]):
            continue
        for node, name, v in _values(m):
            if not v or not _DN.match(v) or _runtime(v):
                continue
            root = v.split("/", 1)[0]
            where = f"{_label(m['dn'])}.{name}"
            if site.roots and root not in site.roots:
                yield {"severity": "warning",
                       "title": f"{where} points at another site",
                       "detail": f"It names {v}, but this file is {', '.join(sorted(site.roots))}. Usually a value "
                                 "left over from the file this one was copied from, or from before the site was "
                                 "renumbered.",
                       "targets": [(node, where)]}
            elif v not in site.by_dn:
                branch = "/".join(v.split("/", 2)[:2])
                if branch not in site.by_dn:
                    yield {"severity": "warning",
                           "title": f"{where} points outside this file",
                           "detail": f"It names {v}, and this file has no {_label(branch)} at all, so it is "
                                     "probably a partial export.",
                           "targets": [(node, where)]}
                else:
                    yield {"title": f"{where} points at a missing object",
                           "detail": f"It names {v}, which isn't in this file.",
                           "targets": [(node, where)]}


# --- Id links ----------------------------------------------------------------

@rule("unique-dn", "Two objects share a distName", "id", "error", "general",
      "A distName names one object. One file in the corpus repeats two (an IPIF and its IPADDRESSV4, holding "
      "different addresses, in a hand-edited export); no other file repeats any.")
def _unique_dn(site: Site) -> Iterator[Finding]:
    seen: dict[str, int] = defaultdict(int)
    for m in site.mos:
        seen[m["dn"]] += 1
    for dn, n in seen.items():
        if n > 1:
            yield {"title": f"{_label(dn)} appears {n} times",
                   "detail": f"The file has {n} objects named {dn}. A distName identifies one object, so which "
                             "values apply is ambiguous; this tool shows them merged into one node. Delete or "
                             "rename the extra one.",
                   "targets": [(dn, _label(dn))]}


@rule("lcr-unique", "Two cells share an lcrId", "id", "error", "files",
      "lcrIds are unique across LTE and NR cells of one site in every file (0 clashes).")
def _lcr_unique(site: Site) -> Iterator[Finding]:
    for root in sorted(site.roots):
        seen: dict[str, list[dict]] = defaultdict(list)
        for cls in ("LNCEL", "NRCELL"):
            for m in site.of(cls, root):
                if m["p"].get("lcrId") not in (None, ""):
                    seen[m["p"]["lcrId"]].append(m)
        for lcr, cells in seen.items():
            if len(cells) > 1:
                yield {"title": f"lcrId {lcr} is used by {len(cells)} cells",
                       "detail": "Each cell of a site needs its own lcrId, across LTE and NR: it names the cell's "
                                 "LCELL or LCELNR channel mapping.",
                       "targets": [(_pid(c["dn"], "lcrId"), _label(c["dn"])) for c in cells]}


@rule("cell-mapping", "A cell has no channel mapping", "id", "error", "files",
      "Every LNCEL has LCELL-{lcrId} and every NRCELL has LCELNR-{lcrId} in each file with CELLMAPPING.")
def _cell_mapping(site: Site) -> Iterator[Finding]:
    for cm in site.of("CELLMAPPING"):
        root = cm["dn"].split("/", 1)[0]
        for cell_cls, map_cls in (("LNCEL", "LCELL"), ("NRCELL", "LCELNR")):
            maps = {_instance(m["dn"]): m for m in site.of(map_cls, root)}
            cells = site.of(cell_cls, root)
            lcrs = {c["p"].get("lcrId") for c in cells}
            for c in cells:
                lcr = c["p"].get("lcrId")
                if lcr not in maps:
                    yield {"title": f"{_label(c['dn'])} has no {map_cls}-{lcr}",
                           "detail": f"A cell's antenna channels are in {map_cls}-{{lcrId}} under CELLMAPPING. "
                                     f"Without one the cell has no radio to transmit on.",
                           "targets": [(_pid(c["dn"], "lcrId"), _label(c["dn"]))]}
            for inst, m in maps.items():
                if inst not in lcrs:
                    yield {"severity": "warning",
                           "title": f"{_label(m['dn'])} belongs to no cell",
                           "detail": f"No {cell_cls} has lcrId {inst}. It is left over from a deleted cell, or "
                                     "the cell's lcrId changed.",
                           "targets": [(m["dn"], _label(m["dn"]))]}


@rule("nr-cell-groups", "An NR cell isn't in a cell group", "id", "error", "files",
      "Every NRCELL is in an NRCELLGRP.nrCellList, and every NRCELLGRP in NRDU.refNrCellGroup (119/119).")
def _nr_cell_groups(site: Site) -> Iterator[Finding]:
    for nrbts in site.of("NRBTS"):
        groups = site.of("NRCELLGRP", nrbts["dn"])
        if not groups:
            continue
        cells = {_instance(c["dn"]): c for c in site.of("NRCELL", nrbts["dn"])}
        listed = {v for g in groups for v in g["simple"].get("nrCellList", [])}
        for inst, c in cells.items():
            if inst not in listed:
                yield {"title": f"{_label(c['dn'])} is in no NRCELLGRP",
                       "detail": "Each NR cell is listed in an NRCELLGRP's nrCellList, which NRDU serves.",
                       "targets": [(c["dn"], _label(c["dn"]))]}
        for g in groups:
            for i, v in enumerate(g["simple"].get("nrCellList", [])):
                if v not in cells:
                    yield {"title": f"{_label(g['dn'])} lists NRCELL-{v}, which doesn't exist",
                           "detail": "nrCellList holds NRCELL instance ids.",
                           "targets": [(f"{g['dn']}::list::nrCellList::item::{i}", _label(g["dn"]))]}
        # Older releases (23R1) have no refNrCellGroup.
        dus = [du for du in site.of("NRDU", nrbts["dn"]) if "refNrCellGroup" in du["simple"]]
        if not dus:
            continue
        refs = {v for du in dus for v in du["simple"].get("refNrCellGroup", [])}
        for g in groups:
            if _instance(g["dn"]) not in refs:
                yield {"title": f"{_label(g['dn'])} isn't served by an NRDU",
                       "detail": "NRDU.refNrCellGroup lists the cell groups the DU serves; this one is missing.",
                       "targets": [(g["dn"], _label(g["dn"]))] + [(du["dn"], _label(du["dn"])) for du in dus]}
        for du in dus:
            for i, v in enumerate(du["simple"].get("refNrCellGroup", [])):
                if v not in {_instance(g["dn"]) for g in groups}:
                    yield {"title": f"{_label(du['dn'])} serves NRCELLGRP-{v}, which doesn't exist",
                           "detail": "refNrCellGroup holds NRCELLGRP instance ids.",
                           "targets": [(f"{du['dn']}::list::refNrCellGroup::item::{i}", _label(du["dn"]))]}


def _own_enb_ids(site: Site, lnbts: dict) -> set[str]:
    return {_instance(lnbts["dn"]), _instance(lnbts["dn"].split("/", 1)[0])}


def _adjl(site: Site, lnbts: dict) -> dict[tuple, dict]:
    """LNADJL by (eNB id, lcrId). Older releases leave ecgiAdjEnbId off
    the LNADJL; its LNADJ's adjEnbId says which eNB it is."""
    out = {}
    for m in site.of("LNADJL", lnbts["dn"]):
        enb = m["p"].get("ecgiAdjEnbId") or (site.by_dn.get(_parent(m["dn"])) or {"p": {}})["p"].get("adjEnbId")
        out[(enb, m["p"].get("ecgiLcrId"))] = m
    return out


def _earfcn(site: Site, cell: dict) -> Optional[str]:
    for sub in ("LNCEL_FDD", "LNCEL_TDD"):
        for m in site.child(cell["dn"], sub):
            return m["p"].get("earfcnDL") or m["p"].get("earfcn")
    return None


@rule("lte-relations", "An LTE neighbour relation has no target", "id", "warning", "files",
      "Each LNREL names an own LNCEL (110/110) or an LNADJL under its LNADJ (716/716).")
def _lte_relations(site: Site) -> Iterator[Finding]:
    for lnbts in site.of("LNBTS"):
        own = _own_enb_ids(site, lnbts)
        cells = {c["p"].get("lcrId"): c for c in site.child(lnbts["dn"], "LNCEL")}
        adjl = set(_adjl(site, lnbts))
        for rel in site.of("LNREL", lnbts["dn"]):
            key = (rel["p"].get("ecgiAdjEnbId"), rel["p"].get("ecgiLcrId"))
            if key in adjl or key[0] in own and key[1] in cells:
                continue
            yield {"title": f"{_label(_parent(rel['dn']))}/{_label(rel['dn'])} has no target cell",
                   "detail": f"It points at eNB {key[0]} cell {key[1]}. That's "
                             + ("not a cell of this eNB." if key[0] in own else
                                "not defined: add an LNADJL for it under the LNADJ of that eNB."),
                   "targets": [(rel["dn"], _label(rel["dn"]))]}


@rule("endc-relations", "An EN-DC relation has no gNB neighbour", "id", "warning", "files",
      "LNRELGNBCELL.nrCellId >> (36 - gnbIdLength) is an LNADJGNB.adjGnbId in every file.")
def _endc_relations(site: Site) -> Iterator[Finding]:
    for lnbts in site.of("LNBTS"):
        # Older releases have no adjGnbId on LNADJGNB, so there's nothing to match.
        gnbs = {m["p"]["adjGnbId"] for m in site.of("LNADJGNB", lnbts["dn"]) if m["p"].get("adjGnbId")}
        for rel in site.of("LNRELGNBCELL", lnbts["dn"]) if gnbs else ():
            nci, length = _int(rel["p"].get("nrCellId")), _int(rel["p"].get("gnbIdLength"))
            if nci is None or length is None or not 22 <= length <= 32:
                continue
            if nci == 0:
                yield {"severity": "info",
                       "title": f"{_label(_parent(rel['dn']))}/{_label(rel['dn'])} has nrCellId 0",
                       "detail": "So it names no NR cell. A placeholder is harmless while EN-DC isn't used.",
                       "targets": [(_pid(rel["dn"], "nrCellId"), _label(rel["dn"]))]}
                continue
            gnb = str(nci >> (36 - length))
            if gnb not in gnbs:
                yield {"title": f"{_label(_parent(rel['dn']))}/{_label(rel['dn'])} points at an unknown gNB",
                       "detail": f"Its nrCellId {nci} is in gNB {gnb} (with a {length}-bit gNB id), and no "
                                 "LNADJGNB has that adjGnbId.",
                       "targets": [(_pid(rel["dn"], "nrCellId"), _label(rel["dn"]))]}


@rule("drx-profiles", "A QCI uses a DRX profile that isn't defined", "id", "error", "files",
      "Every LNBTS qciTabN.drxProfileIndex names a DRX drxProfileN row (1,490 of 1,490).")
def _drx_profiles(site: Site) -> Iterator[Finding]:
    for lnbts in site.of("LNBTS"):
        drx = site.of("DRX", lnbts["dn"])
        if not drx:
            continue
        defined: dict[str, set[str]] = {}
        for d in drx:
            defined[d["dn"]] = {row.get("drxProfileIndex") for rows in d["lists"].values() for row in rows}
        common = set.intersection(*defined.values())
        for ln, rows in lnbts["lists"].items():
            if not ln.startswith("qciTab"):
                continue
            for i, row in enumerate(rows):
                v = row.get("drxProfileIndex")
                if v not in (None, "") and v not in common:
                    missing = [d for d, idx in defined.items() if v not in idx]
                    yield {"title": f"{ln} uses DRX profile {v}",
                           "detail": f"No drxProfile row with drxProfileIndex {v} on "
                                     f"{', '.join(_label(_parent(d)) for d in missing[:5])}"
                                     + (f" and {len(missing) - 5} more" if len(missing) > 5 else "") + ".",
                           "targets": [(f"{lnbts['dn']}::list::{ln}::item::{i}::p::drxProfileIndex", ln)]}


_BEARER_REFS = {"nrDrbMacDN": "NRDRB_MAC", "nrDrbPdcpDN": "NRDRB_PDCP", "nrDrbRlcAmDN": "NRDRB_RLC_AM",
                "nrDrbRlcUmDN": "NRDRB_RLC_UM", "nrDrxDN": "NRDRX"}


@rule("nr-bearers", "A 5G bearer setting names the wrong object", "id", "error", "files",
      "Every NRDRB_5QI and NRDRB_QCI nrDrbDN names an NRDRB, and every NRDRB reference its NRDRB_MAC, NRDRB_PDCP, "
      "NRDRB_RLC_AM or _UM and NRDRX (2,334 of 2,334; one lab export writes them relative to the gNB). An RLC_UM "
      "bearer names an NRDRB_RLC_UM (51 of 51) and an RLC_AM one an NRDRB_RLC_AM (388 of 388 that name profiles; "
      "23R1 bearers name none).")
def _nr_bearers(site: Site) -> Iterator[Finding]:
    for gnb in site.of("NRBTS"):
        def resolve(v: Optional[str]) -> Optional[str]:
            return v if not v or v.startswith("MRBTS-") else f"{gnb['dn']}/{v}"
        for m in site.of("NRDRB_5QI", gnb["dn"]) + site.of("NRDRB_QCI", gnb["dn"]) + site.of("NRDRB", gnb["dn"]):
            refs = {"nrDrbDN": "NRDRB"} if m["cls"] != "NRDRB" else _BEARER_REFS
            for name, cls in refs.items():
                v = resolve(m["p"].get(name))
                target = site.by_dn.get(v) if v else None
                if not v or target is None and m["p"][name].startswith("MRBTS-"):
                    continue  # unset, or missing: the reference rule reports that
                if target is None or target["cls"] != cls:
                    yield {"title": f"{_label(m['dn'])}.{name} names {_label(v)}",
                           "detail": f"It must name an {cls}" + (f"; {_label(v)} is an {target['cls']}." if target
                                                                 else f", and {_label(v)} isn't in this file."),
                           "targets": [(_pid(m["dn"], name), _label(m["dn"]))]}
            if m["cls"] == "NRDRB" and any(m["p"].get(k) for k in _BEARER_REFS):
                mode = m["p"].get("rlcMode")
                need = {"RLC_UM": "nrDrbRlcUmDN", "RLC_AM": "nrDrbRlcAmDN"}.get(mode or "")
                if need and not m["p"].get(need):
                    yield {"title": f"{_label(m['dn'])} is {mode} but names no {_BEARER_REFS[need]}",
                           "detail": f"A bearer in {mode} takes its RLC settings from the profile {need} names.",
                           "targets": [(_pid(m["dn"], "rlcMode"), _label(m["dn"]))]}


@rule("qos-unique", "A 5QI or QCI is mapped twice", "id", "error", "files",
      "No gNB maps one 5QI twice for one slice, or one EN-DC QCI twice (0 in the files). Production maps 5QI 6 twice, "
      "for different slices; a mapping that names no slice covers them all.")
def _qos_unique(site: Site) -> Iterator[Finding]:
    for gnb in site.of("NRBTS"):
        for cls, values in (("NRDRB_5QI", "fiveqiValueList"), ("NRDRB_QCI", "qciValueList")):
            seen: dict[str, list[tuple[dict, set[str]]]] = defaultdict(list)
            for m in site.of(cls, gnb["dn"]):
                slices = {r.get("snssaiDN") or "" for r in m["lists"].get("snssaiList", [])}
                for v in m["simple"].get(values, []):
                    for other, theirs in seen[v]:
                        if not slices or not theirs or slices & theirs:
                            yield {"title": f"{'5QI' if cls == 'NRDRB_5QI' else 'QCI'} {v} is mapped by "
                                            f"{_label(other['dn'])} and {_label(m['dn'])}",
                                   "detail": "Which bearer its flows get is ambiguous"
                                             + (": they name the same slice, or one names none." if cls == "NRDRB_5QI"
                                                else "."),
                                   "targets": [(other["dn"], _label(other["dn"])), (m["dn"], _label(m["dn"]))]}
                    seen[v].append((m, slices))


_QCI_PROFILES = {"pdcpProfIdx": "pdcpProf", "nrPdcpProfIdx": "pdcpProf", "rlcProfIdx": "rlcProf",
                 "rlcProfIdx3cc": "rlcProf", "rlcProfIdx4cc5cc": "rlcProf"}


@rule("qci-profiles", "A QCI names a PDCP or RLC profile that isn't defined", "id", "error", "files",
      "Every LNBTS qciTabN pdcpProfIdx, nrPdcpProfIdx and rlcProfIdx (and its 3cc and 4cc5cc variants) names a "
      "pdcpProfN or rlcProfN list of the eNB (2,799 of 2,799). rlcProfIdx6cc7cc is left out: 130 rows name an "
      "rlcProf7 or 8 that their release doesn't have.")
def _qci_profiles(site: Site) -> Iterator[Finding]:
    for lnbts in site.of("LNBTS"):
        for ln, rows in lnbts["lists"].items():
            if not re.match(r"qciTab\d+$", ln) or not rows:
                continue
            for name, prefix in _QCI_PROFILES.items():
                v = rows[0].get(name)
                if v and f"{prefix}{v}" not in lnbts["lists"]:
                    yield {"title": f"{ln}.{name} names {prefix}{v}, which isn't defined",
                           "detail": f"The eNB has no {prefix}{v} list, so QCI {ln[6:]} bearers have no "
                                     f"{'PDCP' if prefix == 'pdcpProf' else 'RLC'} settings.",
                           "targets": [(f"{lnbts['dn']}::list::{ln}::item::0::p::{name}", ln)]}


@rule("mme-transport", "An MME uses a transport network that isn't defined", "id", "error", "files",
      "LNMME.transportNwId is a TRSNW.transportNwId in every file with TRSNW (149 of 149).")
def _mme_transport(site: Site) -> Iterator[Finding]:
    for lnbts in site.of("LNBTS"):
        nets = {m["p"].get("transportNwId") for m in site.of("TRSNW", lnbts["dn"])}
        if not nets:
            continue
        for mme in site.of("LNMME", lnbts["dn"]):
            v = mme["p"].get("transportNwId")
            if v is not None and v not in nets:
                yield {"title": f"{_label(mme['dn'])} uses transport network {v}",
                       "detail": f"The eNB's TRSNW objects define transport networks {', '.join(sorted(nets))}.",
                       "targets": [(_pid(mme["dn"], "transportNwId"), _label(mme["dn"]))]}


# --- Value links ---------------------------------------------------------------

@rule("inter-frequency", "An inter-frequency neighbour has no carrier settings", "value", "warning", "files",
      "Each inter-frequency LNREL has an IRFIM for the target EARFCN on its cell: 505/505 towards own cells, "
      "427/427 towards neighbour-eNB cells in production (21 of 36 planned ones in lab files). Usually an LNHOIF "
      "too (499/505).")
def _inter_frequency(site: Site) -> Iterator[Finding]:
    for lnbts in site.of("LNBTS"):
        own = _own_enb_ids(site, lnbts)
        cells = {c["p"].get("lcrId"): c for c in site.child(lnbts["dn"], "LNCEL")}
        adjl = _adjl(site, lnbts)
        for cell in cells.values():
            mine = _earfcn(site, cell)
            irfim = {m["p"].get("dlCarFrqEut") for m in site.child(cell["dn"], "IRFIM")}
            lnhoif = {m["p"].get("eutraCarrierInfo") for m in site.child(cell["dn"], "LNHOIF")}
            missing: dict[str, list[dict]] = defaultdict(list)
            for rel in site.child(cell["dn"], "LNREL"):
                key = (rel["p"].get("ecgiAdjEnbId"), rel["p"].get("ecgiLcrId"))
                if key[0] in own and key[1] in cells:
                    target = _earfcn(site, cells[key[1]])
                elif key in adjl:
                    target = adjl[key]["p"].get("fDlEarfcn")
                else:
                    continue
                if target and mine and target != mine and target not in irfim:
                    missing[target].append(rel)
            for target, rels in missing.items():
                yield {"title": f"{_label(cell['dn'])} has neighbours on EARFCN {target} but no IRFIM for it",
                       "detail": f"{len(rels)} relation{'s' if len(rels) != 1 else ''} to that carrier. Idle-mode "
                                 "reselection to it needs an IRFIM with that dlCarFrqEut"
                                 + ("" if target in lnhoif else ", and handover usually an LNHOIF") + ".",
                       "targets": [(cell["dn"], _label(cell["dn"]))] + [(r["dn"], _label(r["dn"])) for r in rels[:3]]}


@rule("cable-ports", "Two cables use one module port", "value", "error", "files",
      "No file cables a module port twice (137/137 files).")
def _cable_ports(site: Site) -> Iterator[Finding]:
    by_port: dict[tuple, list[dict]] = defaultdict(list)
    for m in site.of("CABLINK"):
        for end in ("first", "second"):
            p = m["p"]
            if p.get(f"{end}EndpointDN") and p.get(f"{end}EndpointPortId"):
                by_port[(p[f"{end}EndpointDN"], p.get(f"{end}EndpointLabel") or "", p[f"{end}EndpointPortId"])].append(m)
    for (dn, lab, port), links in by_port.items():
        if len(links) > 1:
            yield {"title": f"{_label(dn)} {lab} {port} has {len(links)} cables",
                   "detail": "A port takes one cable: move one of them to a free port.",
                   "targets": [(dn, _label(dn))] + [(m["dn"], _label(m["dn"])) for m in links]}


@rule("radio-cables", "A radio has no cable", "value", "warning", "files",
      "Where any radio of a file is cabled (CABLINK) every one is (91/91 files; Flexi Zone files cable none).")
def _radio_cables(site: Site) -> Iterator[Finding]:
    cabled = {m["p"].get(end) for m in site.of("CABLINK") for end in ("firstEndpointDN", "secondEndpointDN")}
    radios = site.of("RMOD")
    if not any(r["dn"] in cabled for r in radios):
        return
    for r in radios:
        if r["dn"] not in cabled:
            yield {"title": f"{_label(r['dn'])} has no cable",
                   "detail": "The site's other radios are cabled to a baseband card (CABLINK); this one isn't, so it "
                             "can't carry a cell.",
                   "targets": [(r["dn"], _label(r["dn"]))]}


@rule("route-gateway", "A static route's gateway is off the BTS's subnets", "value", "warning", "official",
      "The dictionary requires the gateway on one of the BTS's subnets, and not its lowest or highest address "
      "(IPRT gateway, IPRTV6 gatewayIpv6Addr). 270 of 274 IPv4 routes in the corpus follow it; 3 lab files "
      "route via 10.0.1.254 from 72.16.0.0/24.")
def _route_gateway(site: Site) -> Iterator[Finding]:
    import ipaddress
    from .transport import subnets
    nets = [n for _, n in subnets(site)]
    if not nets:
        return
    for cls, lname, field in (("IPRT", "staticRoutes", "gateway"), ("IPRTV6", "staticIpv6Routes", "gatewayIpv6Addr")):
        for m in site.of(cls):
            if _runtime(m["dn"]):
                continue
            for i, row in enumerate((m.get("lists") or {}).get(lname, [])):
                try:
                    gw = ipaddress.ip_address((row.get(field) or "").strip())
                except ValueError:
                    continue
                on = [n for n in nets if n.version == gw.version and gw in n]
                at = f"{m['dn']}::list::{lname}::item::{i}::p::{field}"
                if not any(n.version == gw.version for n in nets):
                    continue
                if not on:
                    yield {"title": f"{_label(m['dn'])} routes via {gw}, off the BTS's subnets",
                           "detail": "The BTS reaches a next hop only on its own links: put the gateway on one of "
                                     "its subnets (" + ", ".join(str(n) for n in nets if n.version == gw.version)
                                     + "), or fix the address.",
                           "targets": [(at, _label(m["dn"]))]}
                elif all(n.num_addresses > 2 and gw in (n.network_address, n.broadcast_address) for n in on):
                    yield {"title": f"{_label(m['dn'])} routes via {gw}, the edge of {on[0]}",
                           "detail": "The dictionary doesn't allow a subnet's lowest or highest address as a "
                                     "gateway.",
                           "targets": [(at, _label(m["dn"]))]}


@rule("sync-radios", "A radio isn't in the sync target list", "value", "warning", "files",
      "Where SYNC.targetDNList is used it lists every RMOD (165/165).")
def _sync_radios(site: Site) -> Iterator[Finding]:
    syncs = [s for s in site.of("SYNC") if s["simple"].get("targetDNList")]
    if not syncs:
        return
    listed = {v for s in syncs for v in s["simple"]["targetDNList"]}
    for rmod in site.of("RMOD"):
        if rmod["dn"] not in listed:
            yield {"title": f"{_label(rmod['dn'])} isn't in SYNC.targetDNList",
                   "detail": "The other radios are, so this one won't get the site's synchronisation.",
                   "targets": [(rmod["dn"], _label(rmod["dn"]))] + [(s["dn"], _label(s["dn"])) for s in syncs]}


# --- Companions ----------------------------------------------------------------

# Objects compared between sibling cells. Their children that come one per
# relation or carrier vary legitimately, so they aren't compared.
_COMPANION_PARENTS = ("LNCEL", "NRCELL", "LCELL", "LCELNR")
_PER_RELATION = {
    "AMLEPR", "CAPR", "CAREL", "CAIMLBS", "IRFIM", "LNHOIF", "LNREL", "LNRELG", "LNRELW", "LNRELX",
    "LNRELGNBCELL", "LNRELNRCELL", "NRREL", "NRRELE", "REDRT", "CHANNELGROUP", "CHANNEL", "MTRACE",
}


@rule("companions", "A cell lacks an object its siblings have", "companion", "info", "files",
      "Per-cell objects are 1:1 across the cells of every production file.")
def _companions(site: Site) -> Iterator[Finding]:
    for cls in _COMPANION_PARENTS:
        by_parent: dict[str, list[dict]] = defaultdict(list)
        for m in site.of(cls):
            by_parent[_parent(m["dn"])].append(m)
        for siblings in by_parent.values():
            if len(siblings) < 3:
                continue
            have: dict[str, set[str]] = {}
            for m in siblings:
                have[m["dn"]] = {re.sub(r"_(FDD|TDD)$", "_FDD/TDD", k["cls"])
                                 for k in site.kids.get(m["dn"], [])} - _PER_RELATION
            counts: dict[str, int] = defaultdict(int)
            for kinds in have.values():
                for k in kinds:
                    counts[k] += 1
            for m in siblings:
                lacking = sorted(k for k, n in counts.items() if n >= len(siblings) - 1 and k not in have[m["dn"]])
                if lacking:
                    yield {"title": f"{_label(m['dn'])} has no {', '.join(lacking)}",
                           "detail": f"Every other {cls} here has {'it' if len(lacking) == 1 else 'them'}.",
                           "targets": [(m["dn"], _label(m["dn"]))]}


def run(site: Site) -> list[dict]:
    """Every rule's findings on the file, in rule order."""
    out = []
    for r in RULES:
        for f in r["check"](site):
            out.append({
                "severity": f.get("severity", r["severity"]),
                "basis": r["basis"],
                "rule": None,
                "ruleId": r["id"],
                "ruleTitle": r["title"],
                "evidence": r["evidence"],
                "title": f["title"],
                "detail": f["detail"],
                "targets": [{"id": i, "label": lab} for i, lab in f["targets"]],
            })
    return out

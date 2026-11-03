"""
The reference map behind GET /api/files/{f}/refmap: which managed objects
point at which, for the Map view.

Two kinds of link:
- ref: a parameter, list value or row field holding another object's
  distName (the same values the site check's reference rule reads).
- id: a link a Nokia file makes by id rather than distName, the ones the
  site check's id rules match: a cell and its LCELL/LCELNR channel mapping
  (lcrId), an NRCELLGRP and its NRCELLs (nrCellList), an NRDU and its cell
  groups (refNrCellGroup), an LNREL and its target cell (ecgiAdjEnbId +
  ecgiLcrId), an LNRELGNBCELL and its gNB (nrCellId's gNB id). Implied,
  so the map draws them dashed and says what matched.

A ref whose target isn't in the file is kept with `missing` set to why
(absent, another site, outside a partial export), so the map can show it
broken. Runtime objects (_R) and INVUNIT are skipped when their target is
missing, as the site check does: a runtime export doesn't carry the
configuration they point at.

Every edge names the node id of the value it comes from (the tree's id
scheme), so the map can explain that parameter.

Pure: works on ca._load() output.
"""
from __future__ import annotations

from typing import Iterator, Optional

from .actions.links import _DN, Site, _adjl, _own_enb_ids, _pid, _runtime, _values
from .ca import _instance, _int, _load

# The first of these an object has is its hint on the map: a name, an
# address or the value that says what it is.
_HINTS = ("cellName", "enbName", "btsName", "gnbName", "antennaLabel", "localIpAddr", "ipAddrPrim", "vnfIpAddress",
          "cPlaneIpAddr", "vlanId", "prodCodePlanned", "productCode", "sst", "lcrId", "adjEnbId", "adjGnbId")


def _hint(m: dict) -> Optional[str]:
    p, simple = m["p"], m["simple"]
    for key, label in (("fiveqiValueList", "5QI"), ("qciValueList", "QCI")):
        if simple.get(key):
            return f"{label} {', '.join(simple[key])}"
    for k in _HINTS:
        v = p.get(k)
        if v in (None, ""):
            continue
        if k == "localIpAddr" and p.get("localIpPrefixLength"):
            return f"{v}/{p['localIpPrefixLength']}"
        if k == "vlanId":
            return f"VLAN {v}"
        if k == "sst":
            return f"SST {v}" + (f" · SD {p['sd']}" if p.get("sd") else "")
        if k in ("lcrId", "adjEnbId", "adjGnbId"):
            return f"{k} {v}"
        return v
    return None


def _ref_edges(site: Site) -> Iterator[dict]:
    for m in site.mos:
        runtime = _runtime(m["dn"])
        for node, name, v in _values(m):
            if not v or not _DN.match(v) or v == m["dn"]:
                continue
            edge = {"s": m["dn"], "t": v, "via": name, "at": node, "kind": "ref"}
            if v in site.by_dn:
                yield edge
                continue
            if runtime or _runtime(v):
                continue
            root = v.split("/", 1)[0]
            if site.roots and root not in site.roots:
                edge["missing"] = "other-site"
            elif "/".join(v.split("/", 2)[:2]) not in site.by_dn:
                edge["missing"] = "outside"
            else:
                edge["missing"] = "absent"
            yield edge


def _id_edges(site: Site) -> Iterator[dict]:
    def edge(src: dict, dst: dict, via: str, at: str, why: str) -> dict:
        return {"s": src["dn"], "t": dst["dn"], "via": via, "at": at, "kind": "id", "why": why}

    for cm in site.of("CELLMAPPING"):
        root = cm["dn"].split("/", 1)[0]
        for cell_cls, map_cls in (("LNCEL", "LCELL"), ("NRCELL", "LCELNR")):
            maps = {_instance(m["dn"]): m for m in site.of(map_cls, root)}
            for c in site.of(cell_cls, root):
                lcr = c["p"].get("lcrId")
                if lcr in maps:
                    yield edge(c, maps[lcr], "lcrId", _pid(c["dn"], "lcrId"),
                               f"{map_cls}-{lcr} is the channel mapping of the cell with lcrId {lcr}.")
    for nrbts in site.of("NRBTS"):
        cells = {_instance(c["dn"]): c for c in site.of("NRCELL", nrbts["dn"])}
        groups = {_instance(g["dn"]): g for g in site.of("NRCELLGRP", nrbts["dn"])}
        for g in groups.values():
            for i, v in enumerate(g["simple"].get("nrCellList", [])):
                if v in cells:
                    yield edge(g, cells[v], f"nrCellList[{i + 1}]", f"{g['dn']}::list::nrCellList::item::{i}",
                               f"nrCellList holds NRCELL instance ids: {v}.")
        for du in site.of("NRDU", nrbts["dn"]):
            for i, v in enumerate(du["simple"].get("refNrCellGroup", [])):
                if v in groups:
                    yield edge(du, groups[v], f"refNrCellGroup[{i + 1}]",
                               f"{du['dn']}::list::refNrCellGroup::item::{i}",
                               f"refNrCellGroup holds NRCELLGRP instance ids: {v}.")
    for lnbts in site.of("LNBTS"):
        own = _own_enb_ids(site, lnbts)
        cells = {c["p"].get("lcrId"): c for c in site.child(lnbts["dn"], "LNCEL")}
        adjl = _adjl(site, lnbts)
        for rel in site.of("LNREL", lnbts["dn"]):
            enb, lcr = rel["p"].get("ecgiAdjEnbId"), rel["p"].get("ecgiLcrId")
            target = adjl.get((enb, lcr)) or (cells.get(lcr) if enb in own else None)
            if target:
                yield edge(rel, target, "ecgiAdjEnbId + ecgiLcrId", _pid(rel["dn"], "ecgiLcrId"),
                           f"eNB {enb}, cell {lcr}: " + ("a cell of this eNB." if target["cls"] == "LNCEL"
                                                         else "the neighbour cell defined under its LNADJ."))
        gnbs = {m["p"]["adjGnbId"]: m for m in site.of("LNADJGNB", lnbts["dn"]) if m["p"].get("adjGnbId")}
        for rel in site.of("LNRELGNBCELL", lnbts["dn"]) if gnbs else ():
            nci, length = _int(rel["p"].get("nrCellId")), _int(rel["p"].get("gnbIdLength"))
            if not nci or length is None or not 22 <= length <= 32:
                continue
            gnb = str(nci >> (36 - length))
            if gnb in gnbs:
                yield edge(rel, gnbs[gnb], "nrCellId", _pid(rel["dn"], "nrCellId"),
                           f"nrCellId {nci} is a cell of gNB {gnb} (its top {length} bits).")


def build(mos: list[dict]) -> dict:
    site = Site(mos)
    edges, seen = [], set()
    for e in list(_ref_edges(site)) + list(_id_edges(site)):
        key = (e["s"], e["t"], e["via"])
        if key not in seen:
            seen.add(key)
            edges.append(e)
    nodes = [{"id": m["dn"], "cls": m["cls"], **({"hint": h} if (h := _hint(m)) else {}),
              **({"runtime": True} if _runtime(m["dn"]) else {})} for m in mos if m["dn"]]
    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {"objects": len(nodes), "links": len(edges),
                  "missing": sum(1 for e in edges if e.get("missing")),
                  "implied": sum(1 for e in edges if e["kind"] == "id")},
    }


def refmap(raw: bytes) -> dict:
    return build(_load(raw))


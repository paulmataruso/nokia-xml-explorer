"""
Hardware knowledge for the hardware actions: which objects carry an
editable product code, what each module has around it (antennas, links,
SFPs), and what the BTS itself reported.

Planned codes live on RMOD, BBMOD and SMOD (prodCodePlanned) and on ALD
(productCode). *_R objects carry what the BTS detected and are never
edited; BBMOD_R/SMOD_R also report the module's core board
(coreHwBoardProductCode), which is not a module code. PROJECT_STATE §9.9
("Hardware actions") has the evidence.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Optional

from ..ca import _instance, _label, _parent
from .links import Site

EDITABLE = {"RMOD": "prodCodePlanned", "BBMOD": "prodCodePlanned", "SMOD": "prodCodePlanned", "ALD": "productCode"}
KIND = {"RMOD": "radio", "BBMOD": "baseband", "SMOD": "system module", "ALD": "antenna-line device"}

# Catalog kinds (product_codes.json) a class may take. A Flexi Zone small
# cell's own code sits on its SMOD (FWHT 473531A, FWHR 473548A in the
# corpus), and its RMOD takes a name-style code (FR2HH). ALDs are
# third-party RETs and TMAs, which the catalog doesn't cover.
CLASS_KINDS = {
    "RMOD": {"radio", "mmimo-radio"},
    "BBMOD": {"baseband"},
    "SMOD": {"system-module", "small-cell"},
    "ALD": set(),
}

# How a catalog kind reads in a sentence.
KIND_LABELS = {
    "radio": "radio", "mmimo-radio": "massive-MIMO radio", "small-cell": "small cell",
    "baseband": "baseband card", "system-module": "system module", "sfp": "SFP transceiver",
    "power": "power module", "cable": "cable", "gnss": "GNSS part", "subrack": "subrack",
    "alarm": "alarm module", "antenna": "antenna",
}

NOKIA_CODE = re.compile(r"^\d{6}[A-Z](\.\d{3})?$")


def base(code: Optional[str]) -> str:
    """"474020A.102" -> "474020A"; codes of other shapes (FR2HH) as given."""
    code = (code or "").strip()
    return code.split(".", 1)[0] if NOKIA_CODE.match(code) else code


def _cells_by_lcr(site: Site) -> dict[str, str]:
    out = {}
    for cls in ("LNCEL", "NRCELL"):
        for m in site.of(cls):
            if m["p"].get("lcrId"):
                out[m["p"]["lcrId"]] = _label(m["dn"])
    return out


def modules(site: Site) -> list[dict]:
    """Every object with an editable product code, with its surroundings."""
    links: dict[str, list[dict]] = defaultdict(list)
    for m in site.of("CABLINK"):
        for end in ("firstEndpointDN", "secondEndpointDN"):
            if m["p"].get(end):
                links[m["p"][end]].append(m)
    detected: dict[str, dict] = {}
    for m in site.mos:
        if m["cls"].endswith("_R") and m["p"].get("configDN") and m["p"].get("productCode") not in (None, "-"):
            detected[m["p"]["configDN"]] = m["p"]
    cell_of = _cells_by_lcr(site)
    users: dict[str, set[str]] = defaultdict(set)
    for ch in site.of("CHANNEL"):
        target = ch["p"].get("antlDN") or ch["p"].get("resourceDN") or ""
        mapping = next((part for part in ch["dn"].split("/") if part.startswith(("LCELL-", "LCELNR-", "LCELW-"))), None)
        rmod = re.match(r".*?/RMOD-[^/]+", target)
        if rmod and mapping:
            users[rmod.group(0)].add(cell_of.get(_instance(mapping), mapping))

    out = []
    for cls, param in EDITABLE.items():
        for m in site.of(cls):
            kids = Counter(k["cls"] for k in site.kids.get(m["dn"], []))
            rt = detected.get(m["dn"]) or {}
            mine = links.get(m["dn"], [])
            out.append({
                "dn": m["dn"],
                "label": _label(m["dn"]),
                "class": cls,
                "param": param,
                "code": m["p"].get(param),
                "antl": kids.get("ANTL", 0),
                "phyant": kids.get("PHYANT", 0),
                "rsl": kids.get("RSL", 0),
                "sfp": kids.get("SFP", 0),
                "eacIn": kids.get("EAC_IN", 0),
                "config": m["p"].get("bbmodBoardConfigType"),
                "links": len(mine),
                "protocols": sorted({l["p"].get("radioProtocolType") for l in mine if l["p"].get("radioProtocolType")}),
                "detected": {"code": rt.get("productCode"), "name": rt.get("productName"),
                             "coreBoard": rt.get("coreHwBoardProductCode")} if rt else None,
                "cells": sorted(users.get(m["dn"], ())),
                "parent": _label(_parent(m["dn"])),
                # Flexi Zone small cells version their equipment "EQM23R1_FZM_...".
                "fzm": "_FZM_" in (m["version"] or ""),
            })
    return out


def evidence(mos: list[dict]) -> dict:
    """What the corpus index keeps per file for the hardware actions: each
    module's code with its surroundings, the names the BTS reported for
    codes, and which core boards sit in which modules."""
    site = Site(mos)
    names: dict[str, str] = {}
    core: dict[str, str] = {}
    for m in mos:
        p = m["p"]
        if m["cls"].endswith("_R") and p.get("productCode") not in (None, "-", "0000000000"):
            if p.get("productName"):
                names.setdefault(base(p["productCode"]), p["productName"])
            if p.get("coreHwBoardProductCode"):
                core.setdefault(base(p["coreHwBoardProductCode"]), base(p["productCode"]))
            if p.get("chassisProductCode"):
                core.setdefault(base(p["chassisProductCode"]), base(p["productCode"]))
    shapes = []
    for mod in modules(site):
        if mod["code"]:
            shapes.append({k: mod[k] for k in ("class", "code", "antl", "phyant", "rsl", "sfp", "eacIn", "config",
                                                "links", "protocols", "fzm")})
    return {"modules": shapes, "names": names, "coreBoards": core, "cellRadios": cell_radios(site),
            "radios": radio_shapes(site), "basebands": baseband_ports(site)}


# Radio values that name the template's place, never copied to a new radio.
PLACE_PARAMS = {"RMOD": ("moduleLocation",), "ANTL": ("antennaLabel",)}


def cables(site: Site, dn: str) -> list[dict]:
    """The CABLINKs with `dn` at either end, in file order."""
    return [m for m in site.of("CABLINK") if dn in (m["p"].get("firstEndpointDN"), m["p"].get("secondEndpointDN"))]


def used_ports(site: Site, dn: str) -> set[tuple[str, str]]:
    """(label, port id) of every port of module `dn` a CABLINK uses."""
    out = set()
    for m in cables(site, dn):
        for end in ("first", "second"):
            p = m["p"]
            if p.get(f"{end}EndpointDN") == dn and p.get(f"{end}EndpointPortId"):
                out.add((p.get(f"{end}EndpointLabel") or "", p[f"{end}EndpointPortId"]))
    return out


def radio_shapes(site: Site) -> list[dict]:
    """Each coded radio, for the add-radio action's templates from other
    files: where it is (`dn`, read again at plan time), its code, antennas
    and cables. `sig` tells radios with the same values apart."""
    out = []
    for m in site.of("RMOD"):
        code = base(m["p"].get("prodCodePlanned"))
        if not code:
            continue
        kids = [k for k in site.kids.get(m["dn"], []) if k["cls"] in ("ANTL", "PHYANT", "RSL")]
        mine = cables(site, m["dn"])
        content = {"p": {k: v for k, v in m["p"].items() if k not in PLACE_PARAMS["RMOD"]}, "lists": m["lists"],
                   "kids": sorted((_label(k["dn"]), sorted((n, v) for n, v in k["p"].items()
                                                           if n not in PLACE_PARAMS.get(k["cls"], ()))) for k in kids),
                   "cables": [sorted((n, v) for n, v in c["p"].items() if not n.startswith(("first", "secondEndpointDN")))
                              for c in mine]}
        out.append({"dn": m["dn"], "code": code, "antl": sum(k["cls"] == "ANTL" for k in kids),
                    "phyant": sum(k["cls"] == "PHYANT" for k in kids), "cables": len(mine),
                    "protocols": sorted({c["p"].get("radioProtocolType") for c in mine if c["p"].get("radioProtocolType")}),
                    "fzm": "_FZM_" in (m["version"] or ""), "version": m["version"],
                    "sig": hashlib.sha1(json.dumps(content, sort_keys=True).encode()).hexdigest()[:12]})
    return out


def baseband_ports(site: Site) -> list[dict]:
    """The ports each coded baseband card has cables on, so the action knows
    which ports a card of that kind has."""
    return [{"code": base(m["p"].get("prodCodePlanned")), "ports": sorted(used_ports(site, m["dn"]))}
            for m in site.of("BBMOD") if m["p"].get("prodCodePlanned")]


# NRCELL parameters that follow the radio: 476108A (32TRX) and 476268A
# (64TRX) cells differ in them and nothing else (PROJECT_STATE §9.9).
RADIO_PARAMS = ("mMimoAntArrayMode", "numberOfRxBeamforming", "numberOfRxPucch", "pMax")


def cell_radios(site: Site) -> list[dict]:
    """Each NR cell's radio code with its radio-dependent parameters."""
    code = {m["dn"]: base(m["p"].get("prodCodePlanned")) for m in site.of("RMOD")}
    out = []
    for cell in site.of("NRCELL"):
        lcr = cell["p"].get("lcrId")
        mapping = next((m for m in site.of("LCELNR") if _instance(m["dn"]) == lcr
                        and m["dn"].split("/", 1)[0] == cell["dn"].split("/", 1)[0]), None)
        target = next((ch["p"].get("resourceDN") or ch["p"].get("antlDN")
                       for ch in site.of("CHANNEL", mapping["dn"]) if ch["p"].get("resourceDN") or ch["p"].get("antlDN")),
                      None) if mapping else None
        rmod = re.match(r".*?/RMOD-[^/]+", target or "")
        if rmod and code.get(rmod.group(0)):
            out.append({"code": code[rmod.group(0)], "p": {k: cell["p"][k] for k in RADIO_PARAMS if k in cell["p"]}})
    return out


def corpus_view(corpus: list[dict]) -> dict:
    """Pooled evidence: codes seen per class with counts, the usual shape of
    a module with each code, whether it was on Flexi Zone (FZM) equipment,
    reported names and core boards."""
    seen: dict[str, Counter] = defaultdict(Counter)
    shapes: dict[tuple[str, str], Counter] = defaultdict(Counter)
    platforms: dict[tuple[str, str], set] = defaultdict(set)
    names: dict[str, str] = {}
    core: dict[str, str] = {}
    for f in corpus:
        hw = f.get("hardware") or {}
        for mod in hw.get("modules", []):
            b = base(mod["code"])
            seen[mod["class"]][b] += 1
            key = (mod["antl"], mod["phyant"], mod["rsl"], mod["sfp"], mod["eacIn"], mod["config"],
                   tuple(mod["protocols"]))
            shapes[(mod["class"], b)][key] += 1
            platforms[(mod["class"], b)].add(mod.get("fzm", False))
        for k, v in hw.get("names", {}).items():
            names.setdefault(k, v)
        for k, v in hw.get("coreBoards", {}).items():
            core.setdefault(k, v)
    usual = {}
    for (cls, b), counter in shapes.items():
        (antl, phyant, rsl, sfp, eac, config, protocols), n = counter.most_common(1)[0]
        usual[(cls, b)] = {"antl": antl, "phyant": phyant, "rsl": rsl, "sfp": sfp, "eacIn": eac, "config": config,
                           "protocols": list(protocols), "count": sum(counter.values()), "majority": n}
    return {"seen": seen, "usual": usual, "platforms": platforms, "names": names, "coreBoards": core}

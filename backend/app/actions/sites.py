"""
What a file says about its own eNBs and gNBs as seen from a neighbour: the
ids, PLMN, C-plane address and cells another site's LNADJ/LNADJL or
LNADJGNB/LNRELGNBCELL would name. main.py keeps it per file in the corpus
index, so the neighbour actions can offer every site in the tool.

The ids (measured on the corpus):
  - eNB id = the LNBTS instance (LNADJ.adjEnbId names it). ECGI = eNB id
    and the cell's lcrId.
  - gNB id = the NRBTS instance, gNbIdLength bits long. NCI = gNB id
    shifted left by 36 - gNbIdLength, plus the cell's lcrId
    (NRCELL.nrCellIdentity where a file writes it, 19 of 19 cells;
    LNRELGNBCELL.nrCellId). A file that leaves gNbIdLength out but writes
    nrCellIdentity still tells it: the one length that splits each NCI
    into this gNB's id and the cell's lcrId.

A gNB has two addresses here: the one an eNB's LNADJGNB names (X2-C) and
the one another gNB's XNLINK names (Xn-C). Every gNB in the corpus uses one
address for all its planes, but the lists say which plane is which.

Pure: works on ca._load() output.
"""
from __future__ import annotations

from typing import Optional

from .doc import instance, release_of
from .links import Site
from .transport import address, lte_cplane

# LNCEL_FDD dlChBw / LNCEL_TDD chBw -> resource blocks.
NRB = {"1.4 MHz": 6, "3 MHz": 15, "5 MHz": 25, "10 MHz": 50, "15 MHz": 75, "20 MHz": 100}


def _plmn(p: dict) -> Optional[dict]:
    if p.get("mcc") in (None, "") or p.get("mnc") in (None, ""):
        return None
    return {"mcc": p["mcc"], "mnc": p["mnc"], "mncLength": p.get("mncLength") or str(max(2, len(p["mnc"])))}


def lte_cell(site: Site, cell: dict) -> dict:
    p = cell["p"]
    out = {"lcrId": p.get("lcrId"), "pci": p.get("phyCellId"), "tac": p.get("tac"), "name": p.get("cellName"),
           "earfcn": None, "bw": None, "tdd": False}
    for m in site.child(cell["dn"], "LNCEL_FDD"):
        out.update(earfcn=m["p"].get("earfcnDL"), bw=m["p"].get("dlChBw"))
    for m in site.child(cell["dn"], "LNCEL_TDD"):
        out.update(earfcn=m["p"].get("earfcn"), bw=m["p"].get("chBw"), tdd=True)
    return out


def _plane_address(site: Site, gnb: dict, planes: tuple[str, ...]) -> Optional[str]:
    for plane in planes:
        for row in (gnb.get("lists") or {}).get(plane, []):
            a = address(site, row.get("ipV4AddressDN1") or row.get("ipV6AddressDN1"))
            if a:
                return a
    return None


def x2_address(site: Site, gnb: dict) -> Optional[str]:
    """The address an eNB's LNADJGNB names for this gNB: its X2-C plane,
    else the other planes' address."""
    return _plane_address(site, gnb, ("x2Cplane", "ngCplane", "xnCplane", "s1Uplane", "x2Uplane"))


def xn_address(site: Site, gnb: dict) -> Optional[str]:
    """The address another gNB's XNLINK names for this gNB: its Xn-C plane,
    else the other planes' address."""
    return _plane_address(site, gnb, ("xnCplane", "ngCplane", "x2Cplane", "ngUplane", "s1Uplane"))


def nci(gnb_id, id_length, lcr_id) -> Optional[str]:
    """The NR cell identity, or None when a part is missing or doesn't fit."""
    try:
        g, n, c = int(gnb_id), int(id_length), int(lcr_id)
    except (TypeError, ValueError):
        return None
    if not 22 <= n <= 32 or g >= 1 << n or c >= 1 << (36 - n):
        return None
    return str((g << (36 - n)) | c)


def id_length(gnb_id, cells: list[dict]) -> Optional[str]:
    """The gNB id length the cells' nrCellIdentity values imply: the one
    length (22-32) at which every one of them is this gNB's id and the
    cell's lcrId. None without one, or if more than one length fits."""
    known = [(c.get("nrCellIdentity"), c.get("lcrId")) for c in cells]
    known = [(int(n), int(c)) for n, c in known if (n or "").isdigit() and (c or "").isdigit()]
    if not known or not str(gnb_id).isdigit():
        return None
    fits = [n for n in range(22, 33)
            if all(v >> (36 - n) == int(gnb_id) and v & ((1 << (36 - n)) - 1) == c for v, c in known)]
    return str(fits[0]) if len(fits) == 1 else None


def gscn_to_arfcn(gscn: int) -> int:
    """The NR-ARFCN of the SSB at a synchronization raster entry (GSCN), by
    3GPP TS 38.104 tables 5.4.3.1-1 (GSCN to SS_REF) and 5.4.2.1-1 (SS_REF
    to NR-ARFCN). Checked on the corpus: GSCN 6276 gives the 502110 the LTE
    side measures, and 7846 and 22473 give the arfcnSsbPbch their cells
    write (633312, 2079163)."""
    if gscn < 7499:  # 0-3000 MHz: N x 1200 kHz + M x 50 kHz, GSCN = 3N + (M-3)/2
        m = {0: 3, 1: 5, 2: 1}[gscn % 3]
        khz = (gscn - (m - 3) // 2) // 3 * 1200 + m * 50
    elif gscn < 22256:  # 3000-24250 MHz: 3000 MHz + N x 1.44 MHz
        khz = 3000000 + (gscn - 7499) * 1440
    else:  # 24250-100000 MHz: 24250.08 MHz + N x 17.28 MHz
        khz = 24250080 + (gscn - 22256) * 17280
    if khz < 3000000:
        return khz // 5
    if khz < 24250000:
        return 600000 + (khz - 3000000) // 15
    return 2016667 + (khz - 24250080) // 60


# The lowest NR-ARFCN of any band (400 MHz; the lowest FR1 band starts at
# 460 MHz). 34 lab cells write gscnOrSsPbchArfcn 1, which isn't a raster
# entry (GSCN starts at 2): a placeholder, not a frequency.
MIN_ARFCN = 80000


def ssb_arfcn(p: dict) -> Optional[str]:
    """Where a cell's SSB is, as an NR-ARFCN: arfcnSsbPbch if written, else
    gscnOrSsPbchArfcn, which is a GSCN when small (every NR-ARFCN of a real
    band is above 80000) and an NR-ARFCN otherwise. None for a placeholder."""
    if (p.get("arfcnSsbPbch") or "").isdigit():
        return p["arfcnSsbPbch"]
    v = p.get("gscnOrSsPbchArfcn") or ""
    if not v.isdigit():
        return None
    arfcn = gscn_to_arfcn(int(v)) if int(v) < MIN_ARFCN else int(v)
    return str(arfcn) if int(v) >= 2 and arfcn >= MIN_ARFCN else None


def _scs(value: Optional[str]) -> Optional[str]:
    """NRCELL ssbScs ("30 KHz", "15KHz") as "30kHz"."""
    digits = "".join(ch for ch in value or "" if ch.isdigit())
    return f"{digits}kHz" if digits else None


def nr_cell(site: Site, gnb: dict, cell: dict) -> dict:
    p = cell["p"]
    out = {"lcrId": p.get("lcrId"), "pci": p.get("physCellId"), "name": p.get("cellName"), "arfcn": p.get("nrarfcn"),
           "nci": p.get("nrCellIdentity") or nci(instance(gnb["dn"]), gnb["p"].get("gNbIdLength"), p.get("lcrId")),
           "ssb": ssb_arfcn(p), "band": p.get("freqBandIndicatorNR"), "scs": _scs(p.get("ssbScs"))}
    for m in site.child(cell["dn"], "NRCELL_FDD"):
        out["arfcn"] = m["p"].get("nrarfcnDl") or out["arfcn"]
    return out


def summary(mos: list[dict]) -> dict:
    site = Site(mos)
    enbs = []
    for m in site.of("LNBTS"):
        if m["dn"].count("/") != 1:
            continue
        cells = [lte_cell(site, c) for c in site.child(m["dn"], "LNCEL") if c["p"].get("lcrId") not in (None, "")]
        enbs.append({"dn": m["dn"], "id": instance(m["dn"]), "name": m["p"].get("enbName"),
                     "release": release_of(m["version"]), "plmn": _plmn(m["p"]),
                     "ip": lte_cplane(site, m["dn"], None), "rlf": m["p"].get("actRLFbasedRCR"),
                     "cells": cells})
    gnbs = []
    for m in site.of("NRBTS"):
        if m["dn"].count("/") != 1:
            continue
        plmns = [p for p in (_plmn(x["p"]) for x in site.child(m["dn"], "NRPLMN")) if p]
        own = [c for c in site.child(m["dn"], "NRCELL") if c["p"].get("lcrId") not in (None, "")]
        cells = [nr_cell(site, m, c) for c in own]
        length = m["p"].get("gNbIdLength") or id_length(instance(m["dn"]), [c["p"] for c in own])
        gnbs.append({"dn": m["dn"], "id": instance(m["dn"]), "idLength": length,
                     "name": m["p"].get("btsName") or m["p"].get("nrBtsName"),
                     "release": release_of(m["version"]), "plmn": plmns[0] if plmns else None,
                     "ip": x2_address(site, m), "xn": xn_address(site, m), "cells": cells})
    return {"enbs": enbs, "gnbs": gnbs}

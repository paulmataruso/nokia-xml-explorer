"""
What the QoS action (qos.py) reads from a file: every QCI and 5QI profile
with the settings behind it, as values only.

- On a gNB, each NRDRB_5QI (SA) and NRDRB_QCI (EN-DC) mapping with the
  bearer it names (NRDRB) and that bearer's MAC, PDCP, RLC and DRX profiles.
- On an eNB, each qciTabN row with the LNBTS pdcpProfN and rlcProfN rows it
  names.

Identities (distNames, slices, PLMNs) are left out or reduced to instance
ids, so a template from another file carries only profile values. main.py's
corpus index keeps this per file (corpus.py); qos.py also reads the target
file through it.

Pure: works on ca._load() output.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Optional

# NRDRB references to its profiles: parameter -> class.
PARTS = {"nrDrbMacDN": "NRDRB_MAC", "nrDrbPdcpDN": "NRDRB_PDCP", "nrDrbRlcAmDN": "NRDRB_RLC_AM",
         "nrDrbRlcUmDN": "NRDRB_RLC_UM", "nrDrxDN": "NRDRX"}
MAPPINGS = {"NRDRB_5QI": ("5qi", "fiveqiValueList"), "NRDRB_QCI": ("qci", "qciValueList")}

# qciTabN fields that name an LNBTS profile list. rlcProfIdx6cc7cc is left
# out: 130 rows name an rlcProf7 or 8 their release doesn't have.
LTE_PROFILE_FIELDS = {"pdcpProfIdx": "pdcpProf", "nrPdcpProfIdx": "pdcpProf", "rlcProfIdx": "rlcProf",
                      "rlcProfIdx3cc": "rlcProf", "rlcProfIdx4cc5cc": "rlcProf"}
QCI_TAB = re.compile(r"^qciTab(\d+)$")


def _instance(dn: str) -> str:
    return dn.rsplit("-", 1)[-1]


def resolve(by_dn: dict, gnb: str, value: Optional[str]) -> Optional[str]:
    """A reference as the distName it names. One lab export writes them
    relative to the gNB ("NRDRB_MAC-1")."""
    if not value:
        return None
    dn = value if value.startswith("MRBTS-") else f"{gnb}/{value}"
    return dn if dn in by_dn else None


def values_of(m: dict, drop=()) -> dict:
    """An object's settings: scalars, simple lists and item lists."""
    return {"p": {k: v for k, v in m["p"].items() if k not in drop},
            "simple": {k: list(v) for k, v in m["simple"].items()},
            "rows": {k: [dict(r) for r in v] for k, v in m["lists"].items() if k not in m["simple"]}}


def signature(content) -> str:
    return hashlib.sha1(json.dumps(content, sort_keys=True).encode()).hexdigest()[:12]


def bearer(by_dn: dict, gnb: str, drb_dn: Optional[str]) -> Optional[dict]:
    """An NRDRB and its profiles, as values. `parts` is keyed by the NRDRB
    parameter that names each one, with the profile's class and instance."""
    drb = by_dn.get(drb_dn) if drb_dn else None
    if drb is None or drb["cls"] != "NRDRB":
        return None
    out = {"drb": values_of(drb, drop=PARTS), "parts": {}}
    for name, cls in PARTS.items():
        target = resolve(by_dn, gnb, drb["p"].get(name))
        if target and by_dn[target]["cls"] == cls:
            out["parts"][name] = {"cls": cls, "inst": _instance(target), **values_of(by_dn[target])}
    return out


def bearer_signature(b: dict) -> str:
    return signature({"drb": b["drb"], "parts": {k: {x: v[x] for x in ("cls", "p", "simple", "rows")}
                                                 for k, v in b["parts"].items()}})


def gnb_profiles(mos: list[dict], by_dn: dict, gnb: dict) -> list[dict]:
    out = []
    for m in mos:
        kind = MAPPINGS.get(m["cls"])
        if not kind or not m["dn"].startswith(gnb["dn"] + "/"):
            continue
        b = bearer(by_dn, gnb["dn"], resolve(by_dn, gnb["dn"], m["p"].get("nrDrbDN")))
        slices = []
        for row in m["lists"].get("snssaiList", []):
            s = by_dn.get(resolve(by_dn, gnb["dn"], row.get("snssaiDN")) or "")
            slices.append((s["p"].get("sst"), s["p"].get("sd")) if s else (None, None))
        p = {k: v for k, v in m["p"].items() if k != "nrDrbDN"}
        out.append({"kind": kind[0], "dn": m["dn"], "values": list(m["simple"].get(kind[1], [])), "slices": slices,
                    "p": p, "bearer": b, "sig": signature({"p": p, "bearer": b and bearer_signature(b)})})
    return out


def lte_profiles(enb: dict) -> list[dict]:
    lists = enb["lists"]
    out = []
    for name, rows in lists.items():
        q = QCI_TAB.match(name)
        if not q or not rows:
            continue
        row = rows[0]
        profiles = {}
        for field, prefix in LTE_PROFILE_FIELDS.items():
            if row.get(field) and f"{prefix}{row[field]}" in lists:
                profiles[f"{prefix}{row[field]}"] = [dict(r) for r in lists[f"{prefix}{row[field]}"]]
        out.append({"qci": q.group(1), "row": dict(row), "profiles": profiles,
                    "sig": signature({"row": {k: v for k, v in row.items() if k != "qci"}, "profiles": profiles})})
    return sorted(out, key=lambda t: int(t["qci"]))


def summary(mos: list[dict]) -> dict:
    """{"gnbs": [{dn, version, profiles}], "enbs": [{dn, version, tabs,
    lists, fields}]}: `lists` are the LNBTS list names, `fields` the qciTab
    fields this file writes (for the release filter on rows)."""
    by_dn = {m["dn"]: m for m in mos}
    gnbs = [{"dn": g["dn"], "version": g["version"], "profiles": gnb_profiles(mos, by_dn, g)}
            for g in mos if g["cls"] == "NRBTS" and g["dn"].count("/") == 1]
    enbs = []
    for e in mos:
        if e["cls"] != "LNBTS":
            continue
        tabs = lte_profiles(e)
        enbs.append({"dn": e["dn"], "version": e["version"], "tabs": tabs, "lists": set(e["lists"]),
                     "fields": {k for t in tabs for k in t["row"]}})
    return {"gnbs": [g for g in gnbs if g["profiles"]], "enbs": [e for e in enbs if e["tabs"]]}

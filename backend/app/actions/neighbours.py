"""
What the neighbour actions share: the sites of the other files as
candidates (sites.summary per file in the corpus), option labels that tell
look-alike sites apart, PLMN and number fields, and the eNB's limit on
neighbour objects.

The limit is the dictionary's maxNumAnrMoiAllowed (LNBTS): the LNADJ,
LNADJL, LNREL, LNADJW, LNRELW, LNADJT, LNRELT, LNADJG, LNRELG, LNADJX,
LNRELX, LNNEIH, LNADJGNB and LNRELGNBCELL of an eNB together "shall not
exceed" it, and at or close to it the overload alarm is very likely raised
right after activation. The corpus sets 4000 (99 eNBs), 6000 or 12000, and
no eNB is above 80% of it.
"""
from __future__ import annotations

import collections
import json
from typing import Callable, Optional

from . import Context
from .ip_address import addresses
from .links import Site

ANR_CLASSES = ("LNADJ", "LNADJL", "LNREL", "LNADJW", "LNRELW", "LNADJT", "LNRELT", "LNADJG", "LNRELG", "LNADJX",
               "LNRELX", "LNNEIH", "LNADJGNB", "LNRELGNBCELL")


def lte_enbs(site: Site) -> list[dict]:
    """The eNBs with at least one cell."""
    return [m for m in site.of("LNBTS")
            if any(c["p"].get("lcrId") not in (None, "") for c in site.child(m["dn"], "LNCEL"))]


def own_addresses(site: Site) -> set[str]:
    return {m["p"]["localIpAddr"].strip().lower() for m in addresses(site)}


def plmn_text(p: Optional[dict]) -> str:
    if not p:
        return ""
    try:
        return f"{int(p['mcc']):03d}-{int(p['mnc']):0{int(p.get('mncLength') or 2)}d}"
    except (KeyError, ValueError):
        return ""


def parse_plmn(text: str) -> Optional[dict]:
    parts = [x for x in text.replace("/", "-").replace(" ", "-").split("-") if x]
    if len(parts) != 2 or not all(x.isdigit() for x in parts) or len(parts[0]) != 3 or len(parts[1]) not in (2, 3):
        return None
    return {"mcc": str(int(parts[0])), "mnc": str(int(parts[1])), "mncLength": str(len(parts[1]))}


def same_plmn(a: Optional[dict], b: Optional[dict]) -> bool:
    return bool(a and b) and plmn_text(a) == plmn_text(b)


def plmn_of(m: dict, list_name: str) -> Optional[dict]:
    """An adjacency's PLMN: the first row of its PLMN list, else its scalar
    mcc/mnc (older releases)."""
    rows = (m.get("lists") or {}).get(list_name) or [m["p"]]
    return rows[0] if rows[0].get("mcc") not in (None, "") else None


def same_node(m: dict, list_name: str, plmn: Optional[dict]) -> bool:
    """Whether an adjacency with the right id is this neighbour: a global
    eNB/gNB id is the PLMN plus the id, so a different PLMN is another node.
    An adjacency that doesn't say its PLMN counts as the same."""
    have = plmn_of(m, list_name)
    return not have or not plmn or same_plmn(have, plmn)


def number(value, lo: int, hi: int, what: str, problems: list[str]) -> Optional[str]:
    v = (value or "").strip()
    if not v.isdigit() or not lo <= int(v) <= hi:
        problems.append(f"{what} must be a number from {lo} to {hi}" + (f", not {v!r}." if v else "."))
        return None
    return str(int(v))


def sources(ctx: Context, kind: str, skip: Callable[[dict], bool], fields: tuple[str, ...]) -> list[dict]:
    """The other files' eNBs or gNBs (`kind` "enbs" or "gnbs") as candidates:
    one per distinct (`fields`), from the newest file that has it, with how
    many files have it. `skip` drops a site (this one, one without cells)."""
    seen: dict[str, dict] = {}
    for f in sorted(ctx.corpus(), key=lambda f: -(f.get("mtime") or 0)):
        if f["name"] == ctx.filename and f["source"] == ctx.source:
            continue
        for e in (f.get("sites") or {}).get(kind, []):
            if skip(e):
                continue
            sig = json.dumps([e.get(k) for k in fields], sort_keys=True)
            if sig in seen:
                seen[sig]["files"] += 1
                continue
            seen[sig] = {**e, "file": f["name"], "key": f"{f['key']}|{e['dn']}", "files": 1}
    return sorted(seen.values(), key=lambda e: (int(e["id"]) if e["id"].isdigit() else 0, e["file"]))


def from_text(e: dict) -> str:
    return (f"From {e['file']}" + (f" (and {e['files'] - 1} other file{'s' if e['files'] > 2 else ''} with "
                                   "the same cells)" if e["files"] > 1 else "") + ".")


def distinguish(opts: list[dict], found: list[dict], tails: list[str], address: str = "ip") -> None:
    """Sites that read the same get their address, then their file, where
    that tells them apart; the tail (the cell count) stays last."""
    extra = [[] for _ in opts]
    for get in (lambda e: e.get(address), lambda e: e["file"]):
        groups = collections.defaultdict(list)
        for i, o in enumerate(opts):
            groups[" · ".join([o["label"], *extra[i], tails[i]])].append(i)
        for group in groups.values():
            if len(group) > 1 and len({get(found[i]) for i in group}) > 1:
                for i in group:
                    if get(found[i]):
                        extra[i].append(get(found[i]))
    for o, more, tail in zip(opts, extra, tails):
        o["label"] = " · ".join([o["label"], *more, tail])


def anr_budget(site: Site, enb: dict, added: dict[str, int]) -> tuple[Optional[str], Optional[str]]:
    """(problem, note) for the eNB's neighbour objects after `added` (class
    -> count): over maxNumAnrMoiAllowed is refused, within 10% of it noted."""
    limit = enb["p"].get("maxNumAnrMoiAllowed")
    new = sum(n for cls, n in added.items() if cls in ANR_CLASSES)
    if not new or not (limit or "").isdigit():
        return None, None
    now = sum(1 for m in site.mos if m["cls"] in ANR_CLASSES and m["dn"].startswith(enb["dn"] + "/"))
    total, limit = now + new, int(limit)
    if total > limit:
        return (f"The eNB would have {total} neighbour objects (LNADJ, LNADJL, LNREL, LNADJGNB, LNRELGNBCELL and "
                f"the other ANR classes), over its maxNumAnrMoiAllowed of {limit}. Remove unused neighbours first, "
                "or raise the limit."), None
    if total >= 0.9 * limit:
        return None, (f"The eNB would have {total} neighbour objects, within 10% of its maxNumAnrMoiAllowed of "
                      f"{limit}: the dictionary warns the overload alarm is then very likely right after "
                      "activation.")
    return None, None

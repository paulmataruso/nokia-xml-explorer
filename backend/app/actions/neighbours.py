"""
What the neighbour actions share: the sites of the other files as
candidates (sites.summary per file in the corpus), option labels that tell
look-alike sites apart, PLMN and number fields, and the eNB's limit on
neighbour objects.

The candidates come in groups: this file's own sites (co-sited), then the
other files' sites whose address is on the subnet of this site's own (the
one the neighbour faces), nearest address first, then the rest. Two BTSs
on one BBU exported as separate files share that subnet, on neighbouring
addresses (owner, 2026-11-05). It narrows the list, it doesn't prove a
co-site: a lab subnet holds several BTSs (up to 7 addresses on one
target's subnet in the corpus, though no eNB has more than one gNB
address on its own), and one address every export of the BTS that had it
over time. A site at this site's own address is this BTS in another
export (all 66 gNBs on a gNB's subnet are), so it stays with the rest.

The limit is the dictionary's maxNumAnrMoiAllowed (LNBTS): the LNADJ,
LNADJL, LNREL, LNADJW, LNRELW, LNADJT, LNRELT, LNADJG, LNRELG, LNADJX,
LNRELX, LNNEIH, LNADJGNB and LNRELGNBCELL of an eNB together "shall not
exceed" it, and at or close to it the overload alarm is very likely raised
right after activation. The corpus sets 4000 (99 eNBs), 6000 or 12000, and
no eNB is above 80% of it.
"""
from __future__ import annotations

import collections
import ipaddress
import json
from typing import Callable, Optional

from . import Context
from .ip_address import addresses
from .links import Site
from .sites import summary
from .transport import subnets

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


def id_clash(kind: str, nb_id: Optional[str], nb_plmn: Optional[dict], own_id: str,
             own_plmn: Optional[dict]) -> Optional[str]:
    """Why a neighbour eNB or gNB (`kind`) with this site's own id can't be
    added, or None. A global eNB/gNB id is the PLMN plus the id, so two sites
    of one PLMN need different ids; with another PLMN it is another node.
    Lab files reuse ids (eNB 0, gNB 0), so such a site is offered, not
    hidden, and the reason says what to do."""
    if nb_id is None or nb_id != own_id or (nb_plmn and own_plmn and not same_plmn(nb_plmn, own_plmn)):
        return None
    cls, cgi = ("LNBTS", "ECGI") if kind == "eNB" else ("NRBTS", "NCGI")
    plmn = plmn_text(own_plmn or nb_plmn)
    return (f"{kind} {nb_id} has this {kind}'s own id" + (f" in the same PLMN ({plmn})" if plmn else "")
            + f": two {kind}s of one PLMN need different ids, or their cells' global ids ({cgi}) collide. "
            f"Renumber one of them first (Renumber on its {cls}).")


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


def here(ctx: Context, kind: str, skip: Callable[[dict], bool]) -> list[dict]:
    """This file's own eNBs or gNBs as candidates, as sources() gives the
    other files': a co-sited site is the likeliest neighbour."""
    return [{**e, "file": "this file", "key": f"here|{e['dn']}", "files": 1}
            for e in summary(ctx.site.mos)[kind] if not skip(e)]


def nearby(site: Site, own: Optional[str], found: list[dict], address: str = "ip",
           stale: Callable[[dict], bool] = lambda e: False) -> list[dict]:
    """`found` in its groups: this file's sites, then the other files' on
    the subnet of `own` (this site's address the neighbour faces), each
    with "subnet" set, nearest address first, then the rest; otherwise in
    found's order. A site at `own` itself stays with the rest: one address
    is one system module, so that is this BTS in another export. So does
    one `stale` picks: at an address this site has for another BTS."""
    nets = [net for _, net in subnets(site) if _within(own, net)]
    near, rest = [], []
    for e in found:
        net = (None if e["key"].startswith("here|") or _distance(e.get(address), own) == 0 or stale(e) else
               next((n for n in nets if _within(e.get(address), n)), None))
        if net:
            near.append({**e, "subnet": str(net)})
        else:
            rest.append(e)
    near.sort(key=lambda e: _distance(e[address], own))
    return ([e for e in rest if e["key"].startswith("here|")] + near
            + [e for e in rest if not e["key"].startswith("here|")])


def _distance(a: Optional[str], b: Optional[str]) -> Optional[int]:
    try:
        return abs(int(ipaddress.ip_address((a or "").strip())) - int(ipaddress.ip_address((b or "").strip())))
    except ValueError:
        return None


def _within(value: Optional[str], net) -> bool:
    try:
        ip = ipaddress.ip_address((value or "").strip())
    except ValueError:
        return False
    return ip.version == net.version and ip in net


def group(e: dict) -> str:
    return ("This file" if e["key"].startswith("here|") else
            "On this site's subnet" if e.get("subnet") else "Sites in the tool")


def far(key: Optional[str]) -> Optional[tuple[str, str]]:
    """(corpus key of its file, distName) for a site option from another
    file; None for this file's own (co-sited) or a typed-in one."""
    head, _, dn = (key or "").partition("|")
    if not dn or head == "here" or ":" not in head:
        return None
    return head, dn


def lookup(ctx: Context, found: list[dict], key: str, kind: str) -> Optional[dict]:
    """The site `key` names: an option of `found`, else that file's site
    itself. A run names a site by the file it plans in, which `found` may
    list under a newer file with the same cells."""
    match = next((e for e in found if e["key"] == key), None)
    where = far(key)
    if match or not where or where[0] == ctx.key:
        return match
    for f in ctx.corpus():
        if f["key"] == where[0]:
            for e in (f.get("sites") or {}).get(kind, []):
                if e["dn"] == where[1]:
                    return {**e, "file": f["name"], "key": key, "files": 1}
    return None


def picked(cells: dict[str, dict], inputs: dict, name: str) -> list[dict]:
    """The cells (distName -> object) `inputs[name]` names, by distName, or
    `inputs[name + "Lcr"]` names by lcrId (how a run's other end names this
    file's cells); every one when neither is given."""
    if inputs.get(name) is not None:
        return [cells[d] for d in inputs[name] if d in cells]
    if inputs.get(name + "Lcr") is not None:
        lcrs = {str(x) for x in inputs[name + "Lcr"]}
        return [c for c in cells.values() if c["p"].get("lcrId") in lcrs]
    return list(cells.values())


def lcr_ids(site: Site, dns: Optional[list[str]], parent: str, cls: str) -> list[str]:
    """The lcrIds of the cells `dns` names (every cell of `parent` when
    None): what the other end of a run relates to."""
    cells = [site.by_dn[d] for d in dns if d in site.by_dn] if dns is not None else site.child(parent, cls)
    return [c["p"]["lcrId"] for c in cells if c["p"].get("lcrId") not in (None, "")]


BOTH = "both"


def run_fields(sources: dict[str, list[dict]], kind: str) -> list[dict]:
    """A neighbour form's run fields (run.py): more neighbours from other
    files, added as the first is, and their own end of each relation."""
    more = {dn: [{"value": o["value"], "label": o["label"], "group": o.get("group"),
                  "hint": (o.get("details") or [""])[0]} for o in opts if far(o["value"])]
            for dn, opts in sources.items()}
    return [
        {"id": "more", "label": f"More neighbour {kind}s", "type": "picks", "dependsOn": "target",
         "optionsByKey": more, "excludeField": "source", "optional": True, "default": [],
         "hint": "Each is added as the first, with all its cells, in the same run."},
        {"id": "both", "label": "Their end", "type": "checks", "optional": True,
         "options": [{"value": BOTH, "label": "Add this site to each neighbour's own file too",
                      "hint": "In the file each neighbour comes from, written with this one (a read-only file "
                              "goes into a copy). Not for one typed in or in this file."}]},
    ]


def from_text(e: dict) -> str:
    if e["key"].startswith("here|"):
        return "In this file (co-sited)."
    return (f"From {e['file']}" + (f" (and {e['files'] - 1} other file{'s' if e['files'] > 2 else ''} with "
                                   "the same cells)" if e["files"] > 1 else "") + "."
            + (f" Its address is on this site's subnet ({e['subnet']}), as a co-sited BTS's is." if e.get("subnet")
               else ""))


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

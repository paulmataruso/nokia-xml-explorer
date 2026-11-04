"""
Tidy numbering: the file numbered the way Nokia's production files are
(owner, 2026-11-04: "By 5QI value, as Nokia"). The QoS chain, as all 27
production 25R2 gNBs number it:
- an NRDRB_5QI is numbered by its 5QI (NRDRB_5QI-5 maps 5QI 5), and a
  second mapping of the same 5QI 20 above it (5QI 6 twice: NRDRB_5QI-6 and
  NRDRB_5QI-26). Only the 5QI 1 mapping is NRDRB_5QI-1. An NRDRB_QCI is
  numbered by its QCI;
- the NRDRB one mapping alone names is NRDRB-(10 + 5QI) for 5QI 1-9 and the
  repeat's own number for a repeat (NRDRB-26); an EN-DC bearer takes its
  QCI (NRDRB-5 for QCI 5). NRDRB-1, the default bearer, never moves;
- a profile one bearer alone names takes that bearer's 5QI (NRDRB_MAC-6,
  NRDRB_PDCP-5); a repeat's MAC is 10 above its 5QI (NRDRB_MAC-16).
Anything else in the chain keeps its number: what several bearers share
(production's PDCP-2 and RLC_AM-2 for 5QI 6-9), 5QI 80 (NRDRB-20,
NRDRB_MAC-15 in production), a mapping of several values. An object on a
number another one takes moves to the lowest free number (from 2 for a
mapping, 20 for a bearer, 1 for a profile). The chain's gaps stay, as
production has them, so a production gNB is left as it is.

Outside the chain, only the classes production files always number in
order lose their gaps (IN_ORDER: every group of them, in every production
file, counts from 0 or 1 without a gap). Numbers only go down, since a
class's range isn't known here: each class counts from 1 (from 0 where it
counts from 0 already), or, if picked, keeps its lowest number, and closes
the gaps above it.

Every other class keeps its numbers, as production does (measured
2026-11-04 over the 27 production files; renumber.py still moves any of
them by hand):
- a scheme production keeps on every site: SNSSAI 11-16, BWP_PROFILE 0,
  40, 60, 80, 100, 1130, 1140, 1160, REDRT 1, 5, 9, IPIF 2 and 3,
  NRX2LINK_TRUST from 257, BBPOOL 11 and 12 (in the other files);
- ports and modules, numbered as the hardware is: ETHIF, ETHLK, SFP,
  VLANIF (VLANIF-3 alone on 51 production ports), RMOD, ALD;
- what the BTS numbers itself, never seen in production: the LTE
  neighbours (LNADJ, LNADJL, LNREL and their kin count down from 255);
- the BTS's own numbers, the cells and what follows their lcrId, and the
  classes whose number mirrors a parameter (renumber.HABITS);
- runtime objects and any group with a repeated distName
  (renumber.refusal).

Every link is kept (Doc.renumber). The form lists each group it would
change, ticked: untick what should stay. A chained group follows the
final numbers of the groups it lines up with, ticked or not.
"""
from __future__ import annotations

import collections
from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, instance, label, natural, why
from .renumber import FIXED, MAPPINGS, RESERVED, _cls, _numbered, apply_moves, refusal, why_moved, why_pointed

ID = "tidy"
TITLE = "Tidy numbering"
GROUP = "Edit"
SUMMARY = "Number the file as Nokia's production files are: each 5QI's mapping, bearer and MAC by its value, gaps closed."
UI = "form"
KEYWORDS = "tidy clean renumber numbering gaps order align 5qi qci drb mac pdcp rlc mo instance"

PROFILES = {"nrDrbMacDN": "NRDRB_MAC", "nrDrbPdcpDN": "NRDRB_PDCP", "nrDrbRlcAmDN": "NRDRB_RLC_AM",
            "nrDrbRlcUmDN": "NRDRB_RLC_UM"}
# Class -> how many groups of it the production files have, every one numbered from 0 or 1 without a gap
# (and other files have it with gaps). Tidy closes gaps in these only.
IN_ORDER = {"CHANNEL": 588, "BBMOD": 27, "BRGPRT": 27, "CABINET": 27, "CABLINK": 27, "AMLEPR": 23, "IRFIM": 23,
            "LNHOIF": 23, "ANRPRL": 10, "LNMME": 10}
CHAIN = {*MAPPINGS, "NRDRB", *PROFILES.values()}
BEARER, REPEAT = 10, 20  # NRDRB-(10 + 5QI); a second mapping of a 5QI, and its bearer, 20 above it
SHOWN = 6  # numbers a group's option lists before "and N more", and groups the notes list one by one
FROM_ONE, KEEP = "one", "keep"


def _key(dn: str) -> str:
    return f"{dn.rpartition('/')[0]}|{_cls(dn)}"


def _groups(ctx: Context, doc: Doc) -> dict[str, list[str]]:
    """parent|class -> its objects in number order: the groups tidying may move."""
    out = collections.defaultdict(list)
    for d in doc.mos:
        if instance(d).isdigit() and (_cls(d) in IN_ORDER or _cls(d) in CHAIN):
            out[_key(d)].append(d)
    return {k: sorted(v, key=natural) for k, v in out.items()
            if not any(refusal(ctx, d) for d in v)}


def _fill(members: list[str], start: Optional[int] = None) -> dict[str, str]:
    """old -> new for a whole group: in their order from `start` (default
    the lowest they have; never above it), without gaps. Only changes are
    returned."""
    lowest = min(int(instance(d)) for d in members)
    n = lowest if start is None else min(start, lowest)
    return {d: _numbered(d, str(n + i)) for i, d in enumerate(members) if str(n + i) != instance(d)}


def plan_numbers(ctx: Context, doc: Doc, chosen: Optional[set[str]] = None,
                 start: str = FROM_ONE, reasons: Optional[dict[str, str]] = None) -> dict[str, dict[str, str]]:
    """parent|class -> {old: new} for every group with a change, among
    `chosen` (default all). The chain reads the final numbers of the groups
    before it: a group not chosen keeps its numbers. `reasons`, if given,
    gets why each object moves (old distName -> text)."""
    groups = _groups(ctx, doc)
    first = 1 if start == FROM_ONE else None  # _fill keeps a 0 where a class has one
    out: dict[str, dict[str, str]] = {}
    final: dict[str, int] = {}  # a chained object's final number

    def settle(key: str, numbers: dict[str, int], texts: dict[str, tuple[int, str]], otherwise: str) -> None:
        """`texts`: member -> (its target, why); a member moved off its target is `otherwise`."""
        moves = {d: _numbered(d, str(n)) for d, n in numbers.items() if str(n) != instance(d)}
        if chosen is not None and key not in chosen:
            moves = {}
        if moves:
            out[key] = moves
        for d in groups[key]:
            final[d] = int(instance(moves.get(d, d)))
        for d in moves if reasons is not None else ():
            reasons[d] = texts[d][1] if d in texts and texts[d][0] == numbers[d] else otherwise

    def of(parent: str, *classes: str) -> list[str]:
        return [d for c in classes for d in groups.get(f"{parent}|{c}", ())]

    values = {m: _value(doc, m) for k, ms in groups.items() if k.split("|")[1] in MAPPINGS for m in ms}
    for key in [k for k in groups if k.split("|")[1] in MAPPINGS]:
        targets = _mapping_targets(groups[key], values)
        kind = "QCI" if key.endswith("|NRDRB_QCI") else "5QI"
        texts = {m: (t, f"It maps {kind} {values[m]}: production gNBs number a {kind} mapping by its {kind}." if t == values[m]
                     else f"The second mapping of 5QI {values[m]}: production gNBs number it 20 above the first "
                          f"(NRDRB_5QI-26 for 5QI 6).") for m, t in targets.items()}
        settle(key, _settle(groups[key], targets, 2), texts,
               f"Production numbers {kind} mappings by their {kind}, and this number goes to another one (1 only to "
               f"the {kind} 1 mapping): it takes the lowest free number from 2.")
    named = collections.defaultdict(list)  # bearer -> the mappings naming it
    for m in values:
        named[doc.get(m, "nrDrbDN")].append(m)
    chain = {}  # bearer -> (its one mapping's value, kind): "first", "repeat"
    for m, v in values.items():
        b = doc.get(m, "nrDrbDN")
        if v is None or len(named[b]) != 1:
            continue
        if final[m] == v:
            chain[b] = (v, "first")
        elif _cls(m) == "NRDRB_5QI" and final[m] == REPEAT + v:
            chain[b] = (v, "repeat")
    for key in [k for k in groups if k.split("|")[1] == "NRDRB"]:
        targets, texts = {}, {}
        for b in groups[key]:
            v, kind = chain.get(b, (None, None))
            m = named[b][0] if v is not None else None
            if m and _cls(m) == "NRDRB_QCI":
                targets[b] = v if kind == "first" and v >= 2 else None
                texts[b] = (targets[b], f"The bearer of QCI {v}: production gNBs number an EN-DC bearer by its QCI.")
            elif kind == "first":
                targets[b] = BEARER + v if 1 <= v <= 9 else None
                texts[b] = (targets[b], f"The bearer of 5QI {v}: production gNBs number it 10 + 5QI.")
            elif kind == "repeat":
                targets[b] = final[m]
                texts[b] = (targets[b], f"The bearer of the second mapping of 5QI {v}: production gives it the "
                                        f"mapping's number.")
        settle(key, _settle(groups[key], targets, 20), texts,
               "Its number goes to another bearer by the production numbering: it takes the lowest free number from "
               "20.")
    for key in [k for k in groups if k.split("|")[1] in PROFILES.values()]:
        parent, cls = key.split("|")
        param = next(p for p, c in PROFILES.items() if c == cls)
        holders = collections.defaultdict(list)  # profile -> the bearers naming it
        for b in of(parent, "NRDRB"):
            holders[doc.get(b, param)].append(b)
        targets, texts = {}, {}
        for d in groups[key]:
            if len(holders.get(d, [])) != 1:
                continue
            b = holders[d][0]
            v, kind = chain.get(b, (None, None))
            if v is None or _cls(named[b][0]) != "NRDRB_5QI" or not 1 <= v <= 9:
                continue
            targets[d] = v if kind == "first" else BEARER + v if cls == "NRDRB_MAC" else None
            texts[d] = (targets[d], f"Only the bearer of 5QI {v} uses it: production gNBs number it by the 5QI."
                        if kind == "first" else f"Only the bearer of the second mapping of 5QI {v} uses it: "
                                                f"production numbers its MAC 10 + 5QI (NRDRB_MAC-16 for 5QI 6).")
        settle(key, _settle(groups[key], targets, 1), texts,
               "Its number goes to another profile by the production numbering: it takes the lowest free number.")
    for key in groups:
        if key.split("|")[1] not in CHAIN:
            moves = _fill(groups[key], first)
            cls = key.split("|")[1]
            settle(key, {d: int(instance(moves.get(d, d))) for d in groups[key]}, {},
                   f"Production files number every {cls} in order from 0 or 1 ({IN_ORDER[cls]} groups in the files "
                   f"this was measured on): the gaps close.")
    return out


def _value(doc: Doc, mapping: str) -> Optional[int]:
    """The one 5QI or QCI a mapping maps; None for none or several."""
    values = doc.values(mapping, MAPPINGS[_cls(mapping)])
    return int(values[0]) if len(values) == 1 and values[0].isdigit() else None


def _mapping_targets(members: list[str], values: dict[str, Optional[int]]) -> dict[str, Optional[int]]:
    """Each mapping's number by its value: the first of a value takes the
    value (the one on it already, if one is), a second 5QI 1-9 20 above it."""
    by_value = collections.defaultdict(list)
    for m in members:
        if values[m] is not None:
            by_value[values[m]].append(m)
    targets = {}
    for v, ms in by_value.items():
        ms.sort(key=lambda m: (int(instance(m)) != v, int(instance(m)) != REPEAT + v, natural(m)))
        targets[ms[0]] = v
        if len(ms) > 1 and _cls(ms[1]) == "NRDRB_5QI" and 1 <= v <= 9:
            targets[ms[1]] = REPEAT + v
    return targets


def _settle(members: list[str], targets: dict[str, Optional[int]], base: int) -> dict[str, int]:
    """Final numbers for one chained group. A fixed object, and one on its
    target, keep theirs; the others take their targets in order where still
    free; the rest keep their numbers unless taken, else the lowest free
    from `base`. A reserved number goes only to a target."""
    cls = _cls(members[0])
    now = {d: int(instance(d)) for d in members}
    reserved = {int(RESERVED[cls][0])} if cls in RESERVED else set()
    final = {d: now[d] for d in members if (cls, instance(d)) in FIXED or targets.get(d) == now[d]}
    taken = set(final.values())
    for d in members:
        t = targets.get(d)
        if d not in final and t is not None and t not in taken:
            final[d] = t
            taken.add(t)
    for d in members:
        if d not in final and now[d] not in taken and now[d] not in reserved:
            final[d] = now[d]
            taken.add(now[d])
    n = base
    for d in members:
        if d not in final:
            while n in taken or n in reserved:
                n += 1
            final[d] = n
            taken.add(n)
    return final


def _n(k: int, one: str, many: Optional[str] = None) -> str:
    return f"{k} {one if k == 1 else many or one + 's'}"


def _numbers(moves: dict[str, str]) -> str:
    pairs = [f"{instance(o)} → {instance(n)}" for o, n in sorted(moves.items(), key=lambda m: natural(m[0]))]
    return ", ".join(pairs[:SHOWN]) + (f" and {len(pairs) - SHOWN} more" if len(pairs) > SHOWN else "")


def _option(key: str, moves: dict[str, str]) -> dict:
    parent, cls = key.split("|")
    follows = {"NRDRB_5QI": "numbered by its 5QI", "NRDRB_QCI": "numbered by its QCI",
               "NRDRB": "numbered by its mapping's 5QI or QCI"}.get(cls) or (
        "numbered by its bearer's 5QI" if cls in PROFILES.values() else None)
    return {"value": key, "label": f"{cls} under {label(parent)}",
            "hint": _numbers(moves) + (f" (each {follows}, as Nokia's production gNBs)" if follows else "")}


def available(ctx: Context) -> Optional[str]:
    return None if plan_numbers(ctx, Doc(ctx.raw)) else "The file is numbered as production files are already."


def setup(ctx: Context) -> dict:
    doc = Doc(ctx.raw)
    by_start = {k: plan_numbers(ctx, doc, start=k) for k in (FROM_ONE, KEEP)}
    return {
        "intro": "Numbers the file the way Nokia's production files are numbered. The QoS chain by value: "
                 "NRDRB_5QI-5 maps 5QI 5 and names NRDRB-15, whose MAC is NRDRB_MAC-5; an EN-DC NRDRB_QCI-6 names "
                 "NRDRB-6; profiles several bearers share keep their numbers. Gaps close in the classes production "
                 "always numbers in order, such as CHANNEL, CABLINK, IRFIM and LNHOIF. Numbering schemes production "
                 "keeps (SNSSAI, BWP_PROFILE, REDRT), ports, cells and what the BTS numbers itself stay as they are; "
                 "Renumber moves those one at a time. Every link moves with the numbers.",
        "fields": [
            {"id": "start", "label": "Each class counts", "type": "select", "default": FROM_ONE, "options": [
                {"value": FROM_ONE, "key": FROM_ONE, "label": "From 1, or from 0 where it counts from 0 already"},
                {"value": KEEP, "key": KEEP, "label": "From the lowest number it has now"},
            ]},
            {"id": "groups", "label": "Renumber", "type": "checks", "dependsOn": "start",
             "optionsByKey": {k: [_option(g, m) for g, m in sorted(groups.items(), key=lambda kv: natural(kv[0]))]
                              for k, groups in by_start.items()},
             "hint": "Untick a class to leave its numbers as they are."},
        ],
    }


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    chosen = set(inputs.get("groups") or [])
    if not chosen:
        raise PlanError(["Pick at least one class to renumber."])
    doc = Doc(ctx.raw)
    reasons: dict[str, str] = {}
    groups = plan_numbers(ctx, doc, chosen, KEEP if inputs.get("start") == KEEP else FROM_ONE, reasons)
    if not groups:
        raise PlanError(["The picked classes are numbered as production files are already."])

    def moved(old: str, new: str) -> dict:
        planned = next((m.get(old) for m in groups.values() if old in m), None)
        return why("tidy", reasons[old], "files") if planned == new else \
            why_moved(old, new)

    before = len(doc.changes)
    aside = 0
    # Children before their parents: a parent's move carries them.
    for key in sorted(groups, key=lambda k: -k.count("/")):
        aside += apply_moves(doc, groups[key], moved, why_pointed)
    values = [c for c in doc.changes[before:] if c["op"] != "renumber"]
    objects = sum(len(m) for m in groups.values())
    per = collections.Counter(key.split("|")[1] for key in groups)
    if len(groups) <= SHOWN:
        notes = [f"{key.split('|')[1]} under {label(key.split('|')[0])}: {_numbers(m)}."
                 for key, m in sorted(groups.items(), key=lambda kv: natural(kv[0]))]
    else:  # each change says why; one line per class is enough here
        notes = ["Renumbered: " + ", ".join(f"{cls} under {_n(k, 'parent')}" for cls, k in per.most_common())
                 + ". Each change below says why."]
    notes.append(f"Every link kept: {len(values)} values in {len({c['dn'] for c in values})} objects now name the new "
                 f"numbers." if values else "Nothing in the file names the objects renumbered.")
    if aside:
        notes.append(f"{aside} {'object steps' if aside == 1 else 'objects step'} aside to a spare number first, where "
                     f"two swap numbers; the manual steps show it.")
    notes.append("On a running BTS a new number is a new object: its counters and alarms start again under it.")
    return finish(ctx, doc, {"label": "Tidy numbering",
                             "summary": f"{_n(objects, 'object')} renumbered ({_n(len(per), 'class', 'classes')}"
                                        + (f" under {_n(len(groups), 'parent')}" if len(groups) > len(per) else "")
                                        + f"), {_n(len(values), 'link')} re-pointed.",
                             "notes": notes, "confirm": [], "focus": None})

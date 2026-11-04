"""
Renumber an object: a new instance number for it, or numbers in order for
every object of its class beside it (same parent), closing the gaps. Every
link is kept: links are distName values almost everywhere, so each value
naming the object, or anything under it, moves with it; the two lists that
hold numbers instead (NRCELLGRP nrCellList, NRDU refNrCellGroup) move too
(Doc.renumber).

Not offered:
- a runtime object (what the BTS reported);
- LCELL and LCELNR: their number is their cell's lcrId, which is how the
  cell finds them;
- NRDRB-1, the default bearer (owner, 2026-11-03). Nothing names it, here
  or in any of the 27 production gNBs measured: the gNB takes it by its
  number. It keeps 1, and no other NRDRB takes 1;
- number 1 for an NRDRB_5QI or NRDRB_QCI, except the one that maps 5QI 1
  (or QCI 1): production gNBs number mappings by their value, and NRDRB_5QI-1
  maps 5QI 1 on every one (owner, 2026-11-04).

A parameter that usually carries the object's number is named in the notes
but not changed: in the files this was measured on, NRCELL-n has lcrId n
(130 of 132), LNCEL-n lcrId n (132 of 159), ANTL-n antPortId n (531 of 637)
and NRBEAMMAP-n duBeamId n (30 of 30). lcrId is the cell's identity, so it
moves only when the user changes it.

Nokia's own exports don't line chains up by number (NRDRB_5QI-n naming
NRDRB-n: 27 of 216 in production; NRDRB-n naming NRDRB_MAC-n: 0 of 378):
they number them by 5QI value, which tidy.py follows.

An LNBTS or the BTS can't take a neighbour eNB's id (neighbour_enbs): its
relations to its own cells name the eNB by that number (Doc._own_enb).

The tree's right-click menu opens it on the object ("Renumber…").
"""
from __future__ import annotations

import collections
from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, instance, label, natural, parent_dn, why
from .links import _runtime

ID = "renumber"
TITLE = "Renumber an object"
GROUP = "Edit"
SUMMARY = "Give an object a new number, or number its class in order, with every link to it kept."
UI = "form"
KEYWORDS = "renumber rename instance number id distName mo tidy clean gaps order references links"

ONE, ALL = "one", "all"
# Numbers an object of the class can't have or leave, and why.
FIXED = {("NRDRB", "1"): "NRDRB-1 is the default bearer: the gNB takes it by its number (nothing names it), so it "
                         "keeps 1"}
RESERVED = {"NRDRB": ("1", "1 is the default bearer's number"),
            "NRDRB_5QI": ("1", "1 is the number of the mapping of 5QI 1, as production gNBs number mappings by "
                               "their 5QI"),
            "NRDRB_QCI": ("1", "1 is the number of the mapping of QCI 1, as mappings are numbered by their QCI")}
# A mapping's values: the one that maps 1 alone may have number 1.
MAPPINGS = {"NRDRB_5QI": "fiveqiValueList", "NRDRB_QCI": "qciValueList"}
BY_LCR = {"LCELL": "LNCEL", "LCELNR": "NRCELL"}
# (parameter, how often NRCELL-n has it n, of how many) in the files measured.
HABITS = {"NRCELL": ("lcrId", 130, 132), "LNCEL": ("lcrId", 132, 159), "ANTL": ("antPortId", 531, 637),
          "NRBEAMMAP": ("duBeamId", 30, 30)}


def _cls(dn: str) -> str:
    return label(dn).rsplit("-", 1)[0]


def _numbered(dn: str, n: str) -> str:
    """`dn` under number n: "MRBTS-1/NRBTS-1/SNSSAI-2", "1" -> "MRBTS-1/NRBTS-1/SNSSAI-1"."""
    parent = dn.rpartition("/")[0]
    return f"{parent}/{_cls(dn)}-{n}" if parent else f"{_cls(dn)}-{n}"


def available(ctx: Context) -> Optional[str]:
    return None if ctx.site.mos else "This file has no objects."


def setup(ctx: Context) -> dict:
    return {
        "intro": "Changes an object's number and points every link at the new one: each value naming it or anything "
                 "under it, and the cell group and DU lists that hold numbers. The objects stay where they are in "
                 "the file.",
        "fields": [
            {"id": "object", "label": "Object (distName)", "type": "text",
             "placeholder": "MRBTS-1/NRBTS-1/SNSSAI-2",
             "hint": "Right-click an object in the tree and pick Renumber to fill this in."},
            {"id": "scope", "label": "Renumber", "type": "select", "default": ONE, "options": [
                {"value": ONE, "label": "This object, to a new number"},
                {"value": ALL, "label": "Every object of its class beside it, in order",
                 "hint": "Same parent and class, numbered up from the first number without gaps, in the order "
                         "they have now."},
            ]},
            {"id": "number", "label": "New number", "type": "text", "placeholder": "1",
             "showIf": {"field": "scope", "equals": ONE}},
            {"id": "start", "label": "Number from", "type": "text", "optional": True,
             "placeholder": "The lowest number now", "showIf": {"field": "scope", "equals": ALL},
             "hint": "Leave it empty to keep the lowest number they have and close the gaps above it."},
        ],
    }


def _number(text: str, what: str) -> str:
    text = (text or "").strip()
    if not text.isdigit():
        raise PlanError([f"{what} must be a whole number, such as 1." if text else f"Give {what.lower()}."])
    return str(int(text))


def beside(doc: Doc, dn: str) -> list[str]:
    """The objects of dn's class with its parent (dn among them), in number order."""
    parent, cls = dn.rpartition("/")[0], _cls(dn)
    return sorted((d for d in doc.mos if d.rpartition("/")[0] == parent and _cls(d) == cls), key=natural)


def maps_its_number(doc: Doc, dn: str) -> bool:
    """A mapping on the reserved number that maps that value alone: NRDRB_5QI-1 mapping 5QI 1."""
    cls = _cls(dn)
    return cls in MAPPINGS and instance(dn) == RESERVED[cls][0] and doc.values(dn, MAPPINGS[cls]) == [instance(dn)]


def neighbour_enbs(doc: Doc, dn: str) -> set[str]:
    """The eNB ids of the neighbours of the LNBTS at or under `dn` (an
    LNBTS or the BTS): numbers it can't take, since its relations to its own
    cells name it by its number (Doc._own_enb)."""
    if doc.cls(dn) != "LNBTS" and "/" in dn:
        return set()
    out = set()
    for lnbts in [dn] if doc.cls(dn) == "LNBTS" else doc.of_class("LNBTS", under=dn):
        out |= {doc.get(a, "adjEnbId") for a in doc.of_class("LNADJ", under=lnbts)}
        out |= {doc.get(a, "ecgiAdjEnbId") for a in doc.of_class("LNADJL", under=lnbts)}
    return out - {None}


def in_order(members: list[str], start: Optional[str] = None, taken: frozenset = frozenset(),
             keep: frozenset = frozenset()) -> dict[str, str]:
    """old -> new numbering `members` (one class, one parent) in their order
    from `start` (default: the lowest they have), without gaps. A fixed
    object, and any in `keep`, keeps its number; reserved and `taken`
    numbers are skipped. Only the objects whose number changes are in it."""
    if not members:
        return {}
    cls = _cls(members[0])
    movable = [d for d in members if (cls, instance(d)) not in FIXED and d not in keep]
    skip = {instance(d) for d in members if d not in movable} | set(taken)
    if cls in RESERVED:
        skip.add(RESERVED[cls][0])
    n = int(start if start is not None else min((instance(d) for d in movable), key=int, default="1"))
    out = {}
    for d in sorted(movable, key=natural):
        while str(n) in skip:
            n += 1
        if instance(d) != str(n):
            out[d] = _numbered(d, str(n))
        n += 1
    return out


def apply_moves(doc: Doc, moves: dict[str, str], w, ref) -> int:
    """Renumbers every old -> new in `moves` (new numbers distinct, and free
    once the objects in `moves` have left them), in an order that keeps each
    new number free when it is taken: a move whose number is free first;
    when only cycles are left, one object steps aside to a spare number.
    `w(old, new)` and `ref(old, new)` give the records' why(). Returns how
    many steps aside were needed."""
    pending = dict(moves)
    aside = 0
    while pending:
        ready = [o for o in sorted(pending, key=natural) if not doc.exists(pending[o])]
        if not ready:
            old = min(pending, key=natural)
            used = {int(instance(d)) for d in beside(doc, old) if instance(d).isdigit()}
            used |= {int(instance(n)) for n in pending.values()}
            spare = _numbered(old, str(max(used) + 1))
            doc.renumber(old, spare, w(old, spare), ref=ref(old, spare))
            pending[spare] = pending.pop(old)
            aside += 1
            continue
        for old in ready:
            new = pending.pop(old)
            doc.renumber(old, new, w(old, new), ref=ref(old, new))
    return aside


def why_moved(old: str, new: str) -> dict:
    return why("renumber", f"{label(old)} under its new number, {label(new)}: the same object and parameters.", "choice")


def why_pointed(old: str, new: str) -> dict:
    return why("renumber", f"Names {label(old)}, which is {label(new)} now.", "choice")


def refusal(ctx: Context, dn: str) -> Optional[str]:
    """Why an object can't be renumbered at all, if it can't."""
    cls = _cls(dn)
    if _runtime(dn):
        return f"{label(dn)} is what the BTS reported (a runtime object); it isn't configuration."
    if cls in BY_LCR:
        return (f"{label(dn)}'s number is the lcrId of its {BY_LCR[cls]}, which is how the cell finds it. It moves "
                f"only with the cell's lcrId.")
    if any(d == dn or d.startswith(dn + "/") for d in repeated(ctx)):
        return (f"{label(dn)} appears more than once in this file, so which one to renumber isn't clear. Remove the "
                f"repeat first.")
    return None


def repeated(ctx: Context) -> list[str]:
    """The distNames the file has more than once (worked out once per context)."""
    if not hasattr(ctx, "_repeated"):
        ctx._repeated = [d for d, n in collections.Counter(m["dn"] for m in ctx.mos).items() if n > 1]
    return ctx._repeated


def _moves(doc: Doc, dn: str, inputs: dict) -> dict[str, str]:
    """old -> new distNames."""
    cls, reserved = _cls(dn), RESERVED.get(_cls(dn))
    if inputs.get("scope") != ALL:
        n = _number(inputs.get("number"), "The new number")
        new = _numbered(dn, n)
        if new == dn:
            raise PlanError([f"{label(dn)} has that number already."])
        if reserved and n == reserved[0] and not (cls in MAPPINGS and doc.values(dn, MAPPINGS[cls]) == [n]):
            raise PlanError([f"{label(new)} isn't used: {reserved[1]}."])
        if n in neighbour_enbs(doc, dn):
            raise PlanError([f"{n} is the eNB id of a neighbour of this eNB (an LNADJ names it): its relations to "
                             f"its own cells name it by its number, so they would point at that eNB. Pick another."])
        if doc.exists(new):
            free = int(n)
            while doc.exists(_numbered(dn, str(free))):
                free += 1
            raise PlanError([f"{label(new)} exists already. Renumber it first, or pick a free number such as "
                             f"{free}."])
        return {dn: new}
    start = _number(inputs.get("start"), "The first number") if (inputs.get("start") or "").strip() else None
    members = beside(doc, dn)
    moves = in_order(members, start, keep=frozenset(d for d in members if maps_its_number(doc, d)))
    clash = [o for o, n in moves.items() if instance(n) in neighbour_enbs(doc, o)]
    if clash:
        raise PlanError([f"{label(clash[0])} would take {instance(moves[clash[0]])}, the eNB id of a neighbour of "
                         f"this eNB (an LNADJ names it): its relations to its own cells name it by its number."])
    if not moves:
        parent = dn.rpartition("/")[0]
        raise PlanError([f"The {cls} objects" + (f" under {label(parent)}" if parent else "")
                         + " are numbered so already."])
    return moves


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    dn = (inputs.get("object") or "").strip()
    doc = Doc(ctx.raw)
    if not doc.exists(dn):
        raise PlanError([f"{dn or 'That'} isn't an object of this file."])
    cls = _cls(dn)
    problem = refusal(ctx, dn)
    if (cls, instance(dn)) in FIXED and inputs.get("scope") != ALL:
        problem = FIXED[cls, instance(dn)] + "."
    if inputs.get("scope") == ALL and not problem:
        problem = next((refusal(ctx, d) for d in beside(doc, dn) if refusal(ctx, d)), None)
    if problem:
        raise PlanError([problem])
    moves = _moves(doc, dn, inputs)

    before = len(doc.changes)
    apply_moves(doc, moves, why_moved, why_pointed)
    values = [c for c in doc.changes[before:] if c["op"] != "renumber"]
    holders = {c["dn"] for c in values}

    notes = []
    if len(moves) > 1:
        notes.append("New numbers: " + ", ".join(f"{label(o)} → {instance(n)}" for o, n in sorted(moves.items(),
                                                                                         key=lambda m: natural(m[0])))
                     + ".")
    notes.append(f"Every link kept: {len(values)} values in {len(holders)} objects now name the new numbers."
                 if values else "Nothing in the file names " + ("them" if len(moves) > 1 else label(dn)) + ".")
    under = sum(len(doc.subtree(n)) - 1 for n in moves.values())
    if under:
        notes.append(f"The {under} objects under {'them' if len(moves) > 1 else label(next(iter(moves.values())))} keep their own "
                     f"numbers; their distNames follow.")
    habit = HABITS.get(cls)
    if habit:
        name, k, total = habit
        odd = [(o, n, doc.get(n, name)) for o, n in moves.items() if doc.get(n, name) == instance(o)]
        if odd:
            notes.append(f"In the files this was measured on, {cls}-n usually has {name} n ({k} of {total}). "
                         + ", ".join(f"{label(n)}'s {name} stays {v}" for _, n, v in odd)
                         + f": change it separately if it should follow.")
    if any("/" not in o for o in moves):
        notes.append("The BTS's own number changes: it must match the BTS id the site is planned with.")
    notes.append("On a running BTS a new number is a new object: its counters and alarms start again under it.")

    title = (f"Renumber {label(dn)} to {instance(moves[dn])}" if inputs.get("scope") != ALL
             else f"Renumber the {cls} objects" + (f" under {label(parent_dn(dn))}" if "/" in dn else ""))
    return finish(ctx, doc, {"label": title,
                             "summary": f"{len(moves)} {'object' if len(moves) == 1 else 'objects'} renumbered, "
                                        f"{len(values)} {'link' if len(values) == 1 else 'links'} re-pointed.",
                             "notes": notes, "confirm": [], "focus": moves.get(dn) if len(moves) == 1 else None})

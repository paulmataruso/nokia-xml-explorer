"""
Delete an object with what depends on it: the object and everything under
it, the links and relations to it, its values in other objects' lists, a
cell's channel mapping and CA relations (dependents.py has the rules).
What can't go with it, such as a setting naming it, blocks the delete and
is listed, to change first.

The tree's right-click menu opens it on the object ("Delete with
dependents"); from the action bar, paste the distName.
"""
from __future__ import annotations

from typing import Optional

from . import Context, PlanError, finish
from .dependents import apply_removal, plan_removal, where
from .doc import Doc, label, why
from .links import _runtime

ID = "delete"
TITLE = "Delete with dependents"
GROUP = "Edit"
SUMMARY = "Delete an object and what only makes sense with it: links, relations, list entries, a cell's mapping."
UI = "form"
KEYWORDS = "delete remove object distName cascade dependents references cleanup"


def available(ctx: Context) -> Optional[str]:
    return None if ctx.site.mos else "This file has no objects."


def setup(ctx: Context) -> dict:
    return {
        "intro": "Deletes the object and everything under it, with the links, relations and list entries that point "
                 "at it. Anything else naming it is listed instead, to change first.",
        "fields": [
            {"id": "object", "label": "Object (distName)", "type": "text",
             "placeholder": "MRBTS-1/EQM-1/APEQM-1/RMOD-2",
             "hint": "Right-click an object in the tree and pick Delete with dependents to fill this in."},
        ],
    }


def describe(removal, picked: list[str]) -> list[str]:
    """Notes listing what goes besides the picked objects."""
    notes = []
    extra = [r for r in removal.roots if r not in picked]
    if extra:
        notes.append(f"Also deleted: {', '.join(f'{where(r)} ({removal.why[r]})' for r in extra[:8])}"
                     + (f" and {len(extra) - 8} more" if len(extra) > 8 else "") + ".")
    taken = list(dict.fromkeys([f"{where(dn)}.{name}" for dn, name, _ in removal.values]
                               + [f"{where(dn)}.{name}" for dn, name, _ in removal.rows]))
    if taken:
        notes.append("Taken out of lists: " + ", ".join(taken[:8])
                     + (f" and {len(taken) - 8} more" if len(taken) > 8 else "") + ".")
    return notes + removal.notes


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    dn = (inputs.get("object") or "").strip()
    site = ctx.site
    if dn not in site.by_dn:
        raise PlanError([f"{dn or 'That'} isn't an object of this file."])
    if "/" not in dn:
        raise PlanError([f"{dn} is the whole BTS: delete the file instead."])
    if _runtime(dn):
        raise PlanError([f"{label(dn)} is what the BTS reported (a runtime object); it isn't configuration."])
    removal = plan_removal(site, [dn])
    if removal.blockers:
        raise PlanError(removal.blockers)
    doc = Doc(ctx.raw)
    apply_removal(doc, removal, lambda d, reason: why("delete", f"{label(dn)} and everything under it." if d == dn
                                                      else f"Goes with {label(dn)}: {reason}.", "choice"))
    return finish(ctx, doc, {"label": f"Delete {label(dn)}", "summary": f"{label(dn)} and what depends on it.",
                             "notes": describe(removal, [dn]), "confirm": [], "focus": None})

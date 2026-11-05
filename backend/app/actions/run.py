"""
A run: one action's change on this file and the changes it implies on the
other sites it names (owner, 2026-11-05: "allow the user to add two or more
SCP files to the Add wizard, so it can make the changes to all sites at
once"): a neighbour's own end of the relation, the other side of EN-DC,
more neighbours at once.

An action that names other sites has legs(ctx, inputs): the changes to make
after its own, in order, each {"file": corpus key or None (this file),
"action": id, "inputs": {...}, "what": what it does there}. The legs on one
file chain: each plans on the bytes the one before left, so a second
neighbour sees the first. A leg's "settles" lists the notes it makes moot
("Run it on the gNB's file too"), dropped once it plans. A leg that can't be planned is its file's
problem, listed with the file; the run can't be written while a file has
one (untick what asks for it). This file's own change failing is the run
failing, as for a single action.

Per file the plans merge into one: the changes and steps in order, the
notes, confirms and to-dos once each, the site check of the file as it was
against the file as the last leg left it. main.py writes each file with its
own snapshot, a read-only one into a copy.

Pure: main.py opens the other files (open_ctx) and writes the results.
"""
from __future__ import annotations

from typing import Callable

from . import Context, PlanError
from .site_check import check_loaded, check_site, new_findings
from .steps import steps_text

RUN_KEYS = ("more", "both", "also5g", "enbs")  # a run's own inputs, which the planners never read


def plan_run(ctx: Context, action, inputs: dict, actions: dict, open_ctx: Callable[[str], Context]) -> list[dict]:
    """Per file, in the order the run first names it (this file first):
    {key, name, source, editable, this, what, legs, plan, problems, new}.
    `new` is the file's new bytes, None when a leg failed."""
    legs = [{"file": None, "action": action.ID, "inputs": inputs, "what": None}]
    legs += action.legs(ctx, inputs) if hasattr(action, "legs") else []
    files: dict[str, dict] = {}
    settled: set[str] = set()
    for i, leg in enumerate(legs):
        key = ctx.key if leg["file"] in (None, ctx.key) else leg["file"]
        f = files.get(key)
        if f is None:
            try:
                start = ctx if key == ctx.key else open_ctx(key)
            except FileNotFoundError:
                files[key] = _file(key, None, problems=[f"{key.split(':', 1)[-1]} isn't readable any more."])
                continue
            f = files[key] = _file(key, start)
        if f["problems"]:
            continue
        a = actions[leg["action"]]
        clean = {k: v for k, v in leg["inputs"].items() if k not in RUN_KEYS}
        try:
            reason = a.available(f["ctx"])
            if reason:
                raise PlanError([reason])
            new, plan = a.plan(f["ctx"], clean)
        except PlanError as e:
            if i == 0:
                raise
            f["problems"] = [f"{leg['what']}: {p}" if leg.get("what") else p for p in e.problems]
            continue
        f["plans"].append(plan)
        f["what"] += [leg["what"]] if leg.get("what") else []
        f["ctx"] = f["ctx"].with_raw(new)
        settled.update(leg.get("settles") or [])
    return [_merge(f, settled) for f in files.values()]


def _file(key: str, ctx, problems=None) -> dict:
    source, _, name = key.partition(":")
    return {"key": key, "name": name, "source": source, "editable": source == "upload", "start": ctx, "ctx": ctx,
            "plans": [], "what": [], "problems": problems or []}


def _once(items) -> list:
    return list(dict.fromkeys(items))


def _merge(f: dict, settled: set[str]) -> dict:
    out = {k: f[k] for k in ("key", "name", "source", "editable", "what")}
    out["this"] = False
    out["problems"] = f["problems"] or None
    plans = [{**p, "notes": [n for n in p["notes"] if n not in settled]} for p in f["plans"]]
    if f["problems"] or not plans:
        return {**out, "plan": None, "new": None}
    if len(plans) == 1:
        return {**out, "plan": plans[0], "new": f["ctx"].raw}
    changes = [c for p in plans for c in p["changes"]]
    todo = _once(t for p in plans for t in p.get("todo") or [])
    steps = [s for p in plans for s in p["steps"]]
    before = check_loaded(f["start"].mos)
    after = check_site(f["ctx"].raw)
    moves = [(c["old"], c["new"]) for c in changes if c["op"] == "renumber"]
    plan = {
        **plans[0],
        "label": "; ".join(_once(p["label"] for p in plans)),
        "summary": "; ".join(_once(p.get("summary") or p["label"] for p in plans)),
        "changes": changes,
        "notes": _once(n for p in plans for n in p["notes"]),
        "confirm": _once(c for p in plans for c in p["confirm"]),
        "todo": todo,
        "steps": steps,
        "stepsText": steps_text(steps, todo),
        "check": {"before": before["summary"], "after": after["summary"], "new": new_findings(before, after, moves)},
    }
    return {**out, "plan": plan, "new": f["ctx"].raw}

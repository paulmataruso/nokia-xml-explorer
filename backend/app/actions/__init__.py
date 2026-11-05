"""
Site actions: the dependency-aware operations of the action bar (add a 5G
cell, set up CA, change a product code, ...). PROJECT_STATE §9.9 has the
plan and the corpus findings behind it.

An action is a module with:
- ID, TITLE, GROUP, SUMMARY, and UI: "form" for the generic action modal,
  or the name of a custom modal (the CA wizard has its own).
- available(ctx) -> None if it can run on this file, else the reason.
- setup(ctx) -> what the modal's input step shows. For UI "form": `fields`,
  each {id, label, type: select|text|combo|checks, options, ...}. A field
  with `dependsOn` takes `optionsByKey`/`defaultByKey` from the chosen
  option's key; `showIf: {field, equals}` shows it only for that value;
  `optional` text may stay empty; `hint` is help under a text field.
- plan(ctx, inputs) -> (new bytes, plan). The plan has `label` (for the
  snapshot), `changes` (Doc.changes), `notes`, `confirm` (what the XML
  can't show and the user must check) and `focus` (the node to show after
  applying), and may have `todo`: what is needed but can't be written
  (shown with the manual steps). finish() adds the site check before and
  after, and `steps` and `stepsText`: the changes as steps to make by
  hand (steps.py).
  Raise PlanError for a request the rules forbid.
- legs(ctx, inputs), optional, for an action that names other sites: the
  changes the run makes after this one, on this file or on the files the
  other sites come from (the other end of a neighbour, the other side of
  EN-DC). run.py plans them together; see its docstring.

Actions are pure like parser.py: main.py reads and writes the files.
Rule for every action: template values may come from a donor file;
identities and site values (names, ids, IPs, PCI, TAC) never do. They
come from the inputs or from the target file. The one exception is a
neighbour's own identity, taken from that neighbour's file: it describes
the other site, not this one.
"""
from __future__ import annotations

from functools import cached_property
from typing import Callable, Optional

from ..ca import _load
from .doc import Doc
from .links import Site
from .site_check import check_loaded, check_site, new_findings
from .steps import manual_steps, steps_text


class PlanError(ValueError):
    """The request can't be planned. `problems` lists every reason."""

    def __init__(self, problems: list[str]):
        super().__init__(" ".join(problems))
        self.problems = problems


class Context:
    """What an action may know about its file and the corpus. main.py
    supplies the corpus and file access; actions never touch the disk."""

    def __init__(self, raw: bytes, filename: str, source: str,
                 corpus: Callable[[], list[dict]] = lambda: [],
                 read: Optional[Callable[[str, str], bytes]] = None,
                 release_index: Callable[[], dict] = lambda: {},
                 kb: Optional[dict] = None):
        self.raw = raw
        self.filename = filename
        self.source = source
        self.corpus = corpus
        self.read = read
        self.release_index = release_index
        self.kb = kb or {}

    @cached_property
    def mos(self) -> list[dict]:
        return _load(self.raw)

    @cached_property
    def site(self) -> Site:
        return Site(self.mos)

    @property
    def editable(self) -> bool:
        return self.source == "upload"

    @property
    def key(self) -> str:
        """The file's key in the corpus ("scp:name.xml")."""
        return f"{self.source}:{self.filename}"

    def with_raw(self, raw: bytes) -> "Context":
        """The same file with other bytes: the next change of a run plans
        on what the one before left."""
        return Context(raw, self.filename, self.source, self.corpus, self.read, self.release_index, self.kb)


def finish(ctx: Context, doc: Doc, plan: dict) -> tuple[bytes, dict]:
    """The new bytes, and the plan with its changes and the site check
    before and after. `check.new` lists what the change would break."""
    new_bytes = doc.raw()
    before = check_loaded(ctx.mos)
    after = check_site(new_bytes)
    plan = {"notes": [], "confirm": [], "focus": None, **plan, "changes": doc.changes}
    plan["steps"] = manual_steps(doc, doc.changes, ctx.kb.get("catalog") or {})
    plan["todo"] = plan.get("todo") or []
    plan["stepsText"] = steps_text(plan["steps"], plan["todo"])
    plan["check"] = {
        "before": before["summary"],
        "after": after["summary"],
        "new": new_findings(before, after, [(c["old"], c["new"]) for c in doc.changes if c["op"] == "renumber"]),
    }
    return new_bytes, plan

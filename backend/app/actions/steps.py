"""
A plan as steps to make by hand, in the Nokia WebUI or any editor that
shows the object tree: one step per object, parents first, saying what to
create, change or delete, with each parameter's full name from the
knowledge base and the reason the plan gives.

A created object is read back from the planned document whole, with every
list and row, however the plan built it (create, clone, rows added later).
A changed object lists its parameter and row changes.

A renumber is done by hand as a copy under the new number, the references
re-pointed to it, then the old number deleted. Its steps keep that order,
one renumber after another (the order Doc.renumber was called in keeps each
new number free), so they aren't merged or sorted across renumbers.
"""
from __future__ import annotations

from typing import Optional

from .doc import Doc, _local, _text, label, parent_dn


def _full_name(catalog: dict, cls: str, name: str) -> Optional[str]:
    base = name.split("[", 1)[0].split(".")[-1]
    p = ((catalog.get(cls) or {}).get("params") or {}).get(base) or {}
    return " ".join(p["fullName"].split()) if p.get("fullName") else None


def _content(doc: Doc, dn: str) -> tuple[list[tuple[str, str]], list[dict]]:
    """(parameters, lists) of an object in the planned document."""
    el = doc.mos[dn]
    params, lists = [], []
    for c in el:
        if _local(c.tag) == "p":
            params.append((c.get("name"), _text(c)))
        elif _local(c.tag) == "list":
            items = [i for i in c if _local(i.tag) == "item"]
            if items:
                rows = [{p.get("name"): _text(p) for p in i if _local(p.tag) == "p"} for i in items]
                lists.append({"name": c.get("name"), "rows": rows})
            else:
                lists.append({"name": c.get("name"), "values": [_text(p) for p in c if _local(p.tag) == "p"]})
    return params, lists


def manual_steps(doc: Doc, changes: list[dict], catalog: dict) -> list[dict]:
    steps: dict[tuple[str, int], dict] = {}
    order: list[tuple[str, int]] = []
    created = {c["dn"] for c in changes if c["op"] == "create"}
    phase = 0  # one per renumber
    gone: list[dict] = []  # the renumber in progress: its old number, deleted after its references move

    def step(c: dict, dn: Optional[str] = None) -> dict:
        dn = dn or c["dn"]
        key = (dn, phase)
        if key not in steps:
            steps[key] = {"key": f"{dn}#{phase}", "dn": dn, "class": c["class"], "label": label(dn),
                          "parent": parent_dn(dn), "kind": "modify", "params": [], "lists": [], "items": [],
                          "reasons": []}
            order.append(key)
        s = steps[key]
        if c.get("reason") and c["reason"] not in s["reasons"]:
            s["reasons"].append(c["reason"])
        return s

    def flush() -> None:
        for c in gone:
            s = step({"class": c["class"], "reason": f"The old number: it is {label(c['new'])} now."}, c["old"])
            s.update(kind="delete", count=c["count"])
        gone.clear()

    for c in changes:
        if c["op"] == "renumber":
            flush()
            phase += 1
            s = step(c)
            s.update(kind="create", copyOf=c["old"], count=c["count"])
            gone.append(c)
            continue
        s = step(c)
        if c["op"] == "create":
            s["kind"] = "create"
            if c.get("clonedFrom"):
                s["clonedFrom"] = c["clonedFrom"]
        elif c["op"] == "delete":
            s["kind"] = "delete"
            s["count"] = c.get("count") or 1
        elif c["dn"] in created:
            continue  # read back whole below
        elif c["op"] in ("set", "unset"):
            s["items"].append({"op": c["op"], "param": c["param"], "old": c.get("old"), "new": c.get("new"),
                               "name": _full_name(catalog, c["class"], c["param"])})
        elif c["op"] in ("add-row", "remove-row"):
            s["items"].append({"op": c["op"], "param": c["param"], "row": c.get("row") or {},
                               "name": _full_name(catalog, c["class"], c["param"])})
    flush()
    for key in order:
        s = steps[key]
        if s["kind"] == "create" and s["dn"] in doc.mos:
            params, lists = _content(doc, s["dn"])
            s["params"] = [{"param": k, "value": v, "name": _full_name(catalog, s["class"], k)} for k, v in params]
            s["lists"] = lists
    if phase:
        return [steps[k] for k in order]
    # Parents before children: a created child after its created parent.
    dns = [dn for dn, _ in order]
    return sorted((steps[k] for k in order), key=lambda s: (dns.index(_root_created(s["dn"], created, dns)),
                                                             s["dn"].count("/")))


def _root_created(dn: str, created: set[str], order: list[str]) -> str:
    """The outermost object created in this plan that `dn` lies under (or
    `dn` itself), so a subtree stays together where it first appears."""
    top = dn
    while parent_dn(top) in created and parent_dn(top) in order:
        top = parent_dn(top)
    return top


def _named(param: str, name: Optional[str]) -> str:
    return f"{param} ({name})" if name and name.lower() != param.lower() else param


def _row(row: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in row.items()) or "(empty)"


def steps_text(steps: list[dict], todo: Optional[list[str]] = None) -> str:
    """The steps as plain text, numbered, for copying into a ticket or a
    method of procedure, then what is left to do by hand."""
    out = []
    for n, s in enumerate(steps, 1):
        if s["kind"] == "create":
            copy = (f", a copy of {label(s['copyOf'])}" + (f" with the {s['count'] - 1} objects under it"
                                                           if s["count"] > 1 else "")) if s.get("copyOf") else ""
            out.append(f"{n}. Create {s['label']} under {s['parent']}{copy}")
            out += [f"     {_named(p['param'], p['name'])} = {p['value'] if p['value'] is not None else ''}"
                    for p in s["params"]]
            for lst in s["lists"]:
                if "rows" in lst:
                    out += [f"     {lst['name']} row {i}: {_row(r)}" for i, r in enumerate(lst["rows"], 1)]
                else:
                    out.append(f"     {lst['name']}: {', '.join(v or '' for v in lst['values'])}")
        elif s["kind"] == "delete":
            out.append(f"{n}. Delete {s['dn']}" + (f" and the {s['count'] - 1} objects under it" if s["count"] > 1
                                                    else ""))
        else:
            out.append(f"{n}. On {s['dn']} ({s['class']})")
            for i in s["items"]:
                if i["op"] == "set":
                    out.append(f"     set {_named(i['param'], i['name'])}: "
                               f"{i['old'] if i['old'] is not None else 'not set'} -> {i['new']}")
                elif i["op"] == "unset":
                    out.append(f"     remove {_named(i['param'], i['name'])} (was {i['old']})")
                elif i["op"] == "add-row":
                    out.append(f"     {i['param']}: add a row: {_row(i['row'])}")
                else:
                    out.append(f"     {i['param']}: remove the row {_row(i['row'])}")
    if todo:
        out += ([""] if out else []) + ["Also needed, by hand:"] + [f"  - {t}" for t in todo]
    return "\n".join(out)

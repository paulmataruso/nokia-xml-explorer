"""
The editing engine behind every site action: the target file held as an
ElementTree, with every write recorded as a change for the review step.

Change records use the node ids of parse_file() and parse_file_raw()
("{dn}::p::{name}", "{dn}::list::{name}::item::{i}"), so the editor can
focus what an action touched. Lists are writable here although the manual
editor treats them as read-only: DRX tables, qciTab, NRDU.refNrCellGroup,
SYNC.targetDNList, IPRT and RTPOL are all lists.

Pure like parser.py: bytes in, bytes out.
"""
from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from typing import Optional

from ..parser import XmlParseError, _local, _qualify, _serialize, _short_class, _strip_leading_junk, _text


def natural(dn: str) -> list:
    """Sort key that puts LNCEL-2 before LNCEL-10."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", dn)]


def parent_dn(dn: str) -> str:
    return dn.rsplit("/", 1)[0] if "/" in dn else dn


def label(dn: str) -> str:
    """"MRBTS-1/LNBTS-1/LNCEL-3" -> "LNCEL-3"."""
    return dn.rsplit("/", 1)[-1]


def instance(dn: str) -> str:
    """"MRBTS-1/LNBTS-1/LNCEL-3" -> "3"."""
    return label(dn).rsplit("-", 1)[-1]


def release_of(version: Optional[str]) -> Optional[str]:
    """"TLF21A_2012_03_2010_01" -> "TLF21A"."""
    return version.split("_", 1)[0] if version else None


def why(group: str, reason: str, basis: str, rule: Optional[tuple[str, Optional[str]]] = None) -> dict:
    """What a change record says about itself. `basis` is one of official
    (a dictionary rule, `rule` = (parameter, rule number)), files (a pattern
    from the corpus), donor (a value copied from another file) or choice
    (the user's input)."""
    return {"group": group, "reason": reason, "basis": basis,
            "rule": {"param": rule[0], "number": rule[1]} if rule else None}


def _joined(values: list[str]) -> Optional[str]:
    return ", ".join(values) if values else None


class Doc:
    """The target as an ElementTree; every write is recorded in `changes`."""

    def __init__(self, raw: bytes):
        try:
            self.root = ET.fromstring(_strip_leading_junk(raw))
        except ET.ParseError as e:
            raise XmlParseError(str(e)) from e
        self.cmdata = next((el for el in self.root.iter() if _local(el.tag) == "cmData"), None)
        if self.cmdata is None:
            raise XmlParseError("No <cmData> element found in this file")
        self.mos = {el.get("distName"): el for el in self.cmdata if _local(el.tag) == "managedObject"}
        self.changes: list[dict] = []

    # Reading -----------------------------------------------------------------

    def exists(self, dn: str) -> bool:
        return dn in self.mos

    def cls(self, dn: str) -> Optional[str]:
        el = self.mos.get(dn)
        return _short_class(el.get("class")) if el is not None else None

    def of_class(self, cls: str, under: Optional[str] = None) -> list[str]:
        """Every object of this class, optionally inside one subtree, in
        distName order."""
        out = [d for d, el in self.mos.items() if _short_class(el.get("class")) == cls
               and (under is None or d.startswith(under + "/"))]
        return sorted(out, key=natural)

    def children(self, dn: str, cls: Optional[str] = None) -> list[str]:
        out = [d for d in self.mos if parent_dn(d) == dn and d != dn
               and (cls is None or self.cls(d) == cls)]
        return sorted(out, key=natural)

    def subtree(self, dn: str) -> list[str]:
        """The object and everything under it, in file order."""
        return [d for d in self.mos if d == dn or d.startswith(dn + "/")]

    def _p(self, dn: str, name: str) -> Optional[ET.Element]:
        el = self.mos.get(dn)
        if el is None:
            return None
        return next((c for c in el if _local(c.tag) == "p" and c.get("name") == name), None)

    def get(self, dn: str, name: str) -> Optional[str]:
        p = self._p(dn, name)
        return _text(p) if p is not None else None

    def params(self, dn: str) -> dict[str, Optional[str]]:
        el = self.mos.get(dn)
        if el is None:
            return {}
        return {c.get("name"): _text(c) for c in el if _local(c.tag) == "p"}

    def _list(self, dn: str, name: str) -> Optional[ET.Element]:
        el = self.mos.get(dn)
        if el is None:
            return None
        return next((c for c in el if _local(c.tag) == "list" and c.get("name") == name), None)

    def items(self, dn: str, name: str) -> list[dict[str, Optional[str]]]:
        """Rows of an item list (<list><item><p/>...</item></list>)."""
        lst = self._list(dn, name)
        if lst is None:
            return []
        return [{p.get("name"): _text(p) for p in item if _local(p.tag) == "p"}
                for item in lst if _local(item.tag) == "item"]

    def values(self, dn: str, name: str) -> list[str]:
        """Values of a simple list (<list><p>a</p><p>b</p></list>)."""
        lst = self._list(dn, name)
        if lst is None:
            return []
        return [_text(p) or "" for p in lst if _local(p.tag) == "p"]

    def class_info(self, cls: str) -> Optional[tuple[str, Optional[str]]]:
        """(class attribute, version) of an existing object of this class."""
        el = next((el for el in self.mos.values() if _short_class(el.get("class")) == cls), None)
        return (el.get("class"), el.get("version")) if el is not None else None

    def next_free(self, parent: str, cls: str, start: int = 1) -> str:
        used = {instance(d) for d in self.mos if parent_dn(d) == parent and label(d).rsplit("-", 1)[0] == cls}
        i = start
        while str(i) in used:
            i += 1
        return str(i)

    def raw(self) -> bytes:
        return _serialize(self.root)

    # Writing: scalar parameters ------------------------------------------------

    def _record(self, w: dict, op: str, dn: str, node_id: str, **fields) -> None:
        self.changes.append({**w, "op": op, "dn": dn, "id": node_id, "class": self.cls(dn), **fields})

    def _insert_named(self, el: ET.Element, child: ET.Element) -> None:
        # Keep the alphabetical order Nokia's exports use for <p> and <list>.
        name = (child.get("name") or "").lower()
        at = next((i for i, c in enumerate(el) if (c.get("name") or "").lower() > name), len(el))
        el.insert(at, child)

    def set(self, dn: str, name: str, value: str, w: dict) -> bool:
        old = self.get(dn, name)
        if old == value or dn not in self.mos:
            return False
        el = self.mos[dn]
        p = self._p(dn, name)
        if p is None:
            p = ET.Element(_qualify("p", el.tag))
            p.set("name", name)
            self._insert_named(el, p)
        p.text = value
        self._record(w, "set", dn, f"{dn}::p::{name}", param=name, old=old, new=value)
        return True

    def unset(self, dn: str, name: str, w: dict) -> bool:
        p = self._p(dn, name)
        if p is None:
            return False
        old = _text(p)
        self.mos[dn].remove(p)
        self._record(w, "unset", dn, dn, param=name, old=old, new=None)
        return True

    # Writing: objects --------------------------------------------------------

    def _place(self, el: ET.Element, cls: str, dn: str) -> None:
        # Next to the other objects of its class, in distName order, else
        # after its parent's subtree, so class-sorted exports stay sorted.
        kids = list(self.cmdata)
        same = [i for i, c in enumerate(kids) if _local(c.tag) == "managedObject" and _short_class(c.get("class")) == cls]
        if same:
            before = [i for i in same if natural(kids[i].get("distName") or "") < natural(dn)]
            at = before[-1] + 1 if before else same[0]
        else:
            parent = parent_dn(dn)
            under = [i for i, c in enumerate(kids)
                     if (c.get("distName") or "") == parent or (c.get("distName") or "").startswith(parent + "/")]
            at = under[-1] + 1 if under else len(kids)
        self.cmdata.insert(at, el)
        self.mos[dn] = el

    def create(self, parent: str, cls: str, inst: str, params: list[tuple[str, str]],
               full_class: Optional[str] = None, version: Optional[str] = None,
               w: Optional[dict] = None) -> str:
        """A new object with these scalar parameters. The class attribute
        and version default to those of an existing object of the class."""
        dn = f"{parent}/{cls}-{inst}"
        if dn in self.mos:
            raise ValueError(f"{dn} already exists")
        known = self.class_info(cls)
        el = ET.Element(_qualify("managedObject", self.cmdata.tag))
        el.set("class", full_class or (known[0] if known else cls))
        el.set("distName", dn)
        el.set("operation", "create")
        version = version or (known[1] if known else None)
        if version:
            el.set("version", version)
        for name, value in params:
            p = ET.SubElement(el, _qualify("p", self.cmdata.tag))
            p.set("name", name)
            p.text = value
        self._place(el, cls, dn)
        self._record(w or {}, "create", dn, dn, params=dict(params))
        return dn

    def delete(self, dn: str, w: dict) -> list[str]:
        """Deletes the object and its subtree; returns the distNames gone."""
        gone = self.subtree(dn)
        cls = self.cls(dn)
        for d in gone:
            self.cmdata.remove(self.mos.pop(d))
        self.changes.append({**w, "op": "delete", "dn": dn, "id": parent_dn(dn), "class": cls,
                             "count": len(gone)})
        return gone

    def clone(self, src: str, dst: str, w: dict, rewrite: Optional[dict[str, str]] = None,
              overrides: Optional[dict[str, dict[str, Optional[str]]]] = None,
              skip: frozenset = frozenset()) -> list[str]:
        """Copies the subtree at `src` to `dst` (same class, new instance).

        Every distName inside the copy, and every parameter or list value
        naming an object inside it, moves from `src` to `dst`. `rewrite`
        maps further distName prefixes (objects outside the subtree that the
        copy should point at instead). `overrides` is keyed by the path
        below `dst` ("" for the root, "CHANNELGROUP-1/CHANNEL-3" below it)
        and sets parameters on the copy; None removes one. Objects of a class
        in `skip`, and everything under them, aren't copied (a cell's
        neighbour relations). Returns the new distNames in file order."""
        if src not in self.mos:
            raise ValueError(f"{src} doesn't exist")
        if dst in self.mos:
            raise ValueError(f"{dst} already exists")
        moves = sorted({src: dst, **(rewrite or {})}.items(), key=lambda kv: -len(kv[0]))

        def move(value: Optional[str]) -> Optional[str]:
            if not value:
                return value
            for old, new in moves:
                if value == old or value.startswith(old + "/"):
                    return new + value[len(old):]
            return value

        created = []
        skipped = [d for d in self.subtree(src) if d != src and self.cls(d) in skip]
        for d in self.subtree(src):
            if any(d == x or d.startswith(x + "/") for x in skipped):
                continue
            el = copy.deepcopy(self.mos[d])
            new_dn = dst + d[len(src):]
            el.set("distName", new_dn)
            el.set("operation", "create")
            for p in el.iter():
                if _local(p.tag) == "p" and p.text:
                    p.text = move(p.text)
            rel = new_dn[len(dst) + 1:] if new_dn != dst else ""
            for name, value in ((overrides or {}).get(rel) or {}).items():
                p = next((c for c in el if _local(c.tag) == "p" and c.get("name") == name), None)
                if value is None:
                    if p is not None:
                        el.remove(p)
                    continue
                if p is None:
                    p = ET.Element(_qualify("p", el.tag))
                    p.set("name", name)
                    self._insert_named(el, p)
                p.text = value
            self._place(el, _short_class(el.get("class")), new_dn)
            created.append(new_dn)
            self.changes.append({**w, "op": "create", "dn": new_dn, "id": new_dn, "class": _short_class(el.get("class")),
                                 "params": {c.get("name"): _text(c) for c in el if _local(c.tag) == "p"},
                                 "clonedFrom": d})
        return created

    # Writing: renumbering ----------------------------------------------------

    # Simple lists that hold another object's instance number, not its
    # distName (refmap.py's id links): (holder, list, the class numbered).
    NUMBER_LISTS = (("NRCELLGRP", "nrCellList", "NRCELL"), ("NRDU", "refNrCellGroup", "NRCELLGRP"))

    def renumber(self, old: str, new: str, w: dict, ref: Optional[dict] = None) -> list[str]:
        """Gives the object at `old` the distName `new` (same parent and
        class, another instance number). It and everything under it change
        distName in place, every value in the file naming any of them moves
        with them, and so does its number in the number lists. Recorded the
        way it is done by hand: a "renumber" (steps.py makes it a copy under
        the new number, then the old one's deletion), then each value
        re-pointed, recorded with `ref` (else `w`). Returns the new
        distNames."""
        if old not in self.mos:
            raise ValueError(f"{old} doesn't exist")
        if new in self.mos:
            raise ValueError(f"{new} already exists")
        if old.rpartition("/")[0] != new.rpartition("/")[0] or label(old).rsplit("-", 1)[0] != label(new).rsplit("-", 1)[0]:
            raise ValueError(f"{new} isn't {old} under another number")

        def move(v: Optional[str]) -> Optional[str]:
            return new + v[len(old):] if v and (v == old or v.startswith(old + "/")) else v

        cls = self.cls(old)
        # Every element, not self.mos: a distName a file repeats has more than one.
        elements = [el for el in self.cmdata if _local(el.tag) == "managedObject"]
        moved = [el for el in elements if move(el.get("distName")) != el.get("distName")]
        inside = {id(el) for el in moved}
        for el in moved:
            el.set("distName", move(el.get("distName")))
        self.mos = {el.get("distName"): el for el in elements}
        self.changes.append({**w, "op": "renumber", "dn": new, "id": new, "class": cls, "old": old, "new": new,
                             "count": len({el.get("distName") for el in moved})})
        r = ref or w

        def point(el: ET.Element, p: ET.Element, node_id: str, param: str) -> None:
            before, p.text = _text(p), move(_text(p))
            if id(el) not in inside:
                self._record(r, "set", el.get("distName"), node_id, param=param, old=before, new=p.text)

        for el in elements:
            dn = el.get("distName")
            for c in el:
                tag, name = _local(c.tag), c.get("name")
                if tag == "p" and move(_text(c)) != _text(c):
                    point(el, c, f"{dn}::p::{name}", name)
                elif tag == "list":
                    items = [i for i in c if _local(i.tag) == "item"]
                    for index, item in enumerate(items):
                        for p in item:
                            if _local(p.tag) == "p" and move(_text(p)) != _text(p):
                                point(el, p, f"{dn}::list::{name}::item::{index}::p::{p.get('name')}",
                                      f"{name}[{index + 1}].{p.get('name')}")
                    values = [p for p in c if _local(p.tag) == "p"]
                    if any(move(_text(p)) != _text(p) for p in values):
                        before = [_text(p) or "" for p in values]
                        for p in values:
                            p.text = move(_text(p))
                        if id(el) not in inside:
                            self._record(r, "set", dn, f"{dn}::list::{name}", param=f"{name}[]", old=_joined(before),
                                         new=_joined([_text(p) or "" for p in values]))
        for holder, name, numbered in self.NUMBER_LISTS:
            if cls != numbered:
                continue
            for h in self.of_class(holder, under=parent_dn(new)):
                values = self.values(h, name)
                if instance(old) in values:
                    self.set_values(h, name, [instance(new) if v == instance(old) else v for v in values], r)
        if cls == "LNBTS" or "/" not in old:
            self._own_enb(instance(old), new, r)
        return list(dict.fromkeys(el.get("distName") for el in moved))

    def _own_enb(self, number: str, new: str, w: dict) -> None:
        """An LTE relation to a cell of its own eNB names the eNB by the
        LNBTS's number or the BTS's (links._own_enb_ids). When `number`, one
        of those, is no longer either, its relations to own cells name the
        new number instead."""
        for lnbts in [new] if self.cls(new) == "LNBTS" else self.of_class("LNBTS", under=new):
            if number in (instance(lnbts), instance(lnbts.split("/", 1)[0])):
                continue
            cells = {self.get(c, "lcrId") for c in self.children(lnbts, "LNCEL")}
            # As links._adjl: an LNADJL with that eNB and cell is the target, not an own cell.
            adjl = {(self.get(a, "ecgiAdjEnbId") or self.get(parent_dn(a), "adjEnbId"), self.get(a, "ecgiLcrId"))
                    for a in self.of_class("LNADJL", under=lnbts)}
            for rel in self.of_class("LNREL", under=lnbts):
                key = (self.get(rel, "ecgiAdjEnbId"), self.get(rel, "ecgiLcrId"))
                if key[0] == number and key[1] in cells and key not in adjl:
                    self.set(rel, "ecgiAdjEnbId", instance(new), w)

    # Writing: lists ----------------------------------------------------------

    def _ensure_list(self, dn: str, name: str) -> ET.Element:
        lst = self._list(dn, name)
        if lst is None:
            el = self.mos[dn]
            lst = ET.Element(_qualify("list", el.tag))
            lst.set("name", name)
            self._insert_named(el, lst)
        return lst

    def set_item(self, dn: str, list_name: str, index: int, name: str, value: str, w: dict) -> bool:
        lst = self._list(dn, list_name)
        items = [c for c in lst if _local(c.tag) == "item"] if lst is not None else []
        if index >= len(items):
            return False
        p = next((c for c in items[index] if _local(c.tag) == "p" and c.get("name") == name), None)
        old = _text(p) if p is not None else None
        if old == value:
            return False
        if p is None:
            p = ET.Element(_qualify("p", lst.tag))
            p.set("name", name)
            self._insert_named(items[index], p)
        p.text = value
        self._record(w, "set", dn, f"{dn}::list::{list_name}::item::{index}::p::{name}",
                     param=f"{list_name}[{index + 1}].{name}", old=old, new=value)
        return True

    def unset_item(self, dn: str, list_name: str, index: int, name: str, w: dict) -> bool:
        lst = self._list(dn, list_name)
        items = [c for c in lst if _local(c.tag) == "item"] if lst is not None else []
        if index >= len(items):
            return False
        p = next((c for c in items[index] if _local(c.tag) == "p" and c.get("name") == name), None)
        if p is None:
            return False
        old = _text(p)
        items[index].remove(p)
        self._record(w, "unset", dn, f"{dn}::list::{list_name}::item::{index}",
                     param=f"{list_name}[{index + 1}].{name}", old=old, new=None)
        return True

    def add_item(self, dn: str, list_name: str, row: list[tuple[str, str]], w: dict) -> int:
        """Appends a row to an item list (creating the list); returns its index."""
        lst = self._ensure_list(dn, list_name)
        item = ET.SubElement(lst, _qualify("item", lst.tag))
        for name, value in row:
            p = ET.SubElement(item, _qualify("p", lst.tag))
            p.set("name", name)
            p.text = value
        index = sum(1 for c in lst if _local(c.tag) == "item") - 1
        self._record(w, "add-row", dn, f"{dn}::list::{list_name}::item::{index}",
                     param=list_name, row=dict(row))
        return index

    def remove_item(self, dn: str, list_name: str, index: int, w: dict) -> bool:
        lst = self._list(dn, list_name)
        items = [c for c in lst if _local(c.tag) == "item"] if lst is not None else []
        if index >= len(items):
            return False
        row = {p.get("name"): _text(p) for p in items[index] if _local(p.tag) == "p"}
        lst.remove(items[index])
        if len(items) == 1:
            self.mos[dn].remove(lst)
        self._record(w, "remove-row", dn, f"{dn}::list::{list_name}" if len(items) > 1 else dn,
                     param=f"{list_name}[{index + 1}]", row=row)
        return True

    def set_values(self, dn: str, list_name: str, values: list[str], w: dict) -> bool:
        """Replaces a simple list's values; an empty list removes it."""
        old = self.values(dn, list_name)
        if old == values or dn not in self.mos:
            return False
        lst = self._list(dn, list_name)
        if not values:
            if lst is not None:
                self.mos[dn].remove(lst)
            node_id = dn
        else:
            lst = self._ensure_list(dn, list_name)
            for c in list(lst):
                lst.remove(c)
            for v in values:
                ET.SubElement(lst, _qualify("p", lst.tag)).text = v
            node_id = f"{dn}::list::{list_name}"
        self._record(w, "set", dn, node_id, param=f"{list_name}[]", old=_joined(old), new=_joined(values))
        return True

    def add_value(self, dn: str, list_name: str, value: str, w: dict) -> bool:
        """Appends to a simple list unless the value is already there."""
        old = self.values(dn, list_name)
        return value not in old and self.set_values(dn, list_name, [*old, value], w)

    def remove_value(self, dn: str, list_name: str, value: str, w: dict) -> bool:
        old = self.values(dn, list_name)
        return value in old and self.set_values(dn, list_name, [v for v in old if v != value], w)

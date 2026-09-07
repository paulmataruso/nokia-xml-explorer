"""
Parses a Nokia RAML (raml21.xsd) commissioning/configuration XML file into a
JSON-serializable tree keyed by distName hierarchy, ready for the frontend
tree view.

Nokia's RAML files are *flat*: every managedObject is a sibling under
<cmData>, and its `distName` attribute (e.g. "MRBTS-1/EQM-1/APEQM-1/RMOD-1")
encodes its full ancestry. This module reconstructs the real parent/child
hierarchy from those paths, since that's what a human actually wants to
browse (and is far more useful than the flat, un-nested raw XML order).
"""
from __future__ import annotations

import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

_XML_START_RE = re.compile(rb"<\?xml|<raml", re.IGNORECASE)


class XmlParseError(Exception):
    pass


_ROOT_TAG_RE = re.compile(rb"<([A-Za-z][\w\-]*)")


def _strip_leading_junk(raw: bytes) -> bytes:
    """Some files in the wild have stray text (e.g. a pasted PDF print-preview
    header/footer) before the real `<?xml ...?>` declaration and/or after the
    closing root tag -- apparently from being printed/copied out of a PDF
    viewer. Trim anything outside the actual <raml>...</raml> document."""
    m = _XML_START_RE.search(raw)
    cleaned = raw[m.start():] if m is not None else raw

    m2 = _ROOT_TAG_RE.search(cleaned)
    if m2 is not None:
        root_tag = m2.group(1)
        closing = b"</" + root_tag + b">"
        idx = cleaned.rfind(closing)
        if idx != -1:
            cleaned = cleaned[: idx + len(closing)]
    return cleaned


def _local(tag: str) -> str:
    """Strip a `{namespace}` prefix from an ElementTree tag."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _short_class(full_class: Optional[str]) -> str:
    if not full_class:
        return ""
    return full_class.split(":")[-1]


def _text(el: ET.Element) -> Optional[str]:
    if el.text is None:
        return None
    t = el.text.strip()
    return t if t else None


def _parse_param_children(
    container: ET.Element, base_id: str, short_class: str, owner_dist_name: Optional[str] = None
) -> list[dict]:
    """owner_dist_name is the enclosing managedObject's distName, but ONLY
    set for params that are its DIRECT children -- it's left None for params
    nested inside a list/item (deliberately not threaded into the recursive
    call below), since delete_param (and set_param_value) only operate on an
    object's direct <p> children. The frontend uses this to decide whether a
    delete control makes sense for a given param row."""
    children: list[dict] = []
    for child in container:
        tag = _local(child.tag)
        if tag == "p":
            name = child.get("name") or "(unnamed)"
            children.append({
                "id": f"{base_id}::p::{name}",
                "label": name,
                "kind": "param",
                "value": _text(child),
                "class": short_class,
                "fullClass": None,
                "distName": None,
                "ownerDistName": owner_dist_name,
                "operation": None,
                "version": None,
                "children": [],
            })
        elif tag == "list":
            name = child.get("name") or "(unnamed list)"
            list_id = f"{base_id}::list::{name}"
            items = []
            for i, item_el in enumerate(child):
                item_id = f"{list_id}::item::{i}"
                item_children = _parse_param_children(item_el, item_id, short_class)
                items.append({
                    "id": item_id,
                    "label": f"Row {i + 1}",
                    "kind": "item",
                    "value": None,
                    "class": short_class,
                    "fullClass": None,
                    "distName": None,
                    "operation": None,
                    "version": None,
                    "children": item_children,
                })
            children.append({
                "id": list_id,
                "label": name,
                "kind": "list",
                "value": None,
                "class": short_class,
                "fullClass": None,
                "distName": None,
                "operation": None,
                "version": None,
                "rowCount": len(items),
                "children": items,
            })
        # any other unexpected tag is ignored defensively; RAML files in the
        # wild only use p/list under managedObject.
    return children


def parse_file(raw_bytes: bytes, filename: str) -> dict:
    cleaned = _strip_leading_junk(raw_bytes)
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as e:
        raise XmlParseError(str(e)) from e

    # cmData may or may not be namespaced depending on how the file declares xmlns.
    cmdata = None
    for el in root.iter():
        if _local(el.tag) == "cmData":
            cmdata = el
            break

    raml_attrs = dict(root.attrib)
    cmdata_attrs = dict(cmdata.attrib) if cmdata is not None else {}

    log_nodes = []
    mo_elements: list[ET.Element] = []

    if cmdata is not None:
        for child in cmdata:
            tag = _local(child.tag)
            if tag == "header":
                for i, log_el in enumerate(child):
                    if _local(log_el.tag) != "log":
                        continue
                    attrs = dict(log_el.attrib)
                    summary = f"{attrs.get('action', 'event')} @ {attrs.get('dateTime', '?')}"
                    if attrs.get("user"):
                        summary += f" by {attrs['user']}"
                    log_nodes.append({
                        "id": f"fileinfo::log::{i}",
                        "label": summary,
                        "kind": "log",
                        "value": None,
                        "class": None,
                        "fullClass": None,
                        "distName": None,
                        "operation": None,
                        "version": None,
                        "attrs": attrs,
                        "children": [],
                    })
            elif tag == "managedObject":
                mo_elements.append(child)

    # --- Build MO nodes (params/lists resolved), keyed by distName ---
    nodes: dict[str, dict] = {}
    doc_order: list[str] = []

    for mo in mo_elements:
        dist_name = mo.get("distName")
        if not dist_name:
            continue
        full_class = mo.get("class")
        short_class = _short_class(full_class)
        node = {
            "id": dist_name,
            "label": dist_name.rsplit("/", 1)[-1],
            "kind": "mo",
            "value": None,
            "class": short_class,
            "fullClass": full_class,
            "distName": dist_name,
            "operation": mo.get("operation"),
            "version": mo.get("version"),
            "children": _parse_param_children(mo, dist_name, short_class, owner_dist_name=dist_name),
        }
        if dist_name in nodes:
            # Duplicate distName in the same file (rare, but be defensive):
            # merge children rather than dropping data.
            nodes[dist_name]["children"].extend(node["children"])
        else:
            nodes[dist_name] = node
            doc_order.append(dist_name)

    top_level: list[dict] = []
    linked: set[str] = set()

    def ensure_node(dn: str) -> dict:
        if dn not in nodes:
            last = dn.rsplit("/", 1)[-1]
            short = last.rsplit("-", 1)[0] if "-" in last else last
            nodes[dn] = {
                "id": dn,
                "label": last,
                "kind": "mo-placeholder",
                "value": None,
                "class": short,
                "fullClass": None,
                "distName": dn,
                "operation": None,
                "version": None,
                "children": [],
            }
            doc_order.append(dn)
        link(dn)
        return nodes[dn]

    def link(dn: str) -> None:
        if dn in linked:
            return
        linked.add(dn)
        if "/" not in dn:
            top_level.append(nodes[dn])
            return
        parent_dn = dn.rsplit("/", 1)[0]
        parent = ensure_node(parent_dn)
        parent["children"].append(nodes[dn])

    for dn in list(doc_order):
        link(dn)

    file_info_node = {
        "id": "fileinfo",
        "label": "File Info (raml / cmData / header)",
        "kind": "fileinfo",
        "value": None,
        "class": None,
        "fullClass": None,
        "distName": None,
        "operation": None,
        "version": None,
        "attrs": {**{f"raml.{k}": v for k, v in raml_attrs.items()},
                  **{f"cmData.{k}": v for k, v in cmdata_attrs.items()}},
        "children": log_nodes,
    }

    total_managed_objects = len(nodes)
    total_params = sum(_count_kind(n, "param") for n in top_level)

    return {
        "filename": filename,
        "stats": {
            "managedObjects": total_managed_objects,
            "parameters": total_params,
        },
        "children": [file_info_node] + top_level,
    }


def _count_kind(node: dict, kind: str) -> int:
    count = 1 if node.get("kind") == kind else 0
    for c in node.get("children", []):
        count += _count_kind(c, kind)
    return count


# ---------------------------------------------------------------------------
# Raw/literal XML tree: mirrors the document exactly as written (tag names,
# attribute order, nesting, flat managedObject siblings) rather than the
# distName-reconstructed hierarchy above. Used for the side-by-side "real
# XML" view.
#
# Node ids are deliberately generated with the *same* formula as parse_file()
# above (distName for managedObject, "{base}::p::{name}", "{base}::list::
# {name}", "{list}::item::{i}", and "fileinfo" / "fileinfo::log::{i}" for the
# header/log elements) so the frontend can highlight the raw node
# corresponding to a logical-tree node with a plain id lookup -- no fuzzy
# matching needed.
# ---------------------------------------------------------------------------

def _parse_raw_children(container: ET.Element, base_id: str, owner_dist_name: Optional[str] = None) -> list[dict]:
    """owner_dist_name mirrors _parse_param_children's: set only for <p>
    elements directly under a managedObject, left None for ones nested in a
    list/item (not threaded into the recursive calls below)."""
    children: list[dict] = []
    for child in container:
        tag = _local(child.tag)
        if tag == "p":
            name = child.get("name") or "(unnamed)"
            children.append({
                "id": f"{base_id}::p::{name}",
                "tag": "p",
                "attrs": dict(child.attrib),
                "text": _text(child),
                "ownerDistName": owner_dist_name,
                "children": [],
            })
        elif tag == "list":
            name = child.get("name") or "(unnamed list)"
            list_id = f"{base_id}::list::{name}"
            items = []
            for i, item_el in enumerate(child):
                item_id = f"{list_id}::item::{i}"
                items.append({
                    "id": item_id,
                    "tag": "item",
                    "attrs": dict(item_el.attrib),
                    "text": None,
                    "children": _parse_raw_children(item_el, item_id),
                })
            children.append({
                "id": list_id,
                "tag": "list",
                "attrs": dict(child.attrib),
                "text": None,
                "children": items,
            })
        else:
            # Defensive: preserve any unexpected element verbatim too.
            children.append({
                "id": f"{base_id}::{tag}::{len(children)}",
                "tag": tag,
                "attrs": dict(child.attrib),
                "text": _text(child),
                "children": _parse_raw_children(child, f"{base_id}::{tag}::{len(children)}"),
            })
    return children


def parse_file_raw(raw_bytes: bytes, filename: str) -> dict:
    """Builds a literal DOM-like tree of the file exactly as written."""
    cleaned = _strip_leading_junk(raw_bytes)
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as e:
        raise XmlParseError(str(e)) from e

    root_attrs = dict(root.attrib)
    if root.tag.startswith("{"):
        # ElementTree consumes `xmlns="..."` into the tag's namespace rather
        # than leaving it in .attrib -- put it back so the raw view matches
        # the source file exactly.
        ns = root.tag[1:].split("}", 1)[0]
        root_attrs = {"xmlns": ns, **root_attrs}

    root_node = {
        "id": "raw-root",
        "tag": _local(root.tag),
        "attrs": root_attrs,
        "text": None,
        "children": [],
    }

    cmdata_el = None
    for el in root.iter():
        if _local(el.tag) == "cmData":
            cmdata_el = el
            break

    if cmdata_el is not None:
        cmdata_node = {
            "id": "fileinfo",
            "tag": "cmData",
            "attrs": dict(cmdata_el.attrib),
            "text": None,
            "children": [],
        }
        root_node["children"].append(cmdata_node)

        mo_fallback_counter = 0
        for child in cmdata_el:
            tag = _local(child.tag)
            if tag == "header":
                header_node = {
                    "id": "fileinfo-header",
                    "tag": "header",
                    "attrs": dict(child.attrib),
                    "text": None,
                    "children": [],
                }
                for i, log_el in enumerate(child):
                    if _local(log_el.tag) != "log":
                        continue
                    header_node["children"].append({
                        "id": f"fileinfo::log::{i}",
                        "tag": "log",
                        "attrs": dict(log_el.attrib),
                        "text": None,
                        "children": [],
                    })
                cmdata_node["children"].append(header_node)
            elif tag == "managedObject":
                dist_name = child.get("distName")
                if not dist_name:
                    mo_fallback_counter += 1
                    mo_id = f"__mo_no_distname_{mo_fallback_counter}__"
                else:
                    mo_id = dist_name
                mo_node = {
                    "id": mo_id,
                    "tag": "managedObject",
                    "attrs": dict(child.attrib),
                    "text": None,
                    "children": _parse_raw_children(child, mo_id, owner_dist_name=dist_name),
                }
                cmdata_node["children"].append(mo_node)
            else:
                cmdata_node["children"].append({
                    "id": f"fileinfo-other-{tag}",
                    "tag": tag,
                    "attrs": dict(child.attrib),
                    "text": _text(child),
                    "children": [],
                })

    return {"filename": filename, "root": root_node}


# ---------------------------------------------------------------------------
# Editing: locate the exact <p> element a node id refers to (using the same
# id scheme built above) and update its value in place, then re-serialize
# the whole document. This intentionally re-parses from the raw bytes on
# every edit (rather than keeping a live in-memory tree) so each edit is
# independent and always reflects whatever is currently on disk.
#
# Note on fidelity: re-serializing via ElementTree does not reproduce the
# original file's exact whitespace/indentation -- it normalizes to a clean,
# consistently-indented form. The data and structure are preserved exactly;
# only incidental formatting changes.
# ---------------------------------------------------------------------------

class ParamNotFoundError(Exception):
    pass


def _find_managed_object(cmdata: ET.Element, dist_name: str) -> Optional[ET.Element]:
    for child in cmdata:
        if _local(child.tag) == "managedObject" and child.get("distName") == dist_name:
            return child
    return None


def _navigate_to_param(start: ET.Element, segments: list[str]) -> Optional[ET.Element]:
    """`segments` is the node id's parts after the leading distName, e.g.
    ['p', 'dscp'] or ['list', 'cipherPrefL', 'item', '0', 'p', 'eea0']."""
    current = start
    i = 0
    while i < len(segments):
        kind = segments[i]
        if kind == "p":
            name = segments[i + 1] if i + 1 < len(segments) else None
            for child in current:
                if _local(child.tag) == "p" and child.get("name") == name:
                    return child
            return None
        if kind == "list":
            name = segments[i + 1] if i + 1 < len(segments) else None
            list_el = None
            for child in current:
                if _local(child.tag) == "list" and child.get("name") == name:
                    list_el = child
                    break
            if list_el is None:
                return None
            current = list_el
            i += 2
            continue
        if kind == "item":
            try:
                idx = int(segments[i + 1])
            except (IndexError, ValueError):
                return None
            items = [c for c in current if _local(c.tag) == "item"]
            if idx < 0 or idx >= len(items):
                return None
            current = items[idx]
            i += 2
            continue
        return None
    return None


def update_param_value(raw_bytes: bytes, node_id: str, new_value: str) -> bytes:
    """Returns the full new file content (bytes) with the parameter
    identified by `node_id` set to `new_value` (empty string -> represented
    as an empty/self-closing <p>, matching how "unset" params already look
    elsewhere in these files)."""
    cleaned = _strip_leading_junk(raw_bytes)
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as e:
        raise XmlParseError(str(e)) from e

    cmdata = None
    for el in root.iter():
        if _local(el.tag) == "cmData":
            cmdata = el
            break
    if cmdata is None:
        raise ParamNotFoundError("No <cmData> element found in this file")

    parts = node_id.split("::")
    dist_name = parts[0]
    segments = parts[1:]
    if len(segments) < 2 or segments[-2] != "p":
        raise ParamNotFoundError(f"Not an editable parameter id: {node_id!r}")

    mo = _find_managed_object(cmdata, dist_name)
    if mo is None:
        raise ParamNotFoundError(f"No managedObject with distName={dist_name!r}")

    target = _navigate_to_param(mo, segments)
    if target is None or _local(target.tag) != "p":
        raise ParamNotFoundError(f"Parameter {node_id!r} not found")

    target.text = new_value if new_value != "" else None
    return _serialize(root)


def _serialize(root: ET.Element) -> bytes:
    # Without this, ElementTree serializes the default namespace with an
    # auto-generated "ns0:" prefix on every single tag instead of the
    # original bare-tag + xmlns="raml21.xsd" style Nokia's own tools emit.
    if root.tag.startswith("{"):
        ns_uri = root.tag[1:].split("}", 1)[0]
        ET.register_namespace("", ns_uri)

    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body + "\n").encode("utf-8")


class ObjectExistsError(Exception):
    pass


def _qualify(tag: str, sample_tag: str) -> str:
    """Builds a `{namespace}tag` string matching sample_tag's namespace (if
    any) so a freshly-created element serializes in the same style as its
    namespaced siblings instead of introducing a spurious ns0: prefix."""
    if sample_tag.startswith("{"):
        ns = sample_tag.split("}", 1)[0]
        return f"{ns}}}{tag}"
    return tag


def add_managed_object(
    raw_bytes: bytes,
    parent_dist_name: str | None,
    short_class: str,
    full_class: str,
    version: str | None,
    instance_id: str,
    params: dict[str, str],
) -> tuple[bytes, str]:
    """Appends a new <managedObject operation="create"> to the file. Returns
    (new_file_bytes, new_dist_name). Raises ObjectExistsError if an object
    with the resulting distName is already present."""
    cleaned = _strip_leading_junk(raw_bytes)
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as e:
        raise XmlParseError(str(e)) from e

    cmdata = None
    for el in root.iter():
        if _local(el.tag) == "cmData":
            cmdata = el
            break
    if cmdata is None:
        raise ParamNotFoundError("No <cmData> element found in this file")

    dist_name = f"{parent_dist_name}/{short_class}-{instance_id}" if parent_dist_name else f"{short_class}-{instance_id}"

    for child in cmdata:
        if _local(child.tag) == "managedObject" and child.get("distName") == dist_name:
            raise ObjectExistsError(f"An object with distName={dist_name!r} already exists")

    mo_tag = _qualify("managedObject", cmdata.tag)
    p_tag = _qualify("p", cmdata.tag)

    mo_el = ET.SubElement(cmdata, mo_tag)
    mo_el.set("class", full_class)
    mo_el.set("distName", dist_name)
    if version:
        mo_el.set("version", version)
    mo_el.set("operation", "create")

    for name, value in params.items():
        if value is None:
            continue
        p_el = ET.SubElement(mo_el, p_tag)
        p_el.set("name", name)
        # An explicit "" is a deliberate placeholder (e.g. a Mandatory
        # parameter with no safe default -- still written so it's visible
        # and flagged, but with nothing to text into) -- write it as a
        # self-closing tag rather than silently dropping it.
        p_el.text = str(value) if value != "" else None

    return _serialize(root), dist_name


def set_param_value(raw_bytes: bytes, dist_name: str, param_name: str, value: str) -> bytes:
    """Upsert a scalar parameter on an EXISTING managedObject: updates the
    <p> element's text if that parameter is already present, or creates a
    new one if it isn't. This is how a user adds a parameter to an object
    after creation, not just at the moment they generated it -- the
    "Add Object" form only offers a search box for a reason: nobody is
    expected to fill in a class's entire parameter set (some have 500+) up
    front, so this fills the gap it deliberately leaves open."""
    cleaned = _strip_leading_junk(raw_bytes)
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as e:
        raise XmlParseError(str(e)) from e

    cmdata = None
    for el in root.iter():
        if _local(el.tag) == "cmData":
            cmdata = el
            break
    if cmdata is None:
        raise ParamNotFoundError("No <cmData> element found in this file")

    mo = _find_managed_object(cmdata, dist_name)
    if mo is None:
        raise ParamNotFoundError(f"No managedObject with distName={dist_name!r}")

    target = None
    for child in mo:
        if _local(child.tag) == "p" and child.get("name") == param_name:
            target = child
            break

    if target is None:
        p_tag = _qualify("p", mo.tag)
        target = ET.SubElement(mo, p_tag)
        target.set("name", param_name)

    target.text = value if value != "" else None
    return _serialize(root)


def delete_param(raw_bytes: bytes, dist_name: str, param_name: str) -> bytes:
    """Removes a single scalar <p> from an existing managedObject. Callers
    are expected to have already checked it isn't a Mandatory parameter --
    this module doesn't know about the class catalog, so it just removes
    whatever <p> is asked for."""
    cleaned = _strip_leading_junk(raw_bytes)
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as e:
        raise XmlParseError(str(e)) from e

    cmdata = None
    for el in root.iter():
        if _local(el.tag) == "cmData":
            cmdata = el
            break
    if cmdata is None:
        raise ParamNotFoundError("No <cmData> element found in this file")

    mo = _find_managed_object(cmdata, dist_name)
    if mo is None:
        raise ParamNotFoundError(f"No managedObject with distName={dist_name!r}")

    target = None
    for child in mo:
        if _local(child.tag) == "p" and child.get("name") == param_name:
            target = child
            break
    if target is None:
        raise ParamNotFoundError(f"No parameter {param_name!r} on {dist_name!r}")

    mo.remove(target)
    return _serialize(root)


def delete_managed_object(raw_bytes: bytes, dist_name: str) -> tuple[bytes, list[str]]:
    """Removes a managedObject AND every descendant managedObject under it
    (RAML files are flat -- <cmData> is a plain sibling list of
    managedObjects, so a child like "MRBTS-1/LNBTS-1/LNCEL-1" is its own
    separate top-level element that has to be found and dropped explicitly,
    not something that comes along for free by removing its parent).
    Returns (new_bytes, list_of_deleted_distNames)."""
    cleaned = _strip_leading_junk(raw_bytes)
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as e:
        raise XmlParseError(str(e)) from e

    cmdata = None
    for el in root.iter():
        if _local(el.tag) == "cmData":
            cmdata = el
            break
    if cmdata is None:
        raise ParamNotFoundError("No <cmData> element found in this file")

    prefix = dist_name + "/"
    to_remove = [
        child for child in cmdata
        if _local(child.tag) == "managedObject"
        and (child.get("distName") == dist_name or (child.get("distName") or "").startswith(prefix))
    ]
    if not to_remove:
        raise ParamNotFoundError(f"No managedObject with distName={dist_name!r}")

    deleted_names = [c.get("distName") for c in to_remove]
    for c in to_remove:
        cmdata.remove(c)

    return _serialize(root), deleted_names


def rename_managed_object(raw_bytes: bytes, dist_name: str, new_instance_id: str) -> tuple[bytes, str]:
    """Changes a managedObject's instance ID -- the trailing "-N" of its
    distName, e.g. "MRBTS-1/LNBTS-1/LNCEL-1" -> "...LNCEL-0" -- keeping the
    same class and parent. Every descendant's distName gets the same prefix
    swap applied (RAML distNames are literal ancestry paths, so a child's
    distName has to be rewritten too, not just the renamed object's own).
    Returns (new_bytes, new_dist_name). Raises ObjectExistsError if the
    resulting distName collides with an object that already exists."""
    cleaned = _strip_leading_junk(raw_bytes)
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as e:
        raise XmlParseError(str(e)) from e

    cmdata = None
    for el in root.iter():
        if _local(el.tag) == "cmData":
            cmdata = el
            break
    if cmdata is None:
        raise ParamNotFoundError("No <cmData> element found in this file")

    mo = _find_managed_object(cmdata, dist_name)
    if mo is None:
        raise ParamNotFoundError(f"No managedObject with distName={dist_name!r}")

    parent_prefix, sep, last = dist_name.rpartition("/")
    short_class = last.rsplit("-", 1)[0] if "-" in last else last
    new_last = f"{short_class}-{new_instance_id}"
    new_dist_name = f"{parent_prefix}{sep}{new_last}"

    if new_dist_name == dist_name:
        return _serialize(root), dist_name

    if _find_managed_object(cmdata, new_dist_name) is not None:
        raise ObjectExistsError(f"An object with distName={new_dist_name!r} already exists")

    prefix = dist_name + "/"
    for child in cmdata:
        if _local(child.tag) != "managedObject":
            continue
        dn = child.get("distName") or ""
        if dn == dist_name:
            child.set("distName", new_dist_name)
        elif dn.startswith(prefix):
            child.set("distName", new_dist_name + "/" + dn[len(prefix):])

    return _serialize(root), new_dist_name


def find_existing_class_version(raw_bytes: bytes, short_class: str) -> tuple[Optional[str], Optional[str]]:
    """Scans the file for any existing managedObject of `short_class` and
    returns (full_class, version) to reuse for consistency, or (None, None)
    if this file has no instance of that class yet."""
    try:
        cleaned = _strip_leading_junk(raw_bytes)
        root = ET.fromstring(cleaned)
    except ET.ParseError:
        return None, None
    for el in root.iter():
        if _local(el.tag) != "managedObject":
            continue
        full_class = el.get("class")
        if _short_class(full_class) == short_class:
            return full_class, el.get("version")
    return None, None


def find_any_version(raw_bytes: bytes) -> Optional[str]:
    """Last-resort fallback for a new object's version attribute: borrow
    whatever version any other object in this file already uses, since a
    single site/plan is normally exported from one consistent software load."""
    try:
        cleaned = _strip_leading_junk(raw_bytes)
        root = ET.fromstring(cleaned)
    except ET.ParseError:
        return None
    for el in root.iter():
        if _local(el.tag) == "managedObject" and el.get("version"):
            return el.get("version")
    return None


def next_available_instance_id(raw_bytes: bytes, parent_dist_name: Optional[str], short_class: str) -> str:
    """Looks at existing siblings of `short_class` under `parent_dist_name`
    (or at the root, if None) and returns the next free integer instance id
    as a string, defaulting to "1" if there are none yet."""
    try:
        cleaned = _strip_leading_junk(raw_bytes)
        root = ET.fromstring(cleaned)
    except ET.ParseError:
        return "1"
    prefix = f"{parent_dist_name}/{short_class}-" if parent_dist_name else f"{short_class}-"
    max_id = 0
    for el in root.iter():
        if _local(el.tag) != "managedObject":
            continue
        dn = el.get("distName") or ""
        if dn.startswith(prefix) and "/" not in dn[len(prefix):]:
            suffix = dn[len(prefix):]
            if suffix.isdigit():
                max_id = max(max_id, int(suffix))
    return str(max_id + 1)


def new_file_bytes() -> bytes:
    """A minimal, valid, empty RAML plan -- a starting point for building a
    new commissioning file from scratch via add_managed_object calls."""
    plan_id = str(random.randint(1_000_000_000, 9_999_999_999))
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<raml xmlns="raml21.xsd" version="2.1">\n'
        f'  <cmData type="plan" scope="all" id="{plan_id}">\n'
        "    <header>\n"
        f'      <log action="create" dateTime="{ts}"/>\n'
        "    </header>\n"
        "  </cmData>\n"
        "</raml>\n"
    )
    return xml.encode("utf-8")

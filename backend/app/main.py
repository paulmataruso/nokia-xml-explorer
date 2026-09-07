from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import structural
from .heuristics import generate as heuristic_generate
from .parser import (
    ObjectExistsError,
    ParamNotFoundError,
    XmlParseError,
    _short_class,
    add_managed_object,
    delete_managed_object,
    delete_param,
    find_any_version,
    find_existing_class_version,
    new_file_bytes,
    next_available_instance_id,
    parse_file,
    parse_file_raw,
    rename_managed_object,
    set_param_value,
    update_param_value,
)

def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val.strip().lower() not in ("false", "0", "no", "off")


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


SCP_DIR = Path(os.environ.get("SCP_DIR", "/data/scp")).resolve()
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/data/uploads")).resolve()
SNAPSHOT_DIR = Path(os.environ.get("SNAPSHOT_DIR", "/data/snapshots")).resolve()
# Baked into the Docker image (not a bind mount, unlike SCP_DIR) -- see
# Dockerfile's `COPY example ./example` -- so a handful of sample
# commissioning files are always available to browse, even before you point
# the tool at your own. INCLUDE_EXAMPLES (.env) turns this off.
EXAMPLE_DIR = Path(os.environ.get("EXAMPLE_DIR", "/app/example")).resolve()
INCLUDE_EXAMPLES = _env_bool("INCLUDE_EXAMPLES", True)
DATA_DIR = Path(__file__).parent / "data"
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", "/app/frontend_dist"))
MAX_UPLOAD_BYTES = _env_int("MAX_UPLOAD_MB", 25) * 1024 * 1024
MAX_SNAPSHOTS_PER_FILE = _env_int("MAX_SNAPSHOTS_PER_FILE", 50)
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Nokia RAN Commissioning XML Explorer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Knowledge base: loaded once at startup, served as-is to the frontend, and
# used server-side as the heuristic-fallback source of truth.
# ---------------------------------------------------------------------------
_CLASSES_KB: dict = {}
_PARAMS_KB: dict = {}
_CLASS_CATALOG: dict = {}


def _load_kb() -> None:
    global _CLASSES_KB, _PARAMS_KB, _CLASS_CATALOG
    classes_path = DATA_DIR / "classes.json"
    params_path = DATA_DIR / "parameters.json"
    catalog_path = DATA_DIR / "class_catalog.json"
    _CLASSES_KB = json.loads(classes_path.read_text()) if classes_path.exists() else {}
    _PARAMS_KB = json.loads(params_path.read_text()) if params_path.exists() else {}
    _CLASS_CATALOG = json.loads(catalog_path.read_text()) if catalog_path.exists() else {}


_load_kb()

# in-memory parse cache: filename -> (mtime, tree)
_TREE_CACHE: dict[str, tuple[float, dict]] = {}
_RAW_CACHE: dict[str, tuple[float, dict]] = {}


def _is_safe_filename(filename: str) -> bool:
    if not filename or filename in ("..", "."):
        return False
    if "/" in filename or "\\" in filename:
        return False
    return True


def _resolve_path(filename: str) -> tuple[Path, str]:
    """Looks up `filename` in the writable uploads dir first, then the
    read-only scp dir, then (if enabled) the bundled example dir. Returns
    (path, source) or raises 404/400."""
    if not _is_safe_filename(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    upload_path = (UPLOAD_DIR / filename).resolve()
    if UPLOAD_DIR in upload_path.parents and upload_path.is_file():
        return upload_path, "upload"

    scp_path = (SCP_DIR / filename).resolve()
    if SCP_DIR in scp_path.parents and scp_path.is_file():
        return scp_path, "scp"

    if INCLUDE_EXAMPLES:
        example_path = (EXAMPLE_DIR / filename).resolve()
        if EXAMPLE_DIR in example_path.parents and example_path.is_file():
            return example_path, "example"

    raise HTTPException(status_code=404, detail="File not found")


def _name_taken(name: str) -> bool:
    # Filenames must be unique across all read sources: _resolve_path looks
    # in uploads first, so an upload sharing another source's name would
    # silently shadow the original in every lookup by that name.
    if (UPLOAD_DIR / name).exists() or (SCP_DIR / name).exists():
        return True
    return INCLUDE_EXAMPLES and (EXAMPLE_DIR / name).exists()


def _unique_upload_name(filename: str) -> str:
    """Never silently overwrite -- or shadow an scp/ file of the same name --
    append ' (1)', ' (2)', etc. before the extension until the name is free
    in both directories."""
    stem, ext = os.path.splitext(filename)
    candidate = filename
    i = 1
    while _name_taken(candidate):
        candidate = f"{stem} ({i}){ext}"
        i += 1
    return candidate


def _save_snapshot(filename: str, content: bytes) -> None:
    """Called right before overwriting an uploaded file (from an edit or a
    restore) so there's always a checkpoint to go back to."""
    d = SNAPSHOT_DIR / filename
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%f")[:-3] + "Z"
    (d / f"{ts}.xml").write_bytes(content)
    snaps = sorted(d.glob("*.xml"))
    for old in snaps[:-MAX_SNAPSHOTS_PER_FILE]:
        old.unlink(missing_ok=True)


def _invalidate_caches(filename: str) -> None:
    _TREE_CACHE.pop(filename, None)
    _RAW_CACHE.pop(filename, None)


def _param_meta(short_class: str | None, name: str | None) -> dict | None:
    if not short_class or not name:
        return None
    return _CLASS_CATALOG.get(short_class, {}).get("params", {}).get(name)


def _is_required_missing(meta: dict | None, has_value: bool) -> bool:
    """True for ANY Mandatory parameter (per the official docs) that
    currently has no value -- not just ones with no documented default.
    Deliberately doesn't key off the catalog's static `trulyRequired` flag:
    a Mandatory param whose documented default failed to resolve to a safe
    real-XML value (a small edge case -- see resolve_default_for_xml in
    build_class_catalog.py) also ends up written blank by add_object, and
    still needs to be surfaced and filled in even though the docs say it
    "has a default." What matters here is only whether it actually has a
    value right now."""
    return bool(meta and meta.get("requiredOnCreation") == "Mandatory" and not has_value)


def _annotate_required_logical(node: dict) -> None:
    """Flags every param node in the logical tree with mandatory (Required on
    Creation == Mandatory, regardless of whether it has a default -- drives
    hiding the delete control, since a Mandatory param must always have a
    slot in the file), trulyRequired (Mandatory, no official default --
    informational), and requiredMissing (Mandatory AND currently
    blank/absent -- drives red highlighting) so the frontend doesn't need to
    re-derive the class catalog itself."""
    if node.get("kind") == "param":
        meta = _param_meta(node.get("class"), node.get("label"))
        node["mandatory"] = bool(meta and meta.get("requiredOnCreation") == "Mandatory")
        node["trulyRequired"] = bool(meta and meta.get("trulyRequired"))
        node["requiredMissing"] = _is_required_missing(meta, bool(node.get("value")))
    for child in node.get("children", None) or []:
        _annotate_required_logical(child)


def _annotate_required_raw(node: dict, current_class: str | None = None) -> None:
    """Same as _annotate_required_logical but for the raw DOM-literal tree,
    which has no per-node `class` field -- so the current managedObject's
    short class is threaded down through recursion instead."""
    tag = node.get("tag")
    if tag == "managedObject":
        current_class = _short_class(node.get("attrs", {}).get("class"))
    elif tag == "p":
        meta = _param_meta(current_class, node.get("attrs", {}).get("name"))
        node["mandatory"] = bool(meta and meta.get("requiredOnCreation") == "Mandatory")
        node["trulyRequired"] = bool(meta and meta.get("trulyRequired"))
        node["requiredMissing"] = _is_required_missing(meta, bool(node.get("text")))
    for child in node.get("children", None) or []:
        _annotate_required_raw(child, current_class)


class UpdateParamRequest(BaseModel):
    nodeId: str
    value: str


class NewFileRequest(BaseModel):
    filename: str = "New_Commissioning_File.xml"


class AddObjectRequest(BaseModel):
    parentDistName: str | None = None
    className: str
    instanceId: str | None = None
    params: dict[str, str] = {}


class DeleteObjectRequest(BaseModel):
    distName: str


class DeleteParamRequest(BaseModel):
    distName: str
    paramName: str


class RenameObjectRequest(BaseModel):
    distName: str
    newInstanceId: str


class SetObjectParamRequest(BaseModel):
    distName: str
    paramName: str
    value: str


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "scpDir": str(SCP_DIR),
        "scpDirExists": SCP_DIR.is_dir(),
        "uploadDir": str(UPLOAD_DIR),
        "includeExamples": INCLUDE_EXAMPLES,
        "exampleDirExists": EXAMPLE_DIR.is_dir(),
    }


@app.get("/api/files")
def list_files():
    out = []
    sources = [("upload", UPLOAD_DIR), ("scp", SCP_DIR)]
    if INCLUDE_EXAMPLES:
        sources.append(("example", EXAMPLE_DIR))
    for source, directory in sources:
        if not directory.is_dir():
            continue
        for p in sorted(directory.iterdir()):
            if not p.is_file() or p.name.startswith("."):
                continue
            stat = p.stat()
            out.append({
                "name": p.name,
                "sizeBytes": stat.st_size,
                "mtime": stat.st_mtime,
                "supported": p.suffix.lower() == ".xml",
                "source": source,
            })
    return out


@app.post("/api/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    results = []
    for f in files:
        original_name = os.path.basename(f.filename or "upload.xml")
        if not original_name.lower().endswith(".xml"):
            results.append({"name": original_name, "ok": False, "error": "Only .xml files are accepted"})
            continue

        data = await f.read()
        if len(data) > MAX_UPLOAD_BYTES:
            results.append({
                "name": original_name, "ok": False,
                "error": f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit",
            })
            continue

        try:
            parse_file(data, original_name)
        except XmlParseError as e:
            results.append({"name": original_name, "ok": False, "error": f"Not valid RAML XML: {e}"})
            continue

        saved_name = _unique_upload_name(original_name)
        (UPLOAD_DIR / saved_name).write_bytes(data)
        results.append({"name": saved_name, "ok": True})

    return {"results": results}


@app.delete("/api/files/{filename}")
def delete_uploaded_file(filename: str):
    if not _is_safe_filename(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = (UPLOAD_DIR / filename).resolve()
    if UPLOAD_DIR not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Only uploaded files can be deleted")
    path.unlink()
    shutil.rmtree(SNAPSHOT_DIR / filename, ignore_errors=True)
    _invalidate_caches(filename)
    return {"deleted": filename}


@app.post("/api/files/{filename}/duplicate-to-uploads")
def duplicate_to_uploads(filename: str):
    """Makes an editable copy of any file (scp/ original or another upload)
    in the writable uploads dir, so read-only reference files can still be
    edited without ever touching the original. Always gets a visibly
    distinct name -- reusing the source name would either collide with it
    (same dir) or silently shadow it in every lookup by name (scp/ vs
    uploads/ are looked up as one combined namespace)."""
    path, _source = _resolve_path(filename)
    stem, ext = os.path.splitext(filename)
    new_name = _unique_upload_name(f"{stem} (copy){ext}")
    (UPLOAD_DIR / new_name).write_bytes(path.read_bytes())
    return {"name": new_name}


@app.post("/api/files/new")
def create_new_file(payload: NewFileRequest):
    name = os.path.basename((payload.filename or "").strip() or "New_Commissioning_File.xml")
    if not name.lower().endswith(".xml"):
        name += ".xml"
    if not _is_safe_filename(name):
        raise HTTPException(status_code=400, detail="Invalid filename")
    saved_name = _unique_upload_name(name)
    (UPLOAD_DIR / saved_name).write_bytes(new_file_bytes())
    return {"name": saved_name}


@app.get("/api/catalog/classes")
def catalog_classes():
    """Every MO class either official Nokia dictionary defines (not just
    ones we've actually seen in scp/), with what we know about where it can
    legally live -- powers the 'Add Object' class picker. observedInCorpus
    tells the UI whether this class (and its params) are grounded in your
    real files or only in Nokia's documentation."""
    out = []
    for short, entry in _CLASS_CATALOG.items():
        cls_kb = _CLASSES_KB.get(short, {})
        out.append({
            "shortName": short,
            "directParent": entry.get("directParent"),
            "observedParents": entry.get("observedParents", []),
            "observedInCorpus": entry.get("observedInCorpus", True),
            "description": cls_kb.get("description"),
            "officialFullName": cls_kb.get("officialFullName") or entry.get("officialFullName"),
            "category": cls_kb.get("category"),
            "paramCount": len(entry.get("params", {})),
        })
    return out


@app.get("/api/catalog/classes/{class_name}")
def catalog_class_detail(class_name: str):
    entry = _CLASS_CATALOG.get(class_name)
    if not entry:
        raise HTTPException(status_code=404, detail="Unknown class (not in either official dictionary)")
    return entry


def _resolve_full_class(current_bytes: bytes, short_class: str) -> tuple[str, bool, str | None]:
    """(full_class, classVerified, version). Prefers an existing instance of
    this class already in the file; falls back to the classes.json research
    KB; and as a last resort (a class never observed in scp/ at all -- the
    official dictionaries record hierarchy/parameters but not the XML
    namespace prefix) infers it from a sibling class under the same parent
    that WAS observed, since Nokia namespaces are consistently per-subsystem
    (e.g. every APEQM child in this corpus is "com.nokia.srbts.eqm:*"). That
    last case is flagged classVerified=False -- it's a reasonable guess, not
    a confirmed fact."""
    full_class, version = find_existing_class_version(current_bytes, short_class)
    if full_class:
        return full_class, True, version
    full_names = _CLASSES_KB.get(short_class, {}).get("fullNames") or []
    if full_names:
        return full_names[0], True, version
    full_class = short_class
    parent = _CLASS_CATALOG.get(short_class, {}).get("directParent")
    if parent:
        for sib, sib_entry in _CLASS_CATALOG.items():
            if sib == short_class or sib_entry.get("directParent") != parent:
                continue
            sib_full_names = _CLASSES_KB.get(sib, {}).get("fullNames") or []
            if sib_full_names:
                ns = sib_full_names[0].rsplit(":", 1)[0]
                full_class = f"{ns}:{short_class}"
                break
    return full_class, False, version


def _create_one_object(
    current_bytes: bytes,
    parent_dist_name: str | None,
    short_class: str,
    requested_params: dict[str, str],
    instance_id: str | None = None,
) -> tuple[bytes, dict]:
    """Creates exactly ONE managed object -- no cascading -- filling in every
    Mandatory parameter not already in requested_params (default-resolved
    value if one exists, blank placeholder otherwise -- see the note on
    _is_required_missing). Returns (new_bytes, summary_dict). Raises
    XmlParseError / ParamNotFoundError / ObjectExistsError on failure."""
    full_class, class_verified, version = _resolve_full_class(current_bytes, short_class)
    if not version:
        version = find_any_version(current_bytes)
    resolved_instance_id = instance_id or next_available_instance_id(
        current_bytes, parent_dist_name, short_class
    )

    final_params = dict(requested_params)
    auto_filled_defaults: list[str] = []
    auto_added_blank: list[str] = []
    for name, meta in _CLASS_CATALOG.get(short_class, {}).get("params", {}).items():
        if name in final_params or meta.get("requiredOnCreation") != "Mandatory":
            continue
        resolved = meta.get("resolvedDefault")
        if resolved is not None:
            final_params[name] = resolved
            auto_filled_defaults.append(name)
        else:
            final_params[name] = ""
            auto_added_blank.append(name)

    new_bytes, new_dist_name = add_managed_object(
        current_bytes, parent_dist_name, short_class, full_class, version,
        resolved_instance_id, final_params,
    )
    summary = {
        "distName": new_dist_name,
        "class": full_class,
        "shortClass": short_class,
        "classVerified": class_verified,
        "autoFilledDefaults": sorted(auto_filled_defaults),
        "autoAddedBlank": sorted(auto_added_blank),
    }
    return new_bytes, summary


def _cascade_required_children(
    current_bytes: bytes, parent_dist_name: str, parent_short_class: str, ancestors: frozenset[str]
) -> tuple[bytes, list[dict]]:
    """After creating an object, also creates one instance of every child
    class that's present under EVERY observed instance of its class in your
    corpus ("requiredChildClasses" -- see build_class_catalog.py's walk()).
    This is a heuristic, not an official Nokia rule (no source in ref/
    records MO-class cardinality at all), so each cascaded object's summary
    carries classVerified same as any other, and this list is meant to be
    shown to you, not hidden. Recurses into each created child's own
    required children in turn. `ancestors` guards against a class
    re-appearing in its own cascade chain (structurally shouldn't happen --
    distName nesting is a tree -- but cheap to guard anyway)."""
    results: list[dict] = []
    if parent_short_class in ancestors:
        return current_bytes, results
    ancestors = ancestors | {parent_short_class}
    child_classes = _CLASS_CATALOG.get(parent_short_class, {}).get("requiredChildClasses", [])
    for child_class in child_classes:
        try:
            current_bytes, summary = _create_one_object(current_bytes, parent_dist_name, child_class, {})
        except (XmlParseError, ParamNotFoundError, ObjectExistsError) as e:
            results.append({"shortClass": child_class, "parentDistName": parent_dist_name, "error": str(e)})
            continue
        results.append(summary)
        current_bytes, nested = _cascade_required_children(
            current_bytes, summary["distName"], child_class, ancestors
        )
        results.extend(nested)
    return current_bytes, results


@app.post("/api/files/{filename}/objects")
def add_object(filename: str, payload: AddObjectRequest):
    path, source = _resolve_path(filename)
    if source != "upload":
        raise HTTPException(
            status_code=403,
            detail="This is a read-only reference file. Create an editable copy first.",
        )
    if payload.className not in _CLASS_CATALOG and payload.className not in _CLASSES_KB:
        raise HTTPException(status_code=400, detail=f"Unknown class {payload.className!r}")

    current = path.read_bytes()

    try:
        new_bytes, summary = _create_one_object(
            current, payload.parentDistName, payload.className, payload.params, payload.instanceId
        )
    except (XmlParseError, ParamNotFoundError, ObjectExistsError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    new_bytes, cascaded = _cascade_required_children(
        new_bytes, summary["distName"], payload.className, frozenset()
    )

    try:
        parse_file(new_bytes, filename)
    except XmlParseError as e:
        raise HTTPException(status_code=500, detail=f"This would have produced invalid XML: {e}")

    _save_snapshot(filename, current)
    path.write_bytes(new_bytes)
    _invalidate_caches(filename)
    return {
        "distName": summary["distName"],
        "class": summary["class"],
        "classVerified": summary["classVerified"],
        "autoFilledDefaults": summary["autoFilledDefaults"],
        "autoAddedBlank": summary["autoAddedBlank"],
        "cascadedObjects": cascaded,
    }


@app.put("/api/files/{filename}/objects/param")
def set_object_param(filename: str, payload: SetObjectParamRequest):
    """Adds a parameter to an EXISTING managed object, or updates it if
    already present -- the generator's search-to-add box only sets what you
    ask for up front, so this is how you come back later and set more."""
    path, source = _resolve_path(filename)
    if source != "upload":
        raise HTTPException(
            status_code=403,
            detail="This is a read-only reference file. Create an editable copy first.",
        )

    current = path.read_bytes()
    try:
        new_bytes = set_param_value(current, payload.distName, payload.paramName, payload.value)
    except (XmlParseError, ParamNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        parse_file(new_bytes, filename)
    except XmlParseError as e:
        raise HTTPException(status_code=500, detail=f"This would have produced invalid XML: {e}")

    _save_snapshot(filename, current)
    path.write_bytes(new_bytes)
    _invalidate_caches(filename)
    return {"ok": True}


@app.delete("/api/files/{filename}/objects/param")
def delete_object_param(filename: str, payload: DeleteParamRequest):
    """Removes a single scalar parameter from an existing managed object --
    but never a Mandatory one. This tool goes out of its way to make sure
    every Mandatory parameter always has a slot in the file (auto-filled
    default, or a blank placeholder that's red-flagged until you fill it
    in -- see /missing-required); letting it be deleted outright would undo
    that guarantee, so the only way to change a Mandatory value is to edit
    it, never remove it."""
    path, source = _resolve_path(filename)
    if source != "upload":
        raise HTTPException(
            status_code=403,
            detail="This is a read-only reference file. Create an editable copy first.",
        )

    current = path.read_bytes()
    try:
        tree = parse_file(current, filename)
    except XmlParseError as e:
        raise HTTPException(status_code=422, detail=f"Could not parse XML: {e}")

    mo = None
    def find_mo(node):
        if node.get("kind") == "mo" and node.get("id") == payload.distName:
            return node
        for child in node.get("children", []):
            found = find_mo(child)
            if found:
                return found
        return None
    for root_node in tree.get("children", []):
        mo = find_mo(root_node)
        if mo:
            break
    if mo is None:
        raise HTTPException(status_code=404, detail=f"No managedObject with distName={payload.distName!r}")

    meta = _param_meta(mo.get("class"), payload.paramName)
    if meta and meta.get("requiredOnCreation") == "Mandatory":
        raise HTTPException(
            status_code=400,
            detail=f"{payload.paramName!r} is Mandatory for {mo.get('class')} and can't be deleted -- edit its value instead.",
        )

    try:
        new_bytes = delete_param(current, payload.distName, payload.paramName)
    except (XmlParseError, ParamNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        parse_file(new_bytes, filename)
    except XmlParseError as e:
        raise HTTPException(status_code=500, detail=f"This would have produced invalid XML: {e}")

    _save_snapshot(filename, current)
    path.write_bytes(new_bytes)
    _invalidate_caches(filename)
    return {"ok": True}


@app.delete("/api/files/{filename}/objects")
def delete_object(filename: str, payload: DeleteObjectRequest):
    """Removes a managed object and every descendant object beneath it
    (RAML files are flat, so descendants are separate sibling elements that
    have to be found and removed explicitly -- see delete_managed_object).
    No Mandatory-style protection at the object level: unlike parameters,
    Nokia's docs don't define any class as officially required to exist --
    the corpus-inferred "usually present" child classes used by the +Add
    Object cascade (see add_object) are a heuristic about what to create by
    default, not a hard rule about what you're allowed to remove."""
    path, source = _resolve_path(filename)
    if source != "upload":
        raise HTTPException(
            status_code=403,
            detail="This is a read-only reference file. Create an editable copy first.",
        )

    current = path.read_bytes()
    try:
        new_bytes, deleted = delete_managed_object(current, payload.distName)
    except (XmlParseError, ParamNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        parse_file(new_bytes, filename)
    except XmlParseError as e:
        raise HTTPException(status_code=500, detail=f"This would have produced invalid XML: {e}")

    _save_snapshot(filename, current)
    path.write_bytes(new_bytes)
    _invalidate_caches(filename)
    return {"ok": True, "deleted": deleted}


@app.put("/api/files/{filename}/objects/rename")
def rename_object(filename: str, payload: RenameObjectRequest):
    """Changes a managedObject's instance ID (e.g. LNCEL-1 -> LNCEL-0),
    cascading the same distName-prefix swap into every descendant -- see
    rename_managed_object. Same class, same parent; only the trailing
    instance number changes."""
    path, source = _resolve_path(filename)
    if source != "upload":
        raise HTTPException(
            status_code=403,
            detail="This is a read-only reference file. Create an editable copy first.",
        )

    current = path.read_bytes()
    try:
        new_bytes, new_dist_name = rename_managed_object(current, payload.distName, payload.newInstanceId)
    except (XmlParseError, ParamNotFoundError, ObjectExistsError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        parse_file(new_bytes, filename)
    except XmlParseError as e:
        raise HTTPException(status_code=500, detail=f"This would have produced invalid XML: {e}")

    _save_snapshot(filename, current)
    path.write_bytes(new_bytes)
    _invalidate_caches(filename)
    return {"distName": new_dist_name}


@app.put("/api/files/{filename}/param")
def update_param(filename: str, payload: UpdateParamRequest):
    path, source = _resolve_path(filename)
    if source != "upload":
        raise HTTPException(
            status_code=403,
            detail="This is a read-only reference file. Create an editable copy first.",
        )

    current = path.read_bytes()
    try:
        new_bytes = update_param_value(current, payload.nodeId, payload.value)
    except (XmlParseError, ParamNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Belt-and-braces: make sure whatever we're about to write is actually
    # still valid before it touches disk.
    try:
        parse_file(new_bytes, filename)
    except XmlParseError as e:
        raise HTTPException(status_code=500, detail=f"Edit would have produced invalid XML: {e}")

    _save_snapshot(filename, current)
    path.write_bytes(new_bytes)
    _invalidate_caches(filename)
    return {"ok": True}


@app.get("/api/files/{filename}/snapshots")
def list_snapshots(filename: str):
    d = SNAPSHOT_DIR / filename
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.xml"), reverse=True):
        out.append({"id": p.stem, "sizeBytes": p.stat().st_size})
    return out


@app.post("/api/files/{filename}/snapshots/{snapshot_id}/restore")
def restore_snapshot(filename: str, snapshot_id: str):
    path, source = _resolve_path(filename)
    if source != "upload":
        raise HTTPException(status_code=403, detail="Only uploaded files have snapshot history")
    if not _is_safe_filename(snapshot_id):
        raise HTTPException(status_code=400, detail="Invalid snapshot id")
    snap_path = SNAPSHOT_DIR / filename / f"{snapshot_id}.xml"
    if not snap_path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot not found")

    current = path.read_bytes()
    _save_snapshot(filename, current)  # so restoring is itself undoable
    path.write_bytes(snap_path.read_bytes())
    _invalidate_caches(filename)
    return {"restored": snapshot_id}


@app.get("/api/files/{filename}/tree")
def get_tree(filename: str):
    path, _source = _resolve_path(filename)
    stat = path.stat()
    cached = _TREE_CACHE.get(filename)
    if cached and cached[0] == stat.st_mtime:
        return cached[1]

    raw = path.read_bytes()
    try:
        tree = parse_file(raw, filename)
    except XmlParseError as e:
        raise HTTPException(status_code=422, detail=f"Could not parse XML: {e}")

    for root_node in tree.get("children", []):
        _annotate_required_logical(root_node)

    _TREE_CACHE[filename] = (stat.st_mtime, tree)
    return tree


@app.get("/api/files/{filename}/raw")
def get_raw_tree(filename: str):
    """Literal DOM-like tree of the file exactly as written (tag names,
    attribute order, flat managedObject siblings) -- for the side-by-side
    'real XML' view. Node ids share the same scheme as /tree so the
    frontend can cross-highlight with a plain id lookup."""
    path, _source = _resolve_path(filename)
    stat = path.stat()
    cached = _RAW_CACHE.get(filename)
    if cached and cached[0] == stat.st_mtime:
        return cached[1]

    raw = path.read_bytes()
    try:
        raw_tree = parse_file_raw(raw, filename)
    except XmlParseError as e:
        raise HTTPException(status_code=422, detail=f"Could not parse XML: {e}")

    _annotate_required_raw(raw_tree["root"])

    _RAW_CACHE[filename] = (stat.st_mtime, raw_tree)
    return raw_tree


@app.get("/api/files/{filename}/missing-required")
def missing_required(filename: str):
    """Every Mandatory-with-no-default ('trulyRequired') parameter across the
    whole file that's currently blank or absent -- whether because '+ Add
    Object' added it as an empty placeholder, or it was simply never set.
    Powers the 'Required Fields' table so these can all be found and filled
    in from one place instead of hunting through the tree for red flags."""
    path, _source = _resolve_path(filename)
    raw = path.read_bytes()
    try:
        tree = parse_file(raw, filename)
    except XmlParseError as e:
        raise HTTPException(status_code=422, detail=f"Could not parse XML: {e}")

    out: list[dict] = []

    def walk(node: dict) -> None:
        if node.get("kind") == "mo":
            short_class = node.get("class")
            catalog_params = _CLASS_CATALOG.get(short_class, {}).get("params", {})
            present = {c["label"]: c for c in node.get("children", []) if c.get("kind") == "param"}
            for name, meta in catalog_params.items():
                existing = present.get(name)
                if not _is_required_missing(meta, bool(existing and existing.get("value"))):
                    continue
                out.append({
                    "distName": node["id"],
                    "class": short_class,
                    "paramName": name,
                    "dataType": meta.get("dataType"),
                    "exampleValues": meta.get("exampleValues") or [],
                    "officialRange": meta.get("officialRange"),
                    "description": meta.get("description"),
                    "unit": meta.get("unit"),
                    "observed": meta.get("observed"),
                })
        for child in node.get("children", None) or []:
            walk(child)

    for root_node in tree.get("children", []):
        walk(root_node)

    return out


@app.get("/api/knowledge/classes")
def knowledge_classes():
    return _CLASSES_KB


@app.get("/api/knowledge/parameters")
def knowledge_parameters():
    return _PARAMS_KB


@app.get("/api/knowledge/structural")
def knowledge_structural():
    return {"elements": structural.ELEMENTS, "attributes": structural.ATTRIBUTES}


@app.get("/api/explain/param")
def explain_param(name: str, moClass: str | None = None, value: str | None = None):
    """Server-side fallback lookup, used defensively in case the frontend
    ever asks about a parameter name that isn't in the shipped KB snapshot
    (e.g. KB was updated but frontend cache wasn't). The frontend normally
    does this lookup locally against the already-fetched KB for speed."""
    entry = _PARAMS_KB.get(name)
    if entry:
        return {"name": name, "source": "curated", **entry}
    generated = heuristic_generate(name, [moClass] if moClass else [], [value] if value else [])
    return {"name": name, "source": "heuristic", **generated}


@app.get("/api/explain/class")
def explain_class(name: str):
    entry = _CLASSES_KB.get(name)
    if entry:
        return {"name": name, "source": "curated", **entry}
    return {
        "name": name,
        "source": "heuristic",
        "description": (
            f"No curated description is available for managed object class \"{name}\". "
            "It did not appear in the researched sample set. Based on Nokia RAN naming "
            "conventions, it is a managed object class defined by Nokia's SBTS/AirScale or "
            "Flexi Zone parameter dictionary; consult Nokia's official MOM (Managed Object "
            "Model) reference for an authoritative definition."
        ),
        "category": "Other",
        "confidence": "heuristic",
    }


# ---------------------------------------------------------------------------
# Serve the built frontend (single-container deployment).
# ---------------------------------------------------------------------------
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")

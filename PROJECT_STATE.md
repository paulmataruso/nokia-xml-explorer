# PROJECT_STATE.md — Nokia AirScale/Flexi Zone XML Explorer

**Purpose of this document:** a complete handoff/design document. Assume the
reader (human engineer or another AI instance) has never seen this project,
the codebase, or the conversation that built it. Everything needed to
understand, run, modify, or fully recreate the project from scratch should
be here. Where a design decision isn't obvious from the code, the reasoning
is written down — several of these decisions were arrived at by trial and
error, and re-deriving them the slow way would waste time.

Last updated: 2026-09-07. Repo: `https://github.com/paulmataruso/nokia-xml-explorer`
(public). Current tag: `v0.02`. Working tree at time of writing: 3 commits
on `main` (`3699002` v0.01 → `ef4808a` cleanup → `7fed873` v0.02).

---

## Table of contents

1. [What this project is](#1-what-this-project-is)
2. [Tech stack](#2-tech-stack)
3. [Repository layout](#3-repository-layout)
4. [Core data model](#4-core-data-model)
5. [Backend: full API reference](#5-backend-full-api-reference)
6. [Backend: module walkthrough](#6-backend-module-walkthrough)
7. [Frontend: architecture](#7-frontend-architecture)
8. [The knowledge base system](#8-the-knowledge-base-system)
9. [The XML generator system](#9-the-xml-generator-system)
10. [Docker & deployment](#10-docker--deployment)
11. [Data privacy / what is and isn't in the repo](#11-data-privacy--what-is-and-isnt-in-the-repo)
12. [Known limitations / explicitly out of scope](#12-known-limitations--explicitly-out-of-scope)
13. [Chronological build history](#13-chronological-build-history)
14. [How to recreate this from scratch](#14-how-to-recreate-this-from-scratch)

---

## 1. What this project is

A self-hosted, single-container web tool for **browsing, editing, and
generating Nokia RAN commissioning/configuration XML files** — the RAML
(`raml21.xsd`) "SCF"/CM-data format used by Nokia BTS Site Manager and
NetAct to configure AirScale and Flexi Zone LTE/NR base stations.

### The problem it solves

Nokia commissioning files are enormous flat XML documents — a single
`<cmData>` element containing hundreds or thousands of `<managedObject>`
elements as direct siblings, each with `class`, `distName`, `operation`,
and `version` attributes, and dozens to hundreds of `<p name="...">value</p>`
children. There is no visual hierarchy in the raw file; you infer the
real equipment/cell/feature tree from parsing each object's `distName`
path (e.g. `MRBTS-1/EQM-1/APEQM-1/RMOD-1`). A field engineer or RAN
engineer opening one of these in a text editor has no way to know what a
given parameter does, whether a value is valid, or whether a hand-edited
or hand-built file is actually complete (i.e. every Mandatory field has a
value) without cross-referencing Nokia's parameter dictionaries — which
are thousand-page, customer/partner-confidential Excel/HTML documents.

### What the tool does about it

- Reconstructs the real parent/child object tree from the flat XML and
  displays it as an expandable tree, side by side with the literal raw
  XML (also as an expandable, DOM-accurate tree), with bidirectional
  click-to-sync highlighting between the two.
- Ships a knowledge base (built from Nokia's own official parameter
  dictionaries plus AI-assisted research plus statistical analysis of a
  79-file corpus of real commissioning files) that explains every
  standard managed-object class and parameter in plain English on
  double-click.
- Lets you edit values in place, with automatic pre-edit snapshots and a
  restore-from-history panel.
- Lets you **generate** new managed objects and whole new files from
  scratch — not just a blank template, but one that auto-fills every
  Mandatory parameter (with the correct real-file value, not Nokia's
  documented numeric code) and cascades into child objects that your own
  corpus shows are effectively always present, so a generated object is
  usable immediately rather than needing you to already know Nokia's
  schema.
- Tracks every Mandatory-but-still-unfilled parameter file-wide in one
  table ("Required Fields"), so completeness is answerable at a glance
  instead of requiring you to already know Nokia's schema by heart.

### Who it's for

RF/RAN engineers and Nokia field technicians who work with commissioning
files by hand (a real, common workflow — Nokia's own field tooling is a
set of Excel macro spreadsheets, reverse-engineered as part of this
project; see §9) and want something better than a raw-text editor plus a
1000-page confidential PDF open in another window.

---

## 2. Tech stack

- **Backend:** Python 3.12, FastAPI, stdlib `xml.etree.ElementTree` for all
  XML parsing/editing/serialization (deliberately no external XML library
  — ET is sufficient and this keeps the dependency footprint tiny).
  Pydantic for request bodies. `xlrd` + `openpyxl` for the one-time
  offline knowledge-base extraction scripts only (not a runtime
  dependency of the served app).
- **Frontend:** React 18 + Vite, no UI framework (hand-rolled CSS in one
  `styles.css`, dark theme only). No state management library — all state
  lives in `App.jsx` via `useState`/`useMemo`, passed down as props. No
  router (single-page, no URL-addressable views).
  **NOTE:** the sandbox this project was built in has no local
  `node`/`npm` — the frontend has never been run outside Docker. All
  frontend verification in this project's history was "does `npm run
  build` inside the Docker build stage succeed" plus manual code review,
  never a live browser session against `npm run dev`. If you have
  node/npm available, running `frontend/` directly (`npm install && npm
  run dev`, pointed at a locally-run backend) has never been tried and
  might surface issues the Docker-build-only verification missed.
- **Deployment:** single multi-stage Dockerfile (Node build stage → Python
  runtime stage that also serves the built frontend as static files),
  orchestrated with `docker-compose.yml`. No Kubernetes, no separate
  frontend/backend containers, no reverse proxy, no database — the
  "database" is the filesystem (XML files in directories).
- **No database.** No auth. No multi-user support. Designed to be run
  locally by one person against their own files, not deployed as a shared
  multi-tenant service. (`CORS_ORIGINS` is configurable if you do expose
  it, but there is zero authentication anywhere in the app — do not put
  this on the open internet without putting your own auth layer in front
  of it.)

---

## 3. Repository layout

```
backend/
  app/
    __init__.py
    main.py            904 lines — FastAPI app, every HTTP endpoint, all
                        request/response Pydantic models, env-var config,
                        the required-field annotation logic, the object
                        generator's class-resolution/cascade logic
    parser.py           849 lines — all XML parsing/editing/serialization.
                        No FastAPI/HTTP imports; pure functions operating
                        on bytes/ElementTree. This is the module to read
                        first to understand how the app actually works.
    heuristics.py       199 lines — deterministic fallback explanation
                        generator for parameters not in the knowledge base
    structural.py       165 lines — static glossary of the RAML file-format
                        elements themselves (raml/cmData/header/log), as
                        opposed to RAN config parameters
    data/
      classes.json      297 entries — researched/merged MO class glossary
      parameters.json   5656 entries — researched/merged parameter glossary
      class_catalog.json 557 entries — the generator's per-class parameter
                        catalog + hierarchy + required-child inference
                        (see §8, §9). All three are committed to git —
                        see §11 for why this was a deliberate, discussed
                        decision, not an oversight.
  requirements.txt      fastapi, uvicorn, python-multipart (pydantic comes
                        in as a FastAPI dependency)

frontend/
  index.html, package.json, vite.config.js
  src/
    main.jsx            React root mount
    App.jsx             952 lines — ALL application state and orchestration.
                        No other component holds meaningful state beyond
                        its own local UI concerns (modal open/closed,
                        form field values). See §7.
    api.js              152 lines — every backend HTTP call, one function
                        each, no abstraction beyond that
    knowledge.js        143 lines — client-side logic that decides what to
                        show in the Explain panel for a given tree node
                        using the kb (classes.json/parameters.json/
                        structural glossary) fetched at startup, before
                        falling back to a server round-trip
                        (explainParamFallback/explainClassFallback →
                        heuristics.py) if the kb doesn't have it
    rawTreeUtils.js     69 lines — tree-walking helpers shared between the
                        logical and raw tree views (find node/path by id)
    utils.js            53 lines — filterTree, collectExpandableIds, clamp
    styles.css          ~1200 lines, one file, no CSS modules/framework
    components/
      TreeView.jsx       197 lines — the logical (reconstructed) tree pane
      RawXmlView.jsx     224 lines — the literal/DOM-accurate raw XML pane
      ExplainPanel.jsx   228 lines — right-hand explanation panel
      AddObjectModal.jsx 245 lines — "+ Add Object" generator form
      AddParamModal.jsx  119 lines — "+ Add Parameter" (add to existing object)
      RequiredFieldsModal.jsx 179 lines — file-wide Mandatory-gap table + side panel
      ContextMenu.jsx     65 lines — generic right-click menu (position-aware)
      HistoryPanel.jsx    54 lines — snapshot list + restore
      UploadCard.jsx      77 lines — drag-and-drop upload widget
      EditableValue.jsx   90 lines — inline click-to-edit value widget
      Highlight.jsx       36 lines — search-match text highlighter
      Resizer.jsx         47 lines — draggable pane-resize handle
      paramFields.jsx     96 lines — shared param-input-widget builders used
                          by AddObjectModal/AddParamModal/RequiredFieldsModal

scripts/                 One-time / re-run-able offline pipeline that
                        builds backend/app/data/*.json. Never imported by
                        the running app; run manually, in order, whenever
                        ref/ or scp/ changes. See §8 for exact run order
                        and what each one does.
  extract_inventory.py
  build_knowledge.py
  extract_official_reference.py
  extract_sbts18a_reference.py
  merge_official_reference.py
  build_class_catalog.py

example/                 9 sample commissioning files, baked into the
                        Docker image (see §10), shown by default so the
                        app has something to browse out of the box.

screenshots/             main-page.png, xml-edit.png — used in README.md.

Dockerfile, docker-compose.yml, .dockerignore, .env.example, .gitignore
README.md               User-facing docs — feature list, KB methodology,
                        generator internals, running instructions. Large
                        overlap with this file but written for an end
                        user, not an engineer taking over the codebase.
PROJECT_STATE.md         This file.

--- NOT in git (see .gitignore, and §11 for the reasoning) ---
ref/                    Source Nokia reference documents (proprietary/
                        confidential — parameter dictionaries, MO class
                        trees, legacy XML-generator spreadsheets, PDFs).
                        ~4.4GB. Required to RE-RUN the scripts/ pipeline,
                        NOT required to run the app (backend/app/data/*.json
                        are the pipeline's committed output).
scp/                    The user's own real Nokia commissioning files
                        (~59MB, 78 files at last count). Read-only mount.
research/               Intermediate AI-research pipeline input/output
                        JSON, consumed by build_knowledge.py.
uploads/, snapshots/    Runtime-generated user data (gitignored, exist as
                        empty dirs created by the app at startup).
.claude/                Claude Code local tool settings, not part of the
                        product.
.env                    Optional local overrides of .env.example; never
                        committed (though nothing in it is currently a
                        secret — it's just gitignored by convention).
```

---

## 4. Core data model

This is the single most important section to understand before touching
`parser.py`.

### 4.1 The source format

A Nokia RAML file looks like:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<raml version="2.1" xmlns="raml21.xsd">
  <cmData type="plan" scope="all" id="...">
    <header>
      <log dateTime="..." action="created" user="..."/>
    </header>
    <managedObject class="com.nokia.mrbts:MRBTS" distName="MRBTS-1" version="..." operation="create">
      <p name="btsName">Example Site</p>
      <p name="mrbtsId">1</p>
      <list name="someListParam">
        <item>
          <p name="innerField">value</p>
        </item>
      </list>
    </managedObject>
    <managedObject class="NOKLTE:LNBTS" distName="MRBTS-1/LNBTS-1" version="..." operation="create">
      ...
    </managedObject>
    <managedObject class="NOKLTE:LNCEL" distName="MRBTS-1/LNBTS-1/LNCEL-1" ...>
      ...
    </managedObject>
  </cmData>
</raml>
```

Critical facts about this format that the whole codebase is built around:

- **`<managedObject>` elements are a FLAT list of siblings under
  `<cmData>`.** There is no XML nesting corresponding to the real
  equipment/cell hierarchy. The hierarchy is entirely encoded in the
  `distName` attribute as a `/`-separated path of `ClassName-InstanceId`
  segments (e.g. `MRBTS-1/EQM-1/APEQM-1/RMOD-1`). A child's distName is
  always exactly `{parent distName}/{ClassName}-{InstanceId}`.
- **Multiple XML namespace prefixes coexist in one real file.** Real
  corpus files mix `com.nokia.srbts:*` (newest AirScale/5G), `com.nokia.mrbts:*`
  (BTS Site Manager era), and `NOKLTE:*` (older Flexi Zone/LTE) — e.g. a
  `com.nokia.mrbts:MRBTS` root with `NOKLTE:LNCEL` children is normal and
  correct, confirmed against the corpus. Do not "fix" this if you see it.
- **`<p name="X">value</p>`** is a scalar parameter. **`<list
  name="X"><item>...</item></list>`** is a repeatable table/row structure
  (e.g. neighbor relations); each `<item>` can itself contain `<p>`
  children. List/table parameters are explicitly **out of scope** for the
  generator (see §12) — the tool reads and displays them, but "+ Add
  Object"/"+ Add Parameter" cannot create or edit list rows.
- Some files in the wild have stray text (headers/footers) before the
  `<?xml ...?>` declaration or after the closing `</raml>` tag, apparently
  from being copy-pasted out of a PDF viewer. `parser._strip_leading_junk()`
  trims anything outside the actual `<raml>...</raml>` document before
  parsing.

### 4.2 Two parallel tree representations

The app builds **two different JSON tree structures** from the same file,
served by two different endpoints, rendered by two different React
components, kept in sync by shared node IDs:

**A. The "logical" tree** (`parser.parse_file()`, served by `GET
/api/files/{filename}/tree`, rendered by `TreeView.jsx`) — the
distName-hierarchy-reconstructed parent/child tree a human actually wants
to browse. Node shape:

```jsonc
{
  "id": "MRBTS-1/LNBTS-1/LNCEL-1",       // == distName for "mo" nodes
  "label": "LNCEL-1",                     // last distName path segment
  "kind": "mo",                           // see kinds below
  "value": null,                          // non-null only for kind="param"
  "class": "LNCEL",                       // SHORT class name (no namespace)
  "fullClass": "NOKLTE:LNCEL",            // full namespaced class string
  "distName": "MRBTS-1/LNBTS-1/LNCEL-1",
  "operation": "create",
  "version": "...",
  "children": [ ... ],
  // present only on "param" kind nodes (added when this session's
  // required-field tracking was built -- see §9):
  "ownerDistName": "MRBTS-1/LNBTS-1/LNCEL-1",  // null if nested in a list/item
  "mandatory": true,           // Required on Creation == "Mandatory", any kind
  "trulyRequired": false,      // Mandatory AND no official default
  "requiredMissing": false     // mandatory==true AND no current value
}
```

Node `kind` values: `"mo"` (a real `<managedObject>` present in the file),
`"mo-placeholder"` (a synthetic ancestor inferred from a gap in the
distName chain — e.g. file has `A-1/B-1/C-1` but no literal `A-1/B-1`
managedObject; parser fabricates a placeholder node so the tree is still
navigable — flagged `"tag tag-implied"` in the UI), `"param"` (a `<p>`),
`"list"` (a `<list>`), `"item"` (one `<item>` row inside a list),
`"fileinfo"` (synthetic root node explaining the raml/cmData/header
wrapper), `"log"` (one `<log>` entry under header).

Top-level shape returned by the endpoint:
```jsonc
{
  "filename": "...",
  "stats": { "managedObjects": 821, "parameters": 15885 },
  "children": [ <fileinfo node>, <top-level mo nodes...> ]
}
```

**Algorithm** (in `parse_file`): iterate every `<managedObject>` once,
build a flat `dict[distName -> node]`. Then for every distName, walk up
its `/`-separated path calling `ensure_node(parent_dn)` recursively,
creating placeholder nodes for any missing intermediate ancestor, and
attach each node to its parent's `children` list. This is O(n) in file
size (each node visited once for creation, once for linking).

**B. The "raw" tree** (`parser.parse_file_raw()`, served by `GET
/api/files/{filename}/raw`, rendered by `RawXmlView.jsx`) — the literal
DOM structure exactly as written: tag names, attribute order, and the
flat managedObject sibling order preserved (NOT distName-reconstructed).
Node shape:
```jsonc
{
  "id": "MRBTS-1/LNBTS-1/LNCEL-1",   // SAME id scheme as the logical tree
  "tag": "managedObject",
  "attrs": { "class": "...", "distName": "...", "operation": "...", "version": "..." },
  "text": null,                       // non-null for leaf <p> text content
  "children": [ ... ],
  "ownerDistName": "...",             // present on "p" tag nodes only
  "mandatory": true, "trulyRequired": false, "requiredMissing": false  // "p" tags only
}
```

**Why the IDs match between the two trees — this is load-bearing.** Both
trees use the IDENTICAL id-generation scheme:
- A managedObject's id is its `distName`.
- A direct child param's id is `{ownerDistName}::p::{paramName}`.
- A list's id is `{ownerId}::list::{listName}`.
- An item's id is `{listId}::item::{index}`.
- A param nested in an item is `{itemId}::p::{paramName}`.

This means the frontend can highlight/scroll-to "the same" element in
BOTH panes with a **plain string equality id lookup** — no fuzzy
matching, no separate mapping table. This is the mechanism behind "click
something in one pane, the other pane highlights and scrolls to the
matching element." See §7.3 for the exact frontend algorithm (this had
real timing bugs during development — see §13).

### 4.3 Editing model

Every mutating endpoint follows the same pattern, implemented in
`parser.py` as pure functions operating on raw file bytes (never on the
in-memory tree — every edit re-parses fresh from whatever is currently on
disk, so edits are always independent and race-free within a single
request):

1. `_strip_leading_junk(raw_bytes)` then `ET.fromstring(...)`.
2. Find `<cmData>` (namespace-agnostic — see `_local()` which strips
   `{namespace}` prefixes ElementTree adds to tag names).
3. Locate the target `<managedObject>` by `distName` (`_find_managed_object`)
   or the target `<p>` by name within it.
4. Mutate the `ElementTree` in place.
5. `_serialize(root)` — re-emit as bytes.

`_serialize()` does two things beyond a bare `ET.tostring()`: (a) calls
`ET.register_namespace("", ns_uri)` before serializing, because without
this ElementTree emits an auto-generated `ns0:` prefix on every tag
instead of Nokia's own bare-tag + `xmlns="raml21.xsd"` style — this was a
real bug caught early in development; (b) calls `ET.indent(root,
space="  ")` for clean, consistent formatting. **Known side effect:**
re-serializing does NOT reproduce a source file's original exact
whitespace/indentation — every edit normalizes formatting. Data and
structure are preserved exactly; only incidental formatting changes. This
is called out in the code comments and is considered acceptable (Nokia's
own tools don't preserve byte-exact formatting either).

Every backend mutation endpoint in `main.py` follows this exact wrapper
sequence regardless of which parser.py function it calls:
```python
current = path.read_bytes()
new_bytes = <parser function>(current, ...)          # may raise XmlParseError/ParamNotFoundError/ObjectExistsError -> HTTP 400
parse_file(new_bytes, filename)                        # re-validate; raise HTTP 500 if this produced invalid XML
_save_snapshot(filename, current)                       # snapshot the PRE-edit bytes
path.write_bytes(new_bytes)
_invalidate_caches(filename)
```
Snapshotting happens AFTER re-validation succeeds but the snapshot is of
the ORIGINAL (pre-edit) bytes — so a snapshot is only ever created
immediately before a successful write, never for a rejected edit.

---

## 5. Backend: full API reference

All endpoints are under `/api`. All are synchronous `def`, not `async
def`, except `/api/upload` (needs to await file reads). FastAPI runs sync
endpoints in a thread pool automatically, so this is fine for this
single-user, filesystem-bound workload.

Read-only files (source `"scp"` or `"example"`) return **403** from every
mutating endpoint with detail `"This is a read-only reference file. Create
an editable copy first."` — enforced by checking `_resolve_path()`'s
returned source string equals `"upload"` at the top of every mutator.

| Method & path | Purpose | Request body | Response |
|---|---|---|---|
| `GET /api/health` | Liveness + config visibility | — | `{status, scpDir, scpDirExists, uploadDir, includeExamples, exampleDirExists}` |
| `GET /api/files` | List every visible file across upload/scp/example | — | `[{name, sizeBytes, mtime, supported, source}]` |
| `POST /api/upload` | Upload one or more `.xml` files (multipart) | `files: UploadFile[]` | `[{name, ok, error?}]` per file — rejects non-`.xml`, over `MAX_UPLOAD_BYTES`, or fails `parse_file()` validation |
| `DELETE /api/files/{filename}` | Delete an uploaded file (upload-source only) | — | `{ok: true}` |
| `POST /api/files/{filename}/duplicate-to-uploads` | Copy ANY file (scp/example/upload) into an editable upload | — | `{name: "<original> (copy).xml"}` (see `_unique_upload_name`) |
| `POST /api/files/new` | Create a brand-new, minimal-but-valid empty file | `{filename?}` | `{name}` |
| `GET /api/catalog/classes` | Every known MO class (490+ across both official dictionaries, not just corpus-observed) for the "Add Object" picker | — | `[{shortName, directParent, observedParents[], observedInCorpus, description, officialFullName, category, paramCount}]` |
| `GET /api/catalog/classes/{class_name}` | Full param catalog for one class | — | raw `class_catalog.json[class_name]` entry (404 if unknown class) |
| `POST /api/files/{filename}/objects` | **Generator: add one object** (cascades — see §9) | `AddObjectRequest` | see §9.3 |
| `PUT /api/files/{filename}/objects/param` | Upsert one scalar param on an existing object | `SetObjectParamRequest{distName,paramName,value}` | `{ok: true}` |
| `DELETE /api/files/{filename}/objects/param` | Delete a non-Mandatory scalar param | `DeleteParamRequest{distName,paramName}` | `{ok: true}` (400 if the param is Mandatory) |
| `DELETE /api/files/{filename}/objects` | Delete an object + every descendant | `DeleteObjectRequest{distName}` | `{ok: true, deleted: [distName, ...]}` |
| `PUT /api/files/{filename}/objects/rename` | Change an object's trailing instance number, cascading to descendants | `RenameObjectRequest{distName,newInstanceId}` | `{distName: <new distName>}` (400 on collision) |
| `PUT /api/files/{filename}/param` | Edit one param by tree-node id (the original, pre-generator edit mechanism) | `UpdateParamRequest{nodeId,value}` | `{ok: true}` |
| `GET /api/files/{filename}/snapshots` | List snapshots, newest first | — | `[{id, sizeBytes}]` |
| `POST /api/files/{filename}/snapshots/{snapshot_id}/restore` | Restore a snapshot (itself snapshotted first) | — | `{restored: snapshot_id}` |
| `GET /api/files/{filename}/tree` | The logical tree (§4.2A), mtime-cached | — | tree JSON |
| `GET /api/files/{filename}/raw` | The raw DOM tree (§4.2B), mtime-cached | — | `{filename, root}` |
| `GET /api/files/{filename}/missing-required` | Every Mandatory-and-currently-empty param, file-wide | — | `[{distName, class, paramName, dataType, exampleValues[], officialRange, description, unit, observed}]` |
| `GET /api/knowledge/classes` | Raw `classes.json` (served as-is) | — | dict |
| `GET /api/knowledge/parameters` | Raw `parameters.json` (served as-is) | — | dict |
| `GET /api/knowledge/structural` | `structural.ELEMENTS`/`ATTRIBUTES` glossary | — | dict |
| `GET /api/explain/param?name=&moClass=&value=` | Server-side fallback explanation (heuristics.py) when the frontend's client-side kb.js lookup misses | — | `{description, confidence, dataType, unit, notes}` |
| `GET /api/explain/class?name=` | Same, for a class name | — | similar shape |

### Static file serving

The FastAPI app also mounts the built frontend as static files
(`FRONTEND_DIST`, default `/app/frontend_dist`) so the whole app is one
container, one port, no separate frontend server. (Exact mount code is in
`main.py` near the bottom — not reproduced above since it's standard
FastAPI `StaticFiles` boilerplate, but note it exists: if you add new
backend routes, add them BEFORE the catch-all static mount or they'll be
shadowed.)

---

## 6. Backend: module walkthrough

### 6.1 `main.py` — orchestration layer

Top of file, env-driven config (all new in the v0.02 `.env` work — see
§10 for the full list and defaults):
```python
SCP_DIR, UPLOAD_DIR, SNAPSHOT_DIR   # Path, from env, .resolve()'d
EXAMPLE_DIR                          # Path, default /app/example (baked into image)
INCLUDE_EXAMPLES                     # bool, default True
DATA_DIR                             # NOT env-configurable: always backend/app/data
MAX_UPLOAD_BYTES, MAX_SNAPSHOTS_PER_FILE, CORS_ORIGINS  # env-configurable
```
`_env_bool`/`_env_int` are tiny local helpers (no library) — bool parsing
treats `"false"/"0"/"no"/"off"` (case-insensitive) as False, everything
else (including unset → default) as True.

**Startup:** `_load_kb()` reads the three `backend/app/data/*.json` files
into module globals `_CLASSES_KB`, `_PARAMS_KB`, `_CLASS_CATALOG`. **If
any file is missing, that global becomes `{}`** — the app does not crash,
it just serves an empty knowledge base (plain tree view, editing, and
generation all keep working; Explain panel has nothing to say, generator
doesn't know about Mandatory defaults). This graceful-degradation
behavior was a deliberate design point, discussed explicitly when
deciding whether to commit `backend/app/data/*.json` to git (see §11) —
it means the answer to "what if someone deletes that data" is "app still
works, just dumber," never "app won't start."

**File resolution** (`_resolve_path`, `_name_taken`, `_unique_upload_name`):
priority order is always **upload → scp → example**. A name that exists
in an earlier-priority source shadows a later one in every by-name
lookup, so `_name_taken()`/`_unique_upload_name()` check ALL THREE
directories before assigning a name to a new upload/duplicate/rename, to
guarantee no accidental shadowing. (There is a specific historical bug
fixed for exactly this: duplicating an scp file could originally reuse
the same filename in uploads/, silently shadowing the scp original in
every subsequent lookup — fixed by always appending "(copy)" and
re-checking uniqueness across every source directory.)

**Required-field tracking** (`_param_meta`, `_is_required_missing`,
`_annotate_required_logical`, `_annotate_required_raw`) — added
server-side annotation, applied to the tree JSON right before caching, so
the frontend never has to re-derive "is this Mandatory and empty" itself.
The core predicate, which is more subtle than it looks (see §9.4 for why
it does NOT key off the catalog's static `trulyRequired` flag):
```python
def _is_required_missing(meta, has_value):
    return bool(meta and meta.get("requiredOnCreation") == "Mandatory" and not has_value)
```

**In-memory caches** `_TREE_CACHE`/`_RAW_CACHE`: `dict[filename -> (mtime,
tree)]`, invalidated on file mtime change or explicitly after any write
(`_invalidate_caches`). Not persisted, not shared across processes — fine
for single-process `uvicorn`, would need rethinking if ever run with
multiple workers.

**The generator internals** (`_resolve_full_class`, `_create_one_object`,
`_cascade_required_children`) are the most complex part of this file —
fully covered in §9.

### 6.2 `parser.py` — pure XML mechanics

No FastAPI, no knowledge-base awareness, no HTTP concerns — everything
here is `(bytes, ...) -> bytes` or `(bytes) -> dict`, independently
testable and independently understandable. Two error types raised
throughout: `XmlParseError` (malformed XML) and `ParamNotFoundError`
(well-formed XML, but the requested distName/param doesn't exist);
`add_managed_object`/`rename_managed_object` also raise `ObjectExistsError`
on a distName collision. `main.py` catches all three and maps to HTTP
400/404/500 as appropriate.

Full function inventory (see §4 for the parse/serialize functions already
covered in detail):

- `parse_file`, `parse_file_raw` — build the two tree representations (§4.2).
- `update_param_value(raw_bytes, node_id, new_value)` — the ORIGINAL edit
  mechanism, from before the generator existed: navigates a node id
  (`_navigate_to_param`, walking the `::p::`/`::list::`/`::item::` id
  segments) and sets its text. Still used by the plain "click a value,
  type a new one" edit-mode interaction (`PUT /api/files/{f}/param`);
  the newer `set_param_value(raw_bytes, dist_name, param_name, value)` is
  an *upsert* by distName+paramName instead of by opaque node id (creates
  the `<p>` if absent) — used by the "+ Add Parameter" flow and the
  Required Fields table, both of which need to be able to set a
  parameter that might not exist in the tree yet.
- `add_managed_object(raw_bytes, parent_dist_name, short_class, full_class,
  version, instance_id, params)` — appends one new `<managedObject
  operation="create">`. **Important behavior:** for each `(name, value)`
  in `params`, `None` values are skipped entirely, but `""` (empty
  string) values ARE written, as a self-closing `<p name="X"/>` tag
  (`text = None` when `value == ""`). This distinction — skip-on-None,
  write-empty-string-as-self-closing-tag — is what makes it possible for
  the generator to deliberately write a visible-but-unfilled placeholder
  for a Mandatory parameter with no safe default (see §9.2). This was a
  deliberate behavior CHANGE partway through the project: it originally
  skipped both `None` and `""`, which meant Mandatory-no-default params
  were silently omitted from generated objects — changed after the user
  explicitly required "even mandatory fields with no default must still
  show up in the file, just flagged."
- `set_param_value` — as above, upsert.
- `delete_param(raw_bytes, dist_name, param_name)` — removes one `<p>`
  child. Caller (main.py) is responsible for checking it isn't Mandatory
  first; this function itself has no opinion.
- `delete_managed_object(raw_bytes, dist_name)` — removes the object AND
  every descendant (any managedObject whose distName equals `dist_name`
  OR starts with `dist_name + "/"`), since a flat sibling list means
  descendants are separate elements, not something removed for free by
  deleting the parent. Returns `(new_bytes, list_of_deleted_distNames)`.
- `rename_managed_object(raw_bytes, dist_name, new_instance_id)` —
  changes JUST the trailing `-N` of a distName (same class, same parent),
  and rewrites the identical distName-prefix swap onto every descendant.
  Raises `ObjectExistsError` if the resulting distName already exists.
  Returns `(new_bytes, new_dist_name)`.
- `find_existing_class_version(raw_bytes, short_class)` — scans for any
  existing instance of a class to borrow its namespaced `class` string
  and `version` for consistency when creating a new one of the same class.
- `find_any_version(raw_bytes)` — fallback: version string from ANY
  managedObject in the file, used when creating a class with zero
  existing instances.
- `next_available_instance_id(raw_bytes, parent_dist_name, short_class)` —
  scans siblings under a parent for the same class, returns
  `str(max existing + 1)`, or `"1"` if none exist.
- `new_file_bytes()` — the minimal skeleton for "+ New file": a bare
  `<raml><cmData><header>...</header></cmData></raml>` with no managed
  objects at all.

### 6.3 `heuristics.py` — deterministic fallback explanations

Used when a parameter name has no entry in `parameters.json`. Splits a
camelCase parameter name into tokens, expands each token against a large
hand-built abbreviation dictionary (`ABBREVIATIONS`, ~100+ entries: `act`
→ "activate/enable", `bler` → "block error rate", etc. — standard 3GPP/RAN
jargon), and composes a plain-English sentence, incorporating the
managed-object class(es) it was observed under and any example values
seen in the corpus. Always tagged `confidence: "heuristic"` so the UI can
show an "auto-generated — unverified" badge. Deliberately simple/rule-based
rather than an LLM call — deterministic, free, instant, and transparent
about its own uncertainty.

### 6.4 `structural.py` — file-format glossary

A static hand-written dict explaining the fixed RAML wrapper elements
(`raml`, `cmData`, `header`, `log`, `managedObject`, `p`, `list`, `item`)
and their attributes — this is a small, fixed vocabulary (the XML
*format* itself, not RAN config data), so it's just hand-written once,
no extraction pipeline needed.

---

## 7. Frontend architecture

### 7.1 Component tree (rendering, not data flow)

```
App.jsx (owns ~50 pieces of state, listed below)
├── UploadCard                    (sidebar, drag-and-drop)
├── file list (inline JSX, not a component) — 3 groups: uploads / scp / example
├── toolbar (inline JSX) — search, expand/collapse all, Show Raw XML,
│    Edit Mode, + Add Object, Required Fields (badge), History
├── TreeView                      (logical pane; recursive: renders itself
│    │                             for children of an expanded row)
│    └── EditableValue, Highlight (leaf widgets)
├── RawXmlView                    (raw pane; same recursive-self pattern)
│    └── EditableValue, Highlight
├── ExplainPanel                  (right sidebar)
│    └── AddParamModal            (opened from within ExplainPanel)
├── AddObjectModal                (opened from toolbar)
│    └── paramFields.jsx helpers
├── RequiredFieldsModal           (opened from toolbar)
│    └── paramFields.jsx helpers, own inline side panel
├── ContextMenu                   (rendered at top level, positioned via
│                                   fixed x/y from the triggering click)
└── HistoryPanel                  (opened from toolbar, near History button)
```

### 7.2 State ownership — everything lives in App.jsx

There is no Redux/Zustand/Context — `App.jsx` holds every piece of
cross-cutting state and passes it down as props, plus handler functions
closed over that state. Full state inventory (grouped by concern, from
the actual `useState` calls):

- **File list:** `files`, `filesError`, `selectedFile`, `fileFilter`
- **Logical tree:** `tree`, `loadingTree`, `treeError`, `expanded` (Set of
  expanded node ids), `selectedNode` (the node shown in ExplainPanel —
  set on double-click), `query` (tree search text)
- **Knowledge base:** `kb`, `kbError` (fetched once at startup: classes +
  parameters + structural glossary, bundled into one object)
- **Layout:** `sidebarWidth`, `sidebarCollapsed`, `explainCollapsed`,
  `showRawView`, `rawLayout` ("side"|"stacked"), `splitWidth`, `splitHeight`
- **Raw tree:** `rawTree`, `rawLoading`, `rawError`, `rawExpanded`,
  `rawQuery`, `rawMatchIndex`
- **Bidirectional sync:** `focusId` (the single shared "currently
  active" node id — see §7.3), `logicalFocusMissing`, `rawFocusMissing`
  (true when focusId exists in one tree but not the other — e.g. a raw
  DOM node with no logical-tree equivalent — surfaced as a small notice
  rather than silently failing)
- **Editing:** `editMode`, `duplicating`, `duplicateError`
- **History:** `historyOpen`, `snapshots`, `snapshotsLoading`,
  `snapshotsError`, `restoringId`
- **Generator:** `addObjectOpen`, `generatorWarning` (banner text — used
  both for "this class's namespace was guessed" AND "N required child
  objects were also created" messages, concatenated if both apply)
- **Required fields:** `missingRequired` (array, refetched via a `useEffect`
  keyed on `[selectedFile, isEditableFile, tree]` — refetching on every
  `tree` change is what keeps the badge count and table live after ANY
  edit, without needing an explicit refresh call at every edit site),
  `requiredFieldsOpen`
- **Context menu:** `contextMenu` (`{x, y, node} | null`)

Derived values (not state, `useMemo`/plain consts): `isEditableFile =
selectedFileInfo?.source === "upload"`, `canEditNow = editMode &&
isEditableFile`, `uploadedFiles`/`scpFiles`/`exampleFiles` (filtered from
`files` by `.source`), `displayNodes` (tree filtered by search query),
`rawMatches` (raw-tree search match ids).

### 7.3 Bidirectional highlight sync — the trickiest interaction

This is the single most fiddly piece of frontend logic in the app and the
one most likely to regress if touched carelessly.

**Mechanism:** a single `focusId` state variable represents "the node the
user most recently interacted with, in either pane." Setting it (via
`onActivate` callbacks from either `TreeView` or `RawXmlView`, or via raw
search navigation) triggers one `useEffect` (keyed on
`[focusId, tree, rawTree, showRawView]`) that:
1. Looks up `focusId` in the logical tree (`findPathInForest`) — if
   found, expands every ancestor on that path (`setExpanded`) and calls
   `scrollToDataId(treeScrollRef.current, "data-tree-id", focusId)`.
   If NOT found, sets `logicalFocusMissing = true` instead of scrolling.
2. Does the same for the raw tree (`findPath`, `rawExpanded`,
   `scrollToDataId(rawScrollRef.current, "data-raw-id", focusId)`) — but
   only if `showRawView` is on and `rawTree` is loaded.

Because both trees use the identical id scheme (§4.2), this is a single
string-equality lookup in each tree — no cross-referencing table needed.

**`RAW_TO_LOGICAL_ALIAS`** (a small constant map in App.jsx, not shown
above): handles the one case where raw-tree ids and logical-tree ids
legitimately diverge — the raw tree's synthetic root/`cmData`/`header`
nodes (`"raw-root"`, `"fileinfo"`, `"fileinfo-header"` etc.) map to the
logical tree's single `"fileinfo"` node. `handleRawActivate` looks up this
alias before setting `focusId`.

**`scrollToDataId` — why it's more complex than `scrollIntoView`:**
```js
function scrollToDataId(container, attr, id, retriesLeft = 8) {
  if (!container || !id) return;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const el = container.querySelector(`[${attr}="${cssAttrEscape(id)}"]`);
      if (el) {
        el.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
      } else if (retriesLeft > 0) {
        setTimeout(() => scrollToDataId(container, attr, id, retriesLeft - 1), 40);
      }
    });
  });
}
```
**Why the double `requestAnimationFrame` plus a retry loop:** expanding
ancestors (`setExpanded`) and this scroll call happen from the same
effect, but React's re-render of the newly-revealed DOM rows is not
guaranteed to have painted by the time a single `requestAnimationFrame`
callback runs. A single rAF was the original implementation and it was
buggy in practice — the highlight would "snap to the correct place" only
sometimes, requiring the user to manually scroll to find what they
clicked. This was reported and fixed twice in this project's history
(see §13) before landing on: double-rAF to wait for a full committed
paint, PLUS a `setTimeout` retry loop (up to 8 retries, 40ms apart) to
cover deeply-nested multi-ancestor expansions where even double-rAF isn't
quite enough. If you ever see "sync sometimes doesn't scroll," this
function is where to look first, and increasing `retriesLeft`/the delay
is the first thing to try before assuming something else broke.

### 7.4 Delete / rename / context menu

Two ways to trigger delete on an object or a direct (non-list-nested)
parameter, both editMode-only:
1. An inline `×` button (`.node-delete-btn`), positioned **right after
   the label/tag near the row's start**, not at the row's end. (Originally
   placed at the row's end via `margin-left: auto`; this was a real bug —
   long values/distNames/badges push a row wider than the visible pane,
   which scrolls horizontally, so "the end of the row" can be scrolled
   out of view entirely, making the button invisible in practice. Fixed
   by repositioning near the row's start, which is always in view.)
2. Right-click anywhere on an object or parameter row → `ContextMenu.jsx`,
   which opens at the click's `(clientX, clientY)` — immune to the
   above row-width problem entirely, and is the recommended/more
   discoverable path. Also offers **Rename** for objects (prompts for a
   new instance ID via `window.prompt`, pre-filled with the current one).

Mandatory parameters can never be deleted (button/menu item disabled,
backend also rejects it at 400) — only edited. There is deliberately NO
such restriction on deleting or renaming whole objects: Nokia's own docs
don't define any class as "required to exist" (see §9.1), so there's no
analogous protection to enforce.

A CSS-class-naming collision bug is worth knowing about if you add more
buttons: there is a **pre-existing, unrelated** `.delete-btn` class used
by the file-list's own delete button (sidebar "Your uploads" list). The
tree/raw delete buttons were originally ALSO named `.delete-btn`, which
silently won the cascade (later in the stylesheet) and reused unrelated
positioning rules — this was the actual root cause of a "I can't find the
delete button anywhere" bug report. Fixed by renaming to
`.node-delete-btn`. **Lesson: this codebase has more than one "delete
button" concept: check for existing class names before adding new UI with
a generic name.**

### 7.5 The Explain panel and the knowledge base lookup order

`ExplainPanel.jsx` → `knowledge.js`'s `explainNode(node, kb)`: tries to
build an explanation purely client-side from the already-fetched `kb`
object (classes.json + parameters.json + structural.js glossary,
class-then-param-name lookup). If that lookup can't find anything
(`needsFallback: true`), it falls back to a server round-trip
(`explainParamFallback`/`explainClassFallback` → `GET /api/explain/param`
or `/class` → `heuristics.py`). This two-tier lookup (client-side kb
first, server heuristic fallback second) means the common case (a
well-known parameter) never needs a network round trip after initial
page load.

---

## 8. The knowledge base system

### 8.1 Three-layer sourcing model, by confidence tier

Every parameter/class entry in `backend/app/data/{classes,parameters}.json`
carries a `confidence` field:

| Tier | Source | Notes |
|---|---|---|
| `official` | Nokia's own parameter dictionaries (LTE18 xlsx, SBTS18A xls) | Highest trust. ~2,800 of 5,656 parameters. |
| `high` | 3GPP-standard concept or unambiguous Nokia convention | Manually/AI-researched, cross-checked |
| `medium` | Reasonably confident AI research | |
| `low` | Weaker AI research, less certain | |
| `heuristic` | Auto-generated at request time by `heuristics.py` | Never stored in the JSON — generated live, always flagged "unverified" in the UI |

The `class_catalog.json` generator-specific file (§9) additionally tags
each parameter `"observed": true/false` — whether it was actually seen in
the 78-file `scp/` corpus, independent of the confidence tier.

### 8.2 The two official Nokia source documents

1. **`ref/ref_bts_parameters_lte18.xlsx`** — LTE18 (2018), has separate
   FDD and TDD sheets, plus an "MO Class Tree" sheet (class hierarchy:
   shortName, fullName, depth, parentChain — depth encoded by column
   position in the original spreadsheet).
2. **`ref/SRAN18AISSUE03HTML/.../SBTS_Parameters_18A.xls`** — SBTS18A
   (2019, the newer, unified AirScale/SRAN dictionary) — 10,238 parameter
   rows across 426 classes, one unified "Parameter List" sheet (not
   FDD/TDD split) plus its own "MO Class Tree" sheet. This is treated as
   the more authoritative/current source when the two disagree (loaded
   with SBTS18A last / highest priority in `merge_official_reference.py`'s
   `SOURCE_LABELS` precedence).

Both were extracted with different libraries because of file format:
`xlrd` for the legacy binary `.xls` (SBTS18A), `openpyxl` for the
`.xlsx` (LTE18).

**CRITICAL, project-defining lesson learned early and applied
everywhere:** Nokia's documented values are NOT what real files contain.
The dictionaries encode enums/booleans as numeric codes with a
human-readable label in parens — e.g. `administrativeState`'s documented
range is `"1: unlocked, 2: shutting down, 3: locked"` and its documented
default is the string `"locked (3)"` — but **real commissioning XML in
the corpus contains the text `"Locked"`/`"unlocked"`**, never the number.
Every place in this codebase that surfaces a suggested/default value to
the user or writes one into generated XML is grounded in corpus-observed
`exampleValues`, cross-checked against the documented value, never the
raw documented code taken at face value. See `resolve_default_for_xml()`
in §9.2 for the exact mechanism — this function's whole reason to exist
is this one lesson.

### 8.3 The extraction/merge pipeline — exact run order

None of these run automatically; they're one-time (or re-run-when-source-
data-changes) offline scripts, run manually from the repo root. **This is
the order dependencies require:**

```bash
# 1. Corpus inventory (scans scp/ for every class/param name actually used)
python3 scripts/extract_inventory.py
# → research/input/*.json (inventory, param_stats, etc.)

# 2. AI-assisted research pass merge (research/input -> research/output
#    was done by hand/AI during initial development, not scripted here;
#    build_knowledge.py merges research/output + heuristics into the KB)
python3 scripts/build_knowledge.py
# → backend/app/data/classes.json, parameters.json (heuristic/researched tier)

# 3. Extract the two official Nokia dictionaries into normalized JSON
python3 scripts/extract_official_reference.py     # LTE18 xlsx -> ref/extracted/lte18_*.json
python3 scripts/extract_sbts18a_reference.py       # SBTS18A xls -> ref/extracted/sbts18a_*.json

# 4. Upgrade classes.json/parameters.json entries to "official" tier
#    wherever the two dictionaries have a match; must run AFTER step 2
python3 scripts/merge_official_reference.py

# 5. Build the generator's per-class parameter catalog; must run AFTER
#    step 4 (reads the now-upgraded parameters.json)
python3 scripts/build_class_catalog.py
# → backend/app/data/class_catalog.json
```

Re-run steps 3–5 (or all 5) any time `ref/` or `scp/` changes. Step 5
alone is sufficient after just adding new files to `scp/` (widens
corpus-observed data without needing to re-extract Nokia's dictionaries).

### 8.4 Key merge-time bugs/decisions worth knowing

- **`pick_best_entry()` in `merge_official_reference.py`** handles a
  parameter name that maps to different official descriptions depending
  on class (name reuse across classes is common in Nokia's schema). Real
  bug hit and fixed: `administrativeState` was showing one hyper-specific
  class's (ETHLK's) essay-length description for EVERY use of that
  parameter name, because the picker naively took the first/any matching
  official row. Fixed: if the corpus uses a name across multiple
  classes (generic reuse), prefer the shortest-but-substantial
  description among candidates as a safer generic proxy, rather than one
  class's specific wording.
- **`is_truly_required(official)`** — `Required on Creation == "Mandatory"
  AND Default Value in (None, "")`. This distinction (see §9.1) exists
  because the dictionaries' own field description literally states:
  *"Mandatory parameters with no default value defined must be filled
  in"* — meaning "Mandatory" ALONE does not mean "must appear in every
  file"; only Mandatory-with-no-default truly does.
- **Data-type coercion defensiveness:** some "Range and step" cells in
  the SBTS18A sheet are raw floats, not strings (spreadsheet artifact) —
  a `_s()` helper coerces to string everywhere before regex matching, to
  avoid `TypeError` crashes during extraction.

---

## 9. The XML generator system

This is the feature set that received the most iteration in this
project's history (see §13) — the user's requirements sharpened across
many rounds of feedback, each one catching a real gap. Read this section
in full before touching `_create_one_object`/`_cascade_required_children`
in `main.py` or `build_class_catalog.py`.

### 9.1 The core distinction: parameter-Mandatory vs class-required

Nokia's official dictionaries define, **per parameter**, a `Required on
Creation` field with value `"Mandatory"` or not. There is **no equivalent
concept for managed-object CLASSES** — neither dictionary, nor any XSD
schema (there isn't one in `ref/` — the `raml21.xsd` referenced by the
`xmlns` attribute is a generic structural schema for the `p`/`list`/
`managedObject` wrapper elements, not something that encodes per-class
cardinality rules), says "an LNBTS must have at least one LNCEL." This
was explicitly checked and confirmed absent before building §9.5's
heuristic — don't assume it exists somewhere unexamined.

### 9.2 `resolve_default_for_xml()` — translating documented defaults into real values

Lives in `scripts/build_class_catalog.py`, called once per parameter
while building `class_catalog.json` (not at request time). Takes
`(data_type, official_default, example_values)` and returns either a
real-file-safe string to use as the default, or `None` (meaning: don't
auto-fill, there's no safe/confident value). Logic by data type:
- `integer`/`decimal`: stringify the documented number as-is (numbers
  aren't subject to the code-vs-label problem).
- `string`: stringify as-is.
- `boolean`: documented default is `0.0`/`1.0`-ish → map to `"false"`/`"true"`,
  then if corpus `example_values` exist, match case-insensitively against
  them to get the corpus's actual casing (`match_case()` helper); if no
  corpus examples exist, use the lowercase label as a best-effort guess.
- `enum`: documented default is like `"locked (3)"` → strip the
  parenthesized code, keep the label (`"locked"`), then same
  `match_case()` cross-check against corpus values for correct casing;
  best-effort label if no corpus grounding at all.

Verified quality at build time: **98.4% of 2,584 Mandatory-with-documented-default
parameters** resolve successfully to a value. The remaining ~1.6% return
`None` and are treated identically to "no default at all" (see §9.4) —
written as a blank, red-flagged placeholder rather than silently getting
something wrong.

The resolved value is stored per-parameter in `class_catalog.json` as
`resolvedDefault` (alongside the raw `officialDefault` for reference).

### 9.3 `POST /api/files/{filename}/objects` — the full add-object flow

`AddObjectRequest{parentDistName?, className, instanceId?, params}`.

1. Validate `className` is known (in `_CLASS_CATALOG` or `_CLASSES_KB`) → 400 if not.
2. **`_resolve_full_class()`** determines the namespaced `class` XML
   attribute string to write, in priority order:
   a. An existing instance of this class already in THIS file (reuse its
      exact `class`/`version` strings) — `classVerified=True`.
   b. `classes.json`'s researched `fullNames` list for this short class —
      `classVerified=True`.
   c. **Sibling-namespace inference:** this class was never observed in
      the corpus at all (only known from the official dictionaries, which
      record hierarchy/parameters but NOT the namespace prefix — that's
      only ever visible in a real file). Find a sibling class under the
      SAME parent that WAS observed, and borrow its namespace prefix
      (Nokia namespaces are consistently per-subsystem — e.g. every
      `APEQM` child observed in the corpus uses `com.nokia.srbts.eqm:*`,
      so a never-seen sibling class is very likely the same namespace).
      **`classVerified=False`** — flagged as a guess, surfaced to the
      user via a dismissible banner ("this class was never seen in any
      of your sample files... double-check it in Raw XML").
3. `next_available_instance_id()` if not explicitly given.
4. **Mandatory-parameter auto-fill** (`_create_one_object`'s param-merge
   loop) — for every parameter in this class's catalog with
   `requiredOnCreation == "Mandatory"` that ISN'T already in the
   caller-supplied `params`:
   - if `resolvedDefault` is not `None` → fill it in, record in
     response's `autoFilledDefaults` list.
   - else (no safe default, OR resolution failed) → set it to `""`
     (written by `add_managed_object` as a self-closing, visible-but-empty
     `<p name="X"/>` tag — see §6.2), record in response's
     `autoAddedBlank` list.
   **No Mandatory parameter is ever silently omitted.** This was the
   single most-repeated, most-refined user requirement in this project's
   history (see §13) — three separate follow-up messages progressively
   tightened this from "flag what's missing" to "auto-fill defaults" to
   "even fields with no default must still appear in the file, just
   blank and flagged."
5. `add_managed_object()` writes the new element; re-parse-validate;
   snapshot; write; invalidate caches.
6. **`_cascade_required_children()`** (§9.5) recurses into required child
   classes, using the ALREADY-UPDATED bytes as its new "current" state —
   i.e. cascaded children are created via sequential calls to
   `_create_one_object`, each threading the growing byte string into the
   next, not a single combined write.
7. Response:
```jsonc
{
  "distName": "...", "class": "...", "classVerified": true,
  "autoFilledDefaults": ["administrativeState", "..."],
  "autoAddedBlank": ["mcc", "lnCelId", "..."],
  "cascadedObjects": [
    { "distName": "...", "class": "...", "shortClass": "CABINET", "classVerified": true,
      "autoFilledDefaults": [...], "autoAddedBlank": [...] },
    { "shortClass": "RMOD", "parentDistName": "...", "error": "..." }   // on cascade failure — see below
  ]
}
```

### 9.4 Why "required-missing" is NOT the same check as the catalog's `trulyRequired` flag

`class_catalog.json`'s per-parameter `trulyRequired` field is a STATIC,
build-time fact: Mandatory AND the official dictionary defines no
default at all. But `main.py`'s `_is_required_missing()` (used for the
red-highlight/Required-Fields-table logic) is a DIFFERENT, broader,
RUNTIME check: Mandatory AND **currently has no value** — regardless of
whether a default was documented.

**Why they must differ — a real bug caught during testing:** a parameter
can be Mandatory, HAVE a documented default, and STILL end up written
blank by `_create_one_object` if `resolve_default_for_xml()` was one of
the ~1.6% that couldn't confidently resolve a value (§9.2). If the
red-flag logic had used the static `trulyRequired` flag, THIS parameter
would be written blank but NOT flagged red and NOT appear in the
Required Fields table — a silent gap. Caught in testing (`LNCEL.prsMutingInfo`
was exactly this case: has an official default, `trulyRequired=false`
in the catalog, but its default failed to resolve, so it was written
blank yet initially un-flagged). Fixed by making the red-flag/table logic
check "is there currently a value," full stop, independent of whether the
docs claim a default exists.

### 9.5 `_cascade_required_children()` — the corpus-heuristic required-child inference

Since §9.1 established there's no official source for "class X must have
a child of class Y," the ONLY signal available is a **corpus heuristic**,
computed once at `build_class_catalog.py` build time (in the `walk()`
tree-walker, alongside the existing corpus-scan for parameter examples):

**Algorithm:** for every class `C` observed in the corpus, collect, for
EACH individual instance of `C` (each real distName occurrence across all
78 files), the SET of its direct child classes (one instance = one entry
in a `list[set[str]]`). After the full corpus walk: `common =
set.intersection(*all_instance_child_sets_for_C)` — a child class
survives into `requiredChildClasses[C]` only if it appears under **100%**
of observed instances of `C`, with no minimum-sample-size threshold
applied (a class observed only once still gets an inference — this was a
deliberate choice, not an oversight; the `childSampleSize` field is
stored alongside so confidence is visible/auditable rather than hidden,
and the caller can judge from that number, e.g. one inference in the
current data — `LNADJ → LNADJL` — is based on a sample size of 2).

Stored per-class in `class_catalog.json`:
```jsonc
{ "requiredChildClasses": ["CABINET", "RMOD"], "childSampleSize": 69 }
```
(example real values for `APEQM`, from the current corpus — meaning
every one of 69 observed APEQM instances had at least one CABINET child
and at least one RMOD child).

**Current inference results** (27 classes have ≥1 inferred required
child; regenerate by re-running `build_class_catalog.py` if `scp/`
changes): `RMOD→ANTL`, `LNCEL→SIB`, `LCELL→CHANNELGROUP`, `MNL→MNLENT`,
`MNLENT→{SECADM,SYNC}`, `APEQM→{CABINET,RMOD}`, `CABINET→SMOD`,
`AMGR→LUAC`, `PMRNL→PMCCP`, `TNL→IPNO`, `ETHSVC→{ETHIF,ETHLK}`,
`LNCEL_FDD→APUCCH_FDD`, `RMOD_R→ANTL_R`, `FTM→{AMGR,CERTH,ETHLK,IPNO,
IPSECC,L2SWI,PMTNL,SECPRM,SYNC,TAC,TOPB,UNIT}` (11 required children —
the largest fan-out), `TOPB→{TOPF,TOPP}`, `IPAPP→IPSECC`,
`LCELNR→CHANNELGROUP`, `NRBTS→{NRCELL,NRCELLGRP,NRCUUP,NRDRB,
NRDRB_MAC,NRDRB_PDCP,NRDRB_RLC_AM,NRDU,NRPMRNL,NRSCTP,TRACKINGAREA}` (10),
`PDCCH→PDCCH_CONFIG_COMMON`, `APEQM_R→CABINET_R`, `CABINET_R→SMOD_R`,
`ALD→RETU`, `ALD_R→RETU_R`, `NRSYSINFO_PROFILE→NRIAFIM`, `HW→INVUNIT`.
`MRBTS` and `LNBTS` notably have EMPTY inferred-required-child sets
(no single child class hit 100% presence across their corpus instances).

**The recursion** (`_cascade_required_children(current_bytes,
parent_dist_name, parent_short_class, ancestors)`):
```python
def _cascade_required_children(current_bytes, parent_dist_name, parent_short_class, ancestors):
    results = []
    if parent_short_class in ancestors:
        return current_bytes, results          # cycle guard (defensive; can't actually
                                                  # happen given distName nesting is a tree)
    ancestors = ancestors | {parent_short_class}
    for child_class in _CLASS_CATALOG.get(parent_short_class, {}).get("requiredChildClasses", []):
        try:
            current_bytes, summary = _create_one_object(current_bytes, parent_dist_name, child_class, {})
        except (XmlParseError, ParamNotFoundError, ObjectExistsError) as e:
            results.append({"shortClass": child_class, "parentDistName": parent_dist_name, "error": str(e)})
            continue
        results.append(summary)
        current_bytes, nested = _cascade_required_children(current_bytes, summary["distName"], child_class, ancestors)
        results.extend(nested)
    return current_bytes, results
```
**Real bug hit and fixed during development:** the TOP-LEVEL call site
originally pre-seeded `ancestors` with the just-created class itself
(`frozenset({payload.className})`), but the function ALSO adds
`parent_short_class` to `ancestors` on its own first line — so the
very-first cycle-guard check (`if parent_short_class in ancestors`) was
immediately true, silently short-circuiting the ENTIRE cascade on every
single call. Fixed by calling with an empty `frozenset()` at the top
level. **If cascading ever appears to silently do nothing, check this
call site first.**

Each cascaded child never creates SIBLING instances (e.g. it will not
guess "this cell needs 3 antennas") — only ONE instance of each required
child class, the minimum needed to satisfy the inference. A cascade
failure (e.g. `ObjectExistsError` if a required child happens to already
exist) does NOT abort the whole operation — it's recorded with an
`"error"` key in the response's `cascadedObjects` list and the cascade
continues past it (partial success is better than total failure over a
heuristic).

### 9.6 Required Fields tracking (file-wide)

`GET /api/files/{filename}/missing-required` walks the ENTIRE logical
tree (all "mo" nodes, any file — not just just-generated objects; this
also surfaces gaps in scp/example files if they happen to have any), and
for each object's class, checks every catalog parameter against
`_is_required_missing()` (§9.4). Returns a flat list across the whole
file. `RequiredFieldsModal.jsx` renders this as a table (object / class /
parameter / inline input / Save button, using `fieldInputForParam()`
shared from `paramFields.jsx`) plus a right-side explain panel (click a
row to see its full description/range/unit/corpus example values — built
entirely from data the endpoint already returns, no extra API call).
Saving a row calls the same `PUT /api/files/{f}/objects/param` upsert
endpoint the "+ Add Parameter" flow uses, then `onSaved()` triggers
`refetchAfterEdit()`, which updates `tree`, which (via the `useEffect`
dependency in §7.2) automatically re-fetches `missingRequired` too — no
manual "refresh the table" logic needed anywhere.

---

## 10. Docker & deployment

### 10.1 `Dockerfile` — two stages

```dockerfile
# Stage 1: build the React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build              # -> /build/dist

# Stage 2: Python runtime, serves the built frontend as static files too
FROM python:3.12-slim AS runtime
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend-build /build/dist ./frontend_dist
COPY example ./example                     # baked in, NOT a volume mount
ENV SCP_DIR=/data/scp \
    EXAMPLE_DIR=/app/example \
    FRONTEND_DIST=/app/frontend_dist \
    PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
One container, one process, one port (8000 internally). No supervisor,
no nginx — uvicorn serves both the API and the static frontend files
directly.

### 10.2 `docker-compose.yml`

```yaml
services:
  nokia-xml-explorer:
    build: { context: ., dockerfile: Dockerfile }
    image: nokia-xml-explorer:latest
    ports: ["${PORT:-8080}:8000"]
    volumes:
      - ${SCP_HOST_DIR:-./scp}:/data/scp:ro
      - ${UPLOADS_HOST_DIR:-./uploads}:/data/uploads
      - ${SNAPSHOTS_HOST_DIR:-./snapshots}:/data/snapshots
    environment:
      - SCP_DIR=/data/scp
      - UPLOAD_DIR=/data/uploads
      - SNAPSHOT_DIR=/data/snapshots
      - INCLUDE_EXAMPLES=${INCLUDE_EXAMPLES:-true}
      - MAX_UPLOAD_MB=${MAX_UPLOAD_MB:-25}
      - MAX_SNAPSHOTS_PER_FILE=${MAX_SNAPSHOTS_PER_FILE:-50}
      - CORS_ORIGINS=${CORS_ORIGINS:-*}
    restart: unless-stopped
```
`docker-compose` auto-loads a `.env` file in the same directory and
substitutes `${VAR:-default}` — this is compose's OWN built-in behavior,
no extra plumbing was needed for `.env` support beyond referencing the
variables this way and writing `.env.example` to document them.

### 10.3 Full `.env` variable reference

(documented in `.env.example`, none required — every one has a working
default, so `docker compose up --build` with zero configuration works)

| Variable | Default | Effect |
|---|---|---|
| `PORT` | `8080` | Host port |
| `INCLUDE_EXAMPLES` | `true` | Show `example/`'s 9 bundled files |
| `SCP_HOST_DIR` | `./scp` | Host path bind-mounted read-only to `/data/scp` |
| `UPLOADS_HOST_DIR` | `./uploads` | Host path for uploads (writable) |
| `SNAPSHOTS_HOST_DIR` | `./snapshots` | Host path for edit-history snapshots (writable) |
| `MAX_UPLOAD_MB` | `25` | Per-file upload size limit |
| `MAX_SNAPSHOTS_PER_FILE` | `50` | Oldest snapshots pruned beyond this count |
| `CORS_ORIGINS` | `*` | Comma-separated; only matters if exposed beyond localhost |

### 10.4 The `example/` folder

9 files, curated by the project owner (NOT auto-selected by any script),
copied from their real `scp/` corpus, deliberately chosen as acceptable
to publish (see §11 for the full back-and-forth on this decision — this
is a DIFFERENT, smaller, and deliberately-reviewed set from the 78 files
in the private `scp/` folder). Baked into the Docker image via `COPY
example ./example` (not a bind-mounted volume like `scp/`), so it's
present even with a bare `docker run` of the built image, no
docker-compose or host directory required.

---

## 11. Data privacy / what is and isn't in the repo

This section exists because getting this wrong (in either direction) was
treated as a serious concern during development, with explicit user
back-and-forth — read this before adding any new "bundle X for
convenience" feature.

### 11.1 What's excluded from git, and why

- **`ref/`** (~4.4GB) — Nokia's own parameter dictionaries, MO class
  trees, and legacy XML-generator spreadsheets. Customer/partner
  confidential documentation. Excluded from BOTH the git repo
  (`.gitignore`) and the Docker build context/image (`.dockerignore`).
  Only needed to RE-RUN the extraction pipeline (§8.3); never needed to
  run the shipped app.
- **`scp/`** — the project owner's own real Nokia site commissioning
  files (78 files, filenames like `BackupCommissioning_DHI-B66-...`,
  clearly real site/customer identifiers). Never published.
- **`research/`** — intermediate AI-research pipeline data, derived from
  `ref/`, excluded alongside it.
- **`uploads/`, `snapshots/`** — pure runtime-generated data.
- **`.claude/`** — tool config, not product.
- **`.env`** — gitignored by convention (nothing in it is currently a
  secret, but this keeps local overrides from leaking into commits).

### 11.2 What's INCLUDED despite being derived from confidential material — a deliberate, discussed decision

**`backend/app/data/classes.json`, `parameters.json`, `class_catalog.json`
ARE committed to git and ARE published on the public repo**, despite
containing ~2,800 parameter descriptions extracted essentially verbatim
from Nokia's confidential SBTS18A/LTE18 dictionaries (full descriptions,
valid ranges, defaults — not just parameter names).

**This was flagged explicitly before the first push**, with three options
presented: exclude entirely (app runs with an empty KB), strip the copied
text but keep structural data (param names/types/hierarchy/corpus
examples only), or include as-is. The user's FIRST answer was "exclude
entirely." After a clarifying round trip (the user asked whether
excluding it would break their own local copy — **it would not**: gitignore
only controls what's pushed to GitHub; the files stay on local disk and
Docker still copies them into a locally-built image regardless of git
state, since `.dockerignore` doesn't exclude that path), the user
**changed the decision to "include as-is"** with full understanding that
this publishes Nokia's proprietary documentation content at scale on a
public repo. This is a conscious, informed, and overridable-by-you-later
choice, not an oversight — if you're asked to "harden" this project for
a stricter distribution context, this is the first thing to revisit, and
the mechanism to revert it is simple: add `backend/app/data/*.json` back
to `.gitignore` (the app already degrades gracefully to an empty KB per
§6.1 — no code changes needed to make that reversible).

The user separately asked to keep any written explanation of this
reasoning OUT of the shipped `.gitignore`/README (no inline legal-sounding
commentary) — so the `.gitignore` itself is bare patterns with zero
comments, and the README's note on this is a single plain sentence. This
document (`PROJECT_STATE.md`) is the one place the full reasoning is
written down, since it's an internal engineering handoff doc, not
user/public-facing.

### 11.3 The `example/` vs `scp/` distinction — do not conflate these

When asked to "bake in example SCP files," the FIRST instinct (bundling
some/all of `scp/`) would have been wrong — 76 of 78 `scp/` files are the
owner's real site data; only 2 (prefixed `WWW_`) were originally sourced
from public GitHub searches. This was caught and flagged before acting.
It turned out the user had ALREADY manually curated a separate `example/`
folder with 9 specific files (a different, smaller, deliberately-chosen
set — not "all of scp/", not "just the 2 WWW_ files" either) for exactly
this purpose. **Lesson for future work in this repo: `scp/`'s contents
are never presumed shareable; `example/`'s contents are the
project-owner-reviewed exception.** Never copy files from `scp/` into
`example/` (or any other path that ends up in git/the Docker image)
without this being an explicit, freshly-confirmed decision each time —
don't treat the existing `example/` selection as a precedent that
implies "more scp/ files are probably fine too."

### 11.4 Screenshots

`screenshots/main-page.png` shows real filenames from the owner's actual
`scp/` list in the sidebar, and live parameter values (feature-activation
booleans, not credentials/IPs) from one of their real files, displayed in
the main content area. This was flagged (once, briefly, non-blockingly)
before use, since the user explicitly supplied these exact two
pre-prepared screenshots for the README with clear intent to publish
them — treated as their own informed curation call, not re-litigated.

---

## 12. Known limitations / explicitly out of scope

- **List/table parameters are read-only in the generator.** `<list
  name="X"><item>...</item></list>` structures (neighbor relation
  tables, RLC/PDCP profiles, etc.) are fully parsed and displayed in both
  tree views, but "+ Add Object," "+ Add Parameter," and the delete/rename
  features cannot create, edit, or remove list rows. Only scalar `<p>`
  parameters are generator-supported.
- **No auth, no multi-user, no database.** Single local user assumed.
  `CORS_ORIGINS` is configurable but there is no login/session/permission
  system anywhere — do not expose this beyond localhost/a trusted network
  without adding your own auth layer in front of it.
- **The required-child-class inference (§9.5) is a corpus heuristic, not
  an official rule**, and is only as good as the 78-file corpus it's
  computed from. A class with few observed instances (see `childSampleSize`)
  has a correspondingly weak signal. It will never suggest sibling
  COUNTS (e.g. "this cell type usually has 3 antennas") — only which
  child CLASSES tend to exist, one instance each.
- **Frontend has never been run outside a Docker build.** No node/npm in
  the development sandbox this project was built in — every frontend
  change was verified via "does `docker compose up --build` succeed and
  does the resulting container behave correctly via curl/API tests,"
  never via an actual browser session with live interaction, and never
  via `npm run dev`. Visual/interaction bugs that wouldn't show up in a
  build-success check or an API-level test are plausible and unverified.
  (Claude-in-Chrome browser tooling was offered and declined during this
  project's development, for context on why this gap exists.)
- **No automated test suite.** Verification throughout this project's
  history was manual: local `uvicorn` smoke tests via `curl` against a
  temp upload/snapshot directory, then a full re-test against the actual
  rebuilt Docker container, then a "does every file in scp/ + example/
  still parse via /tree and /raw" regression loop (87 files as of this
  writing: 78 in `scp/` + 9 in `example/` — re-count with `ls scp/*.xml
  example/*.xml | wc -l` since this drifts as files are added) after
  every change. There is no `pytest`/CI anywhere in the repo.
- **In-memory tree cache is single-process.** `_TREE_CACHE`/`_RAW_CACHE`
  in `main.py` are plain module-level dicts — fine for the single-`uvicorn`-
  process deployment this ships with, but would need external caching
  (Redis, etc.) or cache-disabling if ever run with multiple worker
  processes.
- **Re-serializing an edited file does not preserve original
  whitespace/formatting** (see §4.3) — cosmetic only, but worth knowing
  if a user ever reports "the file looks different after I edited it."

---

## 13. Chronological build history

This project was built across a single long, continuous conversation (no
separate planning docs were kept — this section reconstructs the
narrative for onboarding purposes). Order matters for understanding WHY
certain things work the way they do; several later requirements
explicitly corrected or sharpened earlier assumptions.

1. **Initial build.** Tree-view browser for `scp/` XML files, double-click
   any element for a full explanation, "fully research every XML
   element," Docker packaging. This established `parser.py`'s distName-
   hierarchy reconstruction and the original researched knowledge base.
2. **Layout/UX round:** resizable file sidebar; side-by-side raw-XML view
   with click-to-highlight sync (the feature that became §7.3); "exactly
   as written" DOM-accurate rendering.
3. **Sync bug report:** highlighting "snapped to the correct place" only
   inconsistently — root-caused to single-`requestAnimationFrame` timing
   vs. React's actual paint commit; fixed with the double-rAF + retry
   pattern in §7.3 (this exact bug was reported and re-confirmed-fixed
   more than once).
4. **Layout options + corpus expansion:** vertical/horizontal split
   toggle; a "deep web search" pass that found and downloaded additional
   public Nokia SCP file samples, prefixed `WWW_` (only 2 of these exist
   in the final corpus — most public search results were not usable/
   relevant).
5. **Edit mode + versioning:** click-to-edit values in either pane;
   automatic pre-edit snapshots; History panel with restore (itself
   snapshotted, so undoable).
6. **First "goldmine" — the `/ref` folder deep-dive.** Discovery that
   `ref/` contained not just documentation but working Excel-macro "XML
   Generator" tools Nokia field engineers actually use (reverse-engineered
   via `olevba`/oletools VBA extraction) — established the "one sheet per
   MO class, header row of param names, one row per instance, distName
   built from leading columns" pattern that this tool's own generator
   deliberately mirrors and extends.
7. **"Can we generate XML?" feasibility question** → yes, scoped as BOTH
   add-to-existing-file AND full-new-file (user explicitly chose "both"
   over narrower options), unified into one "+ Add Object" / "+ New file"
   mechanism.
8. **Verification challenge:** user asked to confirm they could now
   generate objects of classes not in their sample files. Investigated
   honestly and found this was NOT yet true (class picker was limited to
   ~256 corpus-observed classes of ~490 official ones) — fixed via the
   Pass-2 official-only-class widening in `build_class_catalog.py`.
9. **Second "goldmine" — SRAN18A docs.** A newer, more current, unified
   AirScale parameter dictionary was found and fully extracted (this
   became the `sbts18a_*` extraction scripts and the primary/higher-
   priority official source).
10. **Mid-stream gap reports** (while extending the generator): "I need
    to edit an added element after creation" (→ `set_param_value` upsert
    + "+ Add Parameter" flow); "adding LNCEL doesn't create all its
    possible settings" (→ began the Mandatory-parameter-completeness
    work); "triple check element placement against the docs, and does
    the documentation define the minimum required file?" (→ placement
    cross-check against official MO Class Tree data, found and fixed 11
    real corpus-vs-official parent mismatches: ETHLK, IPSECC, PMTNL,
    TWAMP, EAC_R, FAN_R, INVUNIT_R, POWERGROUP_R, SFP_R, TOPF, TOPP).
11. **The Mandatory-completeness arc — THREE rounds of tightening,**
    each one a real correction to the previous round's understanding:
    a. First: surface which fields are "truly required" (Mandatory +
       no default) distinctly from merely-Mandatory, via `trulyRequired`.
    b. User: "you still have to add the mandatory values, just with
       their default" → built `resolve_default_for_xml()` (§9.2) and
       auto-fill-on-creation.
    c. User: "even mandatory fields with no default must still show up
       in the file, just flagged" → changed `add_managed_object` to
       write empty-string params as visible self-closing tags instead of
       omitting them (§6.2), added the red-highlight/Required-Fields-
       table system (§9.6), and found/fixed the `trulyRequired`-vs-
       `_is_required_missing` gap (§9.4) during testing.
12. **"Show up in both XML panes"** — confirmed (and tested) that the
    above writes to the actual file bytes, so both the logical tree AND
    raw XML view see it for free, since both are derived from the same
    on-disk file — no special-casing needed, this "just worked" once the
    write-blank-placeholder behavior was in place.
13. **Cascading required objects.** User: "you DO need to create child
    objects if they're mandatory, recursively." Established (§9.1) that
    no official source defines this, proposed and got approval for the
    corpus-heuristic approach (§9.5), including catching and fixing the
    `ancestors`-pre-seeding cycle-guard bug (§9.5) during testing.
14. **Delete support** (objects/params, Mandatory-protected) — added
    same session as cascading, on the same "make the generator fully
    capable" push.
15. **"I still don't see delete anywhere"** → root-caused to the
    `.delete-btn` CSS class collision (§7.4), NOT a logic bug — a good
    example of a feature being functionally correct but invisible due to
    an unrelated styling collision. Fixed with `.node-delete-btn` rename
    + repositioning near row start.
16. **Right-click context menu + rename** requested as a position-
    independent alternative once the above visibility bug was found (the
    inline button fix alone wasn't considered sufficient robustness) —
    added `ContextMenu.jsx` and `rename_managed_object` (§6.2) in the
    same round.
17. **Required Fields side panel** (explain-on-click) added to
    `RequiredFieldsModal.jsx`.
18. **Git/GitHub publication pass (v0.01).** Full privacy audit before
    first push (§11) — this is where the `ref/`/`scp/`/`research/`
    exclusions were finalized, the `backend/app/data/*.json` inclusion
    decision was explicitly deliberated (§11.2), the README was given a
    "frontpage" intro with the two screenshots, and the `.gitignore`
    commentary was written then later stripped down to bare patterns per
    user request. Initial commit + `v0.01` tag pushed to
    `github.com/paulmataruso/nokia-xml-explorer` (public repo, pre-existed
    empty before this push).
19. **v0.02 — bundled examples + `.env` config.** "Bake in example SCP
    files" initially misread as "bundle some of `scp/`" — corrected after
    the user clarified an `example/` folder already existed with their
    own curated 9-file selection (§11.3). Added the three-way file-source
    model (upload/scp/example, §6.1), `INCLUDE_EXAMPLES` toggle, and a
    broader `.env` configuration surface (`PORT` already existed;
    added `MAX_UPLOAD_MB`, `MAX_SNAPSHOTS_PER_FILE`, `CORS_ORIGINS`,
    host-mount path overrides). Committed and pushed as `v0.02`.
20. **This document.** Requested as a ruthlessly-detailed handoff/design
    doc for a cold-start engineer or AI instance with zero prior context.

---

## 14. How to recreate this from scratch

If you had to rebuild this project from nothing, this is the order that
avoids rework (mirrors the dependency order that actually emerged above):

1. **Get source data.** You need (a) a corpus of real Nokia RAML
   commissioning XML files (the more classes/parameters they exercise,
   the richer the corpus-grounded knowledge base will be), and (b), if
   available, Nokia's official parameter dictionaries (an LTE-series and/or
   SBTS/SRAN-series parameter list + MO class tree, typically distributed
   as Excel/HTML documentation to Nokia customers/partners under NDA).
   Source (b) is optional — the app works without it, just with a
   thinner/heuristic-only knowledge base (§6.1's graceful degradation).
2. **Build `parser.py` first, in isolation, no HTTP framework yet.**
   Nail down: the distName-hierarchy reconstruction algorithm (§4.2A),
   the shared id scheme between logical/raw trees (§4.2, this is the
   single most important design decision in the whole codebase — get it
   wrong and bidirectional sync becomes a much harder fuzzy-matching
   problem), and the edit/add/delete/rename primitives (§6.2). Test these
   as pure functions against real sample files before writing a single
   line of API code.
3. **Wrap `parser.py` in a minimal FastAPI app**: file listing, `/tree`,
   `/raw`, upload, single-param edit. Get the two-pane tree view working
   end to end in the frontend before adding anything else — this is the
   foundation everything else sits on.
4. **Build the knowledge base**, in this order: corpus inventory scan →
   AI/manual research pass for what's not obvious → (if you have official
   Nokia dictionaries) extract + merge them in as the highest-confidence
   tier, being careful from day one to ground every enum/boolean/default
   value in corpus-observed text values rather than trusting documented
   numeric codes (§8.2's central lesson — designing this in from the
   start avoids a full generator rewrite later).
5. **Build the generator incrementally, expecting requirements to
   sharpen with each round** (§13, sections 7–13 are the real history of
   this): start with "add one object, fill in what the user gives you."
   Then: auto-resolve-and-fill Mandatory defaults. Then: never omit a
   Mandatory field even without a default — write it blank and flag it.
   Then: track flagged-but-unfilled fields file-wide, not just per-object.
   Then (only if you have a large-enough real corpus): infer required
   child classes from corpus presence patterns and cascade creation.
   Each of these is a natural stopping point to ship and get feedback
   before the next.
6. **Add delete/rename last** — genuinely lower-risk once create/edit is
   solid, but don't skimp on the UI discoverability problem (§7.4's
   CSS-collision lesson): verify a new interactive element is actually
   visible on a REAL, wide, deeply-nested row, not just a short test row.
7. **Docker + docs + privacy audit before ever publishing.** Do the
   privacy audit (§11) as connected in this write-up: don't just exclude
   the obviously-sensitive raw source folders, also explicitly check any
   DERIVED data file that ships with the app for reproduced confidential
   content, and get an explicit decision on it rather than assuming
   either "obviously fine" or "obviously not."

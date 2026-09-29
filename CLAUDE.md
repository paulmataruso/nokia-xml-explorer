# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-hosted, single-container web tool for browsing, editing and generating Nokia RAN commissioning XML files. These use the RAML `raml21.xsd` "SCF"/CM-data format for AirScale, Flexi Zone and SRAN LTE/NR. The backend is FastAPI (Python 3.12, stdlib `xml.etree.ElementTree` only). The frontend is React 18 + Vite with no UI or state library. There is no database, auth or router.

**`PROJECT_STATE.md` is the full design/handoff document** (~2,500 lines). It is the only record of the reasoning behind many non-obvious decisions, so read the relevant section before changing a subsystem. It is **private and gitignored**: never commit it.

## Commands

```bash
# Run the app (production-style; http://localhost:8080)
docker compose up --build
docker compose build --no-cache && docker compose up -d   # clean rebuild
docker logs <container>                                   # check backend errors

# Local backend without Docker (paths default to /data/*, so override them)
cd backend && pip install -r requirements.txt
SCP_DIR=../scp UPLOAD_DIR=../uploads SNAPSHOT_DIR=../snapshots SITE_MGMT_DIR=../sitemgmt \
  EXAMPLE_DIR=../example uvicorn app.main:app --reload --port 8000

# Frontend dev server (proxies /api to $BACKEND_URL, default http://localhost:8000)
cd frontend && npm install && npm run dev      # :5173
cd frontend && npm run build                   # -> frontend/dist
```

**There is no test suite, linter or CI.** Verification is manual:
- `curl localhost:8080/api/health`.
- Exercise the changed endpoints with `curl`.
- Regression-check that every file in `scp/` and `example/` still parses through `GET /api/files/{name}/tree` and `/raw`.

No one has ever tested the UI interactively in a browser, so frontend-only bugs (layout, React key reconciliation) won't show up in API checks.

## Knowledge-base pipeline (offline, order matters)

`backend/app/data/{classes,parameters,class_catalog}.json` are committed, pre-built output. The scripts need `ref/` and `scp/` (both gitignored, and `ref/` is proprietary). If the JSON is missing, the app degrades to an empty KB instead of crashing.

```bash
python3 scripts/extract_inventory.py            # 1. scan scp/ -> research/input/
python3 scripts/build_knowledge.py              # 2. research/output + heuristics -> data/*.json
python3 scripts/extract_official_reference.py   # 3. only if ref/ changed (LTE18 xlsx)
python3 scripts/extract_sbts18a_reference.py    # 3. only if ref/ changed (SBTS18A xls)
python3 scripts/merge_official_reference.py     # 4. official overlay; must follow step 2
python3 scripts/build_class_catalog.py          # 5. generator catalog; must follow step 4
python3 scripts/build_3gpp_class_refs.py        # 6a. re-add `threeGpp` fields after any regen
python3 scripts/build_3gpp_param_refs.py        # 6b. reads 6a's output
```

- Running step 5 alone is enough after adding files to `scp/`.
- Editing `ABBREVIATIONS` in `heuristics.py` requires steps 2 → 4 → 5, then 6.
- After any regen, diff the JSON against HEAD to confirm only the intended fields changed.
- 3GPP references must be verified real specs. When a parameter has no 3GPP basis, say so explicitly ("Nokia-proprietary"); never guess a citation.

## Architecture

**Backend (`backend/app/`)**
- `parser.py` holds pure `(bytes, ...) -> bytes|dict` XML functions with no FastAPI or KB knowledge. It raises `XmlParseError`, `ParamNotFoundError` and `ObjectExistsError`.
- `main.py` is the orchestration layer: env config, KB loading, file resolution, required-field annotation, the generator, snapshots, mtime-keyed in-memory tree caches (single-process only), and serving `frontend_dist/` as static files.
- `heuristics.py` builds fallback explanations from parameter/class names. `structural.py` is a glossary for the RAML wrapper elements. `sitemgmt.py` is the Site Management store.

**Two parallel trees with identical node ids.** This is load-bearing.
- `parse_file()` builds the *logical* tree, reconstructed from `distName` paths with synthetic `mo-placeholder` nodes for gaps. It is rendered by `TreeView.jsx`.
- `parse_file_raw()` builds the literal DOM tree, rendered by `RawXmlView.jsx`.
- Both use the same id scheme: a managed object's id is its `distName`, then `{owner}::p::{name}`, `{owner}::list::{name}` and `{list}::item::{i}`. The two panes sync by plain string equality on `focusId` in `App.jsx`. Don't change the id format in one parser without the other.

**Every mutating endpoint follows the same sequence:**
1. Read the current bytes.
2. Run the parser function.
3. Re-parse the result to validate it (HTTP 500 if invalid).
4. Snapshot the *pre-edit* bytes.
5. Write the file.
6. `_invalidate_caches()`.

Re-serialization normalizes whitespace, and that is accepted. `_serialize()` must call `ET.register_namespace("", ...)` or ElementTree emits `ns0:` prefixes.

**File sources.** `scp/` (read-only mount), `uploads/` (writable) and `example/` (baked into the image). Name lookup priority is upload → scp → example, so new names must be unique across all three (`_unique_upload_name`). Only `source == "upload"` files are editable; editing an scp or example file first creates a copy in uploads.

**Generator rules** (see PROJECT_STATE §9):
- "Mandatory" parameters with a resolvable default are auto-filled with the *real-file* value, not the documented enum code (`resolve_default_for_xml()`).
- Mandatory parameters with no default are written as empty `<p name="X"/>` placeholders and flagged `requiredMissing`, never omitted. In `add_managed_object`, a `None` value is skipped but `""` is written.
- Mandatory parameters can't be deleted.
- `requiredMissing` is computed from `requiredOnCreation == "Mandatory"` plus the value being empty, not from the catalog's `trulyRequired` flag.
- Required child classes come from a corpus heuristic (the child is present under every observed parent instance) and are created recursively.
- Only scalar `<p>` parameters are supported; `<list>`/`<item>` tables are read-only.

**Site Management** is a pure metadata layer (folders, tags, sites) stored as JSON in `sitemgmt/`. It never moves or renames real files. Metadata is keyed by `(source, filename)`, not bare filename; a collision bug came from that (§10.6).

**Frontend.** All cross-cutting state lives in `App.jsx` and is passed down as props. `src/api.js` wraps every endpoint. Use the in-app toast/confirm/prompt components; never native `alert`/`confirm`/`prompt`. `scrollToDataId` uses a double `requestAnimationFrame` plus a retry loop on purpose; if the scroll sync regresses, look there first.

## Data handling rules

- `scp/` holds the owner's real, confidential site files. **Never copy anything from `scp/` into `example/`, git, the Docker image or screenshots** without explicit, fresh confirmation.
- `ref/` and `research/` are proprietary or derived and are excluded from both git and the image.
- Committing `backend/app/data/*.json` publicly is a deliberate, already-made decision.
- Keep `.gitignore` free of comments; the user asked for bare patterns.
- The license is AGPL-3.0 (dual-licensing intent). Flag any external contribution that lacks a CLA.

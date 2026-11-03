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

There is no browser test suite either. The UI refactor was checked with throwaway headless-Chromium (Playwright) scripts that aren't kept in the repo. Frontend-only bugs (layout, React key reconciliation, keyboard focus, render performance on the ~23k-row files) won't show up in API checks, so drive the UI in a browser after UI changes.

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

- `backend/app/data/product_codes.json` (the hardware catalog for the product-code action) is separate: `python3 scripts/build_product_codes.py` builds it from `research/input/web_product_codes.json`, which was collected from public web sources and records its source URLs per code. The same script writes `docs/product_codes.md`, a readable copy with every link. At run time the names the BTS reports in the files' `*_R` objects take precedence over it.
- Running step 5 alone is enough after adding files to `scp/`.
- Editing `ABBREVIATIONS` in `heuristics.py` requires steps 2 → 4 → 5, then 6.
- After any regen, diff the JSON against HEAD to confirm only the intended fields changed.
- 3GPP references must be verified real specs. When a parameter has no 3GPP basis, say so explicitly ("Nokia-proprietary"); never guess a citation.

## Architecture

**Backend (`backend/app/`)**
- `parser.py` holds pure `(bytes, ...) -> bytes|dict` XML functions with no FastAPI or KB knowledge. It raises `XmlParseError`, `ParamNotFoundError` and `ObjectExistsError`.
- `main.py` is the orchestration layer: env config, KB loading, file resolution, required-field annotation, the generator, snapshots, mtime-keyed in-memory tree caches (single-process only), and serving `frontend_dist/` as static files.
- `heuristics.py` builds fallback explanations from parameter/class names. `structural.py` is a glossary for the RAML wrapper elements. `sitemgmt.py` is the Site Management store.
- `ca.py` is the read-only LTE carrier aggregation check behind `GET /api/files/{f}/ca` (PROJECT_STATE §9.7), and it is pure like `parser.py`. Each finding has a basis: `official` (dictionary rules, with their rule numbers), `files` (patterns learned from the corpus's working CA exports) or `general`. It was calibrated so every working CA file has no errors; `caPoolId` missing is only a warning because those files leave it unset. Re-run the corpus over `/ca` after changing a rule.
- `actions/` is the site-actions package (PROJECT_STATE §9.9), pure like `parser.py`.
  - `doc.py` is the editing engine. Every action plans through it: set/unset, create, delete, clone a subtree with DN rewriting, list rows, and simple-value lists. Each change carries a reason and a basis.
  - `links.py` holds the link rules. `site_check.py` runs them for `GET /api/files/{f}/check`. After changing a rule, run `python3 scripts/link_rules_check.py example scp` (`-v` lists the findings); the only errors it should report are two known ones: the dangling plane reference in example `UPDATED_..._DHI_NR_n78.xml`, and the repeated IPIF-1/IPADDRESSV4-1 in example `Configuration_scf_MRBTS-1_DHI_NR_n78_20260414-0827-.xml`.
  - Each action is one module with `available(ctx)`, `setup(ctx)` and `plan(ctx, inputs)`, registered in `registry.py`. They are served by `GET /api/files/{f}/actions[/{id}]` and `POST .../actions/{id}/preview|apply`.
  - Apply returns 409 if the plan adds a site-check error.
  - `finish()` adds the manual steps to every plan (`steps.py`): one step per object, parents first, created objects read back whole from the planned document, each parameter with its full name. A plan's `todo` lists what it needs but can't write; it is shown and copied with the steps. The review has a "Changes | Manual steps" switch; `setup()` returning `view: "steps"` opens on the steps (EN-DC does).
  - Evidence counts in reasons ("as on 270 of the 405 links") describe the files a template was built from, not the files loaded now; word them that way, never "in the tool".
  - Actions so far, in the bar's order (`registry.py`), by group:
    - Cells: `nr-cell`, `lte-cell`, `drx`. LTE: `ca`.
    - Features: `endc` (EN-DC, 4G or 5G side), `qos` (a QCI or 5QI with its bearer and profiles), `voice` (VoLTE or VoNR), `slice`.
    - Mobility: `carrier` (IRFIM/LNHOIF, NRFIM, NRIRFIM, NRLIM, REDRT, NRREDRT). Neighbours: `neighbour-enb` (X2 neighbour), `endc-gnb` (an EN-DC gNB on an eNB, X2), `neighbour-gnb` (Xn).
    - Core network: `core` (MME/AMF), `plmn`.
    - Transport: `ip`, `ip-interface` (VLANIF+IPIF+address, with its own routing table and policy), `static-route` (IPRT/IPRTV6), `ntp-dns`.
    - Hardware: `add-radio`, `remove-module`, `product-code`. Edit: `delete` (with dependents; also on the tree's context menu as "Delete with dependents…", which opens it with `initial: {object}`).
  - `dependents.py` decides what a delete takes with it (its docstring has the rules). `ROW_REFS` takes out list rows that only name a deleted object and drops a 5QI mapping or resource group left naming none. `OF_RADIO` drops a radio's CBRS registration (CBSD/NRCBSD) with it.
  - `qos.py`'s `_plan_nr`/`_plan_lte` write into a given `Doc`, so other actions chain them (`voice` maps 5QI 1 and 5 that way). A new NRDRB_5QI or NRDRB_QCI is never instance 1; it is numbered from 2. `qos_templates.py` is generated by `python3 scripts/build_qos_templates.py` from production gNBs; don't edit it by hand.
  - Form fields (`ActionModal`): `select`, `text`, `combo`, `checks`. `dependsOn` + `optionsByKey` chain (a field can depend on a dependent field). A field with fixed `options` and `dependsOn` takes only its default from `defaultByKey`. `showIf` is `{field, equals}` or `{field, in: [...]}`. A select or checks field with no options for the current choice is hidden and not sent. An untouched checks field sends all its options; `default: []` plus `optional` makes it none. Never use `""` as an option value: the form reads it as unanswered.
  - The link rules that guard the newer actions: `nr-bearers`, `qos-unique`, `qci-profiles`, `cable-ports`, `radio-cables`, `route-gateway`.
  - Corpus checks, one per action (each docstring says what it checks; all exit 1 on a failure and default to `example/` and `scp/`):
    - `cell_check.py` for `nr_cell.py`/`lte_cell.py`; `carrier_check.py` for `carrier.py`; `hardware_check.py` for `add_radio.py`, `remove_module.py`, `delete.py` and `dependents.py`.
    - `qos_check.py` for `qos.py` (the sweep takes about half an hour; `--round-trip` skips it); `voice_check.py` for `voice.py`; `slice_check.py` for `slice.py` and the slice rules of `dependents.py`; `plmn_check.py` for `plmn.py`.
    - `route_check.py` for `static_route.py`; `interface_check.py` for `ip_interface.py`; `ntp_check.py` for `ntp_dns.py`.
  - `neighbours.py` holds what the neighbour actions share (sources from other files, labels that tell them apart, PLMN matching, the ANR budget); `sites.py` summarises each file's sites, including the NR cell identity and the SSB NR-ARFCN from the GSCN (TS 38.104). After changing `drx.py`, run `python3 scripts/drx_check.py` (every preset on every eNB/gNB: no crash, no new site-check error, idempotent, off undoes on). After changing `core.py` or `transport.py`, run `python3 scripts/core_check.py` (every MME/AMF and every new one: no new site-check error, nothing the old core reported left behind, a repeat or duplicate address refused). After changing `ip_address.py`, run `python3 scripts/ip_check.py` (every BTS address moved within and out of its subnet: no new site-check error, no configured copy of the old address or old gateway left, a repeat refused). After changing `neighbour_enb.py` or `sites.py`, run `python3 scripts/neighbour_check.py` (a few neighbours from other files, plus one typed in, on every eNB: no new site-check error, a repeat changes nothing; then every planned LNADJ removed and typed back in, with the remaining differences listed by parameter). After changing `endc_gnb.py`, `neighbour_gnb.py` or `neighbours.py`, run `python3 scripts/gnb_neighbour_check.py` (gNBs from other files and typed in, on every eNB and gNB: no new site-check error, a repeat changes nothing, the BTS's own address refused, a learned XNLINK only turned oamControlled; then every LNADJGNB and oamControlled XNLINK removed and typed back in; about 7 minutes). After changing `endc.py`, run `python3 scripts/endc_check.py` (each kind of NR carrier and X2 choice on every eNB, and every gNB: no new site-check error, the dictionary's EN-DC rules hold, every change in the manual steps, a repeat changes nothing).
  - The frontend is `ActionBar` (Ctrl+K) and `ActionModal`, a schema-driven form; a custom UI such as the CA wizard names its own modal.
  - Actions never copy identity or site values (names, ids, IPs) from a donor file.
- `ca_wizard.py` is the CA wizard behind `GET /api/files/{f}/ca/wizard`, `POST .../ca/preview` and `POST .../ca/apply` (PROJECT_STATE §9.8), also pure. It is the `ca` action; the `/ca/*` endpoints are aliases. It plans a full relation set for one eNB, taking values from a donor: a working CA export found among all readable files at request time (main.py's `_corpus()`, mtime-cached and deduped by SHA-1). Donor values pass a release filter: they are written only where some file of the target's release sets that parameter on that class. After changing it, run `python3 scripts/ca_wizard_roundtrip.py`, which strips CA from every working export, rebuilds it with the wizard, and expects the same relations and no errors.

- `refmap.py` is the reference map behind `GET /api/files/{f}/refmap` (PROJECT_STATE §9.10), also pure, mtime-cached in main.py.
  - It returns two kinds of link. **ref** links are every value holding another object's distName: the values the site check's reference rule reads. **id** links are the ones the site check's id rules match: lcrId, nrCellList, refNrCellGroup, an LNREL's ecgi pair and an LNRELGNBCELL's nrCellId.
  - Each edge names the tree node id of the value it comes from (`at`), so the map can explain that parameter.
  - A reference to an object the file lacks is kept, with `missing` set to `absent`, `other-site` or `outside`. Runtime objects pointing at missing targets are skipped, as in the site check.

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
- `requiredMissing` is computed from `_is_mandatory()` plus the value being empty, not from the catalog's `trulyRequired` flag.
- The one exception to all three rules is a class's own instance-id parameter (`nrcellId` on `NRCELL`, `rModId` on `RMOD`; `_is_instance_id_param`). The dictionaries call it Mandatory, but the id lives in the `distName` and no file in the corpus writes it as a `<p>`. `_is_mandatory()` returns False for it, so the generator doesn't write it, it's never flagged, it can be deleted, and `GET /api/catalog/classes/{name}` leaves it out of the Add Object form. Route every Mandatory check through `_is_mandatory()`.
- Required child classes come from a corpus heuristic (the child is present under every observed parent instance) and are created recursively.
- Only scalar `<p>` parameters are supported; `<list>`/`<item>` tables are read-only.

**Parameter Browser** (`GET /api/parameters` for search, `/api/parameters/detail` for one row) is read-only.
- `_param_index()` builds it once at startup: one row per `(kind, class, name)`. Scalars and tables come from `class_catalog.json`. Names in `parameters.json` that the catalog lacks are table fields, whose table and class aren't recorded.
- `parameters.json` is keyed by name alone, so its official fields describe only the class in its `moClass`. `_doc_entry()` says when they apply to a row; when they don't, the detail panel says they were written for another class.

**Site Management** is a pure metadata layer (folders, tags, sites) stored as JSON in `sitemgmt/`. It never moves or renames real files. Metadata is keyed by `(source, filename)`, not bare filename; a collision bug came from that (§10.6).

**Frontend.** All cross-cutting state lives in `App.jsx` and is passed down as props. `src/api.js` wraps every endpoint. Use the in-app toast/confirm/prompt components and the shared `Modal` shell; never native `alert`/`confirm`/`prompt`. `scrollToDataId` uses a double `requestAnimationFrame` plus a retry loop on purpose; if the scroll sync regresses, look there first.
- **Render performance is load-bearing.** Tree and raw rows are `memo`ized with prefix-aware comparators (`sameRow` in `TreeView.jsx`, `sameRawRow` in `RawXmlView.jsx`) that rely on the id scheme above, and App passes stable callbacks (`useStableCallback`). A new prop that names one node must go in the comparator's target list. A new callback must be stable. The focus effect must hand back the *same* `expanded` Set when nothing needs opening, because a new Set re-renders every row (seconds on the big files).
- **Map view.** The workspace toolbar's Tree | Map switch (`workspaceView`, remembered per browser) swaps the tree and raw panes for the reference map. The file header and the Explanation pane stay.
  - `refMapModel.js` is pure: the graph index, the bow-tie view (what points at the centre above it, what it points at below it, folded groups, ghosts for repeats) and the layout.
  - The layout is made of fans: one trunk per parent, one bus per tier, one drop per child. Childless siblings that don't fit across the view wrap into tiers, so the map stays at 100% instead of shrinking the text.
  - `RefMap.jsx` renders it and portals its controls into the toolbar.
  - A card or link label selects through the same `focusId` / `selectedNode` as a tree row.
  - The layers are memoised so a pan re-renders only the camera. Keep it that way, and don't add full-viewport textures: a dot grid doubled the pan frame time under software rendering (RDP or Citrix jump hosts).
  - After changing either file or `refmap.py`, run `node scripts/refmap_check.mjs [base-url]`. It centres on every object of every file, opens two levels, and expects no crash and no overlapping cards.
- **Keyboard.** Both panes are WAI-ARIA trees with a roving tab stop (`tabbableId` / `rawTabbableId`, computed in App). Arrow keys move DOM focus, and the shared focus follows it.
- **Look.** `DESIGN.md` is the design system and `PRODUCT.md` the product brief; read them before UI work. Colours are CSS tokens in the theme blocks at the top of `styles.css` (Night is the default; Slate and GitHub are set via `data-theme` on `<html>`). Soft tints are derived with `color-mix`, so add colours as tokens, never as literals in components. Each pane is a rounded panel on `--bg-page`, and the gutters between panels are the resize handles.
- **Desktop only.** The owner targets desktop browsers; don't spend effort on phone or tablet layouts.

## Data handling rules

- `scp/` holds the owner's real, confidential site files. **Never copy anything from `scp/` into `example/`, git, the Docker image or screenshots** without explicit, fresh confirmation.
- `ref/` and `research/` are proprietary or derived and are excluded from both git and the image.
- Committing `backend/app/data/*.json` publicly is a deliberate, already-made decision.
- Keep `.gitignore` free of comments; the user asked for bare patterns.
- The license is AGPL-3.0 (dual-licensing intent). Flag any external contribution that lacks a CLA.

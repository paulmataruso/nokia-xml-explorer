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
  - Runs (`run.py`; owner, 2026-11-05: "allow the user to add two or more SCP files to the Add wizard, so it can make the changes to all sites at once"): an action with `legs(ctx, inputs)` also changes the other sites' files. Each leg is `{file: corpus key or None, action, inputs, what, settles?}`. Legs on one file chain on the bytes the one before left, and their plans merge per file, with the site check of the file as it was against the last leg's bytes. A leg that can't be planned is its file's problem; this file's own leg failing fails the run. `settles` names the notes a leg makes moot ("Run it on the gNB's file too"), dropped once it plans. `RUN_KEYS` (`more`, `both`, `also5g`, `enbs`) are the run's own inputs, stripped before any planner sees them. They are served by `POST .../actions/{id}/run/preview|apply`, and the modal always previews through `run/preview`. Run apply is all or nothing: 409 on any file's problem or new site-check error. Each file gets its own snapshot, and a read-only one is written to a `(copy)` upload, with its original bytes snapshotted under the copy's name. Undo restores the other files' snapshots, then this file's. The legs so far: the neighbour actions (`neighbours.run_fields`: "More neighbour eNBs/gNBs" picks added as the first is, and "Their end", the neighbour's own file getting this site), and EN-DC (`also5g`: the 4G side with the gNB its X2 goes to, matched by address and gNB id, else the nearest carrying the carrier; `enbs`: the 5G side with each picked eNB's 4G side). After changing `run.py` or any `legs()`, run `python3 scripts/run_check.py` (every neighbour action with another file's site, Their end and one more pick, and co-sited; EN-DC both sides: every file parses with no new site-check error, and the repeat changes nothing in a file that planned).
  - `finish()` adds the manual steps to every plan (`steps.py`): one step per object, parents first, created objects read back whole from the planned document, each parameter with its full name. A plan's `todo` lists what it needs but can't write; it is shown and copied with the steps. The review has a "Changes | Manual steps" switch; `setup()` returning `view: "steps"` opens on the steps (EN-DC does).
  - Evidence counts in reasons ("as on 270 of the 405 links") describe the files a template was built from, not the files loaded now; word them that way, never "in the tool".
  - Actions so far, in the bar's order (`registry.py`), by group:
    - Cells: `nr-cell`, `lte-cell`, `drx`. LTE: `ca`.
    - Features: `endc` (EN-DC, 4G or 5G side), `qos` (a QCI or 5QI with its bearer and profiles, or production's whole set in place of the gNB's), `voice` (VoLTE or VoNR), `slice`.
    - Mobility: `carrier` (IRFIM/LNHOIF, NRFIM, NRIRFIM, NRLIM, NRHOIR, REDRT, NRREDRT). Neighbours, both whatever EN-DC's state: `neighbour-enb` (on an eNB, X2; on a gNB, `gnb_enb.py`: handover, reselection and redirect to the eNB's carriers, optional LTEENB) and `neighbour-gnb` (on a gNB, Xn with NRIRFIM; on an eNB, `endc_gnb.py`: X2, relations, NRFIM and REDRT to its NR carriers). Each dispatches on the target's class; `endc_gnb.py` is no longer registered on its own (`endc.py` imports its planner).
    - `carrier._Plan` turns on the BTS switch an object needs (`SWITCH`: actSIB24 for NRFIM, actRedirect for REDRT and NRREDRT), and leaves the object out when no file of the release has the switch. A profile gets the SIB its new NRLIM (SIB5) or NRIRFIM (SIB4) goes out in, and `profile_of()` gives an NR cell with no profile production's NRSYSINFO_PROFILE-0 (where the release has the class). `BUILTIN` holds production's NRREDRT, NRLIM, NRHOIR, NRFIM and REDRT-9 (each alike across production but for the carrier, with its release); NRHOIR is named from the cells' `nrhoirDNList`. The neighbour actions turn on what production runs with the objects (the NRBTS/LNBTS switch tables in `gnb_enb.py`, `endc_gnb.py`, `neighbour_gnb.py`) and add production's NRANR-1 when it's missing; handover LTE to NR (actHOtoNR) and inter-frequency NR handover stay off, being off in every file.
    - Core network: `core` (MME/AMF), `plmn`.
    - Transport: `ip`, `ip-interface` (VLANIF+IPIF+address, with its own routing table and policy), `static-route` (IPRT/IPRTV6), `ntp-dns`.
    - Hardware: `add-radio`, `remove-module`, `product-code`. Edit: `renumber`, `tidy` (Tidy numbering), `delete` (with dependents). `renumber` and `delete` are also on the tree's context menu ("Renumber…", "Delete with dependents…"), which opens them with `initial: {object}`.
  - `Doc.renumber` moves an object and its subtree to a new number in place, rewrites every value in the file naming any of them (walking every element, so a distName the file repeats moves too), and rewrites the number lists that hold instance numbers instead (NRCELLGRP nrCellList, NRDU refNrCellGroup). An LNBTS or BTS renumber also moves the eNB id its LNRELs to own cells name (`_own_enb`), and the action refuses a number that is a neighbour eNB's id. It records a `renumber` op; `steps.py` turns each one into "create as a copy, re-point, delete the old", in sequence. The action refuses NRDRB-1 (the default bearer, found by its number), LCELL/LCELNR (their number is the cell's lcrId), number 1 for an NRDRB_5QI/NRDRB_QCI that doesn't map 5QI/QCI 1, runtime objects and repeated distNames. `site_check.new_findings` matches the findings through a plan's renumbers, so a warning the file had already isn't "new" under its new number.
  - `tidy` numbers the file as Nokia's production files are (owner, 2026-11-04: "By 5QI value, as Nokia"). The QoS chain by value: NRDRB_5QI-<5QI> (a repeat 20 + 5QI), NRDRB-<10 + 5QI>, NRDRB_MAC-<5QI>; NRDRB_QCI-<QCI> names NRDRB-<QCI>; shared profiles keep their numbers. Gaps close only in `IN_ORDER`, the classes every production file numbers from 0 or 1 without a gap (CHANNEL, CABLINK, IRFIM, LNHOIF…). Everything else keeps its numbers: production's own schemes (SNSSAI 11-16, BWP_PROFILE by bandwidth, REDRT 1/5/9, IPIF), ports and modules, the BTS-numbered LTE neighbours, cells. A production file must come out unchanged (`renumber_check.py` fails otherwise); re-measure before adding a class to `IN_ORDER`. There is no other rename: the old `PUT /objects/rename` only moved distNames and left the links dangling, so it was removed.
  - `dependents.py` decides what a delete takes with it (its docstring has the rules). `ROW_REFS` takes out list rows that only name a deleted object and drops a 5QI mapping or resource group left naming none. `OF_RADIO` drops a radio's CBRS registration (CBSD/NRCBSD) with it.
  - Add actions add everything the feature needs (owner, 2026-11-04: "if there are not the required MO in the SCP YOU MUST ADD THEM, if they are already there then you will change them. This is for all add functions"). A missing object is created (from production's values, another file, or the knowledge base's real-file defaults) and an existing one changed; never a "none is added" note or a to-do for what a file or a dictionary can tell. Only what nothing can tell is asked for, as a form field (voice's EPS fallback EARFCN on a gNB with no NRLIM and no LTE cell); a refusal names the input it needs.
    - A parameter a dictionary rule requires (a change with basis `official` and a rule) passes the release filter in releases 18 and later when the knowledge base has it as official (voice's `_Plan.known(required=True)`), with a "written as the dictionary's rules require" note. Feature switches keep the filter: a feature the release shows no evidence of isn't turned on, nor what it would need.
    - EN-DC: a class no file of the release has is added anyway with the template's values (`_Side.guessed`, with a note); a missing qciTab row comes from `qos.qci_donor` (same release first, any release after); QCI 5 is set not EN-DC; the gNB side gets its X2 planes, NSA PLMN sets and QCI 6-9 mappings. `endc_check.py` checks those rules.
  - Canned features clean out what they replace instead of adding beside it (owner, 2026-11-03: "this tool is not just to help add, its to help make the SCP file clean"), and the canned value wins over the site's own, with each old value in the change's reason or the notes:
    - `qos`: the "Replace every 5QI/QCI mapping with production's set" value. `qos_replace.replace_nr` removes the side's mappings and the bearers and profiles only they use (NRDRB-1, the default bearer, stays), then writes production's templates numbered as `tidy` numbers them. It converges rather than recreating, so a production gNB comes out unchanged and is refused. Profiles are placed on their production numbers before any fallback takes one. Values production doesn't map go unless picked under Keep.
    - `voice`: VoNR rebuilds 5QI 1 and 5 through `replace_nr(..., {"1", "5"})`; production's values win on the picked cells. The LTE QCI 1/5 rows are only added: there is no production template for them (`qos.qci_donor` when no file of the release has one). An eNB without the LNBTS_FDD/_TDD its cells need gets one (number 0, Mandatory switches at their defaults). EPS fallback adds a missing NRREDRT through `carrier._Plan` to the form's `fallbackEarfcn`, offered from the cell's NRLIM carrier (each of the 130 production cells redirects to its one NRLIM carrier), then the file's LTE cells. A VoNR cell's voNRNrDrxDN is pointed at the 5QI 1 bearer's DRX profile.
    - `drx`: NR "on" re-points every picked cell and every bearer at the four default NRDRX profiles, sets their values to production's, and removes profiles nothing names then. LTE has no production profile set.
    - `carrier`: a cell's entries for the carrier are replaced (one entry, the carrier, band and SCS given), not skipped. Their priorities stay: they are that carrier's tuning. Where no file loaded has the object to copy, `BUILTIN` has production's NRREDRT (alike on all 130 production cells but for the carrier).
    - `slice`: "Instead of" rewrites the first replaced slice in place and re-points what named the others, merging a 5QI mapped twice.
  - `qos.py`'s `_plan_nr`/`_plan_lte` write into a given `Doc`, so other actions chain them. A new NRDRB_5QI or NRDRB_QCI is numbered by its value, as production numbers them (a second mapping of 5QI 1-9 20 above it), else from 2: 1 is only for the mapping of value 1. `qos_templates.py` is generated by `python3 scripts/build_qos_templates.py` from production gNBs; don't edit it by hand.
  - Form fields (`ActionModal`): `select`, `text`, `combo`, `checks`, `picks` (a filterable multi-select for long lists; untouched it sends none, and `excludeField` leaves out the option another field has picked). `dependsOn` + `optionsByKey` chain (a field can depend on a dependent field). A field with fixed `options` and `dependsOn` takes only its default from `defaultByKey`. `showIf` is `{field, equals}` or `{field, in: [...]}`. A select or checks field with no options for the current choice is hidden and not sent. An untouched checks field sends all its options; `default: []` plus `optional` makes it none. Never use `""` as an option value: the form reads it as unanswered.
  - The link rules that guard the newer actions: `nr-bearers`, `qos-unique`, `qci-profiles`, `cable-ports`, `radio-cables`, `route-gateway`.
  - Corpus checks, one per action (each docstring says what it checks; all exit 1 on a failure and default to `example/` and `scp/`):
    - `cell_check.py` for `nr_cell.py`/`lte_cell.py`; `carrier_check.py` for `carrier.py`; `hardware_check.py` for `add_radio.py`, `remove_module.py`, `delete.py` and `dependents.py`.
    - `qos_check.py` for `qos.py` and `qos_replace.py` (the sweep, with the replace and Keep checks, takes about 20 minutes; `--round-trip` skips it); `voice_check.py` for `voice.py`; `slice_check.py` for `slice.py` (with its replace) and the slice rules of `dependents.py`; `plmn_check.py` for `plmn.py`.
    - `route_check.py` for `static_route.py`; `interface_check.py` for `ip_interface.py`; `ntp_check.py` for `ntp_dns.py`.
    - `renumber_check.py` for `renumber.py`, `tidy.py` and `Doc.renumber` (round trips keep every reference-map link and the bytes; tidy keeps every link, leaves nothing to tidy and doesn't touch a production gNB's QoS chain; about 50 minutes over example + scp).
  - `neighbours.py` holds what the neighbour actions share (sources from other files, labels that tell them apart, PLMN matching, the ANR budget). Sources come in groups: "This file" (co-sited), "On this site's subnet" (`nearby`: another file's site whose address is on the subnet of the address this site faces it with, nearest first, as two BTSs on one BBU exported separately are), then "Sites in the tool". `sites.py` summarises each file's sites, including the NR cell identity, the gNB id length (from gNbIdLength, else the one length every cell's nrCellIdentity fits) and the SSB NR-ARFCN from the GSCN (TS 38.104). After changing `drx.py`, run `python3 scripts/drx_check.py` (every preset on every eNB/gNB: no crash, no new site-check error, idempotent, off undoes on). After changing `core.py` or `transport.py`, run `python3 scripts/core_check.py` (every MME/AMF and every new one: no new site-check error, nothing the old core reported left behind, a repeat or duplicate address refused). After changing `ip_address.py`, run `python3 scripts/ip_check.py` (every BTS address moved within and out of its subnet: no new site-check error, no configured copy of the old address or old gateway left, a repeat refused). After changing `neighbour_enb.py`, `gnb_enb.py` or `sites.py`, run `python3 scripts/neighbour_check.py` (a few neighbours from other files, plus one typed in, on every eNB and gNB: no new site-check error, a repeat changes nothing, a gNB's X2 to its own address refused; then every planned LNADJ, and every NRHOIR with its NRLIM and NRREDRT, removed and typed back in, with the remaining differences listed by parameter). After changing `endc_gnb.py`, `neighbour_gnb.py` or `neighbours.py`, run `python3 scripts/gnb_neighbour_check.py` (gNBs from other files and typed in, with and without their carrier, on every eNB and gNB: no new site-check error, a repeat changes nothing, the BTS's own address refused, a learned XNLINK turned oamControlled with nothing else but the gNB's switches; then every LNADJGNB and oamControlled XNLINK removed and typed back in; about 7 minutes). After changing `carrier.py`, also run these two and `voice_check.py`: they chain its planner. After changing `endc.py`, run `python3 scripts/endc_check.py` (each kind of NR carrier and X2 choice on every eNB, and every gNB: no new site-check error, the dictionary's EN-DC rules hold, every change in the manual steps, a repeat changes nothing).
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
- Only scalar `<p>` parameters are supported; `<list>`/`<item>` tables are read-only. A list of plain values (`<list name="fiveqiValueList"><p>5</p></list>`) parses as rows that carry their value (`kind: "item"` with `value`; raw `tag: "p"`), shown on the row in both panes and not editable as a parameter.

**Parameter Browser** (`GET /api/parameters` for search, `/api/parameters/detail` for one row) is read-only.
- `_param_index()` builds it once at startup: one row per `(kind, class, name)`. Scalars and tables come from `class_catalog.json`. Names in `parameters.json` that the catalog lacks are table fields, whose table and class aren't recorded.
- `parameters.json` is keyed by name alone, so its official fields describe only the class in its `moClass`. `_doc_entry()` says when they apply to a row; when they don't, the detail panel says they were written for another class.

**Site Management** is a pure metadata layer (folders, tags, sites) stored as JSON in `sitemgmt/`. It never moves or renames real files. Metadata is keyed by `(source, filename)`, not bare filename; a collision bug came from that (§10.6).

**Frontend.** All cross-cutting state lives in `App.jsx` and is passed down as props. `src/api.js` wraps every endpoint. Use the in-app toast/confirm/prompt components and the shared `Modal` shell; never native `alert`/`confirm`/`prompt`. `scrollToDataId` uses a double `requestAnimationFrame` plus a retry loop on purpose; if the scroll sync regresses, look there first.
- **Render performance is load-bearing.** Tree and raw rows are `memo`ized with prefix-aware comparators (`sameRow` in `TreeView.jsx`, `sameRawRow` in `RawXmlView.jsx`) that rely on the id scheme above, and App passes stable callbacks (`useStableCallback`). A new prop that names one node must go in the comparator's target list. A new callback must be stable. The focus effect must hand back the *same* `expanded` Set when nothing needs opening, because a new Set re-renders every row (seconds on the big files).
- **Map view.** The workspace toolbar's Tree | Map switch (`workspaceView`, remembered per browser) swaps the tree and raw panes for the reference map. The file header and the Explanation pane stay.
  - It opens on the whole file (owner: "I would expect to see the ENTIRE TREE in the map"): `buildTree` is the containment tree from the roots, with each reference as a link card (a ghost naming the object and where it is) under the object holding it; a reference to the object's own contained child merges into that child's card. Double-click (or Enter) centres the bow-tie on an object (`buildView`: what points at it and what it sits in on the left, what it points at and contains on the right, folded groups, ghosts for repeats); "Whole file" goes back. The history holds both.
  - Left to right, with no crossing lines and no buses (owner: "show all links between all objects, with out a line crossing another line"). Every link is its own curve from the parent's port to a straight run into the child, so links of one gap share a curve shape and cross only if parents and children come in opposite orders. `layout` packs subtrees column by column (a short one tucks under a deep one) and keeps the tree's order in every column. The whole file uses `align: "top"` (a parent level with its first child, an outline); the bow-tie centres parents on their children.
  - `refMapModel.js` is pure: the graph index, both views, `openAll` (Expand all: every node and every group page) and the layout. Containment is derived in `indexGraph` from the distNames (the nearest ancestor in the file), not sent by `/refmap`: the endpoint's links stay references only, because the site check and `dependents.py` read them. Contents come after the references; their lines are plain, unlabelled and arrowless.
  - The whole file opens all in view up to 100%, else at 40% (`OVERVIEW`) from its top left; a new centre zooms back in to read. Below 60% (`FAR`) a card shows only its name, sized to the card (`--n`) and about 12.5px on screen (`--far-fs`, in 2px steps), and link labels hide.
  - Expand all / Collapse all; the Settings toggle docks the selected object's parameters and lists on the right (`SettingsPanel`, from App's `tree` prop; a row explains through `onSelect`, a distName value goes to its object).
  - A card's settings tab (or S) opens the card down to list them in it (owner: "a button that will expand the box downwords and it will show all the element settings inside each MO"): `settingLines` gives one 20px row per parameter, list, list row and field, and the card grows by `settingsH` and `OPEN_W` wider, away from the centre (`cardBox`). `layout(items, align, grow)` gives it that much more of its column and moves the columns beyond it out, so its links still meet its head. Anything that places a card, port or tile uses `cardBox`, never `NODE_W`/`NODE_H` alone. The rows are cached per object while its tree node is the same, so opening one card doesn't re-render the others; Collapse all closes them.
  - `RefMap.jsx` renders it and portals its controls into the toolbar. A card or link label selects through the same `focusId` / `selectedNode` as a tree row.
  - The layers are memoised so a pan re-renders only the camera, and maps of 400 items or more render only the 640px tiles near the view. Keep it that way, and don't add full-viewport textures: a dot grid doubled the pan frame time under software rendering (RDP or Citrix jump hosts).
  - After changing either file or `refmap.py`, run `node scripts/refmap_check.mjs [base-url]`. Over every file it lays out the whole file (as it opens and all expanded: every object once, every link drawn) and every centre opened two levels, and expects no crash, no overlapping cards and no crossing links; then each layout again with every card open (wider, and taller by a made-up row count), where no card may reach into the next column.
- **Keyboard.** Both panes are WAI-ARIA trees with a roving tab stop (`tabbableId` / `rawTabbableId`, computed in App). Arrow keys move DOM focus, and the shared focus follows it.
- **Look.** `DESIGN.md` is the design system and `PRODUCT.md` the product brief; read them before UI work. Colours are CSS tokens in the theme blocks at the top of `styles.css` (Night is the default; Slate and GitHub are set via `data-theme` on `<html>`). Soft tints are derived with `color-mix`, so add colours as tokens, never as literals in components. Each pane is a rounded panel on `--bg-page`, and the gutters between panels are the resize handles.
- **Desktop only.** The owner targets desktop browsers; don't spend effort on phone or tablet layouts.

## Data handling rules

- `scp/` holds the owner's real, confidential site files. **Never copy anything from `scp/` into `example/`, git, the Docker image or screenshots** without explicit, fresh confirmation.
- `ref/` and `research/` are proprietary or derived and are excluded from both git and the image.
- Committing `backend/app/data/*.json` publicly is a deliberate, already-made decision.
- Keep `.gitignore` free of comments; the user asked for bare patterns.
- The license is AGPL-3.0 (dual-licensing intent). Flag any external contribution that lacks a CLA.

# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

RF/RAN engineers working at a desk on a large monitor, in long, focused sessions with Nokia commissioning files open. They know RAN concepts (cells, carriers, EARFCN, 3GPP) and Nokia's managed-object model, but not every one of Nokia's thousands of parameters by heart.

Nokia field technicians who hand-edit commissioning files are a secondary audience.

The project is published as open source (AGPL-3.0) for other engineers to self-host. Some users will meet the UI for the first time without the author on hand to explain it.

Two jobs share first priority:

1. **Understand a file.** Open an existing commissioning file, find an object or parameter, and read what it means, whether the value is valid, and whether the explanation comes from Nokia's own documentation or is researched/heuristic.
2. **Edit and complete a file.** Change values in place and confirm that every Mandatory parameter has a value before the file goes back to BTS Site Manager / NetAct.

Generating new objects/files and organizing many files (Site Management) are real but secondary jobs.

## Product Purpose

Nokia RAML (`raml21.xsd`) "SCF"/CM-data commissioning files are huge, flat lists of `<managedObject>` elements. Their real equipment → cell → feature hierarchy is only implied by `distName` paths, and their parameters are documented only in thousand-page, partner-confidential dictionaries.

This tool reconstructs the real object tree and explains every class and parameter in plain English. It shows the literal XML in sync beside the tree, lets you edit values safely with automatic snapshots, and tracks completeness file-wide. Success means an engineer can answer "what does this do, is this value right, and is this file complete?" without a text editor plus a dictionary open in another window.

## Positioning

- It is grounded in two real sources: Nokia's official parameter dictionaries (LTE18, SBTS18A) merged with statistics from a corpus of real commissioning files.
- Every explanation carries an honest confidence tier: official, high, medium, low, or auto-generated.
- Generated defaults use real-file values, not documented enum codes.
- Guessed or inferred facts (an unverified class namespace, inferred required children, an unstandardized 3GPP mapping) are labelled as guesses, never presented as fact.

## Operating Context

- Self-hosted, single Docker container, runs locally. Files never leave the machine. No auth, no multi-user, no database.
- File sources:
  - `scp/` holds the owner's real files. It is a read-only mount and its contents are confidential.
  - `uploads/` is writable. Every edit happens here.
  - `example/` holds bundled samples.
- Read-only sources are edited by first creating an editable copy in uploads.
- Typical session: pick a file, then browse or search the reconstructed tree. Click a row to read its explanation, cross-check the raw XML, edit values, and fill in Required Fields.
- Files can hold hundreds to thousands of objects and tens of thousands of parameters, and run up to about 1 MB of XML.

## Capabilities and Constraints

- The logical tree (from `distName`) and the raw DOM tree share one id scheme and sync by focus. This coupling is load-bearing.
- Editing:
  - Only scalar `<p>` parameters can be edited or generated; `<list>`/`<item>` tables are read-only.
  - Mandatory parameters can be edited but not deleted.
  - Every mutation is validated by re-parsing and snapshotted first, and can be undone from History.
- Parameters with a known closed set of values (booleans, enums) edit through a dropdown.
- Every prompt is an in-app toast, confirm or prompt dialog. Never native `alert`/`confirm`/`prompt`.
- Site Management is a pure metadata layer of folders, tags and sites. It never moves or renames real files.
- Frontend: React 18 + Vite, with no UI library, state library or router. Desktop only: built for a desktop browser window, not for phones or tablets (owner decision, 2026-10-23).
- Terminology to keep: managed object (MO), class, distName, parameter, list/table, item/row, Mandatory, Required Fields, Official Nokia documentation, SRAN / Legacy / Mixed, scp / uploads / example.

## Brand Commitments

- The tool is independent and not affiliated with Nokia. Product names (AirScale, Flexi Zone, SRAN) describe compatibility only.
- The UI uses no Nokia logos, brand colours or anything that could read as an official Nokia product.
- The name in use is "Nokia AirScale / Flexi Zone XML Explorer".
- License: AGPL-3.0.

## Evidence on Hand

- `README.md`: the full feature list and the knowledge-base method.
- Coverage: 2,800 of 5,656 parameters and 220 of 297 classes upgraded to official Nokia text.
- `example/` holds 72 bundled sample files that can be shown publicly.
- `screenshots/main-page.png` and `screenshots/xml-edit.png` are owner-curated README screenshots of an older (v0.05) UI.
- There are no testimonials, user counts, customers or benchmarks. Don't fabricate any.
- Never put anything from `scp/` into screenshots, examples or git without fresh confirmation.

## Product Principles

1. **Honesty over polish.** Always show where an explanation or value came from and how sure it is. A labelled guess beats a confident fiction.
2. **The file is the source of truth.** Show it exactly as written (raw XML) next to the reconstruction, and never alter a read-only source.
3. **Safe to touch.** Every edit is validated, snapshotted and undoable, so engineers can edit without fear.
4. **Completeness at a glance.** "Is this file done?" should be answerable without hunting.
5. **Explain to the newcomer, stay out of the expert's way.** Public users need the UI to explain itself, while daily users need density and speed.

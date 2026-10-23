---
version: 1
slug: "frontend-src-app-jsx"
primary_target: "frontend/src/App.jsx"
related_targets: ["frontend/src/styles.css"]
---

# Surface brief: Explorer workspace (App shell + panes + modals)

Scope: the single-page explorer app. Visitor mode: Operate. Audience: RAN engineers at a desk (large monitor, long sessions) plus public first-timers. Jobs: understand a file; edit and complete a file. Constraints: dark only; React 18 + Vite, plain CSS on tokens, no UI/icon library, no runtime font CDN (offline tool); Site Management and Required Fields stay modals; raw XML stacked by default; Official stays a row tint; tree/raw id sync untouched.

## Direction contract

THESIS: Every object's place in the file is a colour-coded address, as a fiber's position in its tube is. Refuses the category default of a blue-black IDE skin with one accent doing every job.

OWN-WORLD: (Revised 2026-10-23 at the user's request: the original warm black-jacket ground was rejected as too drab.) Three switchable dark themes on one token vocabulary, picked in the app bar: Night (default, indigo, neon-pastel), Slate (lifted cool slate with vivid accents) and GitHub (near the original look, punchier). Roles hold in every theme: signal = focus, selection, actions only; official = provenance row tint, always quieter than focus; red = required gap / error; values and raw XML syntax in bright code-editor colours. Fiber-code depth hues (blue, orange, green, brown, slate, white, violet, rose) appear only as depth guides and the Trace route. One optical text size; drawn SVG icons, one stroke.

STORY: The engineer sees which file they are in, whether it is a copy, and how complete it is before touching anything; clicks a row and sees where it lives, what it means, how sure the source is; edits with every change confirmed and undoable; downloads the finished file.

FIRST VIEWPORT: Slim app bar (product name, Site Management). Left: file sidebar with filter + version filter together, sources as sections. Centre: file header (source badge, full filename, Trace address, completeness, History, Download, Edit or Edit-a-copy), view toolbar, tree (~55%) over raw XML (~45%). Right: Explanation panel. Primary action is the file header's Edit / Download pair.

FORM: Fiber Code, position 4 of 7 on the ordered grounded list (3GPP spec, commissioning form, spectrum chart, fiber code, drive-test legend, site drawings, antenna datasheet). Signature move: Trace, selecting a row lights its lineage guides root to row in code hues, mirrored as a colour-banded distName address in the file header. Raises: fixed value column (split-flap board); edited values stay marked (gate board); action hue only where something can be done (consumer app); one size does the work (acetate manual); single ink, spot hue on structure only (event catalog). seed:13c46d76d84de743

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

---
name: Nokia AirScale / Flexi Zone XML Explorer
description: Fiber Code, a dark, colourful workspace in three themes where every object's place in a commissioning file reads as a colour-coded address.
colors:
  # Night, the default theme. Slate and GitHub override the same keys
  # (see the Colors section and the theme blocks in styles.css).
  bg-page: "#13142a"
  bg-0: "#1b1d36"
  bg-1: "#202342"
  bg-2: "#2a2e55"
  bg-3: "#353a68"
  line: "#2e335c"
  line-2: "#464d85"
  line-input: "#7880bd"
  veil: "color-mix(in srgb, #e8ebff 6%, transparent)"
  scrim: "rgb(0 0 0 / 0.55)"
  ink: "#e8ebff"
  ink-2: "#c8d0f5"
  ink-3: "#aeb6e2"
  ink-4: "#6c75a8"
  signal: "#ffc777"
  signal-hover: "color-mix(in srgb, #ffc777 82%, white)"
  signal-ink: "#1e1a10"
  signal-soft: "color-mix(in srgb, #ffc777 15%, transparent)"
  signal-line: "color-mix(in srgb, #ffc777 60%, transparent)"
  highlight: "#ffc777"
  mark: "color-mix(in srgb, #ffc777 90%, transparent)"
  mark-ink: "#15130a"
  official: "#7dcfff"
  official-soft: "color-mix(in srgb, #7dcfff 12%, transparent)"
  official-line: "color-mix(in srgb, #7dcfff 60%, transparent)"
  danger: "#ff757f"
  danger-hover: "color-mix(in srgb, #ff757f 85%, white)"
  danger-ink: "#2a0a10"
  danger-soft: "color-mix(in srgb, #ff757f 15%, transparent)"
  danger-line: "color-mix(in srgb, #ff757f 55%, transparent)"
  ok: "#c3e88d"
  value: "#c3e88d"
  syn-punct: "#8990c8"
  syn-tag: "#ff757f"
  syn-attr: "#c099ff"
  syn-val: "#4fd6be"
  syn-text: "#c3e88d"
  fc-1: "#82aaff"
  fc-2: "#ff966c"
  fc-3: "#c3e88d"
  fc-4: "#d9a87f"
  fc-5: "#a9b8e8"
  fc-6: "#f0f3ff"
  fc-7: "#c099ff"
  fc-8: "#ff79c6"
typography:
  title:
    fontFamily: '"Barlow Semi Condensed", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "normal"
    fontFeature: '"tnum" 1, "liga" 0, "calt" 0'
  body:
    fontFamily: '"Barlow Semi Condensed", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
    fontFeature: '"tnum" 1, "liga" 0, "calt" 0'
  label:
    fontFamily: '"Barlow Semi Condensed", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0.01em"
    fontFeature: '"tnum" 1, "liga" 0, "calt" 0'
  data:
    fontFamily: '"JetBrains Mono Variable", "JetBrains Mono", ui-monospace, "SFMono-Regular", Consolas, "Liberation Mono", monospace'
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
    fontFeature: '"tnum" 1, "liga" 0, "calt" 0'
  chip:
    fontFamily: '"JetBrains Mono Variable", "JetBrains Mono", ui-monospace, "SFMono-Regular", Consolas, "Liberation Mono", monospace'
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: "18px"
    letterSpacing: "0.01em"
    fontFeature: '"tnum" 1, "liga" 0, "calt" 0'
rounded:
  r-1: "4px"
  r-2: "6px"
  r-3: "10px"
  r-4: "12px"
  pill: "999px"
spacing:
  s-1: "2px"
  s-2: "4px"
  s-3: "8px"
  s-4: "12px"
  s-5: "16px"
  s-6: "24px"
  s-7: "32px"
components:
  button:
    backgroundColor: "{colors.bg-2}"
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    rounded: "{rounded.r-2}"
    padding: "0 8px"
    height: "28px"
  button-hover:
    backgroundColor: "{colors.bg-3}"
    textColor: "{colors.ink}"
  button-primary:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.signal-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.r-2}"
    padding: "0 8px"
    height: "28px"
  button-primary-hover:
    backgroundColor: "{colors.signal-hover}"
    textColor: "{colors.signal-ink}"
  button-toggle-on:
    backgroundColor: "{colors.signal-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r-2}"
    height: "28px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.r-2}"
    height: "28px"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.danger-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.r-2}"
    padding: "0 8px"
    height: "28px"
  button-danger-hover:
    backgroundColor: "{colors.danger-hover}"
    textColor: "{colors.danger-ink}"
  icon-button:
    backgroundColor: "transparent"
    textColor: "{colors.ink-3}"
    rounded: "{rounded.r-2}"
    size: "28px"
  icon-button-hover:
    backgroundColor: "{colors.bg-2}"
    textColor: "{colors.ink}"
  icon-button-pressed:
    backgroundColor: "{colors.signal-soft}"
    textColor: "{colors.signal}"
  input:
    backgroundColor: "{colors.bg-0}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.r-2}"
    padding: "0 8px"
    height: "28px"
  input-inline-edit:
    backgroundColor: "{colors.bg-2}"
    textColor: "{colors.ink}"
    typography: "{typography.data}"
    rounded: "{rounded.r-1}"
    padding: "0 5px"
    height: "20px"
  tree-row:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    typography: "{typography.data}"
    padding: "0 12px 0 8px"
    height: "22px"
  tree-row-object:
    textColor: "{colors.ink}"
  tree-row-official:
    backgroundColor: "{colors.official-soft}"
  tree-row-required-missing:
    backgroundColor: "{colors.danger-soft}"
  tree-row-selected:
    backgroundColor: "{colors.signal-soft}"
    textColor: "{colors.ink}"
  raw-row:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    typography: "{typography.data}"
    height: "20px"
  trace-segment:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    typography: "{typography.data}"
    rounded: "{rounded.r-1}"
    padding: "0 6px"
    height: "22px"
  trace-segment-current:
    backgroundColor: "{colors.bg-2}"
    textColor: "{colors.ink}"
  badge:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
  badge-official:
    backgroundColor: "{colors.official-soft}"
    textColor: "{colors.official}"
    rounded: "{rounded.pill}"
  badge-mid:
    textColor: "{colors.ink-2}"
  badge-quiet:
    textColor: "{colors.ink-3}"
  tag:
    backgroundColor: "transparent"
    textColor: "{colors.ink-3}"
    typography: "{typography.label}"
    rounded: "{rounded.r-1}"
    padding: "0 5px"
    height: "18px"
  tag-required-missing:
    textColor: "{colors.danger}"
  chip:
    backgroundColor: "transparent"
    textColor: "{colors.ink-3}"
    typography: "{typography.chip}"
    rounded: "{rounded.r-1}"
    padding: "0 5px"
    height: "20px"
  count-pill:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.signal-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0 4px"
    height: "16px"
  notice-note:
    backgroundColor: "{colors.bg-2}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.r-3}"
    padding: "8px 12px"
  notice-error:
    backgroundColor: "{colors.danger-soft}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.r-3}"
    padding: "8px 12px"
  menu:
    backgroundColor: "{colors.bg-2}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.r-3}"
    padding: "4px"
  menu-item-hover:
    backgroundColor: "{colors.bg-3}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r-2}"
    padding: "7px 8px"
  toast:
    backgroundColor: "{colors.bg-2}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.r-3}"
    padding: "8px 4px 8px 12px"
  modal:
    backgroundColor: "{colors.bg-1}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r-4}"
    width: "560px"
  file-item-selected:
    backgroundColor: "{colors.signal-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r-2}"
    padding: "6px 8px"
  app-bar:
    backgroundColor: "{colors.bg-page}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    padding: "0 8px 0 16px"
    height: "44px"
  panel:
    backgroundColor: "{colors.bg-1}"
    rounded: "{rounded.r-4}"
  workspace-panel:
    backgroundColor: "{colors.bg-0}"
    rounded: "{rounded.r-4}"
---

# Design System: Nokia AirScale / Flexi Zone XML Explorer

## Overview

**Creative North Star: "Fiber Code"**

The explorer takes its visual language from the TIA-598 fiber colour code. A cable has a black jacket, off-white lettering printed along it, and a fixed sequence of hues that tells a splicer which fibre sits where. Here the fibre is a managed object and its position is its distName. Ground and text stay neutral. Colour does three jobs: showing depth (the fiber-code sequence drawn as thin guides), showing state (three hues that each mean one thing) and reading data (values and raw XML syntax in their own bright colours, as in a code editor). Selecting a row lights its lineage as a route of code hues from the root down to that row, and the same route appears as a banded address in the file header. That move, Trace, is the system's signature.

The density suits an engineer at work. Tree, raw XML and explanation share one optical text size. Rows are 22px tall and spacing steps by 4px. Each pane is its own rounded panel floating on a darker page, with an 8px gutter between panels that doubles as the resize handle. Rank comes from weight (400 or 600) and four ink strengths rather than from size. Values line up at a fixed column like a departures board, so a run of parameters can be scanned top to bottom. Motion is nearly absent: the Trace route draws in once, a toast rises into place, and nothing else animates.

The palette is one of three dark themes, picked in the app bar and remembered per browser: **Night** (the default, indigo panels with neon-pastel accents), **Slate** (a lifted cool slate with vivid accents) and **GitHub** (close to the original blue-black look, punchier). Every theme fills the same roles, so no hue does two jobs in any of them. The tool is dark only, and it carries no Nokia logo, Nokia brand colour or anything that could read as an official Nokia product.

**Key Characteristics:**
- Three dark themes (Night, Slate, GitHub) on one token vocabulary: a page ground, four panel ground steps and four ink strengths each.
- Fiber-code hues appear only as 1–2px depth guides, 8px address swatches and the wordmark's Trace glyph.
- Three state hues with one meaning each: yellow for focus, selection and action; aqua for Official provenance; red for gaps and errors.
- Trace: the selected row's lineage drawn as a lit route and mirrored as a banded distName address.
- One optical size (13px mono data, 14px condensed UI), ranked by weight and ink.
- Rounded, hairline-edged panels on a darker page; shadows only on things that float.
- Hand-drawn 16px single-stroke SVG icons.

## Colors

Three dark themes share one set of roles. Each theme defines only its base colours (grounds, hairlines, inks, the three state hues, value and syntax colours, and the eight depth hues); every soft tint, ring, dimmed guide and hover shade is derived from those with `color-mix`, so a theme can't drift out of step with itself. The frontmatter lists **Night**, the default. A browser that already stored a theme keeps it.

| Role | Slate | Night (default) | GitHub |
|---|---|---|---|
| Page ground `bg-page` | `#191d23` | `#13142a` | `#010409` |
| Workspace ground `bg-0` | `#22272e` | `#1b1d36` | `#0d1117` |
| Chrome `bg-1` | `#2a3039` | `#202342` | `#161b22` |
| Raised `bg-2` / hover `bg-3` | `#343b46` / `#3f4754` | `#2a2e55` / `#353a68` | `#21262d` / `#2d333b` |
| Ink `ink` / `ink-2` / `ink-3` | `#f2f5f8` / `#cfd7e0` / `#b0bac7` | `#e8ebff` / `#c8d0f5` / `#aeb6e2` | `#f0f6fc` / `#d1d9e0` / `#9ea7b3` |
| Signal (focus, selection, action) `signal` | electric yellow `#ffd43b` | amber `#ffc777` | blue `#58a6ff` |
| Official provenance `official` | cyan `#3bc9ff` | sky `#7dcfff` | violet `#bc8cff` |
| Gaps and errors `danger` | `#ff8a8a` | `#ff757f` | `#ff7b72` |
| Values `value` | green `#a6f0a0` | lime `#c3e88d` | green `#7ee787` |
| Search match `highlight` | `#ffd43b` | `#ffc777` | `#f2cc60` |

Every pair above was checked for WCAG AA: all text 4.5:1 or better on every ground (the weakest is `ink-3` on hover at 4.77:1 in Slate), field edges and focus rings 3:1 or better.

### Primary
- **Signal** (`signal`): focus, selection and action, nothing else. It is a solid fill only for the one action that moves the current job forward (Edit a copy, Save, Create) and for count pills. At 15% (`signal-soft`) it tints the selected row, the selected file, toggles that are on and the hovered editable value. At 60% (`signal-line`) it draws the 1px ring around a selection and the border of a focused field. Keyboard focus is a 2px solid ring in full signal, and the text caret is signal. Text on a signal fill uses `signal-ink`. A filled action brightens to `signal-hover` on hover.

### Secondary
- **Official** (`official`): provenance from Official Nokia documentation. It appears as a 12% row tint (`official-soft`) in the tree and raw panes, as the "Official Nokia documentation" pill badge (official text, `official-line` border, soft fill), and as the legend swatch on the Official toggle. It is always quieter than focus.

### Tertiary
- **Gap Red** (`danger`): a Mandatory parameter with no value, an error, or a destructive action. At 15% (`danger-soft`) it tints required-missing rows and the completeness control when gaps exist, which `danger-line` borders. A solid red fill with `danger-ink` text is reserved for confirming a destructive action and for the hovered row-delete button.
- **Clear Green** (`ok`): confirmation, used only as an icon colour (the completeness check once no gaps remain, the success toast's icon).
- **Search Match** (`highlight`, drawn as `mark` with `mark-ink` text): the find highlight in both panes. It equals the signal in Slate and Night; GitHub keeps a yellow match against its blue signal.

### Data colours
- **Value** (`value`): parameter values in the tree, and text content in raw XML (`syn-text` is the same colour), so a value reads the same in both panes.
- **Raw XML syntax** (`syn-punct`, `syn-tag`, `syn-attr`, `syn-val`, `syn-text`): punctuation recedes; tag names, attribute names, attribute values (parameter names, distNames) and text content each get their theme's colour. Slate: blue tags, light-blue attributes, orange values. Night: pink tags, purple attributes, teal values. GitHub: red tags, blue attributes, pale-blue values.

### Neutral
- **Page** (`bg-page`): the darkest step, behind everything. The app bar sits directly on it, and it shows through the gutters between panels.
- **Workspace** (`bg-0`): the tree and raw XML panels, and the inside of text fields. Data sits deepest of the panels.
- **Chrome** (`bg-1`): the file sidebar, the workspace head panel (file header, notice, toolbar), the explanation panel, pane toolbars and modals.
- **Raised Sheath** (`bg-2`): buttons, menus, popovers, toasts, neutral notes, and list-item hover.
- **Raised Sheath Hover** (`bg-3`): hover on raised controls and menu items.
- **Hairline** (`line`) and **Strong Hairline** (`line-2`): 1px panel edges, dividers inside a panel, row rules and control borders. The strong one edges popovers, menus, modals, tags and table headers.
- **Field Edge** (`line-input`): text-field borders, held at 3:1 against the chrome.
- **Hover Veil** (`veil`): row hover, painted as an inset overlay so it composites over the official, red and signal tints instead of replacing them.
- **Modal Scrim** (`scrim`): the backdrop behind dialogs.
- **Ink** (`ink`, `ink-2`, `ink-3`, `ink-4`): four strengths. `ink` is for object names, titles and anything being read. `ink-2` is for secondary labels and parameter names. `ink-3` is for metadata, counts, placeholders, carets and resting icons. `ink-4` is for non-text marks only: separators, deep-level guides and the click-to-edit underline.

### Depth Hues (Fiber Code)
The TIA-598 sequence: **Fiber Blue** (`fc-1`), **Fiber Orange** (`fc-2`), **Fiber Green** (`fc-3`), **Fiber Brown** (`fc-4`), **Fiber Slate** (`fc-5`), **Fiber White** (`fc-6`), **Fiber Violet** (`fc-7`), **Fiber Rose** (`fc-8`), each tuned per theme. The root (depth 0) is blue, its children orange, and so on, cycling every eight. Each hue has a derived `-dim` partner (38%) for the resting 1px guide down a nested level. The full hue draws the lit 2px Trace route and fills the 8px swatch on each Trace address segment. From depth 9 the second cycle repeats the hues as a dashed line (4px on, 3px off), the fiber code's own tracer stripe, so blue at depth 9 never reads as depth 1.

### Named Rules
**The Same Roles Rule.** A theme changes colours, never meanings. Every theme defines the same base tokens, and all tints, rings and dims are derived from them. A new theme is a new block of base colours, nothing else.

**The One Meaning Rule.** Each state hue has exactly one job. The signal is never a warning, the official hue is never a link or a selection, and red is never decoration. There is no amber or caution state: a fact the user should weigh is a neutral note on Raised Sheath in full ink.

**The Quieter-Than-Focus Rule.** The official hue is a tint and a badge, never a stripe or a fill in the tree. Selection always wins: a selected row shows the soft signal tint and the signal ring, whatever tint it sits on.

## Typography

**Body Font:** Barlow Semi Condensed 400 and 600 (with system-ui, -apple-system, Segoe UI, Roboto, sans-serif), for every UI role: titles, prose and labels.
**Label/Mono Font:** JetBrains Mono Variable (with JetBrains Mono, ui-monospace, SFMono-Regular, Consolas, Liberation Mono, monospace), for file data only; UI labels use the body face.

There is no display face and no display role. Both faces are bundled with the app, not loaded from a font CDN, because the tool runs offline.

**Character:** A narrow printed grotesk, like the lettering stamped along a cable jacket, is the tool's own voice. A plain code mono carries everything that comes from the file. The UI face never sets file data, and the mono never sets prose.

### Hierarchy
- **Title** (600, 1.125rem, 1.4): the open file's name, the explanation subject, dialog titles and the empty-workspace heading. It is the only role that steps up in size.
- **Body** (400, 0.875rem, 1.55 for prose, 1.4 in chrome): explanation text, dialog copy, empty states and toasts.
- **Label** (400 or 600, 0.8125rem, 0.01em tracking): controls, pane titles, section headers, metadata, counts, badges and tags. It is set at 600 for pane titles, section headers and the labels of filled buttons.
- **Data** (400 or 600, 0.8125rem mono): tree labels, values, raw XML, distNames, the Trace address and history labels. Managed-object rows use 600 in full ink, parameter rows use 400 in `ink-2`, and empty values are italic in `ink-3`.
- **Chip** (400, 0.75rem): used only for the sidebar's per-file metadata chips (release, band, ARFCN), one step down so a file's chips stay on one line. Release and ARFCN chips are set in the mono.

### Named Rules
**The One Optical Size Rule.** 14px UI text and 13px mono data share an x-height, and that pair is the system's single size. Rank within it comes from weight (400 or 600) and ink strength. Only titles step up and only the sidebar chips step down. Add no new sizes.

**The As-Written Rule.** Ligatures and contextual alternates are off everywhere (`font-variant-ligatures: none`), so `>-13` or `!=` never fuse in the mono. Numerals are tabular everywhere (`font-variant-numeric: tabular-nums`), so counts, sizes and ARFCNs line up digit for digit.

**The Syntax Colour Rule.** Raw XML is highlighted like a code editor: punctuation in `syn-punct`, tag names in `syn-tag`, attribute names in `syn-attr`, attribute values in `syn-val` and text content in `syn-text`. Search matches are found on the whole line and split back along token edges, so a query like `name="pMax"` marks across tokens.

## Layout

The shell is a 44px app bar, sitting on the page ground, over three columns of floating panels: the file sidebar, the workspace and the explanation pane. An 8px `gutter` runs between and around the panels. Side panes start at 280px and 380px on windows at least 1600px wide, and at 248px and 320px below that. They resize by dragging the gutter itself: it is transparent at rest, shows a 3px by 40px rounded grip in `line-2` on hover, and the grip turns yellow while dragging. A collapsed side pane becomes a 32px rounded rail with a vertical label. Minimum widths are 200px for the sidebar, 280px for the explanation pane, and 260px for the raw pane when it sits side by side.

The workspace stacks a head panel (file header, any generator notice, the view toolbar) above a split of the tree panel over the raw XML panel (55% to 45% by default), with gutters between them. The header has two rows: identity and actions, then the Trace address with object and parameter counts. The split can turn side by side, and its fraction persists. Pane headers and the raw toolbar are 40px tall, controls are 28px, tree rows are at least 22px and raw rows 20px, and each depth indents 16px.

Spacing runs on a 4px base (`s-1` to `s-7`). Workspace, explanation and dialog gutters are 16px, sidebar gutters 12px, toolbar padding 8px by 16px, and paired controls sit 2px apart. Dialogs come in five widths: 460px (confirm), 560px (default), 800px (add object), 1120px (Required Fields) and 1180px at 82vh (Site Management). Prose is held to about 560–640px in empty and status states.

The tool targets desktop windows only. As a fallback, below 900px the page becomes one scrolling column. Files come first (up to 45vh), then the workspace at 88vh (at least 480px), then the explanation at full width. Rails and side-pane grips disappear, the panels keep their 8px gaps, and the tree/raw split always stacks.

### Named Rules
**The Departures Board Rule.** Tree values align in one column. Its width is measured per file from the widest label (with its indent and row furniture), clamped to 240–560px, and each row's label cell is that width minus its own indent, never under 8rem. Below 900px the column is capped at 46vw and long labels ellipsize.

**The Shed-Before-Wrap Rule.** The file header and toolbars respond to their own width through container queries, because the side panes resize independently of the window. They shed secondary text first: button labels at 880px (header) and 860px (toolbar), then the counts and the read-only note at 640px. Wrapping is the last resort; the raw toolbar wraps only below 560px. The file name and the Edit and Download actions are never dropped.

## Elevation & Depth

The system is flat and uses tonal layering. Depth between regions comes from five ground steps: the page is darkest, the workspace panels sit one step up, the chrome panels one more, raised controls a step above that, and hover lifts one more. Panels, rows and controls cast no shadows; a 1px hairline edges each panel and the page gutter separates them. A shadow means an element floats above the workspace and will go away: a menu, popover, toast or dialog. Selection and hover are drawn as inset box-shadows, so they never shift layout and they compose over row tints.

### Shadow Vocabulary
- **Pop** (`box-shadow: 0 12px 32px oklch(0 0 0 / 0.45), 0 2px 6px oklch(0 0 0 / 0.3)`): context menu, release filter, History popover and toasts.
- **Modal** (`box-shadow: 0 24px 64px oklch(0 0 0 / 0.5), 0 2px 8px oklch(0 0 0 / 0.3)`): dialogs only, over the Modal Scrim.
- **Selection ring** (`box-shadow: inset 0 0 0 1px` in `signal-line`): selected tree row, raw row, file and folder.
- **Hover veil** (`box-shadow: inset 0 0 0 999px` in `veil`): row hover in the tree and raw panes.

### Named Rules
**The Flat Panes Rule.** Panels, rows and controls never cast shadows. Only something that floats above the workspace and can be dismissed gets one, and it uses Pop or Modal, nothing in between.

## Shapes

Corners are soft and nest outward: the bigger the box, the rounder it is, and every edge is a hairline. There are four radii. 4px (`r-1`) is for tags, chips, Trace segments, the source badge, theme swatches and the inline edit field. 6px (`r-2`) is for buttons, fields, file items, menu items, theme options, and the selected or hovered row in the tree and raw panes. 10px (`r-3`) is for notices, popovers, menus, toasts, segmented frames, the theme switcher, the class pick list and the drop overlay. 12px (`r-4`) is for the panels themselves (sidebar, workspace head, tree, raw XML, explanation, collapsed rails) and for modals. Fully round (`pill`) is used only for provenance badges, the resize grip and scrollbar thumbs; 16px count pills reach the same shape with 8px corners. Micro marks use 2px: the 8px Trace swatch, the 10px Official legend swatch and search highlights. The edited-value mark is a 6px circle.

Dashed lines carry meaning and are kept for it. They mark the second fiber-code cycle, an implied tag, an unverified provenance badge, an unknown file family, the click-to-edit underline under values (dashed `ink-4`) and drop targets (1.5px dashed `signal-line`).

Only Site Management's tag chips sit off the scale, at 10px on an 18px chip, which reads as a pill. New work picks from `r-1` to `r-4` by the size of the box.

Row tints for Official and required-missing stay square, so a run of tinted rows reads as one band; only the selected, active or hovered row is rounded. Panels clip their content to their corners, except the file sidebar and the workspace head, whose Release menu and History popover have to hang outside them.

### Named Rules
**The Ruled Rows Rule.** Collections are rows separated by 1px hairlines, never a card per item. Rounded panels are for the regions of the shell, not for the items inside them. This covers the file list, Site Management's files, the Required Fields table, History and the explanation's key/value pairs. Never put a card inside a modal's own card.

## Components

### Buttons
Compact and quiet at rest, with one yellow fill per region.
- **Shape:** softly rounded (6px), 28px tall, 8px side padding, 6px between icon and label.
- **Default:** Raised Sheath with a Hairline border and `ink-2` text. On hover it moves to Raised Sheath Hover, full ink and a Strong Hairline.
- **Primary:** solid Single-Mode Yellow with Yellow-Fill Ink at 600, only for the action that moves the job forward (Edit a copy in the file header, Save, Create or Fill in dialogs).
- **Toggle (on):** soft yellow fill, `signal-line` border, full ink, icon in full yellow. Used for Raw XML, Official and Edit/Editing. A toggle shows a state and never takes the solid fill.
- **Quiet:** transparent until hover.
- **Danger:** solid Gap Red with `danger-ink` at 600, only for confirming a destructive action.
- **Icon button:** a 28px transparent square with an `ink-3` icon. On hover it takes Raised Sheath and full ink; pressed, it takes soft yellow with a yellow icon. Inside a segmented group it shrinks to 24px within a 1px hairline frame.
- **Disabled / Focus:** 45% opacity with no hover response; focus is a 2px yellow outline offset 2px (inset 2px on rows and list items).

### Inputs / Fields
- **Style:** Workspace fill, darker than the chrome around it, with a 1px Field Edge border, 6px corners and a 28px height at label size. Search fields inset a 16px search icon 8px from the left and end with a 24px clear button. Selects match text fields; checkboxes take yellow as their accent colour.
- **Focus:** the border turns `signal-line`, with no outline and no glow.
- **Inline edit:** mono at data size, 20px tall, Raised Sheath, 4px corners, with a `signal-line` border that turns full yellow on focus.
- **Error:** inline Gap Red text with the alert icon, set after the field.

### Tree Rows
The working surface: dense, aligned and quiet until something is selected.
- **Anatomy:** a 12px caret and kind icon in `ink-3`, a mono label in a cell sized to the value column, the value in full ink, then the class name in mono `ink-3`. Managed objects are 600 in full ink; placeholder objects reconstructed for gaps in a distName are `ink-3`.
- **Tints:** Official rows take `official-soft`, and required-missing rows take `danger-soft`, which beats Official. A selected or active row takes `signal-soft` with the 1px yellow ring, which beats both. Hover adds the veil on top.
- **Tags:** outlined, 18px tall, label size, `ink-3`. "Implied" tags are dashed; required-missing tags use red text, a red line and 600.
- **Row delete:** an 18px button hidden until the row is hovered, selected or focused; on hover it fills Gap Red.

### Trace (signature)
The selected row's lineage, drawn as a lit route in the tree and as a banded address in the file header.
- **Resting guides:** each nested level draws a 1px guide down its whole subtree in the dim hue of the parent it hangs from (children of the blue root hang on a blue guide), 13px in and then every 16px. Beyond depth 15 the guide falls back to a single `ink-4` line.
- **Lit route:** a 2px full-hue line runs past the earlier siblings at each level and stops at the selected row's caret (11px into the row). It never continues below the selection.
- **Motion:** each segment scales in from the top over 200ms on `cubic-bezier(0.2, 0.8, 0.2, 1)`, staggered 35ms per depth, so the route pours from root to row. It is off under `prefers-reduced-motion`.
- **Header address:** one mono segment per depth, 22px tall with 4px corners, led by an 8px square swatch in the depth hue and separated by 12px chevrons in `ink-4`. The current segment is 600 in full ink on Raised Sheath. Each segment is a button that selects that ancestor. With nothing selected, a UI-face hint in `ink-3` takes its place.

### Raw XML
- Mono at data size, with 20px rows and whitespace kept exactly as written, highlighted in the theme's syntax colours. The pane uses the same tints, selection ring and edited dot as the tree, keyed by the same ids. Closing tags are `ink-3`, not clickable and skipped by the keyboard. Like the tree it is a keyboard tree with one tab stop: arrows move and open/close, Home/End jump, Enter edits a value, Shift+F10 opens the row menu. In edit mode, values carry a dashed `ink-4` underline that turns yellow, with a soft yellow fill, on hover.

### Provenance Badges
- **Shape:** pill, 1px Strong Hairline, label size, 2px by 8px padding.
- **Tiers:** Official uses aqua text, an `official-line` border and an `official-soft` fill. Every other tier is ink only. High confidence and 3GPP-standardized use full ink; medium and "standardized, not by 3GPP" use `ink-2`; low, auto-generated and "possibly standardized" use `ink-2` with a dashed border; vendor-specific uses `ink-3`.

### Chips, Source Badge and Completeness
- **File chips:** 20px tall, 4px corners, hairline outline, `ink-3`. The release chip uses `ink-2` with a Strong Hairline, and the ARFCN group expands inline.
- **Source badge:** 4px corners and a Strong Hairline. "Your uploads" is filled with Raised Sheath in full ink; read-only sources use `ink-2` with a "· read-only" note in `ink-3`.
- **Completeness:** a 28px outlined control. With gaps it takes the soft red fill, a red line, a red icon and a 600 count; when clear, its check icon is Clear Green.

### Notices
- 8px by 12px padding at label size with a 16px leading icon. A **note** sits on Raised Sheath in full ink with an `ink-2` icon; an **error** sits on soft red in full ink; a **quiet** note sits on Raised Sheath in `ink-2` with tighter padding.

### Menus and Popovers
- Raised Sheath, Strong Hairline, 10px corners, the Pop shadow and 4px inner padding. Items have 6px corners, 7px by 8px padding and a Raised Sheath Hover on hover. Danger items use red text with a soft red hover. A context menu is headed by a mono `ink-3` label naming its target.

### Modals and Tabs
- Jacket Chrome with a Strong Hairline and the Modal shadow over the scrim. The header and footer are divided off by hairlines, with 12px by 16px padding and a Title-size heading; the footer right-aligns its actions.
- **Tabs (Required Fields):** 32px, 600, `ink-2`. The selected tab is full ink with a 2px yellow underline; counts sit in a small Raised Sheath pill.
- **Required Fields table:** a sticky `ink-3` header on chrome, hairline-ruled rows, Raised Sheath hover, and soft yellow on the selected row.

### Toasts
- Stacked bottom-right, up to 380px wide: Raised Sheath, Strong Hairline, 10px corners, the Pop shadow, body size. The icon is `ink-3`, green for success and red for errors. An optional action such as Undo is set at 600 in full ink. A toast rises 6px and fades in over 180ms; under reduced motion it appears in place.

### Navigation
- **App bar:** 44px on the page ground. On the left, the wordmark: an 18px Trace glyph (a 2px route stepping down two levels in `fc-1` then `fc-2`, ending on an `fc-3` dot for the selected row), then the name at 0.8125rem, "Nokia AirScale / Flexi Zone" at 400 in `ink-2` and "XML Explorer" at 600 in full ink, so the tool never passes for a Nokia product. The same glyph is the favicon. On the right, the theme switcher and Site Management.
- **Sidebar:** source sections with sticky 32px headers (600, `ink-2`, count right-aligned in `ink-3`). File items have 6px corners and 6px by 8px padding, take Raised Sheath on hover, and take soft yellow with the 1px yellow ring when selected. Each item's overflow button appears on hover, selection or focus. Unsupported files drop to 45% opacity. The upload drop overlay has 10px corners and a 1.5px dashed yellow border over translucent chrome.

### Site Management
- Folder rows are 36px tall, with Raised Sheath hover and soft yellow plus the ring when selected; a drag target adds a 2px solid yellow outline. File rows are hairline-ruled with 12px vertical padding, mono file names, a veil hover and a family badge (4px corners, Strong Hairline, 600; dashed when the family is unknown). Inline-editable metadata reveals a hairline box on hover. Search snippets are set in mono on Raised Sheath.

### Icons
- One authored set on a 16px grid: 1.5px stroke with round caps and joins, drawn in `currentColor` so an icon takes its control's ink, and hidden from assistive tech (the control carries the name). Trace separators use the same chevron at 12px.

### Named Rules
**The Focus Outranks Rule.** The selected or active row is the strongest state on screen. Soft yellow and the yellow ring override the Official tint, the required-missing tint and the hover veil.

**The Change Stays Lit Rule.** A value edited in this session keeps a 6px yellow dot before it, in both the tree and the raw pane, until the file is closed. Nothing changes silently.

**The One Fill Rule.** Solid yellow belongs to the single action that moves the job forward. Toggles, selections and hovers use the soft fill, never the solid one.

## Do's and Don'ts

### Do:
- **Do** add or change a theme only as a block of base colours in styles.css (`:root[data-theme="…"]`); let every tint, ring and dim derive from them.
- **Do** draw depth only with the fiber-code hues in order, blue at the root: the `-dim` hue for resting guides, the full hue for the lit route and address swatches, and dashes for the second cycle.
- **Do** mark any new "selected" state with `signal-soft` and the 1px `signal-line` ring, and keep the solid yellow fill for the one forward action.
- **Do** show Official provenance as an aqua row tint or pill badge, and let selection override it.
- **Do** set file data in the mono and the UI's own words in Barlow Semi Condensed at the one optical size, ranking with 400/600 and ink strength.
- **Do** align values to the measured value column in any new tree-like list.
- **Do** separate panes and list items with 1px hairlines and save shadows for things that float.
- **Do** adapt headers and toolbars with container queries, shedding labels before anything wraps.
- **Do** draw new icons on the 16px grid with a 1.5px round stroke in `currentColor`.
- **Do** switch off every animation under `prefers-reduced-motion`.

### Don't:
- **Don't** let one accent colour do every job; each theme keeps signal, official and danger distinct.
- **Don't** put red, yellow, aqua or black into the depth sequence, or use a depth hue for anything but a guide line or a Trace swatch.
- **Don't** introduce an amber or caution hue; a fact to weigh is a neutral note.
- **Don't** make Official a stripe, a fill, or louder than selection.
- **Don't** add type sizes beyond the five roles, or turn ligatures back on.
- **Don't** hard-code a colour in a component; reference a role token so every theme works.
- **Don't** render lists as cards, and never nest a card inside a modal.
- **Don't** add a light theme; the tool is dark only.
- **Don't** use Nokia logos, Nokia brand colours or anything that could read as an official Nokia product.
- **Don't** use emoji, unicode glyphs or an icon font as icons.
- **Don't** extend the Trace route below the selected row, or add hover transitions and decorative motion; Trace's draw-in and the toast's entry are the only animations.

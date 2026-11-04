import React, { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon.jsx";
import { usePersistentState } from "../usePersistentState.js";
import {
  GROUP_MAX,
  NODE_H,
  NODE_W,
  PAGE,
  PORT_REACH,
  buildTree,
  buildView,
  cardH,
  classOf,
  hasPort,
  inCount,
  indexGraph,
  label,
  layout,
  neighbours,
  openAll,
  outCount,
  reach,
  refEdges,
  search,
  viaText,
} from "./refMapModel.js";

/**
 * The Map view. By default the whole file, as its containment tree laid
 * out left to right: each object in the column after the one it sits in,
 * its references hanging off it as link cards naming the object they point
 * at (a click goes to that object). Centred on one object (double-click a
 * card, or Enter), the map is a bow-tie: what points at it and what it sits
 * in on the left, what it points at and contains on the right. Either way
 * every link is its own line, labelled with the parameter holding it, and
 * no line crosses another (refMapModel's layout).
 *
 * The port on a card's edge opens or closes its next level; Expand all
 * opens everything, groups too. A click selects, like a tree row: the file
 * header's Trace and the Explanation pane follow, and the Settings panel
 * lists the selected object's parameters and lists. A link's label selects
 * the parameter that holds it.
 *
 * Pan by dragging the canvas or scrolling, zoom with Ctrl+scroll or the
 * toolbar. The map's controls render into `toolbarSlot` (the workspace
 * toolbar) through a portal, so they sit where the tree's controls sit.
 * The layers are memoised, so a pan re-renders only the camera; a big map
 * renders only what is near the view, in tiles, so it re-renders only when
 * the view crosses into another tile.
 */

const ZOOM_MIN = 0.2;
const ZOOM_MAX = 1.6;
const CULL_AT = 400; // items: past this, only what is near the view is rendered
const TILE = 640; // world pixels: the near area is rounded out to these
const POUR_MAX = 300; // more new links than this appear without pouring in
const WHOLE = null; // the history's entry for the whole file
const FAR = 0.6; // zoomed out past this, a card shows only its name, large
const OVERVIEW = 0.4; // the whole file opens all in view, or at this zoom from its top left
// Zoomed out, a name about 12.5px on screen (in 2px steps: a step relays every card's text).
const farFont = (k) => (k < FAR ? `${Math.min(32, Math.round(12.5 / k / 2) * 2)}px` : undefined);
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const ownerOf = (id) => (id ? id.split("::")[0] : null);
const depthHue = (dn) => `var(--fc-${((dn.split("/").length - 1) % 8) + 1})`;
const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const pointing = (n) => `${plural(n, "object")} point${n === 1 ? "s" : ""}`; // "1 object points", "2 objects point"
// The edge counts: side, icon, which way a click moves the map, wording.
const EDGES = [
  ["left", "arrow-left", 1, 0, "to the left"],
  ["right", "arrow-right", -1, 0, "to the right"],
  ["top", "arrow-up", 0, 1, "above"],
  ["bottom", "arrow-down", 0, -1, "below"],
];
const MISSING = {
  absent: "Not in this file",
  "other-site": "On another site",
  outside: "Outside this export",
};

// What a class is, for a card's last line: its official name, else the
// knowledge base's category ("NR-Radio-Cell" -> "NR Radio Cell").
function className(kb, cls) {
  const c = kb?.classesKB?.[cls];
  return c?.officialFullName || c?.category?.replace(/-/g, " ") || null;
}

function ancestors(dn) {
  const parts = dn.split("/").slice(0, -1);
  return parts.length > 2 ? ["…", ...parts.slice(-2)] : parts;
}

function edgeKind(item, g) {
  if (item.kind === "more") return "more";
  if (item.kind === "node" || item.kind === "ghost") {
    if (g.byId.get(item.id)?.missing) return "missing";
  }
  if (item.edges.every((e) => e.kind === "contains")) return "contains";
  return item.edges.some((e) => e.kind === "ref") ? "ref" : "id";
}

// --- Layers (memoised: panning re-renders only the camera) ---------------

const Connectors = memo(function Connectors({ items, lay, g, lit, fresh, vis }) {
  const links = [];
  const lits = [];
  for (const [key, l] of lay.links) {
    if (vis && !vis.links.has(key)) continue;
    const item = items.get(key);
    const cls = `rm-link is-${edgeKind(item, g)} is-${l.side > 0 ? "right" : "left"}`;
    const pour = fresh.keys.has(key);
    links.push(
      <g
        key={key}
        className={cls + (pour ? " is-new" : "")}
        style={pour ? { "--d": `${Math.min(item.depth - fresh.base, 6) * 45}ms` } : null}
      >
        <path d={l.d} />
        <path className="rm-arrow" d={l.arrow} />
      </g>
    );
    if (lit.has(key)) {
      lits.push(
        <g key={key} className={cls + " is-lit"}>
          <path d={l.d} />
          <path className="rm-arrow" d={l.arrow} />
        </g>
      );
    }
  }
  return (
    <svg className="rm-links" width="1" height="1" aria-hidden="true">
      {links}
      {lits}
    </svg>
  );
});

const LinkLabels = memo(function LinkLabels({ items, lay, g, act, selectedAt, vis }) {
  const out = [];
  for (const [key, l] of lay.links) {
    if (vis && !vis.links.has(key)) continue;
    const item = items.get(key);
    // Containment has no parameter to name: its links go unlabelled.
    const links = refEdges(item.edges);
    if (!links.length || item.kind === "more") continue;
    const kind = edgeKind(item, g);
    const other = items.get(item.parent).id;
    const src = item.dir === "up" ? item.id : other;
    const dst = item.dir === "up" ? other : item.id;
    const group = item.kind === "group";
    const vias = [...new Set(links.map((e) => e.via))];
    const why = links.find((e) => e.why)?.why;
    const title = group
      ? `${plural(item.count, "object")} through ${vias.join(", ")}`
      : `${label(src)} → ${label(dst)} through ${vias.join(", ")}` +
        (why ? `\nLinked by id: ${why}` : "") +
        (kind === "missing" ? `\n${MISSING[g.byId.get(dst)?.missing] || "Not in this file"}` : "");
    const selected = links.some((e) => e.at === selectedAt);
    out.push(
      <button
        key={key}
        type="button"
        tabIndex={-1}
        className={`rm-via is-${kind} is-${l.side > 0 ? "right" : "left"}` + (selected ? " is-selected" : "")}
        style={{ left: l.labelX, top: l.labelY }}
        title={title}
        aria-label={
          group
            ? `Show the ${item.count} ${item.cls} objects`
            : `${vias.join(", ")}: ${label(src)} points at ${label(dst)}${kind === "id" ? ", linked by id" : ""}. Explain this parameter.`
        }
        onClick={(e) => {
          e.stopPropagation();
          act(group ? "open" : "via", key);
        }}
      >
        {viaText(links)}
      </button>
    );
  }
  return out;
});

const Card = memo(function Card({ item, x, y, node, fullName, parentLabel, where, ins, outs, inside, selected, target, tabbable, act, register }) {
  const centre = item.key === "c";
  const left = x - NODE_W / 2;
  const top = y - cardH(item) / 2;
  if (item.kind === "group") {
    return (
      <div
        ref={(el) => register(item.key, el)}
        className={"rm-node is-group" + (selected ? " is-selected" : "")}
        style={{ left, top, "--n": String(item.count).length + item.cls.length + 1 }}
        role="button"
        tabIndex={tabbable ? 0 : -1}
        data-key={item.key}
        aria-label={`${item.count} ${item.cls} objects, folded. Show them.`}
        onClick={() => act("open", item.key)}
      >
        <div className="rm-node-head">
          <span className="rm-group-count">{item.count}</span>
          <span className="rm-node-label">{item.cls}</span>
        </div>
        <div className="rm-node-sub">
          {item.held
            ? `${parentLabel} contains all ${item.count}`
            : item.dir === "up"
              ? `All ${item.count} point at ${parentLabel}`
              : `${parentLabel} points at all ${item.count}`}
        </div>
        <div className="rm-node-hint is-action">{`Show ${item.count > PAGE ? `the first ${PAGE}` : "them"}`}</div>
      </div>
    );
  }
  if (item.kind === "more") {
    const shown = item.count - item.left;
    const next = Math.min(PAGE, item.left);
    return (
      <div
        ref={(el) => register(item.key, el)}
        className={"rm-node is-tail" + (selected ? " is-selected" : "")}
        style={{ left, top, "--n": String(item.count).length + item.cls.length + 1 }}
        role="group"
        tabIndex={tabbable ? 0 : -1}
        data-key={item.key}
        aria-label={
          `${shown} of ${item.count} ${item.cls} shown.` + (item.left ? ` Enter shows ${next} more.` : "") + " Escape folds them."
        }
      >
        <div className="rm-node-head">
          <span className="rm-group-count">{item.count}</span>
          <span className="rm-node-label">{item.cls}</span>
        </div>
        <div className="rm-node-sub">{item.left ? `${shown} of ${item.count} shown` : `All ${item.count} shown`}</div>
        <div className="rm-tail-actions">
          {item.left > 0 && (
            <button type="button" tabIndex={-1} className="link-btn" onClick={() => act("open", item.key)}>
              Show {next} more
            </button>
          )}
          <button type="button" tabIndex={-1} className="link-btn" onClick={() => act("fold", item.key)}>
            Fold them
          </button>
        </div>
      </div>
    );
  }
  const missing = node?.missing;
  const name = label(item.id);
  if (item.kind === "ghost") {
    // A copy: the link card of a reference (the whole file), or a repeat
    // (the bow-tie). Two lines: what it names, and where that is.
    const sub = missing ? MISSING[missing] || "Not in this file" : where ? `In ${where} · go to it` : "Already on the map · go to it";
    return (
      <div
        ref={(el) => register(item.key, el)}
        className={
          "rm-node is-ghost" + (missing ? " is-missing" : "") + (target ? " is-target" : "") + (selected ? " is-selected" : "")
        }
        style={{ left, top, "--seg-hue": depthHue(item.id), "--n": name.length }}
        role="button"
        tabIndex={tabbable ? 0 : -1}
        data-key={item.key}
        aria-label={
          missing
            ? `${name}: ${sub}. Enter explains the parameter that names it.`
            : `${name}, ${fullName || node?.cls || ""}. ${where ? `In ${where}.` : "Already on the map."} Enter goes to it.`
        }
        onClick={() => act(missing ? "via" : "jump", item.key)}
      >
        <div className="rm-node-head">
          <span className="rm-swatch" aria-hidden="true" />
          <span className="rm-node-label">{name}</span>
          {!missing && <Icon name="arrow-right" size={12} />}
        </div>
        <div className={"rm-node-hint" + (missing ? "" : " is-action")}>{sub}</div>
      </div>
    );
  }
  const cls = "rm-node" + (centre ? " is-centre" : "") + (missing ? " is-missing" : "") + (selected ? " is-selected" : "");
  const sub = missing ? MISSING[missing] || "Not in this file" : null;
  const hint = node?.hint || fullName || node?.cls;
  return (
    <div
      ref={(el) => register(item.key, el)}
      className={cls}
      style={{ left, top, "--seg-hue": depthHue(item.id), "--n": name.length }}
      role="button"
      tabIndex={tabbable ? 0 : -1}
      data-key={item.key}
      aria-label={
        `${name}, ${fullName || node?.cls || ""}` +
        (node?.hint ? `, ${node.hint}` : "") +
        (missing
          ? `. ${sub}`
          : `. ${pointing(ins)} at it; it points at ${plural(outs, "object")}` +
            (inside ? ` and contains ${plural(inside, "object")}.` : ".")) +
        (centre ? "" : " Enter centres the map on it.")
      }
      onClick={() => act("select", item.key)}
      onDoubleClick={() => !centre && act("centre", item.key)}
    >
      <div className="rm-node-head">
        <span className="rm-swatch" aria-hidden="true" />
        <span className="rm-node-label">{name}</span>
        {!missing && (
          <span className="rm-counts" aria-hidden="true" title={`${pointing(ins)} at it · it points at ${plural(outs, "object")}`}>
            {ins} in · {outs} out
          </span>
        )}
      </div>
      <div className="rm-node-sub">
        {sub ||
          ancestors(item.id).map((a, i) => (
            <React.Fragment key={i}>
              {i > 0 && <Icon name="chevron-right" size={12} />}
              <span>{a}</span>
            </React.Fragment>
          ))}
      </div>
      <div className={"rm-node-hint" + (node?.hint ? " is-value" : "")}>{missing ? item.id : hint}</div>
    </div>
  );
});

// What a port opens, in words: "NRBTS-0 points at 1 object and contains
// 35 objects", "2 objects point at NRDRX-1; it sits in NRBTS-0".
function portText(g, id, dir, { links, held }) {
  const name = label(id);
  if (dir === "down") {
    const parts = [links && `points at ${plural(links, "object")}`, held && `contains ${plural(held, "object")}`];
    return `${name} ${parts.filter(Boolean).join(" and ")}`;
  }
  const sits = held ? `sits in ${label(g.container.get(id))}` : "";
  return links ? `${pointing(links)} at ${name}` + (held ? `; it ${sits}` : "") : `${name} ${sits}`;
}

const Ports = memo(function Ports({ items, pos, g, whole, expanded, collapsed, act, vis }) {
  const out = [];
  for (const item of items.values()) {
    if (!hasPort(item) || (vis && !vis.cards.has(item.key))) continue;
    const p = pos.get(item.key);
    const dir = item.dir === "up" ? "up" : "down";
    const r = reach(g, item.id, dir);
    if (!r.total) continue;
    const open = whole ? !collapsed.has(item.id) : expanded[dir].has(item.id);
    const what = portText(g, item.id, dir, r);
    const right = dir === "down";
    out.push(
      <button
        key={item.key}
        type="button"
        tabIndex={-1}
        className={`rm-port is-${right ? "right" : "left"}` + (open ? " is-open" : "")}
        style={{ left: right ? p.x + NODE_W / 2 - 8 : p.x - NODE_W / 2 + 8, top: p.y }}
        aria-expanded={open}
        aria-label={`${open ? "Hide" : "Show"} the next level: ${what}`}
        title={what}
        onClick={(e) => {
          e.stopPropagation();
          act("toggle", item.key);
        }}
      >
        {!right && <Icon name={open ? "chevron-right" : "chevron-left"} size={12} />}
        <span>{r.total}</span>
        {right && <Icon name={open ? "chevron-left" : "chevron-right"} size={12} />}
      </button>
    );
  }
  return out;
});

const MINI_W = 200;
const MINI_H = 120;

const MinimapCards = memo(function MinimapCards({ items, pos, s, ox, oy, selectedKey }) {
  const out = [];
  for (const item of items.values()) {
    const p = pos.get(item.key);
    const h = cardH(item);
    out.push(
      <rect
        key={item.key}
        className={item.parent == null ? "is-centre" : item.key === selectedKey ? "is-selected" : undefined}
        x={ox + (p.x - NODE_W / 2) * s}
        y={oy + (p.y - h / 2) * s}
        width={Math.max(2, NODE_W * s)}
        height={Math.max(1.5, h * s)}
        rx="1"
      />
    );
  }
  return out;
});

function Minimap({ items, pos, bounds, cam, size, onMove, selectedKey }) {
  const bw = bounds.maxX - bounds.minX + 160;
  const bh = bounds.maxY - bounds.minY + 160;
  const s = Math.min(MINI_W / bw, MINI_H / bh);
  const ox = (MINI_W - bw * s) / 2 - (bounds.minX - 80) * s;
  const oy = (MINI_H - bh * s) / 2 - (bounds.minY - 80) * s;
  const view = {
    x: ox + (-cam.x / cam.k) * s,
    y: oy + (-cam.y / cam.k) * s,
    w: (size.w / cam.k) * s,
    h: (size.h / cam.k) * s,
  };
  const dragging = useRef(false);
  const move = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    onMove(((e.clientX - r.left) - ox) / s, ((e.clientY - r.top) - oy) / s);
  };
  return (
    <svg
      className="rm-minimap"
      width={MINI_W}
      height={MINI_H}
      role="img"
      aria-label="Overview of the map; click to move there"
      onPointerDown={(e) => {
        e.stopPropagation();
        dragging.current = true;
        e.currentTarget.setPointerCapture(e.pointerId);
        move(e);
      }}
      onPointerMove={(e) => dragging.current && move(e)}
      onPointerUp={() => (dragging.current = false)}
    >
      <MinimapCards items={items} pos={pos} s={s} ox={ox} oy={oy} selectedKey={selectedKey} />
      <rect className="rm-minimap-view" x={view.x} y={view.y} width={view.w} height={view.h} rx="2" />
    </svg>
  );
}

function SearchBox({ g, kb, whole, onPick }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const results = useMemo(() => (open ? search(g, q) : []), [g, q, open]);
  useEffect(() => setActive(0), [q]);
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "/" && !/input|textarea|select/i.test(document.activeElement?.tagName || "")) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const pick = (node) => {
    onPick(node.id);
    setQ("");
    setOpen(false);
    inputRef.current?.blur();
  };
  return (
    <div className="rm-search">
      <label className="input-with-icon">
        <Icon name="search" />
        <input
          ref={inputRef}
          className="input"
          placeholder={whole ? "Find an object (press /)" : "Centre on an object (press /)"}
          value={q}
          role="combobox"
          aria-expanded={open && results.length > 0}
          aria-controls="rm-search-list"
          aria-activedescendant={open && results[active] ? `rm-opt-${active}` : undefined}
          aria-label={whole ? "Find an object on the map" : "Find an object to centre the map on"}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(results.length - 1, a + 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(0, a - 1));
            } else if (e.key === "Enter" && results[active]) {
              e.preventDefault();
              pick(results[active]);
            } else if (e.key === "Escape") {
              setQ("");
              setOpen(false);
              e.currentTarget.blur();
            }
          }}
        />
        {q && (
          <button className="icon-btn input-clear" onClick={() => setQ("")} aria-label="Clear">
            <Icon name="x" />
          </button>
        )}
      </label>
      {open && q.trim() && (
        <div className="rm-search-pop" role="listbox" id="rm-search-list">
          {results.length === 0 && <div className="rm-search-empty">No object matches "{q.trim()}".</div>}
          {results.map((n, i) => (
            <div
              key={n.id}
              id={`rm-opt-${i}`}
              role="option"
              aria-selected={i === active}
              className={"rm-search-row" + (i === active ? " is-active" : "")}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setActive(i)}
              onClick={() => pick(n)}
            >
              <span className="rm-search-label">{label(n.id)}</span>
              <span className="rm-search-meta">{n.hint || className(kb, n.cls) || n.cls}</span>
              <span className="rm-search-counts">
                {inCount(g, n.id)} in · {outCount(g, n.id)} out
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Legend({ stats, onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    const onDown = (e) => !ref.current?.parentElement.contains(e.target) && onClose();
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown);
    };
  }, [onClose]);
  return (
    <div ref={ref} className="rm-legend" role="dialog" aria-label="Map legend">
      {[
        ["ref", "Holds the other object's distName"],
        ["id", "Linked by matching ids (implied: the file names no distName)"],
        ["missing", "Names an object this file doesn't have"],
        ["contains", "Contains it: the object sits under the other in the tree"],
      ].map(([kind, text]) => (
        <div className="rm-legend-row" key={kind}>
          <svg width="40" height="14" aria-hidden="true" className={`rm-sample is-${kind}`}>
            <path d="M2 7h34" />
            {kind !== "contains" && <path d="M31 3l5 4-5 4" />}
          </svg>
          <span>{text}</span>
        </div>
      ))}
      <div className="rm-legend-row">
        <span className="rm-legend-ghost" aria-hidden="true" />
        <span>A link card: the object a link names, which sits elsewhere on the map. Click it to go there.</span>
      </div>
      <p className="rm-legend-note">
        Every arrow points right, from the object holding the value to the object it names. The whole file is its
        tree, each object right of the one it sits in, with its links beside its contents. Centred on one object,
        what points at it and what it sits in are on its left, what it points at and contains on its right. No two
        lines cross. The number on a card's edge opens or closes the next level.
      </p>
      <p className="rm-legend-note">
        Keys: arrows move, Enter centres or goes to a link card, Space opens the next level, E explains the link,
        Escape folds a group, Backspace goes back, + and − zoom, 0 fits.
      </p>
      <p className="rm-legend-note">
        This file: {plural(stats.links, "link")}, {stats.implied} by id, {stats.missing} to missing objects.
      </p>
      <button className="btn btn-quiet rm-legend-close" onClick={onClose}>
        Close
      </button>
    </div>
  );
}

// --- Settings: the selected object's own parameters and lists ------------

const empty = (v) => v == null || v === "";

function SettingRow({ id, name, value, missing, selected, depth, g, onPick, onGo }) {
  const target = !empty(value) && g.byId.has(value) && !g.byId.get(value).missing ? value : null;
  return (
    <div className={"rm-set-row" + (selected ? " is-selected" : "") + (depth ? " is-field" : "")}>
      <button type="button" className="rm-set-main" onClick={() => onPick(id)} title={`Explain ${name}`}>
        <span className="rm-set-name">{name}</span>
        <span className={"rm-set-value" + (missing ? " is-missing" : "") + (empty(value) ? " is-empty" : "")}>
          {empty(value) ? (missing ? "Required, empty" : "empty") : value}
        </span>
      </button>
      {target && (
        <button
          type="button"
          className="icon-btn rm-set-go"
          onClick={() => onGo(target)}
          aria-label={`Go to ${label(target)} on the map`}
          title={`Go to ${label(target)} on the map`}
        >
          <Icon name="arrow-right" size={12} />
        </button>
      )}
    </div>
  );
}

function SettingsPanel({ mo, g, kb, focusId, onPick, onGo, onClose }) {
  const [q, setQ] = useState("");
  const query = q.trim().toLowerCase();
  const hit = (...s) => !query || s.some((x) => !empty(x) && String(x).toLowerCase().includes(query));
  const head = (
    <div className="rm-set-head">
      <div className="rm-set-title">
        {mo ? (
          <>
            <span className="rm-swatch" style={{ "--seg-hue": depthHue(mo.id) }} aria-hidden="true" />
            <span className="rm-set-label">{label(mo.id)}</span>
          </>
        ) : (
          <span className="rm-set-label is-quiet">Settings</span>
        )}
        <button className="icon-btn" onClick={onClose} aria-label="Close the settings" title="Close">
          <Icon name="x" />
        </button>
      </div>
      {mo && <div className="rm-set-class">{className(kb, mo.class) || mo.class}</div>}
    </div>
  );
  if (!mo) {
    return (
      <aside className="rm-settings" aria-label="Settings of the selected object">
        {head}
        <p className="rm-set-note">Select an object on the map to see its parameters and lists.</p>
      </aside>
    );
  }
  const params = mo.children.filter((c) => c.kind === "param");
  const lists = mo.children.filter((c) => c.kind === "list");
  const shownParams = params.filter((p) => hit(p.label, p.value));
  const shownLists = lists
    .map((l) => {
      const all = hit(l.label);
      const rows = l.children
        .map((row) => {
          if (row.value != null) return all || hit(row.value) ? { row, fields: null } : null;
          const fields = row.children.filter((f) => all || hit(f.label, f.value));
          return fields.length ? { row, fields } : null;
        })
        .filter(Boolean);
      return all || rows.length ? { list: l, rows } : null;
    })
    .filter(Boolean);
  const row = (p, depth = 0) => (
    <SettingRow
      key={p.id}
      id={p.id}
      name={p.label}
      value={p.value}
      missing={p.requiredMissing}
      selected={focusId === p.id}
      depth={depth}
      g={g}
      onPick={onPick}
      onGo={onGo}
    />
  );
  return (
    <aside className="rm-settings" aria-label={`Settings of ${label(mo.id)}`}>
      {head}
      <div className="rm-set-filter">
        <label className="input-with-icon">
          <Icon name="filter" />
          <input
            className="input"
            placeholder="Filter names and values"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && setQ("")}
            aria-label="Filter the parameters and lists"
          />
          {q && (
            <button className="icon-btn input-clear" onClick={() => setQ("")} aria-label="Clear the filter">
              <Icon name="x" />
            </button>
          )}
        </label>
      </div>
      <div className="rm-set-body">
        <section className="rm-set-section">
          <h3 className="rm-set-section-head">
            Parameters <span className="rm-set-count">{query ? `${shownParams.length} of ${params.length}` : params.length}</span>
          </h3>
          {shownParams.map((p) => row(p))}
          {!shownParams.length && (
            <p className="rm-set-note">{params.length ? `No parameter matches "${q.trim()}".` : "None: this object sets no parameter."}</p>
          )}
        </section>
        {(shownLists.length > 0 || (!query && lists.length > 0)) && (
          <section className="rm-set-section">
            <h3 className="rm-set-section-head">
              Lists <span className="rm-set-count">{query ? `${shownLists.length} of ${lists.length}` : lists.length}</span>
            </h3>
            {shownLists.map(({ list, rows }) => (
              <div className="rm-set-list" key={list.id}>
                <button
                  type="button"
                  className={"rm-set-list-head" + (focusId === list.id ? " is-selected" : "")}
                  onClick={() => onPick(list.id)}
                  title={`Explain ${list.label}`}
                >
                  <span className="rm-set-name">{list.label}</span>
                  <span className="rm-set-count">{plural(list.rowCount ?? list.children.length, "row")}</span>
                </button>
                {rows.map(({ row: r, fields }) =>
                  fields ? (
                    <div className="rm-set-item" key={r.id}>
                      <button
                        type="button"
                        className={"rm-set-item-head" + (focusId === r.id ? " is-selected" : "")}
                        onClick={() => onPick(r.id)}
                      >
                        {r.label}
                      </button>
                      {fields.map((f) => row(f, 1))}
                    </div>
                  ) : (
                    <SettingRow
                      key={r.id}
                      id={r.id}
                      name={r.label}
                      value={r.value}
                      selected={focusId === r.id}
                      depth={1}
                      g={g}
                      onPick={onPick}
                      onGo={onGo}
                    />
                  )
                )}
              </div>
            ))}
          </section>
        )}
      </div>
    </aside>
  );
}

function indexObjects(tree) {
  const m = new Map();
  const walk = (n) => {
    if (n.kind === "mo") m.set(n.id, n);
    for (const c of n.children || []) if (c.kind === "mo" || c.kind === "mo-placeholder") walk(c);
  };
  for (const r of tree?.children || []) walk(r);
  return m;
}

export function RefMap({ data, kb, tree, focusId, onSelect, onOpenInTree, toolbarSlot }) {
  const g = useMemo(() => indexGraph(data), [data]);
  const objects = useMemo(() => indexObjects(tree), [tree]);
  const [nav, setNav] = useState({ list: [WHOLE], index: 0 });
  const entry = nav.list[nav.index];
  const root = entry !== WHOLE && g.byId.has(entry) ? entry : WHOLE;
  const whole = root === WHOLE;
  // The bow-tie's state starts afresh with each centre; the whole file's is kept.
  const [expanded, setExpanded] = useState(() => ({ up: new Set(), down: new Set() }));
  const [pages, setPages] = useState(() => new Map());
  const [collapsed, setCollapsed] = useState(() => new Set());
  const [treePages, setTreePages] = useState(() => new Map());
  const [settings, setSettings] = usePersistentState("mapSettings", false);
  const [cam, setCam] = useState({ x: 0, y: 0, k: 1 });
  const [glide, setGlide] = useState(false);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [legend, setLegend] = useState(false);
  const closeLegend = useMemo(() => () => setLegend(false), []);
  const [panning, setPanning] = useState(false);
  const [keyboard, setKeyboard] = useState(false); // focus is on the map: show its keys
  const [tick, setTick] = useState(0); // a frame was asked for
  const glideTimer = useRef(null);
  const refocus = useRef(false);
  const navRef = useRef(nav);
  navRef.current = nav;
  const [activeKey, setActiveKey] = useState(null);
  const viewportRef = useRef(null);
  const els = useRef(new Map());
  const anchor = useRef(null);
  const frame = useRef(null);
  const framed = useRef(false);
  const self = useRef(null);
  const seen = useRef(null);
  const camRef = useRef(cam);
  camRef.current = cam;
  const sizeRef = useRef(size);
  sizeRef.current = size;
  const revealTimer = useRef(null);

  const items = useMemo(
    () => (whole ? buildTree(g, collapsed, treePages) : buildView(g, root, expanded, pages)),
    [g, whole, root, collapsed, treePages, expanded, pages]
  );
  const lay = useMemo(() => layout(items, whole ? "top" : "middle"), [items, whole]);
  const layRef = useRef(lay);
  layRef.current = lay;
  const firstKey = items.keys().next().value ?? null;
  // Where each object's own card is (the first, in a bow-tie with it in both halves).
  const realKey = useMemo(() => {
    const m = new Map();
    for (const it of items.values()) if (it.kind === "node" && !m.has(it.id)) m.set(it.id, it.key);
    return m;
  }, [items]);

  // Which links are new since the last layout: they pour in, from the
  // card that opened them. Not on the first map, nor when very many open.
  const fresh = useMemo(() => {
    const keys = new Set();
    let base = Infinity;
    if (seen.current) {
      for (const [k, it] of items) {
        if (seen.current.has(k)) continue;
        keys.add(k);
        base = Math.min(base, it.depth);
      }
    }
    return keys.size > POUR_MAX ? { keys: new Set(), base: 0 } : { keys, base };
  }, [items]);
  useEffect(() => {
    seen.current = new Set(items.keys());
  }, [items]);

  // Keep the viewport's size.
  useLayoutEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  const askFrame = (f) => {
    frame.current = f;
    setTick((t) => t + 1);
  };
  const resetCentred = () => {
    setExpanded({ up: new Set(), down: new Set() });
    setPages(new Map());
  };
  const visit = (target) =>
    setNav((n) => {
      if (n.list[n.index] === target) return n;
      const list = [...n.list.slice(0, n.index + 1), target];
      return { list, index: list.length - 1 };
    });
  const keepFocus = () => (refocus.current = !!viewportRef.current?.contains(document.activeElement));

  // Open the whole file's tree down to an object: its containers, and the
  // groups it and they fold into.
  const openPathTo = (id) => {
    const chain = [];
    for (let c = g.container.get(id); c; c = g.container.get(c)) chain.push(c);
    setCollapsed((s) => (chain.some((c) => s.has(c)) ? new Set([...s].filter((x) => !chain.includes(x))) : s));
    setTreePages((m) => {
      let next = m;
      for (const x of [id, ...chain]) {
        const up = g.container.get(x);
        if (!up) continue;
        const cls = classOf(x);
        if (neighbours(g, up, "down").filter(([o]) => classOf(o) === cls).length <= GROUP_MAX) continue;
        for (const key of [`down|${up}|${cls}`, `down|${up}|${cls}|in`]) {
          if (next.get(key) === Infinity) continue;
          if (next === m) next = new Map(m);
          next.set(key, Infinity);
        }
      }
      return next;
    });
  };

  const centreOn = (id) => {
    if (!g.byId.has(id)) return;
    visit(id);
    resetCentred();
    setActiveKey("c");
    askFrame({ centre: true });
    keepFocus();
  };
  // The whole file, at an object (opened down to it) or from its start.
  const showWhole = (id) => {
    visit(WHOLE);
    if (id && g.byId.has(id) && !g.byId.get(id).missing) {
      openPathTo(id);
      askFrame({ reveal: id });
    } else askFrame({ start: true });
    keepFocus();
  };
  // Find an object, as picking it anywhere else would: go to it in the
  // whole file, centre on it in a bow-tie; and select it.
  const pick = (id) => {
    if (whole && !g.byId.get(id)?.missing) showWhole(id);
    else centreOn(id);
    self.current = id;
    onSelect(id);
  };
  const go = (step) => {
    const n = navRef.current;
    const index = clamp(n.index + step, 0, n.list.length - 1);
    if (index === n.index) return;
    setNav({ ...n, index });
    if (n.list[index] === WHOLE) {
      const o = ownerOf(focusId);
      if (o && g.byId.has(o) && !g.byId.get(o).missing) {
        openPathTo(o);
        askFrame({ reveal: o });
      } else askFrame({ start: true });
    } else {
      resetCentred();
      setActiveKey("c");
      askFrame({ centre: true });
    }
    keepFocus();
  };

  // The first map: the whole file, opened down to the selected object. After
  // an edit the map keeps its view and history, less any object that went away.
  useEffect(() => {
    const n = navRef.current;
    const list = n.list.filter((id) => id === WHOLE || g.byId.has(id));
    if (list.length !== n.list.length) setNav({ list, index: Math.max(0, list.indexOf(n.list[n.index])) });
    if (framed.current) return;
    framed.current = true;
    const owner = ownerOf(focusId);
    if (owner && g.byId.has(owner) && !g.byId.get(owner).missing) {
      openPathTo(owner);
      askFrame({ reveal: owner, first: true });
    } else askFrame({ start: true, first: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [g]);

  // A selection made outside the map (the Trace address, say) goes to it:
  // opened down to it in the whole file, re-centred on it in a bow-tie
  // that doesn't show it.
  useEffect(() => {
    const owner = ownerOf(focusId);
    const mine = owner === self.current;
    self.current = null;
    if (mine || !owner || !g.byId.has(owner)) return;
    const key = realKey.get(owner);
    if (key) {
      setActiveKey(key);
      reveal(key);
    } else if (whole) {
      openPathTo(owner);
      askFrame({ reveal: owner });
    } else centreOn(owner);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusId]);

  const glideTo = (next) => {
    if (!reducedMotion()) {
      setGlide(true);
      clearTimeout(glideTimer.current);
      glideTimer.current = setTimeout(() => setGlide(false), 280);
    }
    setCam(next);
  };
  useEffect(
    () => () => {
      clearTimeout(glideTimer.current);
      clearTimeout(revealTimer.current);
    },
    []
  );

  // After a layout: keep an opened card where it was under the pointer.
  useLayoutEffect(() => {
    if (!anchor.current) return;
    const c = camRef.current;
    const { key, sx, sy, opened, refit } = anchor.current;
    anchor.current = null;
    const p = lay.pos.get(key);
    if (!p) return;
    if (typeof refocus.current === "string") {
      const k = refocus.current;
      refocus.current = false;
      requestAnimationFrame(() => els.current.get(k)?.focus({ preventScroll: true }));
    }
    const b = lay.bounds;
    if (refit && (b.maxX - b.minX) * c.k <= size.w - 48 && (b.maxY - b.minY) * c.k <= size.h - 96) {
      // A fold left a map that fits: frame all of it.
      glideTo({ ...c, x: size.w / 2 - ((b.minX + b.maxX) / 2) * c.k, y: size.h / 2 - ((b.minY + b.maxY) / 2) * c.k });
      return;
    }
    setCam({ ...c, x: sx - p.x * c.k, y: sy - p.y * c.k });
    // Once the links have poured out, ease over to what opened.
    const keys = opened(items);
    clearTimeout(revealTimer.current);
    if (keys.length) revealTimer.current = setTimeout(() => showOpened(keys, key), reducedMotion() ? 0 : 240);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lay]);

  // A frame asked for: the start of the whole file, a new centre, or an
  // object to bring into view (at the zoom it has).
  useLayoutEffect(() => {
    const f = frame.current;
    if (!f) return;
    frame.current = null;
    if (refocus.current) {
      const key = typeof refocus.current === "string" ? refocus.current : f.reveal ? realKey.get(f.reveal) : firstKey;
      refocus.current = false;
      requestAnimationFrame(() => els.current.get(key)?.focus({ preventScroll: true }));
    }
    const c = camRef.current;
    const move = f.first ? setCam : glideTo;
    const b = lay.bounds;
    const fits = Math.min((size.w - 48) / (b.maxX - b.minX), (size.h - 96) / (b.maxY - b.minY));
    // The whole file from its start: all of it, up to 100%, or else an
    // overview. A new centre: closer, up to 100%, when that shows all of
    // it; from an overview, close enough to read every card.
    const centred = c.k >= FAR ? Math.max(c.k, Math.min(1, fits)) : fits >= FAR ? Math.min(1, fits) : 1;
    const k = f.start ? clamp(fits, OVERVIEW, 1) : f.centre ? centred : c.k;
    const at = (key, sx, sy) => {
      const p = lay.pos.get(key);
      if (p) move({ k, x: sx - p.x * k, y: sy - p.y * k });
    };
    if (f.reveal) {
      const key = realKey.get(f.reveal);
      if (!key) return;
      setActiveKey(key);
      at(key, size.w / 2, size.h / 2);
      return;
    }
    if ((b.maxX - b.minX) * k <= size.w - 48 && (b.maxY - b.minY) * k <= size.h - 96) {
      move({ k, x: size.w / 2 - ((b.minX + b.maxX) / 2) * k, y: size.h / 2 - ((b.minY + b.maxY) / 2) * k });
      return;
    }
    // Too big to fit: the whole file from its top left, a centre at the
    // side it opens away from.
    const edge = 40 + (NODE_W / 2 + PORT_REACH) * k;
    if (whole || f.start) move({ k, x: 24 - b.minX * k, y: 40 - b.minY * k });
    else if (b.minX >= -NODE_W / 2 - PORT_REACH - 1) at("c", edge, size.h / 2);
    else if (b.maxX <= NODE_W / 2 + PORT_REACH + 1) at("c", size.w - edge, size.h / 2);
    else at("c", size.w / 2, size.h / 2);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lay, tick, size]);

  // Bring cards that just opened into view, keeping the card that opened
  // them on screen: too tall or wide for the view, keep to that card.
  const showOpened = (keys, anchorKey) => {
    const L = layRef.current;
    const c = camRef.current;
    const { w, h } = sizeRef.current;
    const ps = [anchorKey, ...keys].map((k) => L?.pos.get(k)).filter(Boolean);
    if (ps.length < 2) return;
    const sx0 = c.x + (Math.min(...ps.map((q) => q.x)) - NODE_W / 2 - PORT_REACH) * c.k;
    const sx1 = c.x + (Math.max(...ps.map((q) => q.x)) + NODE_W / 2 + PORT_REACH) * c.k;
    const sy0 = c.y + (Math.min(...ps.map((q) => q.y)) - NODE_H / 2) * c.k;
    const sy1 = c.y + (Math.max(...ps.map((q) => q.y)) + NODE_H / 2) * c.k;
    const pad = 24;
    const padBottom = 56;
    let dx = 0;
    let dy = 0;
    if (sx1 - sx0 <= w - 2 * pad) {
      if (sx0 < pad) dx = pad - sx0;
      else if (sx1 > w - pad) dx = w - pad - sx1;
    }
    if (sy1 - sy0 <= h - pad - padBottom) {
      if (sy0 < pad) dy = pad - sy0;
      else if (sy1 > h - padBottom) dy = h - padBottom - sy1;
    }
    if (Math.abs(dx) > 1 || Math.abs(dy) > 1) glideTo({ ...c, x: c.x + dx, y: c.y + dy });
  };

  const screenOf = (key) => {
    const p = lay.pos.get(key);
    const c = camRef.current;
    return p ? { sx: c.x + p.x * c.k, sy: c.y + p.y * c.k } : null;
  };

  const reveal = (key) => {
    const p = layRef.current.pos.get(key);
    if (!p) return;
    const c = camRef.current;
    const { w, h } = sizeRef.current;
    const sx = c.x + p.x * c.k;
    const sy = c.y + p.y * c.k;
    const mx = (NODE_W / 2 + PORT_REACH) * c.k + 24;
    const my = (NODE_H / 2) * c.k + 40;
    if (sx > mx && sx < w - mx && sy > my && sy < h - my) return;
    glideTo({ ...c, x: w / 2 - p.x * c.k, y: h / 2 - p.y * c.k });
  };

  const selectItem = (item) => {
    if (!item) return;
    setActiveKey(item.key);
    if (item.kind === "node") {
      self.current = item.id;
      onSelect(item.id);
    }
  };
  // An object on the map, whether its card is shown yet or not.
  const goTo = (id) => {
    const key = realKey.get(id);
    if (key) {
      selectItem(items.get(key));
      reveal(key);
      els.current.get(key)?.focus({ preventScroll: true });
      return;
    }
    if (g.byId.get(id)?.missing) return;
    if (whole) {
      openPathTo(id);
      askFrame({ reveal: id });
    } else centreOn(id);
    self.current = id;
    onSelect(id);
  };

  const setGroupPages = whole ? setTreePages : setPages;
  const expandAll = () => {
    const at = selectedKey || activeKey || firstKey;
    const sp = screenOf(at);
    if (sp) anchor.current = { key: at, ...sp, opened: () => [] };
    if (whole) {
      setCollapsed(new Set());
      setTreePages(openAll((_, p) => buildTree(g, new Set(), p)).pages);
    } else {
      const all = openAll((ids, p) => buildView(g, root, ids, p));
      setExpanded(all.ids);
      setPages(all.pages);
    }
  };
  const collapseAll = () => {
    if (whole) {
      const roots = new Set(g.roots);
      setCollapsed(new Set([...g.kids.keys(), ...g.out.keys()].filter((id) => !roots.has(id))));
      setTreePages(new Map());
      setActiveKey(firstKey);
      askFrame({ start: true });
    } else {
      resetCentred();
      setActiveKey("c");
      askFrame({ centre: true });
    }
  };

  // Every card, port and label acts through here, so their callbacks stay
  // stable and the memoised layers don't re-render while panning.
  const actions = useRef(null);
  actions.current = {
    select: (key) => selectItem(items.get(key)),
    centre: (key) => {
      const it = items.get(key);
      if (it?.kind === "node" && key !== "c") centreOn(it.id);
    },
    jump: (key) => {
      const it = items.get(key);
      if (!it) return;
      // In a bow-tie, the original in the same half first.
      const same = [...items.values()].find((x) => x.kind === "node" && x.id === it.id && x.dir === it.dir);
      if (same) {
        selectItem(same);
        reveal(same.key);
        els.current.get(same.key)?.focus({ preventScroll: true });
      } else goTo(it.id);
    },
    toggle: (key) => {
      const it = items.get(key);
      if (!it || !hasPort(it)) return;
      const at = screenOf(key);
      if (at) anchor.current = { key, ...at, opened: (next) => next.get(key)?.children || [] };
      if (whole) {
        setCollapsed((s) => {
          const n = new Set(s);
          n.has(it.id) ? n.delete(it.id) : n.add(it.id);
          return n;
        });
      } else {
        setExpanded((e) => {
          const set = new Set(e[it.dir]);
          set.has(it.id) ? set.delete(it.id) : set.add(it.id);
          return { ...e, [it.dir]: set };
        });
      }
      setActiveKey(key);
    },
    open: (key) => {
      const it = items.get(key);
      if (!it) return;
      const parentKey = it.parent;
      const at = screenOf(parentKey);
      const members = (next) => (next.get(parentKey)?.children || []).filter((k) => next.get(k).groupKey === it.groupKey);
      if (at) anchor.current = { key: parentKey, ...at, opened: members };
      setGroupPages((m) => new Map(m).set(it.groupKey, (m.get(it.groupKey) || 0) + 1));
    },
    fold: (key) => {
      const it = items.get(key);
      if (!it?.groupKey) return;
      const parentKey = it.parent;
      const at = screenOf(parentKey);
      const groupCardKey = it.groupCard;
      if (at) anchor.current = { key: parentKey, ...at, opened: () => [groupCardKey], refit: true };
      if (viewportRef.current?.contains(document.activeElement)) refocus.current = groupCardKey;
      setActiveKey(groupCardKey);
      setGroupPages((m) => {
        const next = new Map(m);
        next.delete(it.groupKey);
        return next;
      });
    },
    via: (key) => {
      const it = items.get(key);
      const e = it?.edges.find((x) => x.at);
      if (!e) return;
      self.current = ownerOf(e.at);
      setActiveKey(key);
      onSelect(e.at);
    },
    goTo: (id) => goTo(id),
  };
  const act = useMemo(() => (type, key) => actions.current[type]?.(key), []);
  const register = useMemo(() => (key, el) => (el ? els.current.set(key, el) : els.current.delete(key)), []);
  const onPickSetting = useMemo(() => (id) => {
    self.current = ownerOf(id);
    onSelect(id);
  }, [onSelect]);
  const onGoSetting = useMemo(() => (id) => act("goTo", id), [act]);

  // What's selected, the route to it from the root, and the links to it.
  const owner = ownerOf(focusId);
  const selectedKey = useMemo(() => {
    if (!owner) return null;
    const active = items.get(activeKey);
    if (active?.kind === "node" && active.id === owner) return activeKey;
    return realKey.get(owner) ?? null;
  }, [items, owner, activeKey, realKey]);
  const viaKey = useMemo(() => {
    if (!focusId?.includes("::")) return null;
    for (const it of items.values()) if (it.edges.some((e) => e.at === focusId)) return it.key;
    return null;
  }, [items, focusId]);
  const lit = useMemo(() => {
    const s = new Set();
    for (let k = viaKey || selectedKey; k && items.get(k)?.parent != null; k = items.get(k).parent) s.add(k);
    if (owner) for (const it of items.values()) if (it.kind === "ghost" && it.id === owner) s.add(it.key);
    return s;
  }, [items, selectedKey, viaKey, owner]);

  // Keyboard focus follows activeKey.
  useEffect(() => {
    if (!items.has(activeKey)) setActiveKey(firstKey);
  }, [items, activeKey, firstKey]);

  // Wheel: scroll pans, Ctrl/Cmd+scroll (and pinch) zooms at the pointer.
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const onWheel = (e) => {
      e.preventDefault();
      const c = camRef.current;
      if (e.ctrlKey || e.metaKey) {
        const r = el.getBoundingClientRect();
        const mx = e.clientX - r.left;
        const my = e.clientY - r.top;
        const k = clamp(c.k * Math.exp(-e.deltaY * 0.0018), ZOOM_MIN, ZOOM_MAX);
        setCam({ k, x: mx - (mx - c.x) * (k / c.k), y: my - (my - c.y) * (k / c.k) });
      } else {
        const dx = e.shiftKey && !e.deltaX ? e.deltaY : e.deltaX;
        const dy = e.shiftKey && !e.deltaX ? 0 : e.deltaY;
        setCam({ ...c, x: c.x - dx, y: c.y - dy });
      }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // Drag the canvas to pan.
  const drag = useRef(null);
  const onPointerDown = (e) => {
    if (e.button !== 0 || e.target.closest(".rm-node, .rm-port, .rm-via, .rm-minimap, .rm-overlay")) return;
    drag.current = { x: e.clientX, y: e.clientY, cam: camRef.current, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < 3) return;
    if (!d.moved) setPanning(true);
    d.moved = true;
    setCam({ ...d.cam, x: d.cam.x + dx, y: d.cam.y + dy });
  };
  const onPointerUp = () => {
    drag.current = null;
    setPanning(false);
  };

  const zoomBy = (f) => {
    const c = camRef.current;
    const k = clamp(c.k * f, ZOOM_MIN, ZOOM_MAX);
    const mx = size.w / 2;
    const my = size.h / 2;
    glideTo({ k, x: mx - (mx - c.x) * (k / c.k), y: my - (my - c.y) * (k / c.k) });
  };
  const fit = () => {
    const b = lay.bounds;
    const k = clamp(Math.min((size.w - 64) / (b.maxX - b.minX), (size.h - 64) / (b.maxY - b.minY), 1.2), ZOOM_MIN, ZOOM_MAX);
    glideTo({ k, x: size.w / 2 - ((b.minX + b.maxX) / 2) * k, y: size.h / 2 - ((b.minY + b.maxY) / 2) * k });
  };

  // Arrow keys walk the map as it is drawn: right and left along the links
  // (away from the root on its side, back towards it on the other), up and
  // down the column. Enter centres (opens a group, shows more, goes to a
  // link card's object), Space opens or closes the next level, E explains
  // the link's parameter, Escape folds an open group.
  const onKeyDown = (e) => {
    if (e.target.closest(".rm-overlay")) return;
    const it = items.get(activeKey) || items.get(firstKey);
    if (!it) return;
    const at = lay.pos.get(it.key);
    const nearest = (keys) =>
      keys.length ? keys.reduce((a, b) => (Math.abs(lay.pos.get(b).y - at.y) < Math.abs(lay.pos.get(a).y - at.y) ? b : a)) : null;
    const onSide = (s) => it.children.filter((k) => (items.get(k).dir === "up" ? -1 : 1) === s);
    const inColumn = (dir) => {
      let best = null;
      let bestD = Infinity;
      for (const [k, p] of lay.pos) {
        const d = (p.y - at.y) * dir;
        if (p.x === at.x && k !== it.key && d > 0 && d < bestD) [best, bestD] = [k, d];
      }
      return best;
    };
    const right = it.dir !== "up";
    let next = null;
    if (e.key === "Backspace" || (e.altKey && e.key === "ArrowLeft")) {
      e.preventDefault();
      go(-1);
      return;
    } else if (e.key === "ArrowRight") next = it.parent == null ? nearest(onSide(1)) : right ? nearest(it.children) : it.parent;
    else if (e.key === "ArrowLeft") next = it.parent == null ? nearest(onSide(-1)) : right ? it.parent : nearest(it.children);
    else if (e.key === "ArrowUp") next = inColumn(-1);
    else if (e.key === "ArrowDown") next = inColumn(1);
    else if (e.key === "Home") next = firstKey;
    else if (e.key === "Enter") {
      e.preventDefault();
      if (it.kind === "more" && !it.left) act("fold", it.key);
      else if (it.kind === "ghost") act(g.byId.get(it.id)?.missing ? "via" : "jump", it.key);
      else act(it.kind === "node" ? "centre" : "open", it.key);
      return;
    } else if (e.key === " ") {
      e.preventDefault();
      if (it.kind === "node") act("toggle", it.key);
      else if (it.kind === "group" || (it.kind === "more" && it.left)) act("open", it.key);
      return;
    } else if (e.key === "e" || e.key === "E") {
      if (it.parent != null && it.kind !== "group" && it.edges.some((x) => x.at)) act("via", it.key);
      return;
    } else if (e.key === "Escape") {
      if (it.groupKey && it.kind !== "group") {
        e.preventDefault();
        act("fold", it.key);
      }
      return;
    } else if (e.key === "+" || e.key === "=") return zoomBy(1.2);
    else if (e.key === "-") return zoomBy(1 / 1.2);
    else if (e.key === "0") return fit();
    else return;
    e.preventDefault();
    if (!next) return;
    selectItem(items.get(next));
    reveal(next);
    requestAnimationFrame(() => els.current.get(next)?.focus({ preventScroll: true }));
  };

  // A big map renders only what is near the view: the view and half of it
  // again on each side, rounded out to tiles, so panning re-renders the
  // layers only when it crosses into another tile.
  const near = (() => {
    if (items.size < CULL_AT) return null;
    const k = cam.k;
    const w = size.w / k;
    const h = size.h / k;
    const x = -cam.x / k;
    const y = -cam.y / k;
    const q = (v) => Math.floor(v / TILE);
    return `${q(x - w / 2)},${q(y - h / 2)},${q(x + w * 1.5) + 1},${q(y + h * 1.5) + 1}`;
  })();
  const vis = useMemo(() => {
    if (!near) return null;
    const [x0, y0, x1, y1] = near.split(",").map((n) => Number(n) * TILE);
    const cards = new Set();
    for (const [key, p] of lay.pos) {
      if (p.x + NODE_W / 2 + PORT_REACH >= x0 && p.x - NODE_W / 2 - PORT_REACH <= x1 && p.y + NODE_H / 2 >= y0 && p.y - NODE_H / 2 <= y1) {
        cards.add(key);
      }
    }
    const links = new Set();
    for (const [key, l] of lay.links) if (l.box[2] >= x0 && l.box[0] <= x1 && l.box[3] >= y0 && l.box[1] <= y1) links.add(key);
    return { cards, links };
  }, [near, lay]);

  // Cards lying wholly off each side of the view, for the edge counts.
  const offscreen = useMemo(() => {
    const n = { left: 0, right: 0, top: 0, bottom: 0 };
    const hw = (NODE_W / 2) * cam.k;
    const hh = (NODE_H / 2) * cam.k;
    for (const p of lay.pos.values()) {
      const sx = cam.x + p.x * cam.k;
      const sy = cam.y + p.y * cam.k;
      if (sx + hw < 0) n.left++;
      else if (sx - hw > size.w) n.right++;
      else if (sy + hh < 0) n.top++;
      else if (sy - hh > size.h) n.bottom++;
    }
    return n;
  }, [lay, cam, size]);
  const panBy = (dx, dy) => {
    const c = camRef.current;
    glideTo({ ...c, x: c.x + dx * size.w * 0.6, y: c.y + dy * size.h * 0.6 });
  };

  const cards = useMemo(() => {
    const out = [];
    for (const it of items.values()) {
      if (vis && !vis.cards.has(it.key) && it.key !== activeKey && it.key !== selectedKey) continue;
      const p = lay.pos.get(it.key);
      const node = it.id ? g.byId.get(it.id) : null;
      const where = whole && it.kind === "ghost" && g.container.has(it.id) ? label(g.container.get(it.id)) : null;
      out.push(
        <Card
          key={it.key}
          item={it}
          x={p.x}
          y={p.y}
          node={node}
          fullName={node ? className(kb, node.cls) : null}
          parentLabel={it.parent != null ? label(items.get(it.parent).id) : null}
          where={where}
          ins={it.id ? inCount(g, it.id) : 0}
          outs={it.id ? outCount(g, it.id) : 0}
          inside={it.id ? g.kids.get(it.id)?.length || 0 : 0}
          selected={it.key === selectedKey && !viaKey}
          target={it.kind === "ghost" && it.id === owner}
          tabbable={it.key === activeKey}
          act={act}
          register={register}
        />
      );
    }
    return out;
  }, [items, lay, vis, g, kb, whole, selectedKey, viaKey, activeKey, owner, act, register]);

  const centre = whole ? null : items.get("c");
  const centreNode = centre ? g.byId.get(centre.id) : null;
  const ownerShown = owner && realKey.has(owner);
  const selectedNode = owner ? g.byId.get(owner) : null;
  const lonely = centre && !centre.children.length;
  const selectedMo = owner ? objects.get(owner) || null : null;

  const toolbar = (
    <>
      <SearchBox g={g} kb={kb} whole={whole} onPick={pick} />
      <span className="btn-pair">
        <button className="icon-btn" onClick={() => go(-1)} disabled={nav.index <= 0} aria-label="Back" title="Back (Backspace)">
          <Icon name="arrow-left" />
        </button>
        <button className="icon-btn" onClick={() => go(1)} disabled={nav.index >= nav.list.length - 1} aria-label="Forward" title="Forward">
          <Icon name="arrow-right" />
        </button>
      </span>
      <span className="toolbar-sep" aria-hidden="true" />
      <button
        className="btn"
        onClick={() => showWhole(owner)}
        disabled={whole}
        title="Show the whole file's tree, opened down to the selected object"
      >
        <Icon name="map" />
        <span className="btn-label">Whole file</span>
      </button>
      <button
        className="btn"
        onClick={() => owner && centreOn(owner)}
        disabled={!owner || !g.byId.has(owner) || owner === centre?.id}
        title="Centre the map on the selected object: what points at it on the left, what it points at on the right (Enter on a card, or double-click it)"
      >
        <Icon name="target" />
        <span className="btn-label">Centre on selected</span>
      </button>
      <button className="btn" onClick={onOpenInTree} disabled={!owner} title="Show the selected object in the tree">
        <Icon name="tree" />
        <span className="btn-label">Show in tree</span>
      </button>
      <span className="toolbar-sep" aria-hidden="true" />
      <button
        className="btn"
        onClick={expandAll}
        aria-label="Expand all"
        title={whole ? "Open every object and every group" : "Open every link from the centre, as far as they go, and every group"}
      >
        <Icon name="expand-all" />
        <span className="btn-label">Expand all</span>
      </button>
      <button className="btn" onClick={collapseAll} aria-label="Collapse all" title={whole ? "Close everything below the top object's own level" : "Back to the centre's own links"}>
        <Icon name="collapse-all" />
        <span className="btn-label">Collapse all</span>
      </button>
      <button
        className="btn btn-toggle"
        aria-pressed={settings}
        onClick={() => setSettings((v) => !v)}
        title="Show the selected object's parameters and lists beside the map"
      >
        <Icon name="table" />
        <span className="btn-label">Settings</span>
      </button>
      <span className="toolbar-sep" aria-hidden="true" />
      <div className="segmented rm-zoom" role="group" aria-label="Zoom">
        <button className="icon-btn" onClick={() => zoomBy(1 / 1.2)} aria-label="Zoom out" title="Zoom out (-)">
          <Icon name="minus" />
        </button>
        <button className="rm-zoom-value" onClick={() => glideTo({ ...camRef.current, k: 1 })} title="Back to 100%">
          {Math.round(cam.k * 100)}%
        </button>
        <button className="icon-btn" onClick={() => zoomBy(1.2)} aria-label="Zoom in" title="Zoom in (+)">
          <Icon name="plus" />
        </button>
      </div>
      <button className="icon-btn" onClick={fit} disabled={!items.size} aria-label="Fit the map to the view" title="Fit (0)">
        <Icon name="fit" />
      </button>
      <div className="rm-legend-wrap">
        <button className="icon-btn" aria-pressed={legend} onClick={() => setLegend((v) => !v)} aria-label="Legend" title="What the lines and cards mean">
          <Icon name="info" />
        </button>
        {legend && <Legend stats={g.stats} onClose={closeLegend} />}
      </div>
    </>
  );

  return (
    <section className="split-pane rm" aria-label="Reference map">
      {toolbarSlot && createPortal(toolbar, toolbarSlot)}
      <div
        ref={viewportRef}
        className={"rm-viewport" + (panning ? " is-panning" : "") + (cam.k < FAR ? " is-far" : "")}
        style={{ "--far-fs": farFont(cam.k) }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onKeyDown={onKeyDown}
        onFocus={(e) => {
          const key = e.target.closest(".rm-node")?.dataset.key;
          if (!key) return;
          setKeyboard(e.target.matches(":focus-visible")); // a click focuses cards too; hints are for keys
          setActiveKey(key);
        }}
        onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setKeyboard(false)}
        role="application"
        aria-roledescription="reference map"
        aria-label={centre ? `Reference map centred on ${label(centre.id)}` : "Reference map of the whole file"}
      >
        <div
          className={"rm-world" + (glide ? " is-gliding" : "")}
          style={{ transform: `translate(${cam.x}px, ${cam.y}px) scale(${cam.k})` }}
        >
          <Connectors items={items} lay={lay} g={g} lit={lit} fresh={fresh} vis={vis} />
          <LinkLabels items={items} lay={lay} g={g} act={act} selectedAt={focusId} vis={vis} />
          {cards}
          <Ports items={items} pos={lay.pos} g={g} whole={whole} expanded={expanded} collapsed={collapsed} act={act} vis={vis} />
          {lonely && (
            <div className="rm-lonely rm-overlay" style={{ left: -180, top: NODE_H / 2 + 28 }}>
              <p>
                <span className="mono">{label(centre.id)}</span> points at nothing, nothing points at it, and
                nothing else in this file sits above or under it.
              </p>
            </div>
          )}
        </div>

        {!items.size && (
          <div className="rm-empty rm-overlay">
            <p>This file has no managed objects to map.</p>
          </div>
        )}

        <div className="rm-status rm-overlay" aria-live="polite">
          {whole ? (
            <span>
              Whole file · {plural(data.nodes.length, "object")} · {plural(g.stats.links, "link")}
            </span>
          ) : (
            <span>
              Centred on <span className="mono">{label(centre.id)}</span>
              {centreNode?.missing ? ` (${MISSING[centreNode.missing]})` : ""}
            </span>
          )}
          {owner && !ownerShown && selectedNode && !selectedNode.missing && (
            <>
              <span className="rm-status-sep" aria-hidden="true" />
              <span>
                Selected <span className="mono">{label(owner)}</span> isn't on the map
              </span>
              <button className="link-btn" onClick={() => goTo(owner)}>
                {whole ? "Open it" : "Centre on it"}
              </button>
            </>
          )}
          <span className="rm-status-sep" aria-hidden="true" />
          <span className="rm-status-help">
            {keyboard
              ? "Arrows move · Enter centres · Space opens · E explains the link · Backspace goes back"
              : "Click a link's name to explain it · double-click to centre · drag to pan · Ctrl+scroll to zoom"}
          </span>
        </div>

        {EDGES.filter(([side]) => offscreen[side]).map(([side, icon, dx, dy, where]) => (
          <button
            key={side}
            type="button"
            tabIndex={-1}
            className={`rm-edge rm-overlay is-${side}`}
            onClick={() => panBy(dx, dy)}
            aria-label={`${plural(offscreen[side], "card")} ${where}: move the map to them`}
            title={`${plural(offscreen[side], "card")} ${where}`}
          >
            {(side === "left" || side === "top") && <Icon name={icon} size={12} />}
            {offscreen[side]}
            {(side === "right" || side === "bottom") && <Icon name={icon} size={12} />}
          </button>
        ))}

        {items.size > 0 && (
          <div className="rm-overlay rm-minimap-wrap">
            <Minimap
              items={items}
              pos={lay.pos}
              bounds={lay.bounds}
              cam={cam}
              size={size}
              selectedKey={selectedKey}
              onMove={(wx, wy) => setCam((c) => ({ ...c, x: size.w / 2 - wx * c.k, y: size.h / 2 - wy * c.k }))}
            />
          </div>
        )}
      </div>
      {settings && (
        <SettingsPanel
          mo={selectedMo}
          g={g}
          kb={kb}
          focusId={focusId}
          onPick={onPickSetting}
          onGo={onGoSetting}
          onClose={() => setSettings(false)}
        />
      )}
    </section>
  );
}

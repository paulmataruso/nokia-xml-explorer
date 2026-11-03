import React, { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon.jsx";
import {
  GAP_X,
  NODE_H,
  NODE_W,
  PAGE,
  PORT,
  PORT_Y,
  buildView,
  fanPaths,
  hubs,
  inCount,
  indexGraph,
  label,
  layout,
  outCount,
  search,
} from "./refMapModel.js";

/**
 * The Map view: which objects point at which, around one centred object.
 * What points at it fans out above, what it points at below, so every
 * arrow runs down from the object holding the value to the object it
 * names. Ports on each card open the next level in that direction;
 * double-click (or Enter) re-centres. Childless siblings that don't fit
 * across the view wrap into tiers (refMapModel's layout). A click selects, like a tree row:
 * the file header's Trace and the Explanation pane follow. A link's label
 * selects the parameter that holds it.
 *
 * Pan by dragging the canvas or scrolling, zoom with Ctrl+scroll or the
 * toolbar. The map's controls render into `toolbarSlot` (the workspace
 * toolbar) through a portal, so they sit where the tree's controls sit.
 */

const ZOOM_MIN = 0.3;
const ZOOM_MAX = 1.6;
const VIA_CHARS = 28; // what a link label holds before it shortens (.rm-via's max-width)
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const ownerOf = (id) => (id ? id.split("::")[0] : null);
const clsOfItem = (it) => it.cls || label(it.id).replace(/-[^-]*$/, "");
const depthHue = (dn) => `var(--fc-${((dn.split("/").length - 1) % 8) + 1})`;
const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
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

// A link's label: the parameter holding it, plus how many more hold the
// same link. A long path loses its leading segments, never its leaf name,
// which is what tells sibling parameters apart; the title has them all.
function viaText(edges) {
  const vias = [...new Set(edges.map((e) => e.via))];
  const more = vias.length > 1 ? ` +${vias.length - 1}` : "";
  const room = VIA_CHARS - more.length;
  let first = vias[0];
  if (first.length > room) {
    const parts = first.split(".");
    while (parts.length > 1 && parts.join(".").length + 1 > room) parts.shift();
    first = parts.join(".");
    first = first.length + 1 > room ? `…${first.slice(-(room - 1))}` : `…${first}`;
  }
  return first + more;
}

function edgeKind(item, g) {
  if (item.kind === "more") return "more";
  if (item.kind === "node" || item.kind === "ghost") {
    if (g.byId.get(item.id)?.missing) return "missing";
  }
  return item.edges.some((e) => e.kind === "ref") ? "ref" : "id";
}

// A fan's shared trunk and buses take the strongest kind among its links:
// solid when any is a reference, dashed when all are implied or missing.
function spineKind(kinds) {
  if (kinds.includes("ref")) return "ref";
  if (kinds.every((k) => k === "missing")) return "missing";
  return kinds.some((k) => k === "id" || k === "missing") ? "id" : "more";
}

// --- Layers (memoised: panning re-renders only the camera) ---------------

const Connectors = memo(function Connectors({ items, lay, g, lit, fresh }) {
  const spines = [];
  const drops = [];
  const routes = [];
  for (const fan of lay.fans) {
    const fp = fanPaths(fan, lay.pos);
    const kids = fan.tiers.flat();
    const kinds = kids.map((k) => edgeKind(items.get(k), g));
    const delay = (items.get(kids[0]).depth - 1) * 35;
    const newFan = fresh.has(fan.key);
    spines.push(
      <g key={fan.key} className={`rm-link is-${spineKind(kinds)}` + (newFan ? " is-new" : "")} style={newFan ? { "--d": `${delay}ms` } : null}>
        <path d={fp.spine} />
        {fp.arrow && <path className="rm-arrow" d={fp.arrow} />}
      </g>
    );
    kids.forEach((k, i) => {
      const dp = fp.drops.get(k);
      const newDrop = fresh.has(k);
      drops.push(
        <g key={k} className={`rm-link is-${kinds[i]}` + (newDrop ? " is-new" : "")} style={newDrop ? { "--d": `${delay + 60}ms` } : null}>
          <path d={dp.d} />
          {dp.arrow && <path className="rm-arrow" d={dp.arrow} />}
        </g>
      );
      if (lit.has(k)) {
        routes.push(
          <g key={k} className={`rm-link is-${kinds[i]} is-lit`}>
            <path d={dp.route} />
            <path className="rm-arrow" d={dp.arrow || fp.arrow} />
          </g>
        );
      }
    });
  }
  return (
    <svg className="rm-links" width="1" height="1" aria-hidden="true">
      {spines}
      {drops}
      {routes}
    </svg>
  );
});

const LinkLabels = memo(function LinkLabels({ items, lay, g, act, selectedAt }) {
  const out = [];
  for (const fan of lay.fans) {
    const fp = fanPaths(fan, lay.pos);
    for (const key of fan.tiers.flat()) {
      const item = items.get(key);
      if (!item.edges.length || item.kind === "more") continue;
      const dp = fp.drops.get(key);
      const kind = edgeKind(item, g);
      const src = item.dir === "down" ? items.get(item.parent).id : item.id;
      const dst = item.dir === "down" ? item.id : items.get(item.parent).id;
      const group = item.kind === "group";
      const vias = [...new Set(item.edges.map((e) => e.via))];
      const why = item.edges.find((e) => e.why)?.why;
      const title = group
        ? `${plural(item.count, "object")} through ${vias.join(", ")}`
        : `${label(src)} → ${label(dst)} through ${vias.join(", ")}` +
          (why ? `\nLinked by id: ${why}` : "") +
          (kind === "missing" ? `\n${MISSING[g.byId.get(dst)?.missing] || "Not in this file"}` : "");
      const selected = item.edges.some((e) => e.at === selectedAt);
      out.push(
        <button
          key={key}
          type="button"
          tabIndex={-1}
          className={`rm-via is-${kind}` + (selected ? " is-selected" : "")}
          style={{ left: dp.labelX, top: dp.labelY }}
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
          {viaText(item.edges)}
        </button>
      );
    }
  }
  return out;
});

const Card = memo(function Card({ item, x, y, node, fullName, parentLabel, ins, outs, selected, tabbable, act, register }) {
  const centre = item.key === "c";
  const left = x - NODE_W / 2;
  const top = y - NODE_H / 2;
  if (item.kind === "group") {
    return (
      <div
        ref={(el) => register(item.key, el)}
        className={"rm-node is-group" + (selected ? " is-selected" : "")}
        style={{ left, top }}
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
          {item.dir === "down" ? `${parentLabel} points at all ${item.count}` : `All ${item.count} point at ${parentLabel}`}
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
        style={{ left, top }}
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
  const ghost = item.kind === "ghost";
  const cls =
    "rm-node" +
    (centre ? " is-centre" : "") +
    (ghost ? " is-ghost" : "") +
    (missing ? " is-missing" : "") +
    (selected ? " is-selected" : "");
  const name = label(item.id);
  const sub = missing ? MISSING[missing] || "Not in this file" : null;
  const hint = node?.hint || fullName || node?.cls;
  return (
    <div
      ref={(el) => register(item.key, el)}
      className={cls}
      style={{ left, top, "--seg-hue": depthHue(item.id) }}
      role="button"
      tabIndex={tabbable ? 0 : -1}
      data-key={item.key}
      aria-label={
        `${name}, ${fullName || node?.cls || ""}` +
        (node?.hint ? `, ${node.hint}` : "") +
        (missing ? `. ${sub}` : `. ${plural(ins, "object")} point at it; it points at ${plural(outs, "object")}.`) +
        (ghost ? " Shown elsewhere on the map: Enter goes to it." : centre ? "" : " Enter centres the map on it.")
      }
      onClick={() => act(ghost ? "jump" : "select", item.key)}
      onDoubleClick={() => !ghost && act("centre", item.key)}
    >
      <div className="rm-node-head">
        <span className="rm-swatch" aria-hidden="true" />
        <span className="rm-node-label">{name}</span>
        {!missing && !centre && (
          <span className="rm-counts" aria-hidden="true" title={`${plural(ins, "object")} point at it · it points at ${plural(outs, "object")}`}>
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
      <div className={"rm-node-hint" + (node?.hint ? " is-value" : "") + (ghost ? " is-action" : "")}>
        {ghost ? "Already on the map · go to it" : missing ? item.id : hint}
      </div>
    </div>
  );
});

const Ports = memo(function Ports({ items, pos, g, expanded, act }) {
  const out = [];
  for (const item of items.values()) {
    if (item.kind !== "node") continue;
    const p = pos.get(item.key);
    if (!p) continue;
    const centre = item.key === "c";
    const name = label(item.id);
    for (const dir of centre ? ["up", "down"] : [item.dir]) {
      const n = dir === "down" ? outCount(g, item.id) : inCount(g, item.id);
      if (!n) continue;
      const y = dir === "down" ? p.y + NODE_H / 2 + PORT_Y : p.y - NODE_H / 2 - PORT_Y;
      if (centre) {
        out.push(
          <span key={`c:${dir}`} className={`rm-port is-static is-${dir}`} style={{ left: p.x, top: y }}>
            {dir === "up" ? `${plural(n, "object")} point at it` : `It points at ${plural(n, "object")}`}
          </span>
        );
        continue;
      }
      const open = expanded[dir].has(item.id);
      out.push(
        <button
          key={`${item.key}:${dir}`}
          type="button"
          tabIndex={-1}
          className={`rm-port is-${dir}` + (open ? " is-open" : "")}
          style={{ left: p.x, top: y }}
          aria-expanded={open}
          aria-label={
            (open ? "Hide" : "Show") +
            (dir === "down" ? ` the ${plural(n, "object")} ${name} points at` : ` the ${plural(n, "object")} that point at ${name}`)
          }
          title={dir === "down" ? `${name} points at ${plural(n, "object")}` : `${plural(n, "object")} point at ${name}`}
          onClick={(e) => {
            e.stopPropagation();
            act("toggle", item.key);
          }}
        >
          <span>{n}</span>
          <Icon name={(dir === "down") === open ? "chevron-up" : "chevron-down"} size={12} />
        </button>
      );
    }
  }
  return out;
});

function Minimap({ items, pos, bounds, cam, size, onMove, selectedKey }) {
  const W = 200;
  const H = 120;
  const bw = bounds.maxX - bounds.minX + 160;
  const bh = bounds.maxY - bounds.minY + 160;
  const s = Math.min(W / bw, H / bh);
  const ox = (W - bw * s) / 2 - (bounds.minX - 80) * s;
  const oy = (H - bh * s) / 2 - (bounds.minY - 80) * s;
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
      width={W}
      height={H}
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
      {[...items.values()].map((item) => {
        const p = pos.get(item.key);
        if (!p) return null;
        return (
          <rect
            key={item.key}
            className={item.key === "c" ? "is-centre" : item.key === selectedKey ? "is-selected" : undefined}
            x={ox + (p.x - NODE_W / 2) * s}
            y={oy + (p.y - NODE_H / 2) * s}
            width={Math.max(2, NODE_W * s)}
            height={Math.max(2, NODE_H * s)}
            rx="1"
          />
        );
      })}
      <rect className="rm-minimap-view" x={view.x} y={view.y} width={view.w} height={view.h} rx="2" />
    </svg>
  );
}

function SearchBox({ g, kb, onPick }) {
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
          placeholder="Centre on an object (press /)"
          value={q}
          role="combobox"
          aria-expanded={open && results.length > 0}
          aria-controls="rm-search-list"
          aria-activedescendant={open && results[active] ? `rm-opt-${active}` : undefined}
          aria-label="Find an object to centre the map on"
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
      ].map(([kind, text]) => (
        <div className="rm-legend-row" key={kind}>
          <svg width="40" height="14" aria-hidden="true" className={`rm-sample is-${kind}`}>
            <path d="M2 7h34" />
            <path d="M31 3l5 4-5 4" />
          </svg>
          <span>{text}</span>
        </div>
      ))}
      <div className="rm-legend-row">
        <span className="rm-legend-ghost" aria-hidden="true" />
        <span>Already on the map by a shorter path</span>
      </div>
      <p className="rm-legend-note">
        Arrows run from the object holding the value to the object it names: what points at the centre sits above
        it, what it points at below. The number on a card's edge opens the next level.
      </p>
      <p className="rm-legend-note">
        Keys: arrows move, Enter centres, Space opens the next level, E explains the link, Escape folds a group,
        Backspace goes back, + and − zoom, 0 fits.
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

export function RefMap({ data, kb, focusId, onSelect, onOpenInTree, toolbarSlot }) {
  const g = useMemo(() => indexGraph(data), [data]);
  const [nav, setNav] = useState({ list: [], index: -1 });
  const root = nav.list[nav.index] ?? null;
  const [expanded, setExpanded] = useState(() => ({ up: new Set(), down: new Set() }));
  const [pages, setPages] = useState(() => new Map());
  const [cam, setCam] = useState({ x: 0, y: 0, k: 1 });
  const [glide, setGlide] = useState(false);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [legend, setLegend] = useState(false);
  const closeLegend = useMemo(() => () => setLegend(false), []);
  const [panning, setPanning] = useState(false);
  const [keyboard, setKeyboard] = useState(false); // focus is on the map: show its keys
  const glideTimer = useRef(null);
  const refocus = useRef(false);
  const navRef = useRef(nav);
  navRef.current = nav;
  const [activeKey, setActiveKey] = useState("c");
  const viewportRef = useRef(null);
  const els = useRef(new Map());
  const anchor = useRef(null);
  const frame = useRef(null);
  const self = useRef(null);
  const seen = useRef(new Set());
  const camRef = useRef(cam);
  camRef.current = cam;
  const sizeRef = useRef(size);
  sizeRef.current = size;
  const revealTimer = useRef(null);

  const items = useMemo(() => (root && g.byId.has(root) ? buildView(g, root, expanded, pages) : null), [g, root, expanded, pages]);
  // Childless siblings wrap at as many cards as fit across the view.
  const cols = Math.max(2, Math.floor((size.w - 48 + GAP_X) / (NODE_W + GAP_X)));
  const lay = useMemo(() => (items ? layout(items, cols) : null), [items, cols]);
  const layRef = useRef(lay);
  layRef.current = lay;

  // Which cards and fans are new since the last layout: their links pour in.
  const fresh = useMemo(() => {
    if (!lay) return new Set();
    const out = new Set();
    for (const k of items.keys()) if (!seen.current.has(k)) out.add(k);
    for (const f of lay.fans) if (!seen.current.has(f.key)) out.add(f.key);
    return out;
  }, [items, lay]);
  useEffect(() => {
    if (lay) seen.current = new Set([...items.keys(), ...lay.fans.map((f) => f.key)]);
  }, [items, lay]);

  // Keep the viewport's size.
  useLayoutEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  const centreOn = (id, { push = true } = {}) => {
    if (!g.byId.has(id)) return;
    setNav((n) => {
      if (n.list[n.index] === id) return n;
      const list = push ? [...n.list.slice(0, n.index + 1), id] : n.list;
      return { list, index: push ? list.length - 1 : list.indexOf(id) };
    });
    setExpanded({ up: new Set(), down: new Set() });
    setPages(new Map());
    setActiveKey("c");
    frame.current = "centre";
    refocus.current = !!viewportRef.current?.contains(document.activeElement);
  };
  // Centre on an object and select it, as picking it anywhere else would.
  const pick = (id) => {
    centreOn(id);
    self.current = id;
    onSelect(id);
  };
  const go = (step) => {
    setNav((n) => {
      const index = clamp(n.index + step, 0, n.list.length - 1);
      return index === n.index ? n : { ...n, index };
    });
    setExpanded({ up: new Set(), down: new Set() });
    setPages(new Map());
    setActiveKey("c");
    frame.current = "centre";
    refocus.current = !!viewportRef.current?.contains(document.activeElement);
  };

  // First centre: the selected object, when the map opens. After an edit
  // the map keeps its centre and history, less any object that went away.
  useEffect(() => {
    const n = navRef.current;
    const current = n.list[n.index];
    if (current && g.byId.has(current)) {
      const list = n.list.filter((id) => g.byId.has(id));
      setNav({ list, index: list.indexOf(current) });
      return;
    }
    const owner = ownerOf(focusId);
    setNav({ list: [], index: -1 });
    if (owner && g.byId.has(owner)) centreOn(owner);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [g]);

  // A selection made outside the map (the Trace address, say) re-centres on
  // it when it isn't on the map already.
  const shownIds = useMemo(() => {
    const s = new Set();
    if (items) for (const it of items.values()) if (it.kind === "node") s.add(it.id);
    return s;
  }, [items]);
  useEffect(() => {
    const owner = ownerOf(focusId);
    const mine = owner === self.current;
    self.current = null;
    if (mine || !owner || !g.byId.has(owner)) return;
    if (!root || !shownIds.has(owner)) centreOn(owner);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusId]);

  // After a layout: keep an expanded card where it was under the pointer,
  // or frame a new centre.
  useLayoutEffect(() => {
    if (!lay) return;
    const c = camRef.current;
    if (anchor.current) {
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
      // Once the routes have poured out, ease over to what opened.
      const keys = opened(items);
      clearTimeout(revealTimer.current);
      if (keys.length) revealTimer.current = setTimeout(() => showOpened(keys, key), reducedMotion() ? 0 : 240);
      return;
    }
    if (refocus.current) {
      const key = typeof refocus.current === "string" ? refocus.current : "c";
      refocus.current = false;
      els.current.get(key)?.focus({ preventScroll: true });
    }
    if (frame.current === "centre") {
      frame.current = null;
      // Keep the zoom (100% to start): rows wrap to the view's width, so the
      // text stays at its one size. Too tall to fit, the centre sits mid-view,
      // or high when nothing points at it, or low when it points at nothing.
      const b = lay.bounds;
      const k = c.k;
      const fits = (b.maxY - b.minY) * k <= size.h - 96;
      const y = fits
        ? size.h / 2 - ((b.minY + b.maxY) / 2) * k
        : size.h * (b.minY >= -NODE_H ? 0.3 : b.maxY <= NODE_H ? 0.7 : 0.5);
      glideTo({ x: size.w / 2, y, k });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lay]);

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

  // Bring cards that just opened into view, keeping the card that opened
  // them on screen: too wide for the view, centre on that card instead.
  const showOpened = (keys, anchorKey) => {
    const L = layRef.current;
    const c = camRef.current;
    const { w, h } = sizeRef.current;
    const ps = [anchorKey, ...keys].map((k) => L?.pos.get(k)).filter(Boolean);
    if (ps.length < 2) return;
    const sx0 = c.x + (Math.min(...ps.map((q) => q.x)) - NODE_W / 2) * c.k;
    const sx1 = c.x + (Math.max(...ps.map((q) => q.x)) + NODE_W / 2) * c.k;
    const sy0 = c.y + (Math.min(...ps.map((q) => q.y)) - NODE_H / 2 - PORT) * c.k;
    const sy1 = c.y + (Math.max(...ps.map((q) => q.y)) + NODE_H / 2 + PORT) * c.k;
    const pad = 24;
    const padBottom = 56;
    let dx = 0;
    let dy = 0;
    if (sx1 - sx0 > w - 2 * pad) dx = w / 2 - (c.x + ps[0].x * c.k);
    else if (sx0 < pad) dx = pad - sx0;
    else if (sx1 > w - pad) dx = w - pad - sx1;
    if (sy1 - sy0 <= h - pad - padBottom) {
      if (sy0 < pad) dy = pad - sy0;
      else if (sy1 > h - padBottom) dy = h - padBottom - sy1;
    }
    if (Math.abs(dx) > 1 || Math.abs(dy) > 1) glideTo({ ...c, x: c.x + dx, y: c.y + dy });
  };

  const screenOf = (key) => {
    const p = lay?.pos.get(key);
    const c = camRef.current;
    return p ? { sx: c.x + p.x * c.k, sy: c.y + p.y * c.k } : null;
  };

  const reveal = (key) => {
    const p = lay?.pos.get(key);
    if (!p) return;
    const c = camRef.current;
    const sx = c.x + p.x * c.k;
    const sy = c.y + p.y * c.k;
    const mx = (NODE_W / 2) * c.k + 24;
    const my = (NODE_H / 2) * c.k + 40;
    if (sx > mx && sx < size.w - mx && sy > my && sy < size.h - my) return;
    glideTo({ ...c, x: size.w / 2 - p.x * c.k, y: size.h / 2 - p.y * c.k });
  };

  const selectItem = (item) => {
    if (!item) return;
    setActiveKey(item.key);
    if (item.kind === "node") {
      self.current = item.id;
      onSelect(item.id);
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
      const real = [...items.values()].find((x) => x.kind === "node" && x.id === it.id && x.dir === it.dir) ||
        [...items.values()].find((x) => x.kind === "node" && x.id === it.id);
      if (!real) return;
      selectItem(real);
      reveal(real.key);
      els.current.get(real.key)?.focus({ preventScroll: true });
    },
    toggle: (key) => {
      const it = items.get(key);
      if (!it || it.kind !== "node" || key === "c") return;
      const at = screenOf(key);
      if (at) anchor.current = { key, ...at, opened: (next) => next.get(key)?.children || [] };
      setExpanded((e) => {
        const set = new Set(e[it.dir]);
        set.has(it.id) ? set.delete(it.id) : set.add(it.id);
        return { ...e, [it.dir]: set };
      });
      setActiveKey(key);
    },
    open: (key) => {
      const it = items.get(key);
      if (!it) return;
      const parentKey = it.parent;
      const at = screenOf(parentKey);
      const members = (next) => (next.get(parentKey)?.children || []).filter((k) => clsOfItem(next.get(k)) === it.cls);
      if (at) anchor.current = { key: parentKey, ...at, opened: members };
      setPages((m) => new Map(m).set(it.groupKey, (m.get(it.groupKey) || 0) + 1));
    },
    fold: (key) => {
      const it = items.get(key);
      if (!it?.groupKey) return;
      const parentKey = it.parent;
      const at = screenOf(parentKey);
      const groupCardKey = `${parentKey}>${it.dir}:group:${clsOfItem(it)}`;
      if (at) anchor.current = { key: parentKey, ...at, opened: () => [groupCardKey], refit: true };
      if (viewportRef.current?.contains(document.activeElement)) refocus.current = groupCardKey;
      setActiveKey(groupCardKey);
      setPages((m) => {
        const next = new Map(m);
        next.delete(it.groupKey);
        return next;
      });
    },
    via: (key) => {
      const it = items.get(key);
      const e = it?.edges[0];
      if (!e) return;
      self.current = ownerOf(e.at);
      setActiveKey(key);
      onSelect(e.at);
    },
  };
  const act = useMemo(() => (type, key) => actions.current[type]?.(key), []);
  const register = useMemo(() => (key, el) => (el ? els.current.set(key, el) : els.current.delete(key)), []);

  // What's selected, and the route to it from the centre.
  const owner = ownerOf(focusId);
  const selectedKey = useMemo(() => {
    if (!items || !owner) return null;
    const active = items.get(activeKey);
    if (active?.id === owner) return activeKey;
    if (items.get("c").id === owner) return "c";
    for (const it of items.values()) if (it.kind === "node" && it.id === owner) return it.key;
    return null;
  }, [items, owner, activeKey]);
  const viaKey = useMemo(() => {
    if (!items || !focusId?.includes("::")) return null;
    for (const it of items.values()) if (it.edges.some((e) => e.at === focusId)) return it.key;
    return null;
  }, [items, focusId]);
  const lit = useMemo(() => {
    const s = new Set();
    let k = viaKey || selectedKey;
    while (k && k !== "c" && items?.get(k)) {
      s.add(k);
      k = items.get(k).parent;
    }
    return s;
  }, [items, selectedKey, viaKey]);

  // Keyboard focus follows activeKey.
  useEffect(() => {
    if (!items?.has(activeKey)) setActiveKey("c");
  }, [items, activeKey]);

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
    if (!lay) return;
    const b = lay.bounds;
    const k = clamp(Math.min((size.w - 64) / (b.maxX - b.minX), (size.h - 64) / (b.maxY - b.minY), 1.2), ZOOM_MIN, ZOOM_MAX);
    glideTo({ k, x: size.w / 2 - ((b.minX + b.maxX) / 2) * k, y: size.h / 2 - ((b.minY + b.maxY) / 2) * k });
  };

  // Arrow keys walk the map as it is drawn: away from the centre to the
  // next tier of a wrapped fan or along a link, back towards it the same
  // way, left and right along a row. Enter centres (opens a group, shows
  // more, goes to a ghost's original), Space opens or closes the next
  // level, E explains the link's parameter, Escape folds an open group.
  const onKeyDown = (e) => {
    if (!items || e.target.closest(".rm-overlay")) return;
    const it = items.get(activeKey) || items.get("c");
    const at = lay.pos.get(it.key);
    const nearest = (keys) =>
      keys?.length ? keys.reduce((a, b) => (Math.abs(lay.pos.get(b).x - at.x) < Math.abs(lay.pos.get(a).x - at.x) ? b : a)) : null;
    const fanOf = (key, dir) => lay.fans.find((f) => f.key === `${key}|${dir}`);
    const away = () => {
      const pl = lay.place.get(it.key);
      if (pl && pl.tier < pl.fan.tiers.length - 1 && !it.children.length) return nearest(pl.fan.tiers[pl.tier + 1]);
      return nearest(fanOf(it.key, it.dir)?.tiers[0]);
    };
    const toward = () => {
      const pl = lay.place.get(it.key);
      return pl && pl.tier > 0 ? nearest(pl.fan.tiers[pl.tier - 1]) : it.parent;
    };
    let next = null;
    if (e.key === "ArrowDown") next = it.key === "c" ? nearest(fanOf("c", "down")?.tiers[0]) : it.dir === "down" ? away() : toward();
    else if (e.key === "ArrowUp") next = it.key === "c" ? nearest(fanOf("c", "up")?.tiers[0]) : it.dir === "up" ? away() : toward();
    else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      const row = [...items.values()]
        .filter((x) => x.dir === it.dir && lay.pos.get(x.key).y === at.y)
        .sort((a, b) => lay.pos.get(a.key).x - lay.pos.get(b.key).x);
      const i = row.findIndex((x) => x.key === it.key) + (e.key === "ArrowLeft" ? -1 : 1);
      next = row[i]?.key;
    } else if (e.key === "Home") next = "c";
    else if (e.key === "Enter") {
      e.preventDefault();
      if (it.kind === "more" && !it.left) act("fold", it.key);
      else act(it.kind === "ghost" ? "jump" : it.kind === "node" ? "centre" : "open", it.key);
      return;
    } else if (e.key === " ") {
      e.preventDefault();
      if (it.kind === "node") act("toggle", it.key);
      else if (it.kind === "group" || (it.kind === "more" && it.left)) act("open", it.key);
      return;
    } else if (e.key === "e" || e.key === "E") {
      if (it.key !== "c" && it.kind !== "group" && it.edges.length) act("via", it.key);
      return;
    } else if (e.key === "Escape") {
      if (it.groupKey && it.kind !== "group") {
        e.preventDefault();
        act("fold", it.key);
      }
      return;
    } else if (e.key === "Backspace" || (e.altKey && e.key === "ArrowLeft")) {
      e.preventDefault();
      go(-1);
      return;
    } else if (e.key === "+" || e.key === "=") return zoomBy(1.2);
    else if (e.key === "-") return zoomBy(1 / 1.2);
    else if (e.key === "0") return fit();
    else return;
    e.preventDefault();
    if (!next) return;
    const target = items.get(next);
    selectItem(target);
    reveal(next);
    requestAnimationFrame(() => els.current.get(next)?.focus({ preventScroll: true }));
  };

  // Cards lying wholly off each side of the view, for the edge counts.
  const offscreen = useMemo(() => {
    if (!lay) return null;
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

  const topHubs = useMemo(() => (items ? [] : hubs(g)), [g, items]);
  const centre = items?.get("c");
  const centreNode = centre ? g.byId.get(centre.id) : null;
  const ownerShown = owner && shownIds.has(owner);
  const selectedNode = owner ? g.byId.get(owner) : null;
  const lonely = centre && !centre.children.length;
  const parentDn = centre?.id.includes("/") ? centre.id.slice(0, centre.id.lastIndexOf("/")) : null;

  const toolbar = (
    <>
      <SearchBox g={g} kb={kb} onPick={pick} />
      <span className="btn-pair">
        <button className="icon-btn" onClick={() => go(-1)} disabled={nav.index <= 0} aria-label="Back to the previous centre" title="Back (Backspace)">
          <Icon name="arrow-left" />
        </button>
        <button className="icon-btn" onClick={() => go(1)} disabled={nav.index >= nav.list.length - 1} aria-label="Forward" title="Forward">
          <Icon name="arrow-right" />
        </button>
      </span>
      <span className="toolbar-sep" aria-hidden="true" />
      <button
        className="btn"
        onClick={() => owner && centreOn(owner)}
        disabled={!owner || !g.byId.has(owner) || owner === centre?.id}
        title="Centre the map on the selected object (Enter on a card, or double-click it)"
      >
        <Icon name="target" />
        <span className="btn-label">Centre on selected</span>
      </button>
      <button className="btn" onClick={onOpenInTree} disabled={!owner} title="Show the selected object in the tree">
        <Icon name="tree" />
        <span className="btn-label">Show in tree</span>
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
      <button className="icon-btn" onClick={fit} disabled={!lay} aria-label="Fit the map to the view" title="Fit (0)">
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
        className={"rm-viewport" + (panning ? " is-panning" : "")}
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
        aria-label={centre ? `Reference map centred on ${label(centre.id)}` : "Reference map"}
      >
        {items && lay && (
          <div
            className={"rm-world" + (glide ? " is-gliding" : "")}
            style={{ transform: `translate(${cam.x}px, ${cam.y}px) scale(${cam.k})` }}
          >
            <Connectors items={items} lay={lay} g={g} lit={lit} fresh={fresh} />
            <LinkLabels items={items} lay={lay} g={g} act={act} selectedAt={focusId} />
            {[...items.values()].map((it) => {
              const p = lay.pos.get(it.key);
              const node = it.id ? g.byId.get(it.id) : null;
              return (
                <Card
                  key={it.key}
                  item={it}
                  x={p.x}
                  y={p.y}
                  node={node}
                  fullName={node ? className(kb, node.cls) : null}
                  parentLabel={it.parent ? label(items.get(it.parent).id) : null}
                  ins={it.id ? inCount(g, it.id) : 0}
                  outs={it.id ? outCount(g, it.id) : 0}
                  selected={it.key === selectedKey && !viaKey}
                  tabbable={it.key === activeKey}
                  act={act}
                  register={register}
                />
              );
            })}
            <Ports items={items} pos={lay.pos} g={g} expanded={expanded} act={act} />
            {lonely && (
              <div className="rm-lonely rm-overlay" style={{ left: -180, top: NODE_H / 2 + 28 }}>
                <p>
                  <span className="mono">{label(centre.id)}</span> points at nothing and nothing points at it. It is
                  tied into the file only by where it sits{parentDn ? ", under " : "."}
                  {parentDn && <span className="mono">{label(parentDn)}</span>}
                  {parentDn && "."}
                </p>
                {parentDn && g.byId.has(parentDn) && (
                  <button className="btn" onClick={() => pick(parentDn)}>
                    <Icon name="target" />
                    Centre on {label(parentDn)}
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {!items && (
          <div className="rm-landing rm-overlay">
            <h2 className="rm-landing-title">Reference map</h2>
            <p>
              Centre the map on an object to see what points at it, above, and what it points at, below. Search for
              one, select it in the tree first, or start from the objects most pointed at in this file.
            </p>
            <div className="rm-hubs-head" id="rm-hubs-head">Most pointed at</div>
            {topHubs.length > 0 ? (
              <ul className="rm-hubs" aria-labelledby="rm-hubs-head">
                {topHubs.map((h) => {
                  const n = g.byId.get(h.id);
                  return (
                    <li key={h.id}>
                      <button className="rm-hub" onClick={() => pick(h.id)}>
                        <span className="rm-hub-label">{label(h.id)}</span>
                        <span className="rm-hub-meta">{n?.hint || className(kb, n?.cls) || n?.cls}</span>
                        <span className="rm-hub-count">{plural(h.count, "object")} point at it</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <div className="rm-hubs-empty">No object in this file points at another.</div>
            )}
          </div>
        )}

        {items && (
          <div className="rm-status rm-overlay" aria-live="polite">
            <span>
              Centred on <span className="mono">{label(centre.id)}</span>
              {centreNode?.missing ? ` (${MISSING[centreNode.missing]})` : ""}
            </span>
            {owner && !ownerShown && selectedNode && (
              <>
                <span className="rm-status-sep" aria-hidden="true" />
                <span>
                  Selected <span className="mono">{label(owner)}</span> isn't on the map
                </span>
                <button className="link-btn" onClick={() => centreOn(owner)}>
                  Centre on it
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
        )}

        {offscreen &&
          EDGES.filter(([side]) => offscreen[side]).map(([side, icon, dx, dy, where]) => (
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

        {items && lay && (
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
    </section>
  );
}

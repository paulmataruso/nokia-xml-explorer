/**
 * The Map view's model, kept apart from its rendering: the reference index
 * built from GET /refmap, what is shown, and its layout.
 *
 * Two views. The whole file (the default) is the containment tree: every
 * object under the one it sits in. An object's references hang off it as
 * link cards, each naming the object it points at: a copy, since the object
 * itself sits where the tree puts it. So every link is drawn, and every
 * line is a branch of one tree, which no other line crosses.
 *
 * Centred on one object, the view is a bow-tie whose halves share the
 * centre. "down" follows what an object points at and what it contains;
 * "up" follows what points at it and the object it sits in. Each object
 * appears once per half: a second path to it shows a ghost that goes to the
 * first. Each half is a tree too, so its lines don't cross either.
 *
 * The layout runs left to right: the down half (and the whole file) to the
 * right of its root, the up half to the left. Every arrow points right,
 * from the object holding the value (or the container) to the object it
 * names (or contains).
 *
 * Containment is read here from the distNames, not sent by GET /refmap:
 * an object sits in its nearest ancestor the file has (a gap in the path,
 * a placeholder in the tree, is skipped). The endpoint's links stay the
 * references only, as the site check and the delete action read them.
 */

export const NODE_W = 236;
export const NODE_H = 70;
export const GHOST_H = 50; // a link card or a repeat: two lines
export const ROW_GAP = 32; // between neighbouring subtrees in a column
export const PORT_REACH = 40; // a port's outer end, out from the card's edge (.rm-port: 48 wide, 8 over the card)
export const GROUP_MAX = 6; // more siblings of one class than this fold into a group
export const PAGE = 18; // members shown per page of an open group
export const VIA_CHARS = 26; // what a link label holds before it shortens (.rm-via's max-width)
export const SET_ROW = 20; // a row of an open card's settings (.rm-card-row)
export const OPEN_W = 184; // an open card is this much wider, away from the centre
export const SET_EDGE = 26; // the settings' border and padding, top and bottom (.rm-card-body)
const CHAR_W = 7.8; // one --fs-data monospace character
const LABEL_PAD = 16; // .rm-via's padding and border
const RUN_MIN = 28; // the straight stretch into a card: room for the arrow
const RUN_PAD = 40; // around a label on that stretch
const BEND_MIN = 120; // the curve, from the parent's port to the straight stretch
const BEND_MAX = 200;

const dnLabel = (dn) => dn.slice(dn.lastIndexOf("/") + 1);
const clsOf = (dn) => dnLabel(dn).replace(/-[^-]*$/, "");
const instanceNum = (dn) => {
  const n = Number(dnLabel(dn).slice(dnLabel(dn).lastIndexOf("-") + 1));
  return Number.isFinite(n) ? n : Infinity;
};
const byName = (a, b) => {
  const ca = clsOf(a);
  const cb = clsOf(b);
  return ca === cb ? instanceNum(a) - instanceNum(b) || a.localeCompare(b) : ca.localeCompare(cb);
};

/** Index the endpoint's flat lists: objects by id, and links out and in,
 * grouped by the object at the other end. Missing targets get a node of
 * their own, flagged, so they can be shown and centred on. Containment:
 * `kids` lists what each object contains, `container` the one it sits in,
 * `roots` the objects that sit in none. */
export function indexGraph(data) {
  const byId = new Map();
  for (const n of data.nodes) byId.set(n.id, n);
  const kids = new Map();
  const container = new Map();
  const roots = [];
  for (const n of data.nodes) {
    let up = null;
    for (let i = n.id.lastIndexOf("/"); i > 0; i = n.id.lastIndexOf("/", i - 1)) {
      if (byId.has(n.id.slice(0, i))) {
        up = n.id.slice(0, i);
        break;
      }
    }
    if (!up) {
      roots.push(n.id);
      continue;
    }
    container.set(n.id, up);
    if (!kids.has(up)) kids.set(up, []);
    kids.get(up).push(n.id);
  }
  roots.sort(byName);
  const out = new Map();
  const inn = new Map();
  const add = (map, from, to, e) => {
    let m = map.get(from);
    if (!m) map.set(from, (m = new Map()));
    let list = m.get(to);
    if (!list) m.set(to, (list = []));
    list.push(e);
  };
  for (const e of data.edges) {
    if (!byId.has(e.t)) byId.set(e.t, { id: e.t, cls: clsOf(e.t), missing: e.missing || "absent" });
    add(out, e.s, e.t, e);
    add(inn, e.t, e.s, e);
  }
  return { byId, out, in: inn, kids, container, roots, stats: data.stats };
}

// References only: what an object points at, and what points at it.
export const outCount = (g, id) => g.out.get(id)?.size || 0;
export const inCount = (g, id) => g.in.get(id)?.size || 0;
export const label = dnLabel;
export const classOf = clsOf;
export const refEdges = (edges) => edges.filter((e) => e.kind !== "contains");

/** The objects one step away in a half, each with its links: references,
 * plus a "contains" link to each object it contains (down) or to its
 * container (up). An object both referenced and contained has both. */
export function neighbours(g, id, dir) {
  const links = (dir === "down" ? g.out : g.in).get(id);
  const held = dir === "down" ? g.kids.get(id) || [] : g.container.has(id) ? [g.container.get(id)] : [];
  if (!held.length) return links ? [...links.entries()] : [];
  const all = new Map(links || []);
  for (const other of held) {
    const e = dir === "down" ? { s: id, t: other, kind: "contains" } : { s: other, t: id, kind: "contains" };
    all.set(other, [...(all.get(other) || []), e]);
  }
  return [...all.entries()];
}

/** How much a card's port opens in a half: `links` objects by reference,
 * `held` by containment, `total` without counting one object twice. */
export function reach(g, id, dir) {
  const links = dir === "down" ? outCount(g, id) : inCount(g, id);
  const map = (dir === "down" ? g.out : g.in).get(id);
  const held = dir === "down" ? g.kids.get(id) || [] : g.container.has(id) ? [g.container.get(id)] : [];
  return { links, held: held.length, total: links + held.filter((o) => !map?.has(o)).length };
}

const onlyContains = (edges) => edges.every((e) => e.kind === "contains");

/** Objects matching a query, best first: label prefix, then class, then
 * anywhere in the distName or hint. */
export function search(g, query, n = 10) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const scored = [];
  for (const node of g.byId.values()) {
    const l = dnLabel(node.id).toLowerCase();
    const rank = l === q ? 0 : l.startsWith(q) ? 1 : node.cls.toLowerCase() === q ? 2
      : node.id.toLowerCase().includes(q) ? 3 : (node.hint || "").toLowerCase().includes(q) ? 4 : -1;
    if (rank >= 0) scored.push([rank, outCount(g, node.id) + inCount(g, node.id), node]);
  }
  scored.sort((a, b) => a[0] - b[0] || b[1] - a[1] || a[2].id.localeCompare(b[2].id));
  return scored.slice(0, n).map((s) => s[2]);
}

// References first, then what is contained; by class, then instance.
function sortNeighbours(entries) {
  return entries.sort(([a, ea], [b, eb]) => {
    const ha = onlyContains(ea);
    if (ha !== onlyContains(eb)) return ha ? 1 : -1;
    return byName(a, b);
  });
}

/** One object's next level: its neighbours by class, a class with more
 * than GROUP_MAX of them folded into a group (or its open pages shown, and
 * a "more" card after them). `kindOf(other, edges)` says whether a member
 * is a card ("node") or a copy ("ghost"). */
function fanOut(parent, entries, dir, pages, kindOf) {
  const kids = [];
  const byCls = new Map();
  for (const [other, edges] of sortNeighbours(entries)) {
    const held = onlyContains(edges);
    const c = `${clsOf(other)}${held ? "|in" : ""}`;
    if (!byCls.has(c)) byCls.set(c, { cls: clsOf(other), held, members: [] });
    byCls.get(c).members.push([other, edges]);
  }
  for (const { cls, held, members } of byCls.values()) {
    const sub = `${cls}${held ? ":in" : ""}`;
    const tag = held ? { held } : null;
    let shown = members;
    let group = null;
    if (members.length > GROUP_MAX) {
      group = { groupKey: `${dir}|${parent.id}|${cls}${held ? "|in" : ""}`, groupCard: `${parent.key}>${dir}:group:${sub}` };
      const n = pages.get(group.groupKey) || 0;
      if (!n) {
        kids.push({ kind: "group", key: group.groupCard, cls, count: members.length, ...group, ...tag,
          edges: members.flatMap(([, e]) => e) });
        continue;
      }
      shown = members.slice(0, n * PAGE);
    }
    for (const [other, edges] of shown) {
      kids.push({ kind: kindOf(other, edges), key: `${parent.key}>${dir}:${other}`, id: other, edges, ...group, ...tag });
    }
    if (group) {
      kids.push({ kind: "more", key: `${parent.key}>${dir}:more:${sub}`, cls, count: members.length,
        left: members.length - shown.length, ...group, ...tag, edges: [] });
    }
  }
  for (const k of kids) Object.assign(k, { dir, depth: parent.depth + 1, parent: parent.key, children: [] });
  return kids;
}

/**
 * The bow-tie around `root`: the centre, and in each half the objects
 * reached through expanded nodes, breadth first so the nearest occurrence
 * of an object is the real one. Items are objects, ghosts (a repeat),
 * groups (many siblings of one class, folded) and "more" (the tail of an
 * open group: how many are left, and where it folds back). Items reached
 * only by containment are `held`; they come after the references, and
 * group apart from them.
 *
 * expanded: { up: Set<id>, down: Set<id> }; pages: Map<groupKey, pages shown>
 * (Infinity shows them all).
 */
export function buildView(g, root, expanded, pages) {
  const items = new Map();
  const centre = { key: "c", kind: "node", id: root, dir: "centre", depth: 0, parent: null, children: [], edges: [] };
  items.set(centre.key, centre);
  for (const dir of ["down", "up"]) {
    const placed = new Set([root]);
    const queue = [centre];
    while (queue.length) {
      const parent = queue.shift();
      if (parent !== centre && !expanded[dir].has(parent.id)) continue;
      const kids = fanOut(parent, neighbours(g, parent.id, dir), dir, pages, (other) => {
        if (placed.has(other)) return "ghost";
        placed.add(other);
        return "node";
      });
      for (const k of kids) {
        items.set(k.key, k);
        parent.children.push(k.key);
        if (k.kind === "node") queue.push(k);
      }
    }
  }
  return items;
}

/**
 * The whole file: each root (an object that sits in no other), everything
 * under it, and each object's references as copies ("ghost" items, or the
 * object's own card when it contains what it names). Every object is open
 * unless `collapsed` has it; groups fold as in the bow-tie.
 */
export function buildTree(g, collapsed, pages) {
  const items = new Map();
  const queue = [];
  for (const id of g.roots) {
    const it = { key: `t:${id}`, kind: "node", id, dir: "down", depth: 0, parent: null, children: [], edges: [] };
    items.set(it.key, it);
    queue.push(it);
  }
  const kindOf = (other, edges) => (edges.some((e) => e.kind === "contains") ? "node" : "ghost");
  while (queue.length) {
    const parent = queue.shift();
    if (collapsed.has(parent.id)) continue;
    for (const k of fanOut(parent, neighbours(g, parent.id, "down"), "down", pages, kindOf)) {
      items.set(k.key, k);
      parent.children.push(k.key);
      if (k.kind === "node") queue.push(k);
    }
  }
  return items;
}

/** Every group key and object a view could open: what "Expand all" sets. */
export function openAll(build) {
  const pages = new Map();
  const ids = { up: new Set(), down: new Set() };
  for (let grew = true; grew; ) {
    grew = false;
    for (const it of build(ids, pages).values()) {
      if (it.kind === "group" && !pages.has(it.groupKey)) {
        pages.set(it.groupKey, Infinity);
        grew = true;
      } else if (it.kind === "node" && it.parent != null && (it.dir === "up" || it.dir === "down") && !ids[it.dir].has(it.id)) {
        ids[it.dir].add(it.id);
        grew = true;
      }
    }
  }
  return { ids, pages };
}

/** A link's label: the parameter holding it, plus how many more hold the
 * same link. A long path loses its leading segments, never its leaf name,
 * which is what tells sibling parameters apart; the title has them all. */
export function viaText(edges) {
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

export const cardH = (it) => (it.kind === "ghost" ? GHOST_H : NODE_H);

/**
 * An object's settings as an open card lists them, one row each: its
 * parameters, then each list (its name and row count), the list's rows
 * under it (a plain value, or a row's fields under its own line). `mo` is
 * the object's node in the file's tree.
 */
export function settingLines(mo) {
  const out = [];
  const walk = (kids, depth) => {
    for (const c of kids) {
      if (c.kind === "param") out.push({ kind: "param", id: c.id, name: c.label, value: c.value, missing: !!c.requiredMissing, depth });
    }
    for (const c of kids) {
      if (c.kind !== "list") continue;
      out.push({ kind: "list", id: c.id, name: c.label, rows: c.rowCount ?? c.children.length, depth });
      for (const r of c.children) {
        if (r.value != null) out.push({ kind: "param", id: r.id, name: r.label, value: r.value, missing: false, depth: depth + 1 });
        else {
          out.push({ kind: "item", id: r.id, name: r.label, depth: depth + 1 });
          walk(r.children || [], depth + 2);
        }
      }
    }
  };
  walk(mo?.children || [], 0);
  return out;
}
// How much an open card grows down by, for its rows.
export const settingsH = (rows) => (rows.length ? rows.length * SET_ROW + SET_EDGE : 0);

// A card's edges, from its place in the layout (pos: x, y, and how far it
// grows down, g, and wide, w). A card grows away from the centre: one in a
// bow-tie's up half to the left, any other to the right, so its links and
// its port on the side they come in from stay where they were.
export function cardBox(it, p) {
  const h = cardH(it) / 2;
  const left = it.dir === "up" && it.parent != null;
  return {
    left: p.x - NODE_W / 2 - (left ? p.w : 0),
    right: p.x + NODE_W / 2 + (left ? 0 : p.w),
    top: p.y - h,
    bottom: p.y + h + p.g,
  };
}
const side = (it) => (it.dir === "up" ? -1 : 1);
// Every card with a next level has a port, but the centre: both its halves are always open.
export const hasPort = (it) => it.kind === "node" && it.key !== "c";
// A link is labelled with the parameter holding it; containment and a group's tail have none.
const labelled = (it) => it.kind !== "more" && refEdges(it.edges).length > 0;

/**
 * Left to right. Each object's next level stands in the column beside it,
 * in order. Subtrees are packed column by column: each sits as high as it
 * can, ROW_GAP clear of the ones before it in every column they share, so a
 * short one tucks in under a deep one. Every column keeps the tree's order,
 * so no link crosses another (see the links below). In a bow-tie a parent
 * sits level with the middle of its children, its centre with its down half
 * on the right and its up half on the left. The whole file (align "top")
 * reads like an outline: a parent level with its first child, so the file
 * starts at the top left with its first branch running straight across;
 * its roots stack down column 0.
 *
 * A column's width leaves room for its links: the curve out of the
 * parent's port (wider when the children spread far), then a straight
 * stretch into the card, as long as the column's longest label.
 *
 * A card whose settings are open grows down by `grow` (key -> px), and
 * OPEN_W wider (cardBox): its links still meet it at its head, it holds
 * that much more of its column, and its column moves the ones beyond it
 * out by OPEN_W.
 *
 * Returns { pos: Map<key, {x, y, g, w}> (the centre of a card's head as
 * it is closed, and how far it grows down and wide), bounds, links:
 * Map<key, { d, arrow, labelX, labelY, side, box }> (the link into each
 * item from its parent) }.
 */
export function layout(items, align = "middle", grow = new Map()) {
  const roots = [];
  for (const it of items.values()) if (it.parent == null) roots.push(it.key);
  const off = new Map(); // a card's centre, down from its parent's
  // Subtrees packed down in order: each one's centre down from the first's,
  // and what they hold together, per column from theirs (top and bottom).
  const pack = (ks, gap) => {
    const offs = [];
    const tops = [];
    const bots = [];
    for (const k of ks) {
      const s = shape(k);
      let o = 0;
      if (offs.length) {
        o = -Infinity;
        for (let i = 0; i < Math.min(tops.length, s.tops.length); i++) o = Math.max(o, bots[i] + gap - s.tops[i]);
      }
      offs.push(o);
      s.tops.forEach((t, i) => {
        if (i < tops.length) {
          tops[i] = Math.min(tops[i], o + t);
          bots[i] = Math.max(bots[i], o + s.bots[i]);
        } else {
          tops.push(o + t);
          bots.push(o + s.bots[i]);
        }
      });
    }
    return { offs, tops, bots };
  };
  // A subtree's outline, from its card's centre; its children's offsets on the way.
  const shape = (key) => {
    const it = items.get(key);
    const h = cardH(it) / 2;
    const down = h + (grow.get(key) || 0);
    if (!it.children.length) return { tops: [-h], bots: [down] };
    const { offs, tops, bots } = pack(it.children, ROW_GAP);
    const y = align === "top" ? 0 : offs[offs.length - 1] / 2;
    it.children.forEach((k, i) => off.set(k, offs[i] - y));
    return { tops: [-h, ...tops.map((t) => t - y)], bots: [down, ...bots.map((t) => t - y)] };
  };
  const pos = new Map();
  const place = (key, y) => {
    const g = grow.get(key) || 0;
    pos.set(key, { x: 0, y, g, w: g ? OPEN_W : 0 });
    for (const k of items.get(key).children) place(k, y + off.get(k));
  };
  const centre = roots.length === 1 ? items.get(roots[0]) : null;
  const upHalf = centre ? centre.children.filter((k) => side(items.get(k)) < 0) : [];
  if (upHalf.length) {
    // A bow-tie's centre: each half packed on its own side, level with it.
    for (const half of [upHalf, centre.children.filter((k) => side(items.get(k)) > 0)]) {
      if (!half.length) continue;
      const { offs } = pack(half, ROW_GAP);
      half.forEach((k, i) => off.set(k, offs[i] - offs[offs.length - 1] / 2));
    }
    place(centre.key, 0);
  } else {
    const { offs } = pack(roots, ROW_GAP * 2);
    roots.forEach((r, i) => place(r, offs[i]));
  }
  const y0 = pos.get(roots[0])?.y || 0;
  for (const p of pos.values()) p.y -= y0;

  // Columns: per side and depth, the widest label and the farthest spread,
  // and whether a card in it is open (wider).
  const cols = new Map();
  const colOf = (it) => side(it) * it.depth;
  const wide = new Map();
  for (const it of items.values()) if (pos.get(it.key).w) wide.set(colOf(it), OPEN_W);
  for (const it of items.values()) {
    if (it.parent == null) continue;
    const c = colOf(it);
    const col = cols.get(c) || { run: RUN_MIN, spread: 0 };
    if (labelled(it)) col.run = Math.max(col.run, viaText(refEdges(it.edges)).length * CHAR_W + LABEL_PAD + RUN_PAD);
    col.spread = Math.max(col.spread, Math.abs(pos.get(it.key).y - pos.get(it.parent).y));
    cols.set(c, col);
  }
  const colX = new Map([[0, 0]]);
  for (const s of [1, -1]) {
    for (let d = 1; cols.has(s * d); d++) {
      const col = cols.get(s * d);
      col.bend = Math.min(BEND_MAX, Math.max(BEND_MIN, col.spread * 0.2));
      // The centre's column grows to the right only.
      const before = s < 0 && d === 1 ? 0 : wide.get(s * (d - 1)) || 0;
      colX.set(s * d, colX.get(s * (d - 1)) + s * (NODE_W + before + PORT_REACH + col.bend + col.run));
    }
  }
  for (const [key, p] of pos) p.x = colX.get(colOf(items.get(key))) ?? 0;

  const links = new Map();
  const arrowAt = (x, y) => `M${x - 7} ${y - 4.5}L${x} ${y}L${x - 7} ${y + 4.5}`;
  for (const it of items.values()) {
    if (it.parent == null) continue;
    const par = items.get(it.parent);
    const P = pos.get(par.key);
    const K = pos.get(it.key);
    const pb = cardBox(par, P);
    const col = cols.get(colOf(it));
    const reachOut = hasPort(par) ? PORT_REACH : 0;
    let link;
    if (side(it) > 0) {
      const x0 = pb.right + reachOut;
      const x1 = K.x - NODE_W / 2;
      const xb = x1 - col.run;
      const m = x0 + (xb - x0) / 2;
      link = {
        d: `M${x0} ${P.y}C${m} ${P.y} ${m} ${K.y} ${xb} ${K.y}H${x1}`,
        arrow: arrowAt(x1, K.y),
        labelX: x1 - 18,
        box: [x0, Math.min(P.y, K.y), x1, Math.max(P.y, K.y)],
      };
    } else {
      const x0 = K.x + NODE_W / 2;
      const xb = x0 + col.run;
      const x1 = pb.left - reachOut;
      const m = xb + (x1 - xb) / 2;
      link = {
        d: `M${x0} ${K.y}H${xb}C${m} ${K.y} ${m} ${P.y} ${x1} ${P.y}`,
        arrow: arrowAt(x1, P.y),
        labelX: x0 + 16,
        box: [x0, Math.min(P.y, K.y), x1, Math.max(P.y, K.y)],
      };
    }
    links.set(it.key, { ...link, labelY: K.y, side: side(it) });
  }

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const [key, p] of pos) {
    const b = cardBox(items.get(key), p);
    minX = Math.min(minX, b.left - PORT_REACH);
    maxX = Math.max(maxX, b.right + PORT_REACH);
    minY = Math.min(minY, b.top);
    maxY = Math.max(maxY, b.bottom);
  }
  if (!pos.size) [minX, maxX, minY, maxY] = [0, 0, 0, 0];
  return { pos, bounds: { minX, maxX, minY, maxY }, links };
}

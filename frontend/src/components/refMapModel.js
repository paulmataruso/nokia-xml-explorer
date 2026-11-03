/**
 * The Map view's model, kept apart from its rendering: the reference index
 * built from GET /refmap, the bow-tie of what is shown around the centred
 * object, and its layout.
 *
 * The bow-tie has two halves that share the centre. "down" follows what an
 * object points at; "up" follows what points at it. Either way the arrow
 * runs from the object holding the value to the object it names, so on
 * screen every arrow points down. Each object appears once per half: a
 * second path to it shows a ghost that jumps to the first.
 */

export const NODE_W = 236;
export const NODE_H = 70;
export const GAP_X = 20;
export const GAP_Y = 84; // between levels: the port, the bus, the label
export const LEVEL = NODE_H + GAP_Y;
export const GROUP_MAX = 6; // more siblings of one class than this fold into a group
export const PAGE = 18; // members shown per page of an open group
export const PORT = 16; // the expander sits on the card's edge, mostly outside it
export const PORT_Y = 6; // its centre's offset outwards from the edge

const dnLabel = (dn) => dn.slice(dn.lastIndexOf("/") + 1);
const clsOf = (dn) => dnLabel(dn).replace(/-[^-]*$/, "");
const instanceNum = (dn) => {
  const n = Number(dnLabel(dn).slice(dnLabel(dn).lastIndexOf("-") + 1));
  return Number.isFinite(n) ? n : Infinity;
};

/** Index the endpoint's flat lists: objects by id, and links out and in,
 * grouped by the object at the other end. Missing targets get a node of
 * their own, flagged, so they can be shown and centred on. */
export function indexGraph(data) {
  const byId = new Map();
  for (const n of data.nodes) byId.set(n.id, n);
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
  return { byId, out, in: inn, stats: data.stats };
}

export const outCount = (g, id) => g.out.get(id)?.size || 0;
export const inCount = (g, id) => g.in.get(id)?.size || 0;
export const label = dnLabel;

/** The objects most pointed at: a starting point when nothing is centred. */
export function hubs(g, n = 8) {
  return [...g.in.entries()]
    .filter(([id]) => !g.byId.get(id)?.missing)
    .map(([id, m]) => ({ id, count: m.size }))
    .sort((a, b) => b.count - a.count || a.id.localeCompare(b.id))
    .slice(0, n);
}

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

function sortNeighbours(entries) {
  return entries.sort(([a], [b]) => {
    const ca = clsOf(a);
    const cb = clsOf(b);
    return ca === cb ? instanceNum(a) - instanceNum(b) || a.localeCompare(b) : ca.localeCompare(cb);
  });
}

/**
 * What is shown: the centre, and in each half the objects reached through
 * expanded nodes, breadth first so the nearest occurrence of an object is
 * the real one. Items are objects, ghosts (a repeat), groups (many siblings
 * of one class, folded) and "more" (the tail of an open group: how many are
 * left, and where it folds back).
 *
 * expanded: { up: Set<id>, down: Set<id> }; pages: Map<groupKey, pages shown>.
 */
export function buildView(g, root, expanded, pages) {
  const items = new Map();
  const centre = { key: "c", kind: "node", id: root, dir: "centre", depth: 0, children: [], edges: [] };
  items.set(centre.key, centre);
  for (const dir of ["down", "up"]) {
    const links = dir === "down" ? g.out : g.in;
    const placed = new Set([root]);
    const queue = [centre];
    while (queue.length) {
      const parent = queue.shift();
      if (parent !== centre && !expanded[dir].has(parent.id)) continue;
      const kids = [];
      const byCls = new Map();
      for (const [other, edges] of sortNeighbours([...(links.get(parent.id)?.entries() || [])])) {
        const c = clsOf(other);
        if (!byCls.has(c)) byCls.set(c, []);
        byCls.get(c).push([other, edges]);
      }
      for (const [cls, members] of byCls) {
        let shown = members;
        let groupKey = null;
        if (members.length > GROUP_MAX) {
          groupKey = `${dir}|${parent.id}|${cls}`;
          const n = pages.get(groupKey) || 0;
          if (!n) {
            kids.push({ kind: "group", key: `${parent.key}>${dir}:group:${cls}`, cls, count: members.length,
              groupKey, edges: members.flatMap(([, e]) => e) });
            continue;
          }
          shown = members.slice(0, n * PAGE);
        }
        for (const [other, edges] of shown) {
          const ghost = placed.has(other);
          if (!ghost) placed.add(other);
          kids.push({ kind: ghost ? "ghost" : "node", key: `${parent.key}>${dir}:${other}`, id: other, edges,
            ...(groupKey ? { groupKey } : null) });
        }
        if (groupKey) {
          kids.push({ kind: "more", key: `${parent.key}>${dir}:more:${cls}`, cls, count: members.length,
            left: members.length - shown.length, groupKey, edges: [] });
        }
      }
      for (const k of kids) {
        Object.assign(k, { dir, depth: parent.depth + 1, parent: parent.key, children: [] });
        items.set(k.key, k);
        parent.children.push(k.key);
        if (k.kind === "node") queue.push(k);
      }
    }
  }
  // The centre's children were filled by both halves; split them back out.
  centre.down = centre.children.filter((k) => items.get(k).dir === "down");
  centre.up = centre.children.filter((k) => items.get(k).dir === "up");
  return items;
}

export const TIER = NODE_H + 56; // between the tiers of a wrapped fan: a bus and the labels
const BUS = 36; // a tier's bus, this far out from its cards' edge
const PITCH = NODE_W + GAP_X;

/**
 * Tidy tree layout. Every object's children are a "fan": one trunk from its
 * port, a bus per tier, a drop per child. A fan's children sit in one row
 * centred under it, each as wide as its own subtree; when there are more of
 * them than `cols` fit across the view, the childless ones wrap into tiers
 * of `cols` (past the first bus the trunk runs down the gutter beside the
 * middle column) and the ones with children of their own form the last
 * tier. The up half is the mirror image
 * above the centre. Positions are card centres in world pixels, the centre
 * at (0, 0).
 *
 * Returns { pos: Map<key, {x, y}>, bounds, fans: [{ key, parent, dir, tiers:
 * [[key]], cols? }], place: Map<key, { fan, tier }> }.
 */
export function layout(items, cols = Infinity) {
  const centre = items.get("c");
  const kidsOf = (key, dir) => (key === "c" ? centre[dir] : items.get(key).children);
  const plans = new Map(); // fan key -> { wrap: [[key]] | null, row: [key] }
  const width = new Map();

  const plan = (key, dir) => {
    const kids = kidsOf(key, dir);
    const c = Math.max(2, cols);
    const leaves = kids.filter((k) => !items.get(k).children.length);
    const p = kids.length > c && leaves.length > 1
      ? { wrap: chunk(leaves, c), row: kids.filter((k) => items.get(k).children.length) }
      : { wrap: null, row: kids };
    plans.set(`${key}|${dir}`, p);
    return p;
  };
  const blockWidth = (tiers) => tiers[0].length * PITCH - GAP_X;
  const measureKids = (key, dir) => {
    const p = plan(key, dir);
    const rowW = p.row.length ? p.row.reduce((s, k) => s + measure(k), 0) + GAP_X * (p.row.length - 1) : 0;
    return Math.max(p.wrap ? blockWidth(p.wrap) : 0, rowW);
  };
  const measure = (key) => {
    const own = Math.max(NODE_W, measureKids(key, items.get(key).dir));
    width.set(key, own);
    return own;
  };

  const pos = new Map([["c", { x: 0, y: 0 }]]);
  const fans = [];
  const place = new Map();
  const placeKids = (key, dir, sign) => {
    const P = pos.get(key);
    const p = plans.get(`${key}|${dir}`);
    if (!p || (!p.row.length && !p.wrap)) return;
    const fan = { key: `${key}|${dir}`, parent: key, dir, tiers: [] };
    if (p.wrap) {
      const c = p.wrap[0].length;
      fan.cols = c;
      const left = P.x - ((c - 1) * PITCH) / 2;
      p.wrap.forEach((tier, t) => {
        tier.forEach((k, i) => pos.set(k, { x: left + i * PITCH, y: P.y + sign * (LEVEL + t * TIER) }));
        fan.tiers.push(tier);
      });
    }
    if (p.row.length) {
      const y = P.y + sign * (LEVEL + fan.tiers.length * TIER);
      const total = p.row.reduce((s, k) => s + width.get(k), 0) + GAP_X * (p.row.length - 1);
      let left = P.x - total / 2;
      for (const k of p.row) {
        pos.set(k, { x: left + width.get(k) / 2, y });
        left += width.get(k) + GAP_X;
      }
      fan.tiers.push(p.row);
    }
    fan.tiers.forEach((tier, t) => tier.forEach((k) => place.set(k, { fan, tier: t })));
    fans.push(fan);
    for (const k of p.row) placeKids(k, dir, sign);
  };
  for (const [half, sign] of [["down", 1], ["up", -1]]) {
    measureKids("c", half);
    placeKids("c", half, sign);
  }

  let minX = -NODE_W / 2, maxX = NODE_W / 2, minY = -NODE_H / 2, maxY = NODE_H / 2;
  for (const { x, y } of pos.values()) {
    minX = Math.min(minX, x - NODE_W / 2);
    maxX = Math.max(maxX, x + NODE_W / 2);
    minY = Math.min(minY, y - NODE_H / 2 - PORT);
    maxY = Math.max(maxY, y + NODE_H / 2 + PORT);
  }
  return { pos, bounds: { minX, maxX, minY, maxY }, fans, place };
}

function chunk(list, n) {
  const out = [];
  for (let i = 0; i < list.length; i += n) out.push(list.slice(i, i + n));
  return out;
}

/**
 * A fan's connectors, as SVG paths that run the arrow's way (downwards).
 * `spine` is the trunk and every tier's bus, drawn once for the fan: the
 * trunk meets the nearest bus at the parent's x, and in a wrapped fan
 * carries on to the farther buses down `gutter`, the gap left of the middle
 * column (the middle gap, for an even count). Each
 * child has its own `drop` (and, in the down half, its arrowhead), where its
 * label sits, and the `route` from the parent's port to it, for lighting.
 * Down half: the trunk leaves the parent's lower port and each drop ends on
 * a child's top. Up half: each drop leaves a child's bottom and the trunk
 * ends on the parent's upper port, under one arrowhead.
 */
export function fanPaths(fan, pos) {
  const P = pos.get(fan.parent);
  const down = fan.dir === "down";
  const tx = P.x;
  const port = down ? P.y + NODE_H / 2 + PORT : P.y - NODE_H / 2 - PORT;
  const arrowAt = (x, y) => `M${x - 4} ${y - 5}L${x} ${y}L${x + 4} ${y - 5}`;
  const buses = fan.tiers.map((tier) => {
    const edge = pos.get(tier[0]).y + (down ? -NODE_H / 2 : NODE_H / 2);
    const xs = tier.map((k) => pos.get(k).x);
    return { tier, edge, bus: down ? edge - BUS : edge + BUS, x0: Math.min(tx, ...xs), x1: Math.max(tx, ...xs) };
  });
  const gx = fan.cols ? tx - (fan.cols % 2 ? PITCH / 2 : 0) : tx;
  for (const b of buses) {
    b.x0 = Math.min(b.x0, gx);
    b.x1 = Math.max(b.x1, gx);
  }
  const near = buses[0].bus;
  const far = buses[buses.length - 1].bus;
  let spine = `M${tx} ${port}V${near}`;
  if (far !== near) spine += `M${gx} ${near}V${far}`;
  for (const b of buses) if (b.x1 > b.x0) spine += `M${b.x0} ${b.bus}H${b.x1}`;
  const drops = new Map();
  for (const b of buses) {
    for (const k of b.tier) {
      const x = pos.get(k).x;
      drops.set(k, {
        d: down ? `M${x} ${b.bus}V${b.edge}` : `M${x} ${b.edge}V${b.bus}`,
        arrow: down ? arrowAt(x, b.edge) : null,
        labelX: x,
        labelY: down ? b.edge - 17 : b.edge + 17,
        route:
          b.bus === near
            ? down ? `M${tx} ${port}V${near}H${x}V${b.edge}` : `M${x} ${b.edge}V${near}H${tx}V${port}`
            : down ? `M${tx} ${port}V${near}H${gx}V${b.bus}H${x}V${b.edge}` : `M${x} ${b.edge}V${b.bus}H${gx}V${near}H${tx}V${port}`,
      });
    }
  }
  return { spine, arrow: down ? null : arrowAt(tx, port), drops };
}

// Reference map check, over every readable file:
// - the whole file as the map opens (groups folded) and with Expand all:
//   every object on it exactly once as its own card, every link drawn
//   exactly once (a link card, or the contained card it names);
// - every object as the centre of a bow-tie, two levels opened both ways
//   and every group opened a page;
// and for each of those layouts: no crash, every card placed, no two cards
// of a column overlapping, and no two links crossing. Each layout is checked
// again with every object card open down to list its settings (a made-up
// number of rows per card, up to 60), which also makes them wider: no card
// may then reach into the next column, or past where its links start. Links between two
// columns share one curve (the same x at every step), so two of them cross
// exactly when their parents and their children come in opposite orders.
// Then a synthetic 40-member group checks paging and folding, and a small
// tree checks containment.
//
//   node scripts/refmap_check.mjs [base-url]     (default http://localhost:8080)
//
// Run it after changing frontend/src/components/refMapModel.js or
// backend/app/refmap.py. Needs a running app; it reads GET /api/files and
// /api/files/{f}/refmap.
import {
  indexGraph,
  buildTree,
  buildView,
  layout,
  openAll,
  cardBox,
  settingsH,
  PAGE,
  PORT_REACH,
  ROW_GAP,
} from "../frontend/src/components/refMapModel.js";

const base = process.argv[2] || "http://localhost:8080";
const listing = await (await fetch(`${base}/api/files`)).json();
const files = Array.isArray(listing) ? listing : listing.files;
let centres = 0;
let wholes = 0;
let biggest = { n: 0, at: "" };
let slowest = { ms: 0, at: "" };
const failures = [];

// Every object card open, with 0-60 rows by a hash of its key.
function grown(items) {
  const m = new Map();
  for (const it of items.values()) {
    if (it.kind !== "node") continue;
    let h = 0;
    for (const ch of it.key) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    m.set(it.key, settingsH({ length: h % 61 }));
  }
  return m;
}

function checkLayout(items, align, grow = new Map()) {
  const { pos, links, bounds } = layout(items, align, grow);
  const cols = new Map();
  const span = new Map(); // per side and depth: the column's left and right
  for (const it of items.values()) {
    const p = pos.get(it.key);
    if (!p || !Number.isFinite(p.x) || !Number.isFinite(p.y)) throw new Error(`${it.key} has no position`);
    if (it.parent != null && !links.has(it.key)) throw new Error(`${it.key} has no link`);
    if (!cols.has(p.x)) cols.set(p.x, []);
    const b = cardBox(it, p);
    if (b.bottom > bounds.maxY + 0.5 || b.right > bounds.maxX + 0.5 || b.left < bounds.minX - 0.5) throw new Error(`${it.key} runs out of the bounds`);
    cols.get(p.x).push([b.top, b.bottom, it.key]);
    const c = (it.dir === "up" ? -1 : 1) * it.depth;
    const s = span.get(c) || [Infinity, -Infinity];
    span.set(c, [Math.min(s[0], b.left), Math.max(s[1], b.right)]);
    if (it.parent != null) {
      // Its link starts clear of its parent's edge, and ends at its own.
      const pb = cardBox(items.get(it.parent), pos.get(it.parent));
      const [x0, , x1] = links.get(it.key).box;
      const ok = it.dir === "up" ? x0 === b.right && x1 <= pb.left : x0 >= pb.right && x1 === b.left;
      if (!ok) throw new Error(`${it.key}'s link doesn't run from edge to edge`);
    }
  }
  for (const [c, [left, right]] of span) {
    const r = span.get(c + 1);
    const l = span.get(c - 1);
    if ((c >= 0 && r && right + PORT_REACH > r[0]) || (c <= 0 && l && left - PORT_REACH < l[1])) throw new Error(`column ${c} reaches into the next`);
  }
  for (const [x, cards] of cols) {
    cards.sort((a, b) => a[0] - b[0]);
    for (let i = 1; i < cards.length; i++) {
      if (cards[i][0] - cards[i - 1][1] < ROW_GAP / 2 - 0.5) throw new Error(`cards overlap in column ${x}: ${cards[i - 1][2]}, ${cards[i][2]}`);
    }
  }
  // The links of each gap (side and depth), by parent then child: the
  // children must come in order too.
  const gaps = new Map();
  for (const it of items.values()) {
    if (it.parent == null) continue;
    const g = `${it.dir === "up" ? -1 : 1}|${it.depth}`;
    if (!gaps.has(g)) gaps.set(g, []);
    gaps.get(g).push([pos.get(it.parent).y, pos.get(it.key).y, it.key]);
  }
  for (const list of gaps.values()) {
    list.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    for (let i = 1; i < list.length; i++) {
      if (list[i][1] < list[i - 1][1] - 0.01) throw new Error(`links cross: ${list[i - 1][2]} and ${list[i][2]}`);
    }
  }
}

function checkWhole(g, items, all) {
  const cards = new Map();
  const links = new Map();
  for (const it of items.values()) {
    if (it.kind === "node") cards.set(it.id, (cards.get(it.id) || 0) + 1);
    if (it.parent == null) continue;
    const from = items.get(it.parent).id;
    for (const e of it.edges) if (e.kind !== "contains") links.set(`${from}>${it.id}`, (links.get(`${from}>${it.id}`) || 0) + 1);
  }
  for (const [id, n] of cards) if (n > 1) throw new Error(`${id} has ${n} cards`);
  if (!all) return;
  for (const n of g.byId.values()) if (!n.missing && !cards.has(n.id)) throw new Error(`${n.id} isn't on the map`);
  for (const [s, m] of g.out) {
    for (const t of m.keys()) if (!links.has(`${s}>${t}`)) throw new Error(`the link ${s} → ${t} isn't drawn`);
  }
}

function centred(g, root) {
  const expanded = { up: new Set(), down: new Set() };
  const pages = new Map();
  let items = buildView(g, root, expanded, pages);
  for (let level = 0; level < 2; level++) {
    for (const it of items.values()) {
      if (it.kind === "node" && it.key !== "c") expanded[it.dir].add(it.id);
      if (it.kind === "group") pages.set(it.groupKey, 1);
    }
    items = buildView(g, root, expanded, pages);
  }
  checkLayout(items);
  checkLayout(items, "middle", grown(items));
}

const timed = (at, fn) => {
  const t = performance.now();
  try {
    fn();
  } catch (e) {
    failures.push(`${at}: ${e.message}`);
  }
  const ms = performance.now() - t;
  if (ms > slowest.ms) slowest = { ms, at };
};

for (const f of files) {
  const res = await fetch(`${base}/api/files/${encodeURIComponent(f.name)}/refmap`);
  if (!res.ok) continue; // not XML: the tree refuses it too
  const data = await res.json();
  const g = indexGraph(data);
  wholes++;
  timed(`${f.name}: whole file`, () => {
    const items = buildTree(g, new Set(), new Map());
    checkWhole(g, items, false);
    checkLayout(items, "top");
    checkLayout(items, "top", grown(items));
  });
  timed(`${f.name}: whole file, all open`, () => {
    const items = buildTree(g, new Set(), openAll((_, p) => buildTree(g, new Set(), p)).pages);
    if (items.size > biggest.n) biggest = { n: items.size, at: f.name };
    checkWhole(g, items, true);
    checkLayout(items, "top");
    checkLayout(items, "top", grown(items));
  });
  for (const root of new Set([...data.nodes.map((n) => n.id), ...data.edges.flatMap((e) => [e.s, e.t])])) {
    centres++;
    timed(`${f.name}: centred on ${root}`, () => centred(g, root));
  }
}
console.log(
  `${files.length} files, ${wholes} whole maps, ${centres} centres, ${failures.length} failures; ` +
    `slowest ${slowest.ms.toFixed(1)} ms (${slowest.at.split(": ").pop()}); biggest all-open map ${biggest.n} cards`
);
failures.slice(0, 20).forEach((x) => console.log("  " + x));

// Paging: 40 objects of one class pointing at one target show as a group,
// then 18, 36 and 40 of them, with the group's tail card after the members
// shown; folding (no pages) shows the group again.
const nodes = [{ id: "R-1/T-1", cls: "T" }];
const edges = [];
for (let i = 1; i <= 40; i++) {
  nodes.push({ id: `R-1/S-${i}`, cls: "S" });
  edges.push({ s: `R-1/S-${i}`, t: "R-1/T-1", via: "x", at: `R-1/S-${i}::p::x`, kind: "ref" });
}
const g = indexGraph({ nodes, edges, stats: {} });
const none = { up: new Set(), down: new Set() };
const upOf = (v) => v.get("c").children.filter((k) => v.get(k).dir === "up").map((k) => v.get(k));
const first = buildView(g, "R-1/T-1", none, new Map());
const group = [...first.values()].find((i) => i.kind === "group");
const paging = [group ? "ok" : "no group"];
for (const n of [1, 2, 3]) {
  const up = upOf(buildView(g, "R-1/T-1", none, new Map([[group?.groupKey, n]])));
  const shown = up.filter((i) => i.kind === "node").length;
  const more = up.findIndex((i) => i.kind === "more");
  const want = Math.min(40, n * PAGE);
  const tail = up[more];
  paging.push(shown === want && more === up.length - 1 && tail.left === 40 - want ? "ok" : `page ${n}: ${shown} shown`);
}
const folded = buildView(g, "R-1/T-1", none, new Map());
paging.push([...folded.values()].some((i) => i.kind === "group") ? "ok" : "fold: no group");
const pagingOk = paging.every((x) => x === "ok");
console.log(`paging: ${pagingOk ? "ok" : paging.join(", ")}`);

// Containment: an object sits in its nearest ancestor the file has (X-1 is
// a gap, so Y-1 sits in A-1); one both contained and referenced is one card,
// a reference; contents come after the references and fold apart from them.
// In the whole file, a reference to an object elsewhere is a link card.
const tree = indexGraph({
  nodes: ["A-1", "A-1/B-1", "A-1/B-1/C-1", "A-1/X-1/Y-1", ...Array.from({ length: 8 }, (_, i) => `A-1/B-1/D-${i + 1}`)].map(
    (id) => ({ id, cls: id.split("/").pop().replace(/-.*/, "") })
  ),
  edges: [
    { s: "A-1", t: "A-1/B-1", via: "bDN", at: "A-1::p::bDN", kind: "ref" },
    { s: "A-1/B-1", t: "A-1/X-1/Y-1", via: "yDN", at: "A-1/B-1::p::yDN", kind: "ref" },
  ],
  stats: {},
});
const contain = [];
const half = (v, dir) => v.get("c").children.filter((k) => v.get(k).dir === dir).map((k) => v.get(k));
const a = buildView(tree, "A-1", none, new Map());
const aDown = half(a, "down");
const b = aDown.find((i) => i.id === "A-1/B-1");
if (!b || b.held || !b.edges.some((e) => e.kind === "ref") || !b.edges.some((e) => e.kind === "contains")) contain.push("B-1 not one card, a reference");
if (!aDown.find((i) => i.id === "A-1/X-1/Y-1")?.held) contain.push("Y-1 not held by A-1 across the gap");
if (aDown.findIndex((i) => i.held) < aDown.findIndex((i) => !i.held)) contain.push("contents before references");
const bv = buildView(tree, "A-1/B-1", none, new Map());
const bUp = half(bv, "up");
if (!bUp.some((i) => i.id === "A-1" && !i.held) || bUp.length !== 1) contain.push("B-1's container (and referrer) A-1 not left of it once");
const bDown = half(bv, "down");
if (bDown[0]?.id !== "A-1/X-1/Y-1" || bDown[0].held) contain.push("B-1's reference not first");
if (!bDown.some((i) => i.id === "A-1/B-1/C-1" && i.held)) contain.push("C-1 not under B-1");
const d = bDown.find((i) => i.kind === "group");
if (!d?.held || d.count !== 8 || d.groupCard !== d.key) contain.push("D group not folded as contents");
const c = half(buildView(tree, "A-1/B-1/C-1", none, new Map()), "up");
if (c.length !== 1 || c[0].id !== "A-1/B-1" || !c[0].held) contain.push("C-1's container not left of it");
const w = buildTree(tree, new Set(), new Map());
const wb = [...w.values()].filter((i) => i.id === "A-1/B-1");
if (wb.length !== 1 || wb[0].kind !== "node" || !wb[0].edges.some((e) => e.kind === "ref")) contain.push("whole: B-1 not one card, a reference");
const wy = [...w.values()].filter((i) => i.id === "A-1/X-1/Y-1");
if (wy.length !== 2 || !wy.some((i) => i.kind === "ghost" && items(w, i.parent).id === "A-1/B-1") || !wy.some((i) => i.kind === "node"))
  contain.push("whole: Y-1 not its card plus B-1's link card");
const shut = buildTree(tree, new Set(["A-1/B-1"]), new Map());
if ([...shut.values()].some((i) => i.id?.startsWith("A-1/B-1/"))) contain.push("whole: a collapsed B-1 still shows its contents");
console.log(`containment: ${contain.length ? contain.join(", ") : "ok"}`);
function items(v, key) {
  return v.get(key);
}
process.exit(failures.length || !pagingOk || contain.length ? 1 : 0);

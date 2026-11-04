// Reference map check: every object of every readable file as the Map
// view's centre, two levels opened both ways and every group opened a page,
// laid out unwrapped and wrapped at 3 cards. Fails on a crash, a card
// without a position or a fan, two cards overlapping, a fan whose trunk
// would cross one of its own cards, or a wrapped tier mixing references
// with contained objects. Then a synthetic 40-member group checks paging
// and folding, and a small tree checks containment.
//
//   node scripts/refmap_check.mjs [base-url]     (default http://localhost:8080)
//
// Run it after changing frontend/src/components/refMapModel.js or
// backend/app/refmap.py. Needs a running app; it reads GET /api/files and
// /api/files/{f}/refmap.
import { indexGraph, buildView, layout, fanPaths, GAP_X, NODE_W, PAGE } from "../frontend/src/components/refMapModel.js";

const base = process.argv[2] || "http://localhost:8080";
const listing = await (await fetch(`${base}/api/files`)).json();
const files = Array.isArray(listing) ? listing : listing.files;
let centres = 0;
let slowest = { ms: 0, at: "" };
const failures = [];

function check(g, root) {
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
  for (const cols of [Infinity, 3]) {
    const { pos, fans, place } = layout(items, cols);
    const rows = new Map();
    for (const it of items.values()) {
      const p = pos.get(it.key);
      if (!p) throw new Error(`${it.key} has no position`);
      if (it.key !== "c" && !place.has(it.key)) throw new Error(`${it.key} is in no fan`);
      if (!rows.has(p.y)) rows.set(p.y, []);
      rows.get(p.y).push(p.x);
    }
    for (const [y, xs] of rows) {
      xs.sort((a, b) => a - b);
      for (let i = 1; i < xs.length; i++) if (xs[i] - xs[i - 1] < NODE_W - 0.5) throw new Error(`cards overlap at y ${y} (cols ${cols})`);
    }
    for (const fan of fans) {
      const fp = fanPaths(fan, pos);
      if (fan.cols) {
        // Wrapped: references first, then what is contained, never in one tier.
        const held = fan.tiers.map((tier) => tier.filter((k) => !items.get(k).children.length).map((k) => !!items.get(k).held));
        if (held.some((t) => t.some((h) => h !== t[0]))) throw new Error(`${fan.key} mixes references and contents in a tier`);
        const order = held.flat();
        if (order.some((h, i) => i && order[i - 1] && !h)) throw new Error(`${fan.key} has a reference after its contents`);
      }
      for (const k of fan.tiers.flat()) if (!fp.drops.get(k)) throw new Error(`no drop for ${k}`);
      // Past the first bus a wrapped fan's trunk runs down its gutter through
      // every tier but the last: no card in those tiers may sit across it.
      const tx = pos.get(fan.parent).x;
      const gx = fan.cols ? tx - (fan.cols % 2 ? (NODE_W + GAP_X) / 2 : 0) : tx;
      for (const tier of fan.tiers.slice(0, -1)) {
        for (const k of tier) if (Math.abs(pos.get(k).x - gx) < NODE_W / 2) throw new Error(`trunk of ${fan.key} crosses ${k}`);
      }
    }
  }
}

for (const f of files) {
  const res = await fetch(`${base}/api/files/${encodeURIComponent(f.name)}/refmap`);
  if (!res.ok) continue; // not XML: the tree refuses it too
  const data = await res.json();
  const g = indexGraph(data);
  for (const root of new Set([...data.nodes.map((n) => n.id), ...data.edges.flatMap((e) => [e.s, e.t])])) {
    centres++;
    const t = performance.now();
    try {
      check(g, root);
    } catch (e) {
      failures.push(`${f.name}: centred on ${root}: ${e.message}`);
    }
    const ms = performance.now() - t;
    if (ms > slowest.ms) slowest = { ms, at: `${f.name}, ${root.split("/").pop()}` };
  }
}
console.log(`${files.length} files, ${centres} centres, ${failures.length} failures; slowest ${slowest.ms.toFixed(1)} ms (${slowest.at})`);
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
const first = buildView(g, "R-1/T-1", none, new Map());
const group = [...first.values()].find((i) => i.kind === "group");
const paging = [group ? "ok" : "no group"];
for (const n of [1, 2, 3]) {
  const v = buildView(g, "R-1/T-1", none, new Map([[group?.groupKey, n]]));
  const up = v.get("c").up.map((k) => v.get(k));
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
const at = (v, half) => v.get("c")[half].map((k) => v.get(k));
const a = buildView(tree, "A-1", none, new Map());
const aDown = at(a, "down");
const b = aDown.find((i) => i.id === "A-1/B-1");
if (!b || b.held || !b.edges.some((e) => e.kind === "ref") || !b.edges.some((e) => e.kind === "contains")) contain.push("B-1 not one card, a reference");
if (!aDown.find((i) => i.id === "A-1/X-1/Y-1")?.held) contain.push("Y-1 not held by A-1 across the gap");
if (aDown.findIndex((i) => i.held) < aDown.findIndex((i) => !i.held)) contain.push("contents before references");
const bv = buildView(tree, "A-1/B-1", none, new Map());
const bUp = at(bv, "up");
if (!bUp.some((i) => i.id === "A-1" && !i.held) || bUp.length !== 1) contain.push("B-1's container (and referrer) A-1 not above it once");
const bDown = at(bv, "down");
if (bDown[0]?.id !== "A-1/X-1/Y-1" || bDown[0].held) contain.push("B-1's reference not first");
if (!bDown.some((i) => i.id === "A-1/B-1/C-1" && i.held)) contain.push("C-1 not under B-1");
const d = bDown.find((i) => i.kind === "group");
if (!d?.held || d.count !== 8 || d.groupCard !== d.key) contain.push("D group not folded as contents");
const c = at(buildView(tree, "A-1/B-1/C-1", none, new Map()), "up");
if (c.length !== 1 || c[0].id !== "A-1/B-1" || !c[0].held) contain.push("C-1's container not above it");
console.log(`containment: ${contain.length ? contain.join(", ") : "ok"}`);
process.exit(failures.length || !pagingOk || contain.length ? 1 : 0);

function nodeMatches(node, q) {
  if (node.label && node.label.toLowerCase().includes(q)) return true;
  if (node.value && String(node.value).toLowerCase().includes(q)) return true;
  if (node.class && node.class.toLowerCase().includes(q)) return true;
  if (node.fullClass && node.fullClass.toLowerCase().includes(q)) return true;
  return false;
}

/**
 * Prunes a tree down to nodes that match `query` plus the ancestor chain
 * needed to reach them. If a node itself matches, its original (unpruned)
 * subtree is kept intact so the user can keep browsing normally from there;
 * if only some descendant matches, only the path down to those matches is
 * kept, and matching nodes are flagged with `_matched` for highlighting.
 */
export function filterTree(nodes, query) {
  const q = query.trim().toLowerCase();
  if (!q) return nodes;

  function walk(node) {
    const selfMatch = nodeMatches(node, q);
    if (selfMatch) {
      return { ...node, _matched: true };
    }
    const childMatches = (node.children || []).map(walk).filter(Boolean);
    if (childMatches.length > 0) {
      return { ...node, children: childMatches, _matched: false };
    }
    return null;
  }

  return nodes.map(walk).filter(Boolean);
}

/** Collects the ids of every node (in the given array of root nodes, or a
 * single root node) that has at least one child -- i.e. every id an
 * "expand all" action needs to add to the expanded-set. */
export function collectExpandableIds(nodeOrNodes) {
  const roots = Array.isArray(nodeOrNodes) ? nodeOrNodes : [nodeOrNodes];
  const ids = [];
  function walk(node) {
    if (node.children && node.children.length > 0) {
      ids.push(node.id);
      node.children.forEach(walk);
    }
  }
  roots.forEach(walk);
  return ids;
}

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

/**
 * Parses Nokia's own official-dictionary "3GPP Reference" text (e.g.
 * "• 3GPP Reference: TS36.331" or a multi-line string listing several)
 * into a deduped list of {spec, url} pairs, so the Explain panel can render
 * real clickable links instead of a plain-text citation. `spec` here is
 * exactly this Nokia-sourced data -- see merge_official_reference.py -- not
 * something guessed; the parsing just extracts the spec number and builds
 * the (verified, public, no-login) 3GPP archive URL for it.
 */
export function parseThreeGppRefs(raw) {
  if (!raw) return [];
  const seen = new Set();
  const out = [];
  for (const m of raw.matchAll(/TS\s*(\d+\.\d+)/g)) {
    const spec = m[1];
    if (seen.has(spec)) continue;
    seen.add(spec);
    const series = spec.split(".")[0];
    out.push({ spec, url: `https://www.3gpp.org/ftp/Specs/archive/${series}_series/${spec}/` });
  }
  return out;
}

const DATE_RE = /(20\d{2})(\d{2})(\d{2})(?:-(\d{2})(\d{2}))?(?!\d)/g;
const BAND_RE = /(Band|[Bbn])(\d{1,3})(?![0-9A-Za-z])/g;

/**
 * Best-effort metadata from a Nokia export's file name, e.g.
 * "Configuration_scf_MRBTS-1_DHI_NR_n78_20260414-0827.xml" ->
 * { date: "2026-04-14 08:27", bands: ["n78"] }. BTS Site Manager / WebEM
 * name exports <Type>_<site>_<YYYYMMDD[-HHMM]>; anything that doesn't fit
 * is left null/empty.
 * When a name carries several dates (e.g. "..._modified_20260510-1947"),
 * the last one is used, since it's the most recent save.
 */
export function parseFileName(name) {
  const base = name.replace(/\.xml.*$/i, "");

  let date = null;
  for (const m of base.matchAll(DATE_RE)) {
    const [, y, mo, d, hh, mm] = m;
    if (+mo < 1 || +mo > 12 || +d < 1 || +d > 31) continue;
    if (hh !== undefined && (+hh > 23 || +mm > 59)) continue;
    date = `${y}-${mo}-${d}` + (hh !== undefined ? ` ${hh}:${mm}` : "");
  }

  const bands = [];
  for (const [, prefix, num] of base.matchAll(BAND_RE)) {
    const band = (prefix === "n" ? "n" : "B") + String(+num);
    if (!bands.includes(band)) bands.push(band);
  }

  return { date, bands };
}

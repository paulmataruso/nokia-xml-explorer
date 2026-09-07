/** Path of node ids from the root down to (and including) targetId, or null
 * if targetId isn't present in this tree. Used to know which ancestors to
 * auto-expand before scrolling a node into view. */
export function findPath(node, targetId, path = []) {
  const newPath = [...path, node.id];
  if (node.id === targetId) return newPath;
  for (const child of node.children || []) {
    const res = findPath(child, targetId, newPath);
    if (res) return res;
  }
  return null;
}

/** Same as findPath, but for a forest (array of root nodes) -- used for the
 * logical tree, whose top level is `tree.children`, an array rather than a
 * single root object like the raw tree's. */
export function findPathInForest(roots, targetId) {
  for (const root of roots || []) {
    const path = findPath(root, targetId);
    if (path) return path;
  }
  return null;
}

/** The actual node object (not just its id) matching targetId, or null.
 * Used to re-point ExplainPanel's selectedNode at the fresh copy after a
 * refetch (e.g. after adding/editing a parameter) -- selectedNode is a
 * plain object reference frozen at double-click time, so without this it
 * would keep showing a stale snapshot even after the underlying tree
 * state updates. */
export function findNodeInForest(roots, targetId) {
  function walk(node) {
    if (node.id === targetId) return node;
    for (const child of node.children || []) {
      const found = walk(child);
      if (found) return found;
    }
    return null;
  }
  for (const root of roots || []) {
    const found = walk(root);
    if (found) return found;
  }
  return null;
}

function rawNodeMatches(node, q) {
  if (node.tag && node.tag.toLowerCase().includes(q)) return true;
  if (node.text && node.text.toLowerCase().includes(q)) return true;
  for (const [k, v] of Object.entries(node.attrs || {})) {
    if (k.toLowerCase().includes(q)) return true;
    if (v != null && String(v).toLowerCase().includes(q)) return true;
  }
  return false;
}

/** Every node id (in document order) whose tag, attributes, or text contain
 * `query` (case-insensitive). */
export function collectRawMatches(root, query) {
  const q = query.trim().toLowerCase();
  const out = [];
  if (!q) return out;
  function walk(node) {
    if (rawNodeMatches(node, q)) out.push(node.id);
    for (const child of node.children || []) walk(child);
  }
  walk(root);
  return out;
}

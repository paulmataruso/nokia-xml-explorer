import React, { memo } from "react";
import { highlightSegments } from "./Highlight.jsx";
import { EditableValue } from "./EditableValue.jsx";
import { Icon } from "./Icon.jsx";
import { collectExpandableIds } from "../utils.js";
import { nodeConfidence } from "../knowledge.js";

// Each line of the raw view is a list of [kind, text] tokens rather than one
// string, so it can be set in syntax ink levels (see .x-* in styles.css):
// punctuation and attribute names recede, values read brightest.
function attrTokens(attrs) {
  const out = [];
  for (const [k, v] of Object.entries(attrs || {})) {
    out.push(["punct", " "], ["attr", k], ["punct", '="'], ["val", String(v)], ["punct", '"']);
  }
  return out;
}

function openTag(node) {
  return [["punct", "<"], ["tag", node.tag], ...attrTokens(node.attrs), ["punct", ">"]];
}
function selfClosingTag(node) {
  return [["punct", "<"], ["tag", node.tag], ...attrTokens(node.attrs), ["punct", "/>"]];
}
function closeTag(node) {
  return [["punct", "</"], ["tag", node.tag], ["punct", ">"]];
}
function leafLine(node) {
  return [...openTag(node), ["text", node.text], ...closeTag(node)];
}

/**
 * Renders syntax tokens with search matches highlighted. Matches are found
 * on the whole line first (so a query like name="pMax" still marks across
 * token boundaries), then split back along the token edges.
 */
function SyntaxLine({ tokens, query }) {
  const segments = highlightSegments(tokens.map((t) => t[1]).join(""), query);
  const out = [];
  let ti = 0;
  let offset = 0;
  for (const seg of segments) {
    let rest = seg.text;
    while (rest.length > 0 && ti < tokens.length) {
      const [kind, text] = tokens[ti];
      const take = Math.min(text.length - offset, rest.length);
      const piece = rest.slice(0, take);
      out.push(
        <span key={out.length} className={`x-${kind}`}>
          {seg.match ? <mark>{piece}</mark> : piece}
        </span>
      );
      rest = rest.slice(take);
      offset += take;
      if (offset >= text.length) {
        ti += 1;
        offset = 0;
      }
    }
  }
  return <span className="mono raw-text">{out}</span>;
}

function RequiredBadge({ node }) {
  if (!node.requiredMissing) return null;
  return (
    <span className="tag tag-required-missing" title="Mandatory per Nokia's docs but has no value yet">
      <Icon name="alert" size={12} />
      required
    </span>
  );
}

// Same render-skipping idea as TreeView's sameRow: below the document
// wrappers, ids are prefix-structured (a <p>'s id is its managedObject's
// distName + "::p::name"), so a focus change only re-renders the rows it
// actually moves between. The wrappers (<raml>, <cmData>, <header>) hold
// flat managedObject siblings whose ids don't share their prefix, so they
// always re-render -- there are only a handful of them.
const PREFIXED_TAGS = new Set(["managedObject", "p", "list", "item"]);
const RAW_SHARED_PROPS = [
  "node",
  "depth",
  "expanded",
  "editedIds",
  "query",
  "editable",
  "kb",
  "onToggle",
  "onToggleSubtree",
  "onActivate",
  "onSaveEdit",
  "onContextMenu",
];

function inSubtree(id, target) {
  return target != null && (target === id || target.startsWith(id + "/") || target.startsWith(id + "::"));
}

function sameRawRow(prev, next) {
  for (const k of RAW_SHARED_PROPS) if (prev[k] !== next[k]) return false;
  for (const k of ["focusId", "tabbableId"]) {
    if (prev[k] === next[k]) continue;
    if (!PREFIXED_TAGS.has(next.node.tag)) return false;
    if (inSubtree(next.node.id, prev[k]) || inSubtree(next.node.id, next[k])) return false;
  }
  return true;
}

/**
 * Keyboard model: the same WAI-ARIA tree pattern as the object tree, over a
 * flat list of lines. One row is tabbable at a time (tabbableId, owned by
 * App); arrows move focus and the shared focus follows it. Closing-tag lines
 * aren't items, so the arrows skip them. Rows are found in DOM order, which
 * is exactly the visible order; a row's parent is the nearest row above it
 * with a lower aria-level.
 */
function rawItems(fromEl) {
  const tree = fromEl.closest('[role="tree"]');
  return tree ? [...tree.querySelectorAll('[role="treeitem"]')] : [];
}

const RawRow = memo(function RawRow({
  node,
  depth,
  expanded,
  onToggle,
  onToggleSubtree,
  onActivate,
  focusId,
  tabbableId,
  editedIds,
  query,
  editable,
  onSaveEdit,
  onContextMenu,
  kb,
}) {
  const hasChildren = !!(node.children && node.children.length > 0);
  const isEmpty = !hasChildren && node.text == null;
  const isLeafText = !hasChildren && node.text != null;
  const isOpen = expanded.has(node.id);
  const isFocused = node.id === focusId;
  const pad = 6 + depth * 16;
  const isOfficial = nodeConfidence(node, kb) === "official";
  const rowClass =
    "raw-row" +
    (isFocused ? " focused" : "") +
    (node.requiredMissing ? " required-missing" : "") +
    (isOfficial ? " official-doc" : "") +
    (editedIds?.has(node.id) ? " edited" : "");
  const canEditThis = editable && node.tag === "p";

  const handleClick = () => {
    if (hasChildren) {
      // Same reasoning as TreeView: a <list>'s <item> rows are each
      // independently collapsed by default, so expand the whole
      // list+rows+fields subtree in one click instead of one level at a time.
      if (node.tag === "list" && onToggleSubtree) {
        onToggleSubtree(collectExpandableIds(node), !isOpen);
      } else {
        onToggle(node.id);
      }
    }
    onActivate && onActivate(node);
  };
  const handleContextMenu = (e) => {
    if (!editable || !onContextMenu) return;
    onContextMenu(e, node);
  };

  // The shared focus follows keyboard focus. A click focuses the row too,
  // so skip the row that already holds the shared focus.
  const handleFocus = (e) => {
    if (e.target !== e.currentTarget || isFocused) return;
    onActivate && onActivate(node);
  };

  const handleKeyDown = (e) => {
    if (e.target !== e.currentTarget) return; // e.g. typing in an inline editor
    const row = e.currentTarget;
    const move = (target) => {
      if (!target) return;
      e.preventDefault();
      target.focus();
    };
    switch (e.key) {
      case "ArrowDown":
      case "ArrowUp": {
        const items = rawItems(row);
        const i = items.indexOf(row);
        move(items[e.key === "ArrowDown" ? i + 1 : i - 1]);
        break;
      }
      case "Home":
      case "End": {
        const items = rawItems(row);
        move(e.key === "Home" ? items[0] : items[items.length - 1]);
        break;
      }
      case "ArrowRight":
        e.preventDefault();
        if (hasChildren && !isOpen) onToggle(node.id);
        else if (hasChildren) {
          const items = rawItems(row);
          move(items[items.indexOf(row) + 1]);
        }
        break;
      case "ArrowLeft": {
        e.preventDefault();
        if (hasChildren && isOpen) {
          onToggle(node.id);
          break;
        }
        const items = rawItems(row);
        const above = items.slice(0, items.indexOf(row)).reverse();
        move(above.find((el) => Number(el.getAttribute("aria-level")) <= depth));
        break;
      }
      case "Enter":
        e.preventDefault();
        if (canEditThis) row.querySelector(".editable-value")?.click();
        else if (hasChildren) handleClick();
        break;
      case "ContextMenu":
      case "F10":
        if (e.key === "F10" && !e.shiftKey) break;
        if (editable && onContextMenu) {
          e.preventDefault();
          const rect = row.getBoundingClientRect();
          onContextMenu(
            { preventDefault() {}, stopPropagation() {}, clientX: rect.left + pad + 48, clientY: rect.bottom },
            node
          );
        }
        break;
      default:
    }
  };

  const rowProps = {
    className: rowClass,
    style: { paddingLeft: pad },
    "data-raw-id": node.id,
    role: "treeitem",
    "aria-level": depth + 1,
    "aria-selected": isFocused,
    tabIndex: tabbableId === node.id ? 0 : -1,
    onClick: handleClick,
    onContextMenu: handleContextMenu,
    onFocus: handleFocus,
    onKeyDown: handleKeyDown,
  };

  if (canEditThis) {
    return (
      <div {...rowProps}>
        <span className="raw-caret empty" />
        {/* No inline delete button in this pane: it shows the file exactly as
            written, and a button wedged into the tag broke that. Right-click
            the row (or use the tree pane) to delete. */}
        <SyntaxLine tokens={openTag(node)} />
        <EditableValue value={node.text} onSave={(v) => onSaveEdit(node.id, v)} knownValues={node.knownValues} />
        <SyntaxLine tokens={closeTag(node)} />
        <RequiredBadge node={node} />
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div {...rowProps}>
        <span className="raw-caret empty" />
        <SyntaxLine tokens={selfClosingTag(node)} query={query} />
        <RequiredBadge node={node} />
      </div>
    );
  }

  if (isLeafText) {
    return (
      <div {...rowProps}>
        <span className="raw-caret empty" />
        <SyntaxLine tokens={leafLine(node)} query={query} />
      </div>
    );
  }

  return (
    <>
      <div {...rowProps} aria-expanded={isOpen}>
        <span className="raw-caret">
          <Icon name={isOpen ? "chevron-down" : "chevron-right"} size={12} />
        </span>
        <SyntaxLine tokens={openTag(node)} query={query} />
      </div>
      {isOpen && (
        <>
          {node.children.map((c) => (
            <RawRow
              key={c.id}
              node={c}
              depth={depth + 1}
              expanded={expanded}
              onToggle={onToggle}
              onToggleSubtree={onToggleSubtree}
              onActivate={onActivate}
              focusId={focusId}
              tabbableId={tabbableId}
              editedIds={editedIds}
              query={query}
              editable={editable}
              onSaveEdit={onSaveEdit}
              onContextMenu={onContextMenu}
              kb={kb}
            />
          ))}
          <div className="raw-row raw-close" style={{ paddingLeft: pad }} aria-hidden="true">
            <span className="raw-caret empty" />
            <SyntaxLine tokens={closeTag(node)} />
          </div>
        </>
      )}
    </>
  );
}, sameRawRow);

export function RawXmlView({
  root,
  expanded,
  onToggle,
  onToggleSubtree,
  onActivate,
  focusId,
  tabbableId,
  editedIds,
  query,
  editable,
  onSaveEdit,
  onContextMenu,
  kb,
}) {
  return (
    <div className="raw-tree" role="tree" aria-label="Raw XML">
      <RawRow
        node={root}
        depth={0}
        expanded={expanded}
        onToggle={onToggle}
        onToggleSubtree={onToggleSubtree}
        onActivate={onActivate}
        focusId={focusId}
        tabbableId={tabbableId}
        editedIds={editedIds}
        query={query}
        editable={editable}
        onSaveEdit={onSaveEdit}
        onContextMenu={onContextMenu}
        kb={kb}
      />
    </div>
  );
}

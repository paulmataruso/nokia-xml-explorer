import React, { memo } from "react";
import { Highlight } from "./Highlight.jsx";
import { EditableValue } from "./EditableValue.jsx";
import { Icon } from "./Icon.jsx";
import { collectExpandableIds } from "../utils.js";
import { nodeConfidence } from "../knowledge.js";

// One indent step; must match the generated .d{n} rules in styles.css (row
// padding, value-column width and guide x all step by this much per level).
const INDENT = 16;
// x of depth 0's guide line: the 8px row inset plus the centre of the 12px caret.
const GUIDE_X0 = 13;

/**
 * Trace, the tree's depth guides: every nested level (the <ul> of an
 * expanded node's children) draws ONE dim vertical line down its whole
 * height, in its parent's fiber-code hue (.tree-level.d{n}::before in
 * styles.css). The lineage of the selected row is then drawn as a lit
 * ROUTE on top: on each level whose parent is on the lineage, the siblings
 * before the lineage child carry the lit line past them ("through") and the
 * lineage child carries it down to its own row ("end") -- so the route
 * reads root to row and stops there, instead of running on to the end of
 * every ancestor's group. One dim element per expanded node plus a lit
 * segment per sibling on the route, never one per row per ancestor: an
 * earlier per-row background version restyled all 23k rows of the largest
 * file whenever the root's line lit up. Depth geometry is static classes
 * (d0-d15); deeper levels, which no real file has, fall back to inline
 * styles.
 */
const STATIC_DEPTHS = 16;

function depthClass(depth) {
  return depth < STATIC_DEPTHS ? ` d${depth}` : " is-deep";
}

function deepLevelStyle(depth) {
  if (depth < STATIC_DEPTHS) return undefined;
  return { "--deep-x": `${GUIDE_X0 + (depth - 1) * INDENT}px` };
}

function deepRowStyle(depth) {
  return depth < STATIC_DEPTHS ? undefined : { paddingLeft: 8 + depth * INDENT };
}

/** Node ids are prefix-structured -- a descendant's id always starts with
 * its ancestor's id plus "/" or "::" (see parser.py) -- so "could this id be
 * this row or something under it" is a string-prefix check. */
function inSubtree(id, target) {
  return target != null && (target === id || target.startsWith(id + "/") || target.startsWith(id + "::"));
}

// Props that, when they change at all, can change any row.
const SHARED_PROPS = [
  "node",
  "depth",
  "route",
  "expanded",
  "editedIds",
  "forceExpand",
  "query",
  "editable",
  "kb",
  "onToggle",
  "onToggleSubtree",
  "onSelect",
  "onActivate",
  "onSaveEdit",
  "onDeleteObject",
  "onDeleteParam",
  "onContextMenu",
];
// Props naming one node: a change only matters to rows on the path to the
// old or new node (they render the selected/lit state, or pass it down).
const TARGET_PROPS = ["selectedId", "activeId", "traceId", "tabbableId"];

/**
 * Keyboard model (WAI-ARIA tree pattern): one treeitem is tabbable at a
 * time (tabbableId, owned by App); arrows move focus and selection follows
 * it, so the Explanation and raw-XML sync update as you go. Items are found
 * in DOM order, which is exactly the visible order.
 */
function treeItems(fromEl) {
  const tree = fromEl.closest('[role="tree"]');
  return tree ? [...tree.querySelectorAll('[role="treeitem"]')] : [];
}

/** A selection change re-renders only the rows on the old and new lineage,
 * instead of every row in the file. */
function sameRow(prev, next) {
  for (const k of SHARED_PROPS) if (prev[k] !== next[k]) return false;
  const id = next.node.id;
  for (const k of TARGET_PROPS) {
    if (prev[k] !== next[k] && (inSubtree(id, prev[k]) || inSubtree(id, next[k]))) return false;
  }
  return true;
}

export function TreeView({
  nodes,
  depth = 0,
  parentId = null,
  traceId,
  tabbableId,
  editedIds,
  expanded,
  onToggle,
  onToggleSubtree,
  onSelect,
  onActivate,
  selectedId,
  activeId,
  forceExpand,
  query,
  editable,
  onSaveEdit,
  onDeleteObject,
  onDeleteParam,
  onContextMenu,
  kb,
}) {
  // The route passes this level when its parent is a strict ancestor of the
  // trace target: it runs past the siblings before the lineage child and
  // ends at that child's row.
  const routeIndex =
    parentId != null && traceId !== parentId && inSubtree(parentId, traceId)
      ? nodes.findIndex((n) => inSubtree(n.id, traceId))
      : -1;
  return (
    <ul
      className={"tree-level" + (depth > 0 ? ` is-nested${depthClass(depth)}` : "")}
      role={depth === 0 ? "tree" : "group"}
      aria-label={depth === 0 ? "Object tree" : undefined}
      style={deepLevelStyle(depth)}
    >
      {nodes.map((node, i) => (
        <TreeRow
          key={node.id}
          node={node}
          depth={depth}
          route={i < routeIndex ? "through" : i === routeIndex ? "end" : null}
          traceId={traceId}
          tabbableId={tabbableId}
          editedIds={editedIds}
          expanded={expanded}
          onToggle={onToggle}
          onToggleSubtree={onToggleSubtree}
          onSelect={onSelect}
          onActivate={onActivate}
          selectedId={selectedId}
          activeId={activeId}
          forceExpand={forceExpand}
          query={query}
          editable={editable}
          onSaveEdit={onSaveEdit}
          onDeleteObject={onDeleteObject}
          onDeleteParam={onDeleteParam}
          onContextMenu={onContextMenu}
          kb={kb}
        />
      ))}
    </ul>
  );
}

const TreeRow = memo(function TreeRow({
  node,
  depth,
  route,
  traceId,
  tabbableId,
  editedIds,
  expanded,
  onToggle,
  onToggleSubtree,
  onSelect,
  onActivate,
  selectedId,
  activeId,
  forceExpand,
  query,
  editable,
  onSaveEdit,
  onDeleteObject,
  onDeleteParam,
  onContextMenu,
  kb,
}) {
  const hasChildren = !!(node.children && node.children.length > 0);
  const isOpen = forceExpand || expanded.has(node.id);
  const isSelected = selectedId === node.id;
  const isActive = activeId === node.id;
  const isOfficial = nodeConfidence(node, kb) === "official";
  const canEditThis = editable && node.kind === "param";
  const canDeleteObject = editable && node.kind === "mo" && onDeleteObject;
  const canDeleteParam = editable && node.kind === "param" && !node.mandatory && node.ownerDistName && onDeleteParam;

  const handleRowClick = () => {
    if (hasChildren) {
      // A "list" node's children are table rows (items), each of which is
      // independently collapsed by default -- one click on the list would
      // otherwise only reveal the rows, still collapsed, needing a further
      // click per row to see its fields. Expand/collapse the whole
      // list+rows+fields subtree in one click instead.
      if (node.kind === "list" && onToggleSubtree) {
        onToggleSubtree(collectExpandableIds(node), !isOpen);
      } else {
        onToggle(node.id);
      }
    }
    onActivate && onActivate(node);
    onSelect(node);
  };
  const handleDeleteObject = (e) => {
    e.stopPropagation();
    onDeleteObject(node);
  };
  const handleDeleteParam = (e) => {
    e.stopPropagation();
    onDeleteParam(node);
  };
  const handleContextMenu = (e) => {
    if (!editable || !onContextMenu) return;
    onContextMenu(e, node);
  };

  // Selection follows keyboard focus. Focus events bubble in React, so only
  // react to focus landing on this item itself, not on a descendant.
  const handleFocus = (e) => {
    if (e.target !== e.currentTarget) return;
    onActivate && onActivate(node);
    onSelect(node);
  };

  const handleKeyDown = (e) => {
    if (e.target !== e.currentTarget) return; // e.g. typing in an inline editor
    const li = e.currentTarget;
    const move = (target) => {
      if (!target) return;
      e.preventDefault();
      target.focus();
    };
    switch (e.key) {
      case "ArrowDown":
      case "ArrowUp": {
        const items = treeItems(li);
        const i = items.indexOf(li);
        move(items[e.key === "ArrowDown" ? i + 1 : i - 1]);
        break;
      }
      case "Home":
      case "End": {
        const items = treeItems(li);
        move(e.key === "Home" ? items[0] : items[items.length - 1]);
        break;
      }
      case "ArrowRight":
        e.preventDefault();
        if (hasChildren && !isOpen) onToggle(node.id);
        else if (hasChildren) move(li.querySelector('[role="group"] > [role="treeitem"]'));
        break;
      case "ArrowLeft":
        e.preventDefault();
        if (hasChildren && isOpen) onToggle(node.id);
        else move(li.parentElement.closest('[role="treeitem"]'));
        break;
      case "Enter":
        e.preventDefault();
        if (canEditThis) li.querySelector(".editable-value")?.click();
        else if (hasChildren) handleRowClick();
        break;
      case "Delete":
        if (canDeleteObject || canDeleteParam) {
          e.preventDefault();
          (canDeleteObject ? onDeleteObject : onDeleteParam)(node);
        }
        break;
      case "ContextMenu":
      case "F10":
        if (e.key === "F10" && !e.shiftKey) break;
        if (editable && onContextMenu) {
          e.preventDefault();
          const rect = li.firstElementChild.getBoundingClientRect();
          onContextMenu(
            { preventDefault() {}, stopPropagation() {}, clientX: rect.left + 48, clientY: rect.bottom },
            node
          );
        }
        break;
      default:
    }
  };

  const ariaLabel =
    node.kind === "param"
      ? `${node.label}: ${node.value == null || node.value === "" ? "empty" : node.value}${node.requiredMissing ? ", required" : ""}`
      : node.kind === "mo"
      ? `${node.label}, ${node.class}`
      : node.kind === "list"
      ? `${node.label}, table with ${node.rowCount ?? node.children.length} rows`
      : node.label;

  return (
    <li
      role="treeitem"
      aria-level={depth + 1}
      aria-expanded={hasChildren ? isOpen : undefined}
      aria-selected={isSelected}
      aria-label={ariaLabel}
      tabIndex={tabbableId === node.id ? 0 : -1}
      className={"tree-item" + (route ? ` route-${route}` : "")}
      onFocus={handleFocus}
      onKeyDown={handleKeyDown}
    >
      <div
        className={
          `tree-row kind-${node.kind}${depthClass(depth)}` +
          (isSelected ? " selected" : "") +
          (isActive ? " active" : "") +
          (node._matched ? " matched" : "") +
          (node.requiredMissing ? " required-missing" : "") +
          (isOfficial ? " official-doc" : "") +
          (editedIds?.has(node.id) ? " edited" : "")
        }
        style={deepRowStyle(depth)}
        data-tree-id={node.id}
        onClick={handleRowClick}
        onContextMenu={handleContextMenu}
        title={isOfficial ? "Explained verbatim from Nokia's official parameter dictionary" : undefined}
      >
        <span className={"caret" + (hasChildren ? "" : " empty")}>
          {hasChildren && <Icon name={isOpen ? "chevron-down" : "chevron-right"} size={12} />}
        </span>
        {/* The label cell is the fixed-width first column, so values line up
            down the whole list. The delete button lives at its right edge:
            near the row's start (long values and distNames make rows wider
            than the pane, and .tree-scroll scrolls horizontally, so anything
            anchored to the row's far end could be scrolled out of view), and
            inside the column so it never pushes the value sideways. It only
            shows on the hovered/selected row; right-click works anywhere on
            the row and also offers Rename for objects. */}
        <span className="tree-label-cell">
          {node.kind === "list" && <Icon name="table" size={12} className="tree-kind-icon" />}
          <Highlight className="tree-label" title={node.label} text={node.label} query={query} />
          {(canDeleteObject || canDeleteParam) && (
            <button
              className="node-delete-btn"
              onClick={canDeleteObject ? handleDeleteObject : handleDeleteParam}
              aria-label={canDeleteObject ? `Delete ${node.label} and everything under it` : `Delete parameter ${node.label}`}
              title={canDeleteObject ? "Delete this object (and everything under it)" : "Delete this parameter"}
            >
              <Icon name="x" size={12} />
            </button>
          )}
        </span>
        {node.kind === "mo" && node.class && <span className="tree-class">{node.class}</span>}
        {node.kind === "mo-placeholder" && <span className="tag tag-implied">implied</span>}
        {node.kind === "param" && canEditThis && (
          <span className="value">
            <EditableValue value={node.value} onSave={(v) => onSaveEdit(node.id, v)} knownValues={node.knownValues} />
          </span>
        )}
        {node.kind === "param" && !canEditThis && node.value != null && (
          <span className="value">
            <Highlight text={node.value} query={query} />
          </span>
        )}
        {node.kind === "param" && !canEditThis && node.value == null && (
          <span className="value empty">(empty)</span>
        )}
        {node.requiredMissing && (
          <span className="tag tag-required-missing" title="Mandatory per Nokia's docs but has no value yet">
            <Icon name="alert" size={12} />
            required
          </span>
        )}
        {node.kind === "list" && (
          <span className="tag">
            {(node.rowCount ?? node.children.length) === 1 ? "1 row" : `${node.rowCount ?? node.children.length} rows`}
          </span>
        )}
      </div>
      {hasChildren && isOpen && (
        <TreeView
          nodes={node.children}
          depth={depth + 1}
          parentId={node.id}
          traceId={traceId}
          tabbableId={tabbableId}
          editedIds={editedIds}
          expanded={expanded}
          onToggle={onToggle}
          onToggleSubtree={onToggleSubtree}
          onSelect={onSelect}
          onActivate={onActivate}
          selectedId={selectedId}
          activeId={activeId}
          forceExpand={forceExpand}
          query={query}
          editable={editable}
          onSaveEdit={onSaveEdit}
          onDeleteObject={onDeleteObject}
          onDeleteParam={onDeleteParam}
          onContextMenu={onContextMenu}
          kb={kb}
        />
      )}
    </li>
  );
}, sameRow);

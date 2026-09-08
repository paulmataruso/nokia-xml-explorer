import React from "react";
import { Highlight } from "./Highlight.jsx";
import { EditableValue } from "./EditableValue.jsx";
import { collectExpandableIds } from "../utils.js";

const KIND_META = {
  mo: { color: "#5aa9e6" },
  "mo-placeholder": { color: "#7d8590" },
  param: { color: "#d7ba7d" },
  list: { color: "#c894ff" },
  item: { color: "#9aa5b1" },
  fileinfo: { color: "#4dd0c8" },
  log: { color: "#4dd0c8" },
};

export function TreeView({
  nodes,
  depth = 0,
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
}) {
  return (
    <ul className="tree-level" role="group">
      {nodes.map((node) => (
        <TreeRow
          key={node.id}
          node={node}
          depth={depth}
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
        />
      ))}
    </ul>
  );
}

function TreeRow({
  node,
  depth,
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
}) {
  const hasChildren = !!(node.children && node.children.length > 0);
  const isOpen = forceExpand || expanded.has(node.id);
  const meta = KIND_META[node.kind] || { color: "#888" };
  const isSelected = selectedId === node.id;
  const isActive = activeId === node.id;
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

  return (
    <li>
      <div
        className={
          "tree-row" +
          (isSelected ? " selected" : "") +
          (isActive ? " active" : "") +
          (node._matched ? " matched" : "") +
          (node.requiredMissing ? " required-missing" : "")
        }
        style={{ paddingLeft: 8 + depth * 18 }}
        data-tree-id={node.id}
        onClick={handleRowClick}
        onContextMenu={handleContextMenu}
        title="Click to expand/collapse, sync with raw XML, and see a full explanation — right-click for more actions"
      >
        <span className={"caret" + (hasChildren ? "" : " empty")}>
          {hasChildren ? (isOpen ? "▾" : "▸") : ""}
        </span>
        <span className="kind-dot" style={{ background: meta.color }} />
        <Highlight className="tree-label" text={node.label} query={query} />
        {node.kind === "mo" && node.class && <span className="tag">{node.class}</span>}
        {node.kind === "mo-placeholder" && <span className="tag tag-implied">implied</span>}
        {/* Delete buttons sit right after the label/tag -- close to the row's
            left edge -- rather than at the row's far end: values, distNames,
            and required-badges can make a row much wider than the visible
            pane, and .tree-scroll scrolls horizontally, so anything anchored
            to "the end" of a long row can end up scrolled out of view. The
            right-click context menu (see App.jsx) works from anywhere on the
            row regardless, and also offers Rename for objects. */}
        {canDeleteObject && (
          <button
            className="node-delete-btn"
            onClick={handleDeleteObject}
            title="Delete this object (and everything under it)"
          >
            ×
          </button>
        )}
        {canDeleteParam && (
          <button
            className="node-delete-btn"
            onClick={handleDeleteParam}
            title="Delete this parameter"
          >
            ×
          </button>
        )}
        {node.kind === "param" && canEditThis && (
          <span className="value">
            = <EditableValue value={node.value} onSave={(v) => onSaveEdit(node.id, v)} />
          </span>
        )}
        {node.kind === "param" && !canEditThis && node.value != null && (
          <span className="value">
            = <Highlight text={node.value} query={query} />
          </span>
        )}
        {node.kind === "param" && !canEditThis && node.value == null && (
          <span className="value empty">(empty)</span>
        )}
        {node.requiredMissing && (
          <span className="tag tag-required-missing" title="Mandatory per Nokia's docs but has no value yet">
            ⚠ required
          </span>
        )}
        {node.kind === "list" && (
          <span className="tag">{node.rowCount ?? node.children.length} rows</span>
        )}
      </div>
      {hasChildren && isOpen && (
        <TreeView
          nodes={node.children}
          depth={depth + 1}
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
        />
      )}
    </li>
  );
}

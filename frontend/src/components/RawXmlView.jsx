import React from "react";
import { Highlight } from "./Highlight.jsx";
import { EditableValue } from "./EditableValue.jsx";
import { collectExpandableIds } from "../utils.js";

function attrString(attrs) {
  return Object.entries(attrs || {})
    .map(([k, v]) => ` ${k}="${v}"`)
    .join("");
}

function openTag(node) {
  return `<${node.tag}${attrString(node.attrs)}>`;
}
function selfClosingTag(node) {
  return `<${node.tag}${attrString(node.attrs)}/>`;
}
function closeTag(node) {
  return `</${node.tag}>`;
}
function leafLine(node) {
  return `${openTag(node)}${node.text}${closeTag(node)}`;
}

function RequiredBadge({ node }) {
  if (!node.requiredMissing) return null;
  return (
    <span className="tag tag-required-missing" title="Mandatory per Nokia's docs but has no value yet">
      ⚠ required
    </span>
  );
}

function RawRow({
  node,
  depth,
  expanded,
  onToggle,
  onToggleSubtree,
  onActivate,
  focusId,
  query,
  editable,
  onSaveEdit,
  onDeleteObject,
  onDeleteParam,
  onContextMenu,
}) {
  const hasChildren = !!(node.children && node.children.length > 0);
  const isEmpty = !hasChildren && node.text == null;
  const isLeafText = !hasChildren && node.text != null;
  const isOpen = expanded.has(node.id);
  const isFocused = node.id === focusId;
  const pad = 6 + depth * 16;
  const rowClass = "raw-row" + (isFocused ? " focused" : "") + (node.requiredMissing ? " required-missing" : "");
  const canEditThis = editable && node.tag === "p";
  const canDeleteParam = editable && node.tag === "p" && !node.mandatory && node.ownerDistName && onDeleteParam;
  const canDeleteObject = editable && node.tag === "managedObject" && onDeleteObject;

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
  const handleDeleteParam = (e) => {
    e.stopPropagation();
    onDeleteParam(node);
  };
  const handleDeleteObject = (e) => {
    e.stopPropagation();
    onDeleteObject(node);
  };
  const handleContextMenu = (e) => {
    if (!editable || !onContextMenu) return;
    onContextMenu(e, node);
  };

  if (canEditThis) {
    return (
      <div
        className={rowClass}
        style={{ paddingLeft: pad }}
        data-raw-id={node.id}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
      >
        <span className="raw-caret empty" />
        <span className="mono raw-text">{openTag(node)}</span>
        {/* Delete button goes right after the (short) opening tag, not at
            the row's end -- the value or a long distName/class attribute
            elsewhere in the row can push the end of the row past the
            visible edge of this horizontally-scrolling pane. Right-click
            anywhere on the row works regardless of row width. */}
        {canDeleteParam && (
          <button className="node-delete-btn" onClick={handleDeleteParam} title="Delete this parameter">
            ×
          </button>
        )}
        <EditableValue value={node.text} onSave={(v) => onSaveEdit(node.id, v)} knownValues={node.knownValues} />
        <span className="mono raw-text">{closeTag(node)}</span>
        <RequiredBadge node={node} />
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div
        className={rowClass}
        style={{ paddingLeft: pad }}
        data-raw-id={node.id}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
        title="Click to sync with the logical tree"
      >
        <span className="raw-caret empty" />
        <Highlight className="mono raw-text" text={selfClosingTag(node)} query={query} />
        <RequiredBadge node={node} />
      </div>
    );
  }

  if (isLeafText) {
    return (
      <div
        className={rowClass}
        style={{ paddingLeft: pad }}
        data-raw-id={node.id}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
        title="Click to sync with the logical tree"
      >
        <span className="raw-caret empty" />
        <Highlight className="mono raw-text" text={leafLine(node)} query={query} />
      </div>
    );
  }

  return (
    <>
      <div
        className={rowClass}
        style={{ paddingLeft: pad }}
        data-raw-id={node.id}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
        title="Click to expand/collapse and sync with the logical tree — right-click for more actions"
      >
        <span className="raw-caret">{isOpen ? "▾" : "▸"}</span>
        {canDeleteObject ? (
          <>
            {/* managedObject's opening tag has 3-4 attributes (class,
                distName, operation, version) and can easily run 80-150+
                characters -- put the delete button right after the bare tag
                name instead of after the whole thing, so it isn't scrolled
                out of view on a long row. */}
            <span className="mono raw-text">{`<${node.tag}`}</span>
            <button className="node-delete-btn" onClick={handleDeleteObject} title="Delete this object (and everything under it)">
              ×
            </button>
            <Highlight className="mono raw-text" text={`${attrString(node.attrs)}>`} query={query} />
          </>
        ) : (
          <Highlight className="mono raw-text" text={openTag(node)} query={query} />
        )}
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
              query={query}
              editable={editable}
              onSaveEdit={onSaveEdit}
              onDeleteObject={onDeleteObject}
              onDeleteParam={onDeleteParam}
              onContextMenu={onContextMenu}
            />
          ))}
          <div className="raw-row raw-close" style={{ paddingLeft: pad }}>
            <span className="raw-caret empty" />
            <span className="mono raw-text">{closeTag(node)}</span>
          </div>
        </>
      )}
    </>
  );
}

export function RawXmlView({
  root,
  expanded,
  onToggle,
  onToggleSubtree,
  onActivate,
  focusId,
  query,
  editable,
  onSaveEdit,
  onDeleteObject,
  onDeleteParam,
  onContextMenu,
}) {
  return (
    <div className="raw-tree">
      <RawRow
        node={root}
        depth={0}
        expanded={expanded}
        onToggle={onToggle}
        onToggleSubtree={onToggleSubtree}
        onActivate={onActivate}
        focusId={focusId}
        query={query}
        editable={editable}
        onSaveEdit={onSaveEdit}
        onDeleteObject={onDeleteObject}
        onDeleteParam={onDeleteParam}
        onContextMenu={onContextMenu}
      />
    </div>
  );
}

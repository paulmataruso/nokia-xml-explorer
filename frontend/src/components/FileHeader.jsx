import React from "react";
import { Icon } from "./Icon.jsx";
import { HistoryPanel } from "./HistoryPanel.jsx";
import { MiddleTruncate } from "./MiddleTruncate.jsx";
import { depthHue } from "../utils.js";

const SOURCE_LABELS = {
  upload: "Upload",
  scp: "Commissioning",
  example: "Example",
};

function Completeness({ completeness, onOpen }) {
  if (!completeness) return null;
  const { gaps, unverified, loading } = completeness;
  if (loading) {
    return <span className="fh-complete is-loading">Checking required fields…</span>;
  }
  const label =
    gaps > 0
      ? `${gaps.toLocaleString()} gap${gaps === 1 ? "" : "s"}`
      : unverified > 0
      ? "No gaps"
      : "Complete";
  return (
    <button
      className={"fh-complete" + (gaps > 0 ? " has-gaps" : " is-clear")}
      onClick={onOpen}
      title="Mandatory parameters without a value. Gaps were seen set in real files; unverified ones are documented but never observed in any sample file."
      aria-label={`Required fields: ${gaps} gaps, ${unverified} unverified. Open the list.`}
    >
      <Icon name={gaps > 0 ? "alert" : "check-circle"} />
      <span className="fh-complete-main">{label}</span>
      {unverified > 0 && <span className="fh-complete-sub">{unverified.toLocaleString()} unverified</span>}
    </button>
  );
}

/**
 * The Trace address: the selected row's lineage from the root, one segment
 * per ancestor, each banded in its depth's fiber-code hue -- the same hue
 * as that ancestor's guide line in the tree, so the address and the lit
 * guides read as one thing. Clicking a segment jumps to that ancestor.
 */
function TraceAddress({ path, onSelect }) {
  if (!path || path.length === 0) {
    return (
      <div className="trace is-empty">
        <span>Select a row to trace its address</span>
      </div>
    );
  }
  return (
    <nav className="trace" aria-label="Address of the selected row">
      <ol>
        {path.map((node, depth) => {
          const isLast = depth === path.length - 1;
          return (
            <li key={node.id}>
              {depth > 0 && <Icon name="chevron-right" size={12} className="trace-sep" />}
              <button
                className="trace-seg"
                style={{ "--seg-hue": depthHue(depth) }}
                onClick={() => onSelect(node)}
                aria-current={isLast ? "location" : undefined}
                title={node.kind === "mo" || node.kind === "mo-placeholder" ? node.id : node.label}
              >
                {node.kind === "fileinfo" ? "File Info" : node.label}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function FileHeader({
  file,
  stats,
  tracePath,
  onTraceSelect,
  completeness,
  onOpenRequired,
  editable,
  editMode,
  onToggleEdit,
  onEditCopy,
  duplicating,
  downloadHref,
  history,
}) {
  return (
    <header className="file-header">
      <div className="fh-row">
        <span className={"source-badge source-" + file.source}>
          {SOURCE_LABELS[file.source] || file.source}
          {!editable && <span className="source-badge-ro"> · read-only</span>}
        </span>
        <h1 className="fh-name" title={file.name}>
          <MiddleTruncate text={file.name} />
        </h1>
        <div className="fh-actions">
          <Completeness completeness={completeness} onOpen={onOpenRequired} />
          {editable && (
            <div className="history-wrap">
              <button
                className="btn"
                onClick={history.toggle}
                aria-expanded={history.open}
                aria-label="History"
                title="Every edit saves a snapshot of the file first; restore any of them here"
              >
                <Icon name="history" />
                <span className="btn-label">History</span>
              </button>
              {history.open && (
                <HistoryPanel
                  snapshots={history.snapshots}
                  loading={history.loading}
                  error={history.error}
                  onRestore={history.onRestore}
                  restoringId={history.restoringId}
                />
              )}
            </div>
          )}
          <a
            className="btn"
            href={downloadHref}
            download={file.name}
            aria-label="Download"
            title="Save this file's current contents"
          >
            <Icon name="download" />
            <span className="btn-label">Download</span>
          </a>
          {editable ? (
            <button
              className="btn btn-toggle"
              aria-pressed={editMode}
              onClick={onToggleEdit}
              title={editMode ? "Stop editing; values become read-only again" : "Click any value in either pane to edit it"}
            >
              <Icon name="pencil" />
              {editMode ? "Editing" : "Edit"}
            </button>
          ) : (
            <button
              className="btn btn-primary"
              onClick={onEditCopy}
              disabled={duplicating}
              title="This source is read-only. Makes an editable copy in Your uploads and opens it."
            >
              <Icon name="copy" />
              {duplicating ? "Copying…" : "Edit a copy"}
            </button>
          )}
        </div>
      </div>
      <div className="fh-row fh-subrow">
        <TraceAddress path={tracePath} onSelect={onTraceSelect} />
        {stats && (
          <span className="fh-stats">
            {stats.managedObjects.toLocaleString()} objects · {stats.parameters.toLocaleString()} parameters
          </span>
        )}
      </div>
    </header>
  );
}

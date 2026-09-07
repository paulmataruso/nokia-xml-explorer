import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  listFiles,
  getFileTree,
  getFileRawTree,
  getClassesKB,
  getParamsKB,
  getStructuralKB,
  deleteFile,
  updateParam,
  duplicateToUploads,
  listSnapshots,
  restoreSnapshot,
  createNewFile,
  getMissingRequired,
  deleteObject,
  deleteObjectParam,
  renameObject,
} from "./api.js";
import { TreeView } from "./components/TreeView.jsx";
import { ExplainPanel } from "./components/ExplainPanel.jsx";
import { RawXmlView } from "./components/RawXmlView.jsx";
import { Resizer } from "./components/Resizer.jsx";
import { UploadCard } from "./components/UploadCard.jsx";
import { HistoryPanel } from "./components/HistoryPanel.jsx";
import { AddObjectModal } from "./components/AddObjectModal.jsx";
import { RequiredFieldsModal } from "./components/RequiredFieldsModal.jsx";
import { ContextMenu } from "./components/ContextMenu.jsx";
import { filterTree, collectExpandableIds, clamp } from "./utils.js";
import { findPath, findPathInForest, findNodeInForest, collectRawMatches } from "./rawTreeUtils.js";

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

// Raw-XML-only wrapper elements (the <raml> root and <header> container) have
// no single corresponding node in the logical (distName) tree -- clicking
// them is treated as clicking the logical "File Info" node instead.
const RAW_TO_LOGICAL_ALIAS = {
  "raw-root": "fileinfo",
  "fileinfo-header": "fileinfo",
};

const DEFAULT_SIDEBAR_WIDTH = 280;
const DEFAULT_SPLIT_WIDTH = 480;
const DEFAULT_SPLIT_HEIGHT = 320;

export default function App() {
  const [files, setFiles] = useState([]);
  const [filesError, setFilesError] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [tree, setTree] = useState(null);
  const [loadingTree, setLoadingTree] = useState(false);
  const [treeError, setTreeError] = useState(null);
  const [kb, setKb] = useState(null);
  const [kbError, setKbError] = useState(null);
  const [expanded, setExpanded] = useState(() => new Set());
  const [selectedNode, setSelectedNode] = useState(null);
  const [query, setQuery] = useState("");
  const [fileFilter, setFileFilter] = useState("");
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [explainCollapsed, setExplainCollapsed] = useState(false);

  // --- Raw XML side-by-side view ---
  const [showRawView, setShowRawView] = useState(false);
  const [rawTree, setRawTree] = useState(null);
  const [rawLoading, setRawLoading] = useState(false);
  const [rawError, setRawError] = useState(null);
  const [rawExpanded, setRawExpanded] = useState(() => new Set());
  const [rawQuery, setRawQuery] = useState("");
  const [rawMatchIndex, setRawMatchIndex] = useState(0);
  const [rawLayout, setRawLayout] = useState("side"); // "side" | "stacked"
  const [splitWidth, setSplitWidth] = useState(DEFAULT_SPLIT_WIDTH);
  const [splitHeight, setSplitHeight] = useState(DEFAULT_SPLIT_HEIGHT);

  // --- Shared cross-highlight target: whichever node id was last clicked in
  // EITHER the logical tree or the raw XML tree. Both panes watch this to
  // expand their own ancestors and scroll/highlight the matching row. ---
  const [focusId, setFocusId] = useState(null);
  const [logicalFocusMissing, setLogicalFocusMissing] = useState(false);
  const [rawFocusMissing, setRawFocusMissing] = useState(false);

  // --- Editing + version history ---
  const [editMode, setEditMode] = useState(false);
  const [duplicating, setDuplicating] = useState(false);
  const [duplicateError, setDuplicateError] = useState(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [snapshots, setSnapshots] = useState([]);
  const [snapshotsLoading, setSnapshotsLoading] = useState(false);
  const [snapshotsError, setSnapshotsError] = useState(null);
  const [restoringId, setRestoringId] = useState(null);
  const [addObjectOpen, setAddObjectOpen] = useState(false);
  const [generatorWarning, setGeneratorWarning] = useState(null);
  const [missingRequired, setMissingRequired] = useState([]);
  const [requiredFieldsOpen, setRequiredFieldsOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState(null); // { x, y, node }

  const treeScrollRef = useRef(null);
  const rawScrollRef = useRef(null);

  const refreshFiles = () =>
    listFiles()
      .then(setFiles)
      .catch((e) => setFilesError(String(e.message || e)));

  useEffect(() => {
    refreshFiles();
    Promise.all([getClassesKB(), getParamsKB(), getStructuralKB()])
      .then(([classesKB, paramsKB, structural]) => setKb({ classesKB, paramsKB, structural }))
      .catch((e) => setKbError(String(e.message || e)));
  }, []);

  useEffect(() => {
    if (!selectedFile) return;
    setLoadingTree(true);
    setTreeError(null);
    setSelectedNode(null);
    setQuery("");
    setRawTree(null);
    setRawError(null);
    setRawQuery("");
    setRawMatchIndex(0);
    setFocusId(null);
    setLogicalFocusMissing(false);
    setRawFocusMissing(false);
    setHistoryOpen(false);
    setSnapshots([]);
    setDuplicateError(null);
    setGeneratorWarning(null);
    getFileTree(selectedFile)
      .then((t) => {
        setTree(t);
        setExpanded(new Set(t.children.slice(0, 2).map((n) => n.id)));
      })
      .catch((e) => setTreeError(String(e.message || e)))
      .finally(() => setLoadingTree(false));
  }, [selectedFile]);

  // Fetch the raw tree lazily: only once the user actually asks to see it
  // (or when they switch files while it's already open).
  useEffect(() => {
    if (!showRawView || !selectedFile) return;
    setRawLoading(true);
    setRawError(null);
    getFileRawTree(selectedFile)
      .then((rt) => {
        setRawTree(rt);
        setRawExpanded(new Set(["raw-root", "fileinfo", "fileinfo-header"]));
      })
      .catch((e) => setRawError(String(e.message || e)))
      .finally(() => setRawLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showRawView, selectedFile]);

  // Bidirectional sync: whenever the shared focus target changes (from a
  // click in either pane, or from raw search navigation), expand ancestors
  // and scroll the matching row into view in BOTH the logical tree and the
  // raw XML tree.
  useEffect(() => {
    if (!focusId) return;

    if (tree) {
      const path = findPathInForest(tree.children, focusId);
      if (path) {
        setLogicalFocusMissing(false);
        setExpanded((prev) => {
          const next = new Set(prev);
          path.forEach((id) => next.add(id));
          return next;
        });
        scrollToDataId(treeScrollRef.current, "data-tree-id", focusId);
      } else {
        setLogicalFocusMissing(true);
      }
    }

    if (showRawView && rawTree) {
      const rpath = findPath(rawTree.root, focusId);
      if (rpath) {
        setRawFocusMissing(false);
        setRawExpanded((prev) => {
          const next = new Set(prev);
          rpath.forEach((id) => next.add(id));
          return next;
        });
        scrollToDataId(rawScrollRef.current, "data-raw-id", focusId);
      } else {
        setRawFocusMissing(true);
      }
    }
  }, [focusId, tree, rawTree, showRawView]);

  const displayNodes = useMemo(() => {
    if (!tree) return [];
    if (!query.trim()) return tree.children;
    return filterTree(tree.children, query);
  }, [tree, query]);

  const rawMatches = useMemo(() => {
    if (!rawTree || !rawQuery.trim()) return [];
    return collectRawMatches(rawTree.root, rawQuery);
  }, [rawTree, rawQuery]);

  // Jump to the first match whenever the raw search text changes.
  useEffect(() => {
    if (rawQuery.trim() && rawMatches.length > 0) {
      setRawMatchIndex(0);
      setFocusId(rawMatches[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawQuery, rawTree]);

  const gotoRawMatch = (delta) => {
    if (rawMatches.length === 0) return;
    const next = (rawMatchIndex + delta + rawMatches.length) % rawMatches.length;
    setRawMatchIndex(next);
    setFocusId(rawMatches[next]);
  };

  const toggle = (id) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleRaw = (id) => {
    setRawExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleActivate = (node) => setFocusId(node.id);
  const handleRawActivate = (node) => setFocusId(RAW_TO_LOGICAL_ALIAS[node.id] || node.id);

  const handleSelectExplain = (node) => {
    setSelectedNode(node);
    setExplainCollapsed(false);
  };

  const expandAll = () => {
    if (!tree) return;
    setExpanded(new Set(collectExpandableIds(tree.children)));
  };
  const collapseAll = () => setExpanded(new Set());

  const expandAllRaw = () => {
    if (!rawTree) return;
    setRawExpanded(new Set(collectExpandableIds(rawTree.root)));
  };
  const collapseAllRaw = () => setRawExpanded(new Set());

  const handleDelete = (e, filename) => {
    e.stopPropagation();
    deleteFile(filename)
      .then(() => {
        refreshFiles();
        if (selectedFile === filename) {
          setSelectedFile(null);
          setTree(null);
        }
      })
      .catch((err) => setFilesError(String(err.message || err)));
  };

  const visibleFiles = useMemo(() => {
    const q = fileFilter.trim().toLowerCase();
    if (!q) return files;
    return files.filter((f) => f.name.toLowerCase().includes(q));
  }, [files, fileFilter]);

  const uploadedFiles = visibleFiles.filter((f) => f.source === "upload");
  const scpFiles = visibleFiles.filter((f) => f.source !== "upload");

  const selectedFileInfo = useMemo(
    () => files.find((f) => f.name === selectedFile) || null,
    [files, selectedFile]
  );
  const isEditableFile = selectedFileInfo?.source === "upload";
  const canEditNow = editMode && isEditableFile;

  // Re-derives whenever `tree` changes -- which every edit/add already
  // triggers via refetchAfterEdit -- so the red-flag count and the
  // Required Fields table both stay current without a separate refresh call
  // at every edit site.
  useEffect(() => {
    if (!selectedFile || !isEditableFile) {
      setMissingRequired([]);
      return;
    }
    getMissingRequired(selectedFile)
      .then(setMissingRequired)
      .catch(() => setMissingRequired([]));
  }, [selectedFile, isEditableFile, tree]);

  const refetchAfterEdit = () =>
    getFileTree(selectedFile).then((newTree) => {
      setTree(newTree);
      // selectedNode is a frozen object reference from whenever it was
      // double-clicked -- without re-pointing it at the fresh copy, the
      // explain panel would keep showing a stale snapshot (e.g. missing a
      // parameter that was just added) even though the tree underneath it
      // has already updated.
      setSelectedNode((prev) => (prev ? findNodeInForest(newTree.children, prev.id) || prev : prev));
      return showRawView ? getFileRawTree(selectedFile).then(setRawTree) : Promise.resolve();
    });

  const handleSaveEdit = (nodeId, value) => updateParam(selectedFile, nodeId, value).then(refetchAfterEdit);

  // node comes from either TreeView ("mo"/kind-based) or RawXmlView
  // ("managedObject"/tag-based) -- both share the same id scheme (id ==
  // distName), so a single handler covers both panes.
  const handleDeleteObject = (node) => {
    const distName = node.id;
    const label = distName.split("/").pop();
    const hasNestedObject = (n) =>
      (n.children || []).some((c) => c.kind === "mo" || c.tag === "managedObject" || hasNestedObject(c));
    const confirmMsg = hasNestedObject(node)
      ? `Delete ${label} and every object nested under it? A snapshot is saved first, so this can be undone from History.`
      : `Delete ${label}? A snapshot is saved first, so this can be undone from History.`;
    if (!window.confirm(confirmMsg)) return;
    deleteObject(selectedFile, distName)
      .then((res) => {
        const deleted = new Set(res.deleted || [distName]);
        if (selectedNode && deleted.has(selectedNode.distName || selectedNode.id)) setSelectedNode(null);
        if (focusId && deleted.has(focusId)) setFocusId(null);
        return refetchAfterEdit();
      })
      .catch((e) => alert(String(e.message || e)));
  };

  const handleDeleteParam = (node) => {
    const distName = node.ownerDistName;
    const paramName = node.label || node.attrs?.name;
    if (!distName || !paramName) return;
    deleteObjectParam(selectedFile, distName, paramName)
      .then(() => refetchAfterEdit())
      .catch((e) => alert(String(e.message || e)));
  };

  // Changes just the trailing instance number (e.g. LNCEL-1 -> LNCEL-0),
  // same class/parent -- see rename_managed_object in parser.py. Every
  // descendant's distName is rewritten server-side too, so anything the UI
  // was pointing at by the old path (selectedNode/focusId) is now stale and
  // gets cleared rather than silently showing the wrong node.
  const handleRenameObject = (node) => {
    const distName = node.id;
    const label = distName.split("/").pop();
    const currentId = label.includes("-") ? label.slice(label.lastIndexOf("-") + 1) : "";
    const input = window.prompt(`New instance ID for ${label}:`, currentId);
    if (input == null) return;
    const newId = input.trim();
    if (!newId || newId === currentId) return;
    renameObject(selectedFile, distName, newId)
      .then(() => {
        const isStale = (id) => id === distName || (id || "").startsWith(distName + "/");
        if (selectedNode && (isStale(selectedNode.distName) || isStale(selectedNode.id))) setSelectedNode(null);
        if (focusId && isStale(focusId)) setFocusId(null);
        return refetchAfterEdit();
      })
      .catch((e) => alert(String(e.message || e)));
  };

  // Right-click menu (either pane) -- position-independent alternative to
  // the inline × buttons, which can end up scrolled out of view on a wide
  // row. Only intercepts the browser's default context menu for rows that
  // actually have an action (a real object or a direct object parameter);
  // everything else falls through to the normal browser menu.
  const handleContextMenu = (e, node) => {
    const isObject = node.kind === "mo" || node.tag === "managedObject";
    const isParam = node.kind === "param" || node.tag === "p";
    if (!isObject && !isParam) return;
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, node });
  };

  const contextMenuItems = useMemo(() => {
    if (!contextMenu) return [];
    const node = contextMenu.node;
    const isObject = node.kind === "mo" || node.tag === "managedObject";
    if (isObject) {
      return [
        { type: "label", label: node.label || node.id },
        { label: "Rename (change instance ID)…", onClick: () => handleRenameObject(node) },
        { label: "Delete object", danger: true, onClick: () => handleDeleteObject(node) },
      ];
    }
    const paramName = node.label || node.attrs?.name;
    const deletable = !node.mandatory && node.ownerDistName;
    return [
      { type: "label", label: paramName },
      {
        label: node.mandatory ? "Delete parameter (Mandatory — edit instead)" : "Delete parameter",
        danger: true,
        disabled: !deletable,
        onClick: () => handleDeleteParam(node),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contextMenu]);

  const handleCreateEditableCopy = () => {
    setDuplicating(true);
    setDuplicateError(null);
    duplicateToUploads(selectedFile)
      .then((res) => refreshFiles().then(() => setSelectedFile(res.name)))
      .catch((e) => setDuplicateError(String(e.message || e)))
      .finally(() => setDuplicating(false));
  };

  const handleNewFile = () => {
    const name = window.prompt("New file name:", "New_Commissioning_File.xml");
    if (!name) return;
    createNewFile(name)
      .then((res) => refreshFiles().then(() => setSelectedFile(res.name)))
      .catch((e) => setFilesError(String(e.message || e)));
  };

  // A logical "mo"/"mo-placeholder" node's id IS its distName (see
  // backend/app/parser.py); param/list/item ids contain "::" and "fileinfo"
  // is the synthetic file-info node, so this cheaply tells us whether the
  // current focus is a real managed object we can default the "Add Object"
  // parent field to.
  const focusedDistName = focusId && focusId !== "fileinfo" && !focusId.includes("::") ? focusId : "";

  const handleObjectCreated = (result) => {
    setAddObjectOpen(false);
    const messages = [];
    if (!result.classVerified) {
      messages.push(
        `Created with class="${result.class}" — this class was never seen in any of your sample ` +
          `files, so its namespace prefix is inferred from a sibling class, not verified. Double-check ` +
          `it in Raw XML before relying on this file.`
      );
    }
    const cascaded = result.cascadedObjects || [];
    const created = cascaded.filter((c) => !c.error);
    const failed = cascaded.filter((c) => c.error);
    if (created.length > 0) {
      messages.push(
        `Also created ${created.length} required child object${created.length === 1 ? "" : "s"} ` +
          `(inferred from your sample files, not an official Nokia rule — see Raw XML to review): ` +
          created.map((c) => c.shortClass).join(", ") +
          "."
      );
    }
    if (failed.length > 0) {
      messages.push(
        `Couldn't auto-create ${failed.length} inferred required child object${failed.length === 1 ? "" : "s"}: ` +
          failed.map((c) => `${c.shortClass} (${c.error})`).join("; ")
      );
    }
    setGeneratorWarning(messages.length > 0 ? messages.join(" ") : null);
    refetchAfterEdit().then(() => setFocusId(result.distName));
  };

  const toggleHistory = () => {
    const opening = !historyOpen;
    setHistoryOpen(opening);
    if (opening) {
      setSnapshotsLoading(true);
      setSnapshotsError(null);
      listSnapshots(selectedFile)
        .then(setSnapshots)
        .catch((e) => setSnapshotsError(String(e.message || e)))
        .finally(() => setSnapshotsLoading(false));
    }
  };

  const handleRestore = (snapshotId) => {
    setRestoringId(snapshotId);
    restoreSnapshot(selectedFile, snapshotId)
      .then(() => refetchAfterEdit())
      .then(() => listSnapshots(selectedFile))
      .then(setSnapshots)
      .catch((e) => setSnapshotsError(String(e.message || e)))
      .finally(() => setRestoringId(null));
  };

  return (
    <div className="app">
      <header className="topbar">
        <h1>Nokia AirScale / Flexi Zone XML Explorer</h1>
        {tree && (
          <div className="stats">
            {tree.stats.managedObjects.toLocaleString()} objects · {tree.stats.parameters.toLocaleString()} parameters
          </div>
        )}
      </header>

      <div className="body">
        {sidebarCollapsed ? (
          <button
            className="pane-expand-btn"
            onClick={() => setSidebarCollapsed(false)}
            title="Show file list"
          >
            ▶
          </button>
        ) : (
          <>
            <aside className="sidebar" style={{ width: sidebarWidth }}>
              <div className="pane-header">
                <span>Files</span>
                <button className="collapse-btn" onClick={() => setSidebarCollapsed(true)} title="Collapse file list">
                  ◀
                </button>
              </div>

              <button className="btn new-file-btn" onClick={handleNewFile} title="Start a brand-new commissioning file">
                + New file
              </button>

              <UploadCard onUploaded={refreshFiles} />

              <input
                className="file-filter"
                placeholder="Filter files…"
                value={fileFilter}
                onChange={(e) => setFileFilter(e.target.value)}
              />
              {filesError && <div className="placeholder error">{filesError}</div>}

              {uploadedFiles.length > 0 && (
                <>
                  <div className="sidebar-title">Your uploads ({uploadedFiles.length})</div>
                  <ul className="file-list file-list-uploads">
                    {uploadedFiles.map((f) => (
                      <li
                        key={f.name}
                        className={"file-item" + (selectedFile === f.name ? " selected" : "")}
                        onClick={() => setSelectedFile(f.name)}
                        title={`${f.name} (${formatBytes(f.sizeBytes)})`}
                      >
                        <span className="file-name">{f.name}</span>
                        <button
                          className="delete-btn"
                          onClick={(e) => handleDelete(e, f.name)}
                          title="Delete this upload"
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              )}

              <div className="sidebar-title">Commissioning files ({scpFiles.length})</div>
              <ul className="file-list">
                {scpFiles.map((f) => (
                  <li
                    key={f.name}
                    className={
                      "file-item" +
                      (selectedFile === f.name ? " selected" : "") +
                      (!f.supported ? " unsupported" : "")
                    }
                    onClick={() => f.supported && setSelectedFile(f.name)}
                    title={f.supported ? `${f.name} (${formatBytes(f.sizeBytes)})` : "Unsupported file type — not a RAML XML file"}
                  >
                    <span className="file-name">{f.name}</span>
                    <span className="file-size">{formatBytes(f.sizeBytes)}</span>
                  </li>
                ))}
              </ul>
            </aside>

            <Resizer
              title="Drag to resize the file list"
              onDrag={(dx) => setSidebarWidth((w) => clamp(w + dx, 160, 640))}
            />
          </>
        )}

        <main className="tree-pane">
          {!selectedFile && (
            <div className="placeholder">
              <p>Select a commissioning XML file on the left to explore it, or upload your own.</p>
              <p className="hint">
                Click a row to expand/collapse it (and sync the raw XML view). Double-click any
                object, parameter, or table row for a full explanation.
              </p>
            </div>
          )}
          {selectedFile && (
            <>
              <div className="toolbar">
                <input
                  className="search-box"
                  placeholder="Search parameters, classes, or values in this file…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <button className="btn" onClick={expandAll} title="Expand every node">
                  Expand all
                </button>
                <button className="btn" onClick={collapseAll} title="Collapse every node">
                  Collapse all
                </button>
                <button
                  className={"btn toggle-raw-btn" + (showRawView ? " active" : "")}
                  onClick={() => setShowRawView((v) => !v)}
                  title="Show the file exactly as written, side by side"
                >
                  {showRawView ? "Hide Raw XML" : "Show Raw XML"}
                </button>
                <button
                  className={"btn" + (editMode ? " active" : "")}
                  onClick={() => setEditMode((v) => !v)}
                  title="Click values in either pane to edit them"
                >
                  {editMode ? "Editing" : "Edit Mode"}
                </button>
                {isEditableFile && (
                  <button className="btn" onClick={() => setAddObjectOpen(true)} title="Add a new managed object">
                    + Add Object
                  </button>
                )}
                {isEditableFile && (
                  <button
                    className={"btn" + (requiredFieldsOpen ? " active" : "")}
                    onClick={() => setRequiredFieldsOpen(true)}
                    title="Show every Mandatory parameter that still has no value"
                  >
                    Required Fields
                    {missingRequired.length > 0 && (
                      <span className="badge-count">{missingRequired.length}</span>
                    )}
                  </button>
                )}
                {isEditableFile && (
                  <div className="history-wrap">
                    <button
                      className={"btn" + (historyOpen ? " active" : "")}
                      onClick={toggleHistory}
                      title="View and restore previous versions"
                    >
                      History
                    </button>
                    {historyOpen && (
                      <HistoryPanel
                        snapshots={snapshots}
                        loading={snapshotsLoading}
                        error={snapshotsError}
                        onRestore={handleRestore}
                        restoringId={restoringId}
                      />
                    )}
                  </div>
                )}
              </div>

              {editMode && !isEditableFile && (
                <div className="readonly-banner">
                  <span>
                    This is a read-only reference file — edits go to an editable copy instead.
                  </span>
                  <button className="btn" onClick={handleCreateEditableCopy} disabled={duplicating}>
                    {duplicating ? "Copying…" : "Create editable copy"}
                  </button>
                  {duplicateError && <span className="edit-error-text">{duplicateError}</span>}
                </div>
              )}

              {generatorWarning && (
                <div className="readonly-banner">
                  <span>{generatorWarning}</span>
                  <button className="btn" onClick={() => setGeneratorWarning(null)}>
                    Dismiss
                  </button>
                </div>
              )}

              {loadingTree && <div className="placeholder">Parsing {selectedFile}…</div>}
              {treeError && (
                <div className="placeholder error">Failed to parse this file: {treeError}</div>
              )}

              {!loadingTree && !treeError && tree && (
                <>
                  {kbError && (
                    <div className="placeholder error">Failed to load knowledge base: {kbError}</div>
                  )}
                  {!kbError && !kb && <div className="placeholder">Loading knowledge base…</div>}
                  {!kbError && kb && (
                    <div className={"split-container" + (showRawView && rawLayout === "stacked" ? " stacked" : "")}>
                      <div
                        className="split-left"
                        style={
                          !showRawView
                            ? { flex: 1 }
                            : rawLayout === "stacked"
                            ? { height: splitHeight, flex: "0 0 auto" }
                            : { width: splitWidth, flex: "0 0 auto" }
                        }
                      >
                        {logicalFocusMissing && (
                          <div className="raw-missing-note">
                            Not present in the reconstructed tree — this raw XML element doesn't map
                            to a browsable node here.
                          </div>
                        )}
                        <div className="tree-scroll" ref={treeScrollRef}>
                          {displayNodes.length === 0 ? (
                            <div className="placeholder">No matches for "{query}".</div>
                          ) : (
                            <TreeView
                              nodes={displayNodes}
                              expanded={expanded}
                              onToggle={toggle}
                              onSelect={handleSelectExplain}
                              onActivate={handleActivate}
                              selectedId={selectedNode?.id}
                              activeId={focusId}
                              forceExpand={query.trim().length > 0}
                              query={query}
                              editable={canEditNow}
                              onSaveEdit={handleSaveEdit}
                              onDeleteObject={handleDeleteObject}
                              onDeleteParam={handleDeleteParam}
                              onContextMenu={handleContextMenu}
                            />
                          )}
                        </div>
                      </div>

                      {showRawView && (
                        <>
                          <Resizer
                            title="Drag to resize"
                            orientation={rawLayout === "stacked" ? "horizontal" : "vertical"}
                            onDrag={(d) =>
                              rawLayout === "stacked"
                                ? setSplitHeight((h) => clamp(h + d, 120, 1200))
                                : setSplitWidth((w) => clamp(w + d, 260, 1400))
                            }
                          />
                          <div className="split-right">
                            <div className="raw-toolbar">
                              <span className="raw-title">Raw XML</span>
                              <div className="layout-toggle">
                                <button
                                  className={"btn icon-btn" + (rawLayout === "side" ? " active" : "")}
                                  onClick={() => setRawLayout("side")}
                                  title="Side by side (vertical split)"
                                >
                                  ⬌
                                </button>
                                <button
                                  className={"btn icon-btn" + (rawLayout === "stacked" ? " active" : "")}
                                  onClick={() => setRawLayout("stacked")}
                                  title="Stacked, top/bottom (horizontal split)"
                                >
                                  ⬍
                                </button>
                              </div>
                              <input
                                className="search-box raw-search"
                                placeholder="Find in raw XML…"
                                value={rawQuery}
                                onChange={(e) => setRawQuery(e.target.value)}
                              />
                              <span className="match-count">
                                {rawQuery.trim() ? `${rawMatches.length ? rawMatchIndex + 1 : 0} / ${rawMatches.length}` : ""}
                              </span>
                              <button
                                className="btn icon-btn"
                                onClick={() => gotoRawMatch(-1)}
                                disabled={rawMatches.length === 0}
                                title="Previous match"
                              >
                                ↑
                              </button>
                              <button
                                className="btn icon-btn"
                                onClick={() => gotoRawMatch(1)}
                                disabled={rawMatches.length === 0}
                                title="Next match"
                              >
                                ↓
                              </button>
                              <button className="btn icon-btn" onClick={expandAllRaw} title="Expand all">
                                ⊞
                              </button>
                              <button className="btn icon-btn" onClick={collapseAllRaw} title="Collapse all">
                                ⊟
                              </button>
                            </div>
                            {rawFocusMissing && (
                              <div className="raw-missing-note">
                                Not present as its own element in this file — this object is only
                                implied by another element's distName path.
                              </div>
                            )}
                            {rawLoading && <div className="placeholder">Loading raw XML…</div>}
                            {rawError && <div className="placeholder error">{rawError}</div>}
                            {rawTree && !rawLoading && (
                              <div className="tree-scroll raw-scroll" ref={rawScrollRef}>
                                <RawXmlView
                                  root={rawTree.root}
                                  expanded={rawExpanded}
                                  onToggle={toggleRaw}
                                  onActivate={handleRawActivate}
                                  focusId={focusId}
                                  query={rawQuery}
                                  editable={canEditNow}
                                  onSaveEdit={handleSaveEdit}
                                  onDeleteObject={handleDeleteObject}
                                  onDeleteParam={handleDeleteParam}
                                  onContextMenu={handleContextMenu}
                                />
                              </div>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </main>

        {explainCollapsed ? (
          <button
            className="pane-expand-btn"
            onClick={() => setExplainCollapsed(false)}
            title="Show explanation panel"
          >
            ◀
          </button>
        ) : (
          <aside className="explain-pane">
            <div className="pane-header">
              <span>Explanation</span>
              <button className="collapse-btn" onClick={() => setExplainCollapsed(true)} title="Collapse explanation panel">
                ▶
              </button>
            </div>
            {kb ? (
              <ExplainPanel
                node={selectedNode}
                kb={kb}
                onClose={() => setSelectedNode(null)}
                editable={canEditNow}
                filename={selectedFile}
                onParamAdded={refetchAfterEdit}
              />
            ) : (
              <div className="explain-panel empty">
                <p>Loading knowledge base…</p>
              </div>
            )}
          </aside>
        )}
      </div>

      {addObjectOpen && (
        <AddObjectModal
          filename={selectedFile}
          defaultParentDistName={focusedDistName}
          onClose={() => setAddObjectOpen(false)}
          onCreated={handleObjectCreated}
        />
      )}

      {requiredFieldsOpen && (
        <RequiredFieldsModal
          filename={selectedFile}
          rows={missingRequired}
          onClose={() => setRequiredFieldsOpen(false)}
          onSaved={refetchAfterEdit}
        />
      )}

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={contextMenuItems}
          onClose={() => setContextMenu(null)}
        />
      )}
    </div>
  );
}

function cssAttrEscape(id) {
  return String(id).replace(/"/g, '\\"');
}

/**
 * Scrolls the row matching `id` into view inside `container`, once it
 * actually exists in the DOM. Expanding ancestors (setExpanded/setRawExpanded)
 * and this scroll are triggered from the same effect, but React's re-render
 * of the newly-revealed rows isn't guaranteed to have painted yet by the
 * time a single requestAnimationFrame callback runs -- a double rAF waits
 * for a full committed paint first, and a few retries cover any remaining
 * timing slop (e.g. nested expand of several ancestor levels at once).
 */
function scrollToDataId(container, attr, id, retriesLeft = 8) {
  if (!container || !id) return;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const el = container.querySelector(`[${attr}="${cssAttrEscape(id)}"]`);
      if (el) {
        el.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
      } else if (retriesLeft > 0) {
        setTimeout(() => scrollToDataId(container, attr, id, retriesLeft - 1), 40);
      }
    });
  });
}

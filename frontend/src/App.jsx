import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  downloadUrl,
} from "./api.js";
import { TreeView } from "./components/TreeView.jsx";
import { ExplainPanel } from "./components/ExplainPanel.jsx";
import { RawXmlView } from "./components/RawXmlView.jsx";
import { Resizer } from "./components/Resizer.jsx";
import { AddObjectModal } from "./components/AddObjectModal.jsx";
import { RequiredFieldsModal } from "./components/RequiredFieldsModal.jsx";
import { ContextMenu } from "./components/ContextMenu.jsx";
import { ToastStack } from "./components/Toast.jsx";
import { SiteManagementModal } from "./components/SiteManagementModal.jsx";
import { ParameterBrowserModal } from "./components/ParameterBrowserModal.jsx";
import { versionKey } from "./components/VersionFilter.jsx";
import { FileSidebar } from "./components/FileSidebar.jsx";
import { FileHeader } from "./components/FileHeader.jsx";
import { Icon } from "./components/Icon.jsx";
import { ThemeSwitcher, THEMES } from "./components/ThemeSwitcher.jsx";
import { Wordmark } from "./components/Wordmark.jsx";
import { ConfirmDialog } from "./components/ConfirmDialog.jsx";
import { PromptDialog } from "./components/PromptDialog.jsx";
import { filterTree, collectExpandableIds, clamp } from "./utils.js";
import {
  findPath,
  findPathInForest,
  findNodeInForest,
  findNodePathInForest,
  collectRawMatches,
} from "./rawTreeUtils.js";
import { usePersistentState } from "./usePersistentState.js";

const COLLAPSED_SECTIONS_KEY = "nokiaXmlExplorer.collapsedFileSections";

// Raw-XML-only wrapper elements (the <raml> root and <header> container) have
// no single corresponding node in the logical (distName) tree -- clicking
// them is treated as clicking the logical "File Info" node instead.
const RAW_TO_LOGICAL_ALIAS = {
  "raw-root": "fileinfo",
  "fileinfo-header": "fileinfo",
};

// Side panes start narrower on laptop-class windows so the workspace keeps
// room for the tree's value column; once dragged, the user's width wins.
const ROOMY_WINDOW = typeof window === "undefined" || window.innerWidth >= 1600;
const DEFAULT_SIDEBAR_WIDTH = ROOMY_WINDOW ? 280 : 248;
const DEFAULT_EXPLAIN_WIDTH = ROOMY_WINDOW ? 380 : 320;
// Share of the split given to the reconstructed tree (the primary pane);
// raw XML gets the rest. Stored as a fraction so it holds across window sizes.
const DEFAULT_SPLIT_FRACTION = 0.55;

/**
 * A callback whose identity never changes but always runs the latest
 * version of `fn`. The tree and raw rows are memoized (they skip
 * re-rendering unless something on their own lineage changed); handing
 * them freshly-created handlers on every App render would defeat that, and
 * handing them stale ones would act on old state.
 */
function useStableCallback(fn) {
  const ref = useRef(fn);
  ref.current = fn;
  return useCallback((...args) => ref.current(...args), []);
}

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
  // Selected BTS software releases (e.g. "SBTS20C"); empty = no filter.
  const [versionFilter, setVersionFilter] = useState(() => new Set());
  // Sidebar sections ("upload" | "scp" | "example") the user has collapsed,
  // remembered in this browser across reloads. Storage can be unavailable
  // (private mode, blocked site data), so failures just fall back to all-open.
  const [collapsedSections, setCollapsedSections] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(COLLAPSED_SECTIONS_KEY));
      return new Set(Array.isArray(saved) ? saved : []);
    } catch {
      return new Set();
    }
  });
  const toggleSection = (id) =>
    setCollapsedSections((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        localStorage.setItem(COLLAPSED_SECTIONS_KEY, JSON.stringify([...next]));
      } catch {
        // Not persisted this time; the in-memory state still applies.
      }
      return next;
    });

  // --- Workspace layout: remembered per browser (usePersistentState), so
  // the panes come back the way they were left. ---
  const [sidebarWidth, setSidebarWidth] = usePersistentState("sidebarWidth", DEFAULT_SIDEBAR_WIDTH);
  const [sidebarCollapsed, setSidebarCollapsed] = usePersistentState("sidebarCollapsed", false);
  const [explainWidth, setExplainWidth] = usePersistentState("explainWidth", DEFAULT_EXPLAIN_WIDTH);
  const [explainCollapsed, setExplainCollapsed] = usePersistentState("explainCollapsed", false);
  const [highlightOfficial, setHighlightOfficial] = usePersistentState("highlightOfficial", true);
  // Colour theme (see styles.css); index.html applies the saved one before
  // first paint so a reload never flashes the default.
  const [theme, setTheme] = usePersistentState("theme", "night");
  useEffect(() => {
    document.documentElement.dataset.theme = THEMES.some((t) => t.id === theme) ? theme : "night";
  }, [theme]);

  // --- Raw XML split view ---
  const [showRawView, setShowRawView] = usePersistentState("showRawView", true);
  const [rawTree, setRawTree] = useState(null);
  const [rawLoading, setRawLoading] = useState(false);
  const [rawError, setRawError] = useState(null);
  const [rawExpanded, setRawExpanded] = useState(() => new Set());
  const [rawQuery, setRawQuery] = useState("");
  const [rawMatchIndex, setRawMatchIndex] = useState(0);
  // "stacked" == horizontal split (tree on top, raw below) -- the default;
  // "side" == vertical split.
  const [rawLayout, setRawLayout] = usePersistentState("rawLayout", "stacked");
  const [splitFraction, setSplitFraction] = usePersistentState("splitFraction", {
    stacked: DEFAULT_SPLIT_FRACTION,
    side: DEFAULT_SPLIT_FRACTION,
  });

  // --- Shared cross-highlight target: whichever node id was last clicked in
  // EITHER the logical tree or the raw XML tree. Both panes watch this to
  // expand their own ancestors and scroll/highlight the matching row. ---
  const [focusId, setFocusId] = useState(null);
  const [logicalFocusMissing, setLogicalFocusMissing] = useState(false);
  const [rawFocusMissing, setRawFocusMissing] = useState(false);

  // --- Editing + version history ---
  const [editMode, setEditMode] = useState(false);
  // Node ids changed in this session (by inline edit or Required Fields);
  // their rows stay marked so nothing changes silently. Cleared per file.
  const [editedIds, setEditedIds] = useState(() => new Set());
  const [duplicating, setDuplicating] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [snapshots, setSnapshots] = useState([]);
  const [snapshotsLoading, setSnapshotsLoading] = useState(false);
  const [snapshotsError, setSnapshotsError] = useState(null);
  const [restoringId, setRestoringId] = useState(null);
  const [addObjectOpen, setAddObjectOpen] = useState(false);
  const [generatorWarning, setGeneratorWarning] = useState(null);
  const [missingRequired, setMissingRequired] = useState(null);
  const [requiredFieldsOpen, setRequiredFieldsOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState(null); // { x, y, items }
  const [toasts, setToasts] = useState([]);
  const [confirmDialog, setConfirmDialog] = useState(null); // { title, message, confirmLabel, danger, onConfirm }
  const [promptDialog, setPromptDialog] = useState(null); // { title, message, initialValue, placeholder, confirmLabel, onConfirm }
  const [siteManagementOpen, setSiteManagementOpen] = useState(false);
  const [paramBrowserOpen, setParamBrowserOpen] = useState(false);

  // The tree's value column ("split-flap board"): wide enough for this
  // file's longest label at its depth, so values line up on every row; the
  // rare label longer than the cap is ellipsized (full name on hover, in the
  // Trace address and in the Explanation).
  const [labelCol, setLabelCol] = useState(null);
  const treeScrollRef = useRef(null);
  const rawScrollRef = useRef(null);
  const splitRef = useRef(null);

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
    setGeneratorWarning(null);
    setMissingRequired(null);
    setEditedIds(new Set());
    getFileTree(selectedFile)
      .then((t) => {
        setTree(t);
        setExpanded(new Set(t.children.slice(0, 2).map((n) => n.id)));
      })
      .catch((e) => setTreeError(String(e.message || e)))
      .finally(() => setLoadingTree(false));
  }, [selectedFile]);

  useEffect(() => {
    if (!tree) return;
    let cancelled = false;
    document.fonts.ready.then(() => {
      if (cancelled) return;
      const root = getComputedStyle(document.documentElement);
      const size = parseFloat(root.fontSize) * 0.8125; // --fs-data
      const family = root.getPropertyValue("--font-mono");
      const ctx = document.createElement("canvas").getContext("2d");
      const fonts = { 400: `400 ${size}px ${family}`, 600: `600 ${size}px ${family}` };
      let widest = 0;
      const walk = (nodes, depth) => {
        for (const n of nodes) {
          ctx.font = n.kind === "mo" || n.kind === "fileinfo" ? fonts[600] : fonts[400];
          // + table icon for lists; depth indent; delete button and gap
          const w = ctx.measureText(n.label || "").width + depth * 16 + (n.kind === "list" ? 18 : 0) + 30;
          if (w > widest) widest = w;
          if (n.children) walk(n.children, depth + 1);
        }
      };
      walk(tree.children, 0);
      setLabelCol(Math.round(Math.min(Math.max(widest + 12, 240), 560)));
    });
    return () => {
      cancelled = true;
    };
  }, [tree]);

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
      const nodePath = findNodePathInForest(tree.children, focusId);
      if (nodePath) {
        setLogicalFocusMissing(false);
        // Open every ancestor -- not the target itself: a click on a tree
        // row toggles that row, and the pane a selection came FROM is left
        // to its own toggle (see expandCounterpart). Same Set back when
        // nothing needs opening: a new Set re-renders every row in the tree.
        const toOpen = nodePath.slice(0, -1).map((n) => n.id);
        setExpanded((prev) => {
          if (toOpen.every((id) => prev.has(id))) return prev;
          const next = new Set(prev);
          toOpen.forEach((id) => next.add(id));
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
        const toOpen = rpath.slice(0, -1);
        setRawExpanded((prev) => {
          if (toOpen.every((id) => prev.has(id))) return prev;
          const next = new Set(prev);
          toOpen.forEach((id) => next.add(id));
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

  // Trace: the lineage of whatever row is focused (from either pane), root
  // first. Drives the file header's address and the lit guides in the tree.
  const traceId = focusId || selectedNode?.id || null;
  const tracePath = useMemo(
    () => (tree && traceId ? findNodePathInForest(tree.children, traceId) : null),
    [tree, traceId]
  );

  // The tree's single keyboard tab stop (roving tabindex): the focused or
  // selected row while it's actually rendered -- every ancestor open, or a
  // search is showing everything -- otherwise the first row, so Tab can
  // always get into the tree.
  const tabbableId = useMemo(() => {
    const id = focusId || selectedNode?.id;
    if (id) {
      const path = findPathInForest(displayNodes, id);
      if (path && (query.trim() || path.slice(0, -1).every((a) => expanded.has(a)))) return id;
    }
    return displayNodes[0]?.id ?? null;
  }, [displayNodes, focusId, selectedNode, expanded, query]);

  // The raw pane's tab stop, by the same rule: the focused line while it's
  // rendered, otherwise the document's first line.
  const rawTabbableId = useMemo(() => {
    if (!rawTree) return null;
    if (focusId) {
      const path = findPath(rawTree.root, focusId);
      if (path && path.slice(0, -1).every((a) => rawExpanded.has(a))) return focusId;
    }
    return rawTree.root.id;
  }, [rawTree, focusId, rawExpanded]);

  const rawMatches = useMemo(() => {
    if (!rawTree || !rawQuery.trim()) return [];
    return collectRawMatches(rawTree.root, rawQuery);
  }, [rawTree, rawQuery]);

  // Find-in-raw navigation behaves like clicking the match: it moves the
  // shared focus (scroll + Trace) and explains the matching node, so the
  // address and the Explanation never describe two different rows.
  const focusRawMatch = (id) => {
    const logicalId = RAW_TO_LOGICAL_ALIAS[id] || id;
    setFocusId(logicalId);
    const logicalNode = tree ? findNodeInForest(tree.children, logicalId) : null;
    if (logicalNode) setSelectedNode(logicalNode);
  };

  // Jump to the first match whenever the raw search text changes.
  useEffect(() => {
    if (rawQuery.trim() && rawMatches.length > 0) {
      setRawMatchIndex(0);
      focusRawMatch(rawMatches[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawQuery, rawTree]);

  const gotoRawMatch = (delta) => {
    if (rawMatches.length === 0) return;
    const next = (rawMatchIndex + delta + rawMatches.length) % rawMatches.length;
    setRawMatchIndex(next);
    focusRawMatch(rawMatches[next]);
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

  // Used for "expand/collapse a whole subtree in one click" (e.g. a <list>
  // and every <item> row under it) -- ids is every expandable id within
  // that subtree (see collectExpandableIds), expand is true/false for the
  // whole batch rather than toggling each individually.
  const toggleSubtree = (ids, expand) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => (expand ? next.add(id) : next.delete(id)));
      return next;
    });
  };

  const toggleRawSubtree = (ids, expand) => {
    setRawExpanded((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => (expand ? next.add(id) : next.delete(id)));
      return next;
    });
  };

  const addToast = (message, type = "info", ttlMs = 6000, action = null) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setToasts((prev) => [...prev, { id, message, type, action }]);
    if (ttlMs) setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), ttlMs);
  };
  const dismissToast = (id) => setToasts((prev) => prev.filter((t) => t.id !== id));

  // A selection made in one pane also opens the matching node in the OTHER
  // pane (click a managedObject in raw XML and its parameters show in the
  // tree, and vice versa). Only the other pane: expanding the originating
  // pane's own target here would fight that row's click toggle.
  const expandCounterpart = (setter, node) => {
    if (!node?.children?.length) return;
    setter((prev) => (prev.has(node.id) ? prev : new Set(prev).add(node.id)));
  };

  const handleActivate = (node) => {
    setFocusId(node.id);
    if (showRawView && rawTree) expandCounterpart(setRawExpanded, findNodeInForest([rawTree.root], node.id));
  };
  // Raw-pane nodes are a different shape (tag/attrs/text) than logical-tree
  // nodes (kind/class/value) that ExplainPanel knows how to render -- both
  // trees share the same id scheme (see parser.py), so a click in the raw
  // pane looks up the matching logical node and selects THAT, rather than
  // trying to hand the raw node itself to ExplainPanel.
  const handleRawActivate = (node) => {
    const logicalId = RAW_TO_LOGICAL_ALIAS[node.id] || node.id;
    setFocusId(logicalId);
    const logicalNode = tree ? findNodeInForest(tree.children, logicalId) : null;
    if (logicalNode) {
      handleSelectExplain(logicalNode);
      expandCounterpart(setExpanded, logicalNode);
    }
  };

  // Selecting a row never re-opens a collapsed Explanation pane: collapsing
  // it is a deliberate "give me the space", and the pane used to spring
  // back open on the very next click.
  const handleSelectExplain = (node) => setSelectedNode(node);

  const handleTraceSelect = (node) => {
    setFocusId(node.id);
    handleSelectExplain(node);
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

  // Deleting an upload also removes its snapshot history on the server, so
  // it's the one action here that can't be undone -- always confirm, and
  // say exactly what goes with it.
  const handleDeleteFile = (filename) => {
    listSnapshots(filename)
      .catch(() => [])
      .then((snaps) => {
        const n = snaps.length;
        setConfirmDialog({
          title: "Delete file",
          message:
            `Delete "${filename}" from Your uploads?` +
            (n > 0 ? ` Its ${n} saved snapshot${n === 1 ? "" : "s"} will be deleted too.` : "") +
            " This can't be undone.",
          confirmLabel: "Delete file",
          danger: true,
          onConfirm: () => {
            setConfirmDialog(null);
            deleteFile(filename)
              .then(() => {
                refreshFiles();
                if (selectedFile === filename) {
                  setSelectedFile(null);
                  setTree(null);
                }
                addToast(`Deleted ${filename}.`, "success");
              })
              .catch((err) => addToast(String(err.message || err), "error"));
          },
        });
      });
  };

  const handleFileMenu = (e, file) => {
    e.preventDefault();
    const rect = e.currentTarget.getBoundingClientRect?.();
    const fromButton = e.type === "click" && rect;
    setContextMenu({
      x: fromButton ? rect.right : e.clientX,
      y: fromButton ? rect.bottom + 4 : e.clientY,
      items: [
        { type: "label", label: file.name },
        {
          label: "Download",
          onClick: () => {
            const a = document.createElement("a");
            a.href = downloadUrl(file.name);
            a.download = file.name;
            a.click();
          },
        },
        { label: "Delete file…", danger: true, onClick: () => handleDeleteFile(file.name) },
      ],
    });
  };

  const visibleFiles = useMemo(() => {
    const q = fileFilter.trim().toLowerCase();
    return files.filter(
      (f) =>
        (!q || f.name.toLowerCase().includes(q)) &&
        (versionFilter.size === 0 || versionFilter.has(versionKey(f)))
    );
  }, [files, fileFilter, versionFilter]);

  const uploadedFiles = visibleFiles.filter((f) => f.source === "upload");
  const scpFiles = visibleFiles.filter((f) => f.source === "scp");
  const exampleFiles = visibleFiles.filter((f) => f.source === "example");

  const selectedFileInfo = useMemo(
    () => files.find((f) => f.name === selectedFile) || null,
    [files, selectedFile]
  );
  const isEditableFile = selectedFileInfo?.source === "upload";
  const canEditNow = editMode && isEditableFile;

  // Re-derives whenever `tree` changes -- which every edit/add already
  // triggers via refetchAfterEdit -- so the header's completeness and the
  // Required Fields table both stay current without a separate refresh call
  // at every edit site. Fetched for read-only files too: "is this export
  // complete?" is part of understanding a file, not only of editing one.
  useEffect(() => {
    if (!selectedFile || !tree) return;
    getMissingRequired(selectedFile)
      .then(setMissingRequired)
      .catch(() => setMissingRequired([]));
  }, [selectedFile, tree]);

  // Gaps = Mandatory and empty, for parameters actually seen set in real
  // files; unverified = documented as Mandatory but never observed in any
  // sample file, so the docs may not reflect what a real export needs.
  const completeness = useMemo(() => {
    if (missingRequired == null) return { loading: true, gaps: 0, unverified: 0 };
    const unverified = missingRequired.filter((r) => r.observed === false).length;
    return { loading: false, gaps: missingRequired.length - unverified, unverified };
  }, [missingRequired]);

  const refetchAfterEdit = () =>
    getFileTree(selectedFile).then((newTree) => {
      setTree(newTree);
      // selectedNode is a frozen object reference from whenever it was
      // clicked -- without re-pointing it at the fresh copy, the explain
      // panel would keep showing a stale snapshot (e.g. missing a
      // parameter that was just added) even though the tree underneath it
      // has already updated.
      setSelectedNode((prev) => (prev ? findNodeInForest(newTree.children, prev.id) || prev : prev));
      return showRawView ? getFileRawTree(selectedFile).then(setRawTree) : Promise.resolve();
    });

  // Every mutating endpoint snapshots the file first and returns that
  // snapshot's id, so "Undo" restores exactly the state before this change
  // (and the restore is itself snapshotted, so Undo can be undone from
  // History).
  const undoTo = (snapshotId, what, nodeIds = []) =>
    restoreSnapshot(selectedFile, snapshotId)
      .then(() => {
        setEditedIds((prev) => {
          const next = new Set(prev);
          nodeIds.forEach((id) => next.delete(id));
          return next;
        });
        return refetchAfterEdit();
      })
      .then(() => addToast(`Undone: ${what}`, "success"))
      .catch((e) => addToast(`Couldn't undo: ${String(e.message || e)}`, "error", 10000));

  const confirmChange = (res, message, nodeIds = []) =>
    addToast(
      message,
      "success",
      9000,
      res?.snapshot ? { label: "Undo", icon: "undo", onClick: () => undoTo(res.snapshot, message, nodeIds) } : null
    );

  const markEdited = (ids) =>
    setEditedIds((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.add(id));
      return next;
    });

  const handleSaveEdit = (nodeId, value) =>
    updateParam(selectedFile, nodeId, value).then((res) => {
      const [owner, name] = nodeId.split("::p::");
      markEdited([nodeId]);
      return refetchAfterEdit().then(() =>
        confirmChange(res, `Saved ${name} = ${value === "" ? "(empty)" : value} on ${owner.split("/").pop()}.`, [nodeId])
      );
    });

  // A parameter set from Required Fields or "+ Add parameter".
  const handleParamSet = (res, distName, paramName, value) => {
    const nodeId = `${distName}::p::${paramName}`;
    markEdited([nodeId]);
    return refetchAfterEdit().then(() =>
      confirmChange(res, `Set ${paramName} = ${value === "" ? "(empty)" : value} on ${distName.split("/").pop()}.`, [nodeId])
    );
  };

  // node comes from either TreeView ("mo"/kind-based) or RawXmlView
  // ("managedObject"/tag-based) -- both share the same id scheme (id ==
  // distName), so a single handler covers both panes.
  const handleDeleteObject = (node) => {
    const distName = node.id;
    const label = distName.split("/").pop();
    const hasNestedObject = (n) =>
      (n.children || []).some((c) => c.kind === "mo" || c.tag === "managedObject" || hasNestedObject(c));
    const message = hasNestedObject(node)
      ? `Delete ${label} and every object nested under it? A snapshot is saved first, so this can be undone from History.`
      : `Delete ${label}? A snapshot is saved first, so this can be undone from History.`;
    setConfirmDialog({
      title: "Delete object",
      message,
      confirmLabel: "Delete",
      danger: true,
      onConfirm: () => {
        setConfirmDialog(null);
        deleteObject(selectedFile, distName)
          .then((res) => {
            const deleted = new Set(res.deleted || [distName]);
            if (selectedNode && deleted.has(selectedNode.distName || selectedNode.id)) setSelectedNode(null);
            if (focusId && deleted.has(focusId)) setFocusId(null);
            return refetchAfterEdit().then(() =>
              confirmChange(
                res,
                deleted.size > 1 ? `Deleted ${label} and ${deleted.size - 1} nested object(s).` : `Deleted ${label}.`
              )
            );
          })
          .catch((e) => addToast(String(e.message || e), "error"));
      },
    });
  };

  const handleDeleteParam = (node) => {
    const distName = node.ownerDistName;
    const paramName = node.label || node.attrs?.name;
    if (!distName || !paramName) return;
    deleteObjectParam(selectedFile, distName, paramName)
      .then((res) =>
        refetchAfterEdit().then(() => confirmChange(res, `Deleted ${paramName} from ${distName.split("/").pop()}.`))
      )
      .catch((e) => addToast(String(e.message || e), "error"));
  };

  // Changes just the trailing instance number (e.g. LNCEL-1 -> LNCEL-0),
  // same class/parent -- see rename_managed_object in parser.py. Every
  // descendant's distName is rewritten server-side too, so anything the UI
  // was pointing at by the old path (selectedNode/focusId) is now stale and
  // gets cleared rather than silently showing the wrong node.
  const handleRenameObject = (node) => {
    const distName = node.id;
    const label = distName.split("/").pop();
    const shortClass = label.includes("-") ? label.slice(0, label.lastIndexOf("-")) : label;
    const currentId = label.includes("-") ? label.slice(label.lastIndexOf("-") + 1) : "";
    setPromptDialog({
      title: "Rename object",
      message: `New instance ID for ${label}:`,
      initialValue: currentId,
      confirmLabel: "Rename",
      onConfirm: (newId) => {
        setPromptDialog(null);
        if (newId === currentId) return;
        renameObject(selectedFile, distName, newId)
          .then((res) => {
            const isStale = (id) => id === distName || (id || "").startsWith(distName + "/");
            if (selectedNode && (isStale(selectedNode.distName) || isStale(selectedNode.id))) setSelectedNode(null);
            if (focusId && isStale(focusId)) setFocusId(null);
            return refetchAfterEdit().then(() => confirmChange(res, `Renamed ${label} to ${shortClass}-${newId}.`));
          })
          .catch((e) => addToast(String(e.message || e), "error"));
      },
    });
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
    setContextMenu({ x: e.clientX, y: e.clientY, items: nodeMenuItems(node) });
  };

  const nodeMenuItems = (node) => {
    const isObject = node.kind === "mo" || node.tag === "managedObject";
    if (isObject) {
      return [
        { type: "label", label: node.label || node.id },
        {
          label: "Add object here…",
          onClick: () => {
            // AddObjectModal defaults its parent field from focusId (see
            // focusedDistName below) -- syncing focus to the right-clicked
            // node first means the modal opens targeting THIS object, not
            // whatever was last single-clicked elsewhere.
            setFocusId(node.id);
            setAddObjectOpen(true);
          },
        },
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
  };

  // Read-only sources (scp/, example/) are never edited in place: "Edit a
  // copy" duplicates the file into Your uploads, opens the copy, and turns
  // editing on, in one step.
  const handleEditCopy = () => {
    setDuplicating(true);
    duplicateToUploads(selectedFile)
      .then((res) =>
        refreshFiles().then(() => {
          setSelectedFile(res.name);
          setEditMode(true);
          addToast(`Editing a copy: ${res.name}. The original stays untouched.`, "success");
        })
      )
      .catch((e) => addToast(`Couldn't make an editable copy: ${String(e.message || e)}`, "error", 10000))
      .finally(() => setDuplicating(false));
  };

  const handleNewFile = () => {
    setPromptDialog({
      title: "New file",
      message: "New file name:",
      initialValue: "New_Commissioning_File.xml",
      confirmLabel: "Create",
      onConfirm: (name) => {
        setPromptDialog(null);
        createNewFile(name)
          .then((res) => refreshFiles().then(() => setSelectedFile(res.name)))
          .catch((e) => addToast(String(e.message || e), "error"));
      },
    });
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
    refetchAfterEdit().then(() => {
      setFocusId(result.distName);
      confirmChange(result, `Added ${result.distName.split("/").pop()}.`);
    });
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
      .then((res) =>
        refetchAfterEdit().then(() => confirmChange(res, "Restored an earlier version of this file."))
      )
      .then(() => listSnapshots(selectedFile))
      .then(setSnapshots)
      .catch((e) => setSnapshotsError(String(e.message || e)))
      .finally(() => setRestoringId(null));
  };

  // Stable identities for everything the memoized tree/raw rows receive.
  const onTreeToggle = useStableCallback(toggle);
  const onTreeToggleSubtree = useStableCallback(toggleSubtree);
  const onTreeSelect = useStableCallback(handleSelectExplain);
  const onTreeActivate = useStableCallback(handleActivate);
  const onRawToggle = useStableCallback(toggleRaw);
  const onRawToggleSubtree = useStableCallback(toggleRawSubtree);
  const onRawActivate = useStableCallback(handleRawActivate);
  const onSaveEdit = useStableCallback(handleSaveEdit);
  const onDeleteObject = useStableCallback(handleDeleteObject);
  const onDeleteParam = useStableCallback(handleDeleteParam);
  const onRowContextMenu = useStableCallback(handleContextMenu);

  const fraction = splitFraction[rawLayout] ?? DEFAULT_SPLIT_FRACTION;
  const handleSplitDrag = (d) => {
    const el = splitRef.current;
    if (!el) return;
    const size = rawLayout === "stacked" ? el.clientHeight : el.clientWidth;
    if (!size) return;
    setSplitFraction((prev) => ({
      ...prev,
      [rawLayout]: clamp((prev[rawLayout] ?? DEFAULT_SPLIT_FRACTION) + d / size, 0.15, 0.85),
    }));
  };

  return (
    <div className="app">
      <header className="appbar">
        <Wordmark />
        <div className="appbar-actions">
          <ThemeSwitcher value={theme} onChange={setTheme} />
          <button className="btn btn-quiet" onClick={() => setParamBrowserOpen(true)}>
            <Icon name="book" />
            Parameter Browser
          </button>
          <button className="btn btn-quiet" onClick={() => setSiteManagementOpen(true)}>
            <Icon name="folders" />
            Site Management
          </button>
        </div>
      </header>

      <div className="body">
        {sidebarCollapsed ? (
          <button className="pane-rail" onClick={() => setSidebarCollapsed(false)} aria-label="Show file list">
            <Icon name="panel-left" />
            <span className="pane-rail-label">Files</span>
          </button>
        ) : (
          <>
            <FileSidebar
              width={sidebarWidth}
              allFiles={files}
              uploadedFiles={uploadedFiles}
              scpFiles={scpFiles}
              exampleFiles={exampleFiles}
              selectedFile={selectedFile}
              onSelectFile={setSelectedFile}
              fileFilter={fileFilter}
              onFileFilterChange={setFileFilter}
              versionFilter={versionFilter}
              onVersionFilterChange={setVersionFilter}
              collapsedSections={collapsedSections}
              onToggleSection={toggleSection}
              onNewFile={handleNewFile}
              onUploaded={(single) =>
                refreshFiles().then(() => {
                  if (single) setSelectedFile(single);
                })
              }
              onFileMenu={handleFileMenu}
              filesError={filesError}
              addToast={addToast}
              onCollapse={() => setSidebarCollapsed(true)}
            />
            <Resizer
              title="Drag to resize the file list"
              onDrag={(dx) => setSidebarWidth((w) => clamp(w + dx, 200, 640))}
            />
          </>
        )}

        <main className="workspace">
          {!selectedFile && (
            <div className="workspace-box">
              <div className="workspace-empty">
                <h1>Open a file to explore it</h1>
                <p>
                  Pick a commissioning file on the left, or drop your own .xml onto the file list. The file is
                  rebuilt as its real object tree, with the raw XML kept in sync underneath.
                </p>
                <p>
                  Click any object, parameter or table row to see what it means and where that explanation
                  comes from.
                </p>
              </div>
            </div>
          )}
          {selectedFile && selectedFileInfo && (
            <>
              <div className="workspace-head">
                <FileHeader
                  file={selectedFileInfo}
                  stats={tree?.stats}
                  tracePath={tracePath}
                  onTraceSelect={handleTraceSelect}
                  completeness={tree ? completeness : null}
                  onOpenRequired={() => setRequiredFieldsOpen(true)}
                  editable={isEditableFile}
                  editMode={editMode}
                  onToggleEdit={() => setEditMode((v) => !v)}
                  onEditCopy={handleEditCopy}
                  duplicating={duplicating}
                  downloadHref={downloadUrl(selectedFile)}
                  history={{
                    open: historyOpen,
                    toggle: toggleHistory,
                    snapshots,
                    loading: snapshotsLoading,
                    error: snapshotsError,
                    onRestore: handleRestore,
                    restoringId,
                  }}
                />

                {generatorWarning && (
                  <div className="notice is-note" role="status">
                    <Icon name="info" />
                    <span className="notice-text">{generatorWarning}</span>
                    <button className="btn btn-quiet" onClick={() => setGeneratorWarning(null)}>
                      Dismiss
                    </button>
                  </div>
                )}

                <div className="toolbar-wrap">
                  <div className="toolbar" role="toolbar" aria-label="Tree view">
                    <label className="input-with-icon toolbar-search">
                      <Icon name="search" />
                      <input
                        className="input"
                        placeholder="Search names, classes and values"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={(e) => e.key === "Escape" && setQuery("")}
                        aria-label="Search this file's tree"
                      />
                      {query && (
                        <button className="icon-btn input-clear" onClick={() => setQuery("")} aria-label="Clear search">
                          <Icon name="x" />
                        </button>
                      )}
                    </label>
                    <button
                      className="btn"
                      onClick={expandAll}
                      aria-label="Expand all"
                      title="Expand every node"
                    >
                      <Icon name="expand-all" />
                      <span className="btn-label">Expand all</span>
                    </button>
                    <button
                      className="btn"
                      onClick={collapseAll}
                      aria-label="Collapse all"
                      title="Collapse every node"
                    >
                      <Icon name="collapse-all" />
                      <span className="btn-label">Collapse all</span>
                    </button>
                    <span className="toolbar-sep" aria-hidden="true" />
                    <button
                      className="btn btn-toggle"
                      aria-pressed={showRawView}
                      onClick={() => setShowRawView((v) => !v)}
                      title="Show the file exactly as written, in sync with the tree"
                    >
                      <Icon name="layout-stacked" />
                      Raw XML
                    </button>
                    <button
                      className="btn btn-toggle"
                      aria-pressed={highlightOfficial}
                      onClick={() => setHighlightOfficial((v) => !v)}
                      title="Tint rows whose explanation comes verbatim from Nokia's own parameter dictionary"
                    >
                      <span className="official-swatch" aria-hidden="true" />
                      Official
                    </button>
                    {canEditNow && (
                      <>
                        <span className="toolbar-sep" aria-hidden="true" />
                        <button className="btn" onClick={() => setAddObjectOpen(true)} title="Add a new managed object">
                          <Icon name="plus" />
                          Add object
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {loadingTree && <div className="workspace-status">Parsing {selectedFile}…</div>}
              {treeError && (
                <div className="workspace-status is-error">Couldn't parse this file: {treeError}</div>
              )}

              {!loadingTree && !treeError && tree && (
                <>
                  {kbError && (
                    <div className="workspace-status is-error">Couldn't load the knowledge base: {kbError}</div>
                  )}
                  {!kbError && !kb && <div className="workspace-status">Loading knowledge base…</div>}
                  {!kbError && kb && (
                    <div
                      ref={splitRef}
                      className={"split-container" + (showRawView && rawLayout === "stacked" ? " stacked" : "")}
                    >
                      <section
                        className="split-pane split-tree"
                        aria-label="Object tree"
                        style={{
                          ...(labelCol ? { "--label-col": `${labelCol}px` } : null),
                          ...(!showRawView
                            ? { flex: 1 }
                            : rawLayout === "stacked"
                            ? { height: `${fraction * 100}%`, flex: "0 0 auto" }
                            : { width: `${fraction * 100}%`, flex: "0 0 auto" }),
                        }}
                      >
                        {logicalFocusMissing && (
                          <div className="notice is-quiet">
                            Not in the reconstructed tree — this raw XML element doesn't map to a browsable node.
                          </div>
                        )}
                        <div className="tree-scroll" ref={treeScrollRef}>
                          {displayNodes.length === 0 ? (
                            <div className="workspace-status">
                              Nothing in this file matches "{query}". Search looks at object names, classes,
                              parameter names and values.{" "}
                              <button className="link-btn" onClick={() => setQuery("")}>
                                Clear search
                              </button>
                            </div>
                          ) : (
                            <TreeView
                              nodes={displayNodes}
                              traceId={traceId}
                              tabbableId={tabbableId}
                              editedIds={editedIds}
                              expanded={expanded}
                              onToggle={onTreeToggle}
                              onToggleSubtree={onTreeToggleSubtree}
                              onSelect={onTreeSelect}
                              onActivate={onTreeActivate}
                              selectedId={selectedNode?.id}
                              activeId={focusId}
                              forceExpand={query.trim().length > 0}
                              query={query}
                              editable={canEditNow}
                              onSaveEdit={onSaveEdit}
                              onDeleteObject={onDeleteObject}
                              onDeleteParam={onDeleteParam}
                              onContextMenu={onRowContextMenu}
                              kb={highlightOfficial ? kb : null}
                            />
                          )}
                        </div>
                      </section>

                      {showRawView && (
                        <>
                          <Resizer
                            title="Drag to resize"
                            orientation={rawLayout === "stacked" ? "horizontal" : "vertical"}
                            onDrag={handleSplitDrag}
                          />
                          <section className="split-pane split-raw" aria-label="Raw XML">
                            <div className="raw-toolbar" role="toolbar" aria-label="Raw XML">
                              <span className="pane-title">Raw XML</span>
                              <label className="input-with-icon raw-find">
                                <Icon name="search" />
                                <input
                                  className="input"
                                  placeholder="Find in raw XML"
                                  value={rawQuery}
                                  onChange={(e) => setRawQuery(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                      e.preventDefault();
                                      gotoRawMatch(e.shiftKey ? -1 : 1);
                                    } else if (e.key === "Escape") {
                                      setRawQuery("");
                                    }
                                  }}
                                  aria-label="Find in raw XML (Enter for next match, Shift+Enter for previous)"
                                />
                              </label>
                              <span className="match-count" aria-live="polite">
                                {rawQuery.trim()
                                  ? `${rawMatches.length ? rawMatchIndex + 1 : 0} of ${rawMatches.length}`
                                  : ""}
                              </span>
                              <span className="btn-pair">
                              <button
                                className="icon-btn"
                                onClick={() => gotoRawMatch(-1)}
                                disabled={rawMatches.length === 0}
                                aria-label="Previous match"
                                title="Previous match (Shift+Enter)"
                              >
                                <Icon name="arrow-up" />
                              </button>
                              <button
                                className="icon-btn"
                                onClick={() => gotoRawMatch(1)}
                                disabled={rawMatches.length === 0}
                                aria-label="Next match"
                                title="Next match (Enter)"
                              >
                                <Icon name="arrow-down" />
                              </button>
                              </span>
                              <span className="toolbar-sep" aria-hidden="true" />
                              <button className="icon-btn" onClick={expandAllRaw} aria-label="Expand all raw XML" title="Expand all">
                                <Icon name="expand-all" />
                              </button>
                              <button className="icon-btn" onClick={collapseAllRaw} aria-label="Collapse all raw XML" title="Collapse all">
                                <Icon name="collapse-all" />
                              </button>
                              <span className="toolbar-sep" aria-hidden="true" />
                              <div className="segmented" role="group" aria-label="Split layout">
                                <button
                                  className="icon-btn"
                                  aria-pressed={rawLayout === "stacked"}
                                  onClick={() => setRawLayout("stacked")}
                                  aria-label="Stacked: tree above, raw XML below"
                                  title="Stacked: tree above, raw XML below"
                                >
                                  <Icon name="layout-stacked" />
                                </button>
                                <button
                                  className="icon-btn"
                                  aria-pressed={rawLayout === "side"}
                                  onClick={() => setRawLayout("side")}
                                  aria-label="Side by side"
                                  title="Side by side"
                                >
                                  <Icon name="layout-side" />
                                </button>
                              </div>
                            </div>
                            {rawFocusMissing && (
                              <div className="notice is-quiet">
                                Not its own element in this file — this object is only implied by another
                                element's distName path.
                              </div>
                            )}
                            {rawLoading && <div className="workspace-status">Loading raw XML…</div>}
                            {rawError && <div className="workspace-status is-error">{rawError}</div>}
                            {rawTree && !rawLoading && (
                              <div className="tree-scroll raw-scroll" ref={rawScrollRef}>
                                <RawXmlView
                                  root={rawTree.root}
                                  editedIds={editedIds}
                                  expanded={rawExpanded}
                                  onToggle={onRawToggle}
                                  onToggleSubtree={onRawToggleSubtree}
                                  onActivate={onRawActivate}
                                  focusId={focusId}
                                  tabbableId={rawTabbableId}
                                  query={rawQuery}
                                  editable={canEditNow}
                                  onSaveEdit={onSaveEdit}
                                  onContextMenu={onRowContextMenu}
                                  kb={highlightOfficial ? kb : null}
                                />
                              </div>
                            )}
                          </section>
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
          <button className="pane-rail" onClick={() => setExplainCollapsed(false)} aria-label="Show explanation panel">
            <Icon name="panel-right" />
            <span className="pane-rail-label">Explanation</span>
          </button>
        ) : (
          <>
            <Resizer
              title="Drag to resize the explanation panel"
              onDrag={(dx) => setExplainWidth((w) => clamp(w - dx, 280, 800))}
            />
            <aside className="explain-pane" style={{ width: explainWidth }} aria-label="Explanation">
              <div className="pane-header">
                <span className="pane-title">Explanation</span>
                <div className="pane-header-actions">
                  <button
                    className="icon-btn"
                    onClick={() => setExplainCollapsed(true)}
                    aria-label="Hide explanation panel"
                    title="Hide explanation panel"
                  >
                    <Icon name="panel-right" />
                  </button>
                </div>
              </div>
              {kb ? (
                <ExplainPanel
                  node={selectedNode}
                  kb={kb}
                  onClose={() => setSelectedNode(null)}
                  editable={canEditNow}
                  filename={selectedFile}
                  onParamAdded={handleParamSet}
                />
              ) : (
                <div className="explain-panel empty">
                  <p>Loading knowledge base…</p>
                </div>
              )}
            </aside>
          </>
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
          rows={missingRequired || []}
          readOnly={!isEditableFile}
          onClose={() => setRequiredFieldsOpen(false)}
          onSaved={handleParamSet}
          onShowInTree={(distName, paramName) => {
            setRequiredFieldsOpen(false);
            const paramId = `${distName}::p::${paramName}`;
            const node = tree ? findNodeInForest(tree.children, paramId) || findNodeInForest(tree.children, distName) : null;
            setFocusId(node ? node.id : distName);
            if (node) setSelectedNode(node);
          }}
        />
      )}

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={contextMenu.items}
          onClose={() => setContextMenu(null)}
        />
      )}

      {confirmDialog && (
        <ConfirmDialog
          title={confirmDialog.title}
          message={confirmDialog.message}
          confirmLabel={confirmDialog.confirmLabel}
          danger={confirmDialog.danger}
          onConfirm={confirmDialog.onConfirm}
          onCancel={() => setConfirmDialog(null)}
        />
      )}

      {promptDialog && (
        <PromptDialog
          title={promptDialog.title}
          message={promptDialog.message}
          initialValue={promptDialog.initialValue}
          placeholder={promptDialog.placeholder}
          confirmLabel={promptDialog.confirmLabel}
          onConfirm={promptDialog.onConfirm}
          onCancel={() => setPromptDialog(null)}
        />
      )}

      {siteManagementOpen && (
        <SiteManagementModal
          onClose={() => setSiteManagementOpen(false)}
          onOpenFile={(filename) => setSelectedFile(filename)}
          addToast={addToast}
        />
      )}

      {paramBrowserOpen && <ParameterBrowserModal onClose={() => setParamBrowserOpen(false)} />}

      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
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
        el.scrollIntoView({ block: "center", inline: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
      } else if (retriesLeft > 0) {
        setTimeout(() => scrollToDataId(container, attr, id, retriesLeft - 1), 40);
      }
    });
  });
}

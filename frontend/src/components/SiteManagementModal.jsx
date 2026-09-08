import React, { useEffect, useMemo, useState } from "react";
import {
  getSiteManagementTree,
  createFolder,
  updateFolder,
  deleteFolder,
  updateFileMeta,
  searchSiteManagement,
} from "../api.js";
import { FolderTree, FILE_MIME } from "./FolderTree.jsx";
import { ContextMenu } from "./ContextMenu.jsx";
import { ConfirmDialog } from "./ConfirmDialog.jsx";
import { PromptDialog } from "./PromptDialog.jsx";

const FAMILY_LABELS = { sran: "SRAN", legacy: "Legacy", mixed: "Mixed", unknown: "Unknown" };

// Some filenames exist in more than one source (example/ deliberately
// mirrors a few real scp/ files) -- name alone is NOT a safe React key or a
// safe way to address "this specific file" through the API. A duplicate
// key corrupts React's list reconciliation badly enough that it can leave
// stale rows on screen even after the data is correctly filtered down --
// this is exactly what happened before this fix.
const fileKey = (f) => `${f.source}:${f.name}`;

function formatBytes(n) {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Site Management: a virtual folder/tag/site organization layer over every
 * file the app already knows about (uploads, scp/, example/) -- see
 * backend/app/sitemgmt.py. Folders and tags are pure metadata; nothing here
 * ever moves or renames a real file. Drag a file (or a whole folder) onto
 * a folder in the sidebar to file it there; drag onto "Unfiled" or the
 * empty area below the tree to un-file/un-nest it.
 */
export function SiteManagementModal({ onClose, onOpenFile, addToast }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [selectedFolderId, setSelectedFolderId] = useState("ALL");
  const [query, setQuery] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [siteFilter, setSiteFilter] = useState("");
  const [familyFilter, setFamilyFilter] = useState("");
  const [sortBy, setSortBy] = useState("name");
  const [sortDir, setSortDir] = useState("asc");
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [contextMenu, setContextMenu] = useState(null);
  const [confirmDialog, setConfirmDialog] = useState(null);
  const [promptDialog, setPromptDialog] = useState(null);
  const [editingTagsFor, setEditingTagsFor] = useState(null);
  const [tagDraft, setTagDraft] = useState("");
  const [editingSiteFor, setEditingSiteFor] = useState(null);
  const [siteDraft, setSiteDraft] = useState("");

  const refresh = () =>
    getSiteManagementTree()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isFiltering = Boolean(query.trim() || tagFilter || siteFilter || familyFilter);

  useEffect(() => {
    if (!isFiltering) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    const handle = setTimeout(() => {
      searchSiteManagement({ q: query.trim(), tag: tagFilter, site: siteFilter, family: familyFilter, sortBy, sortDir })
        .then(setSearchResults)
        .catch((e) => addToast(String(e.message || e), "error"))
        .finally(() => setSearching(false));
    }, 250);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, tagFilter, siteFilter, familyFilter, sortBy, sortDir]);

  const visibleFiles = useMemo(() => {
    if (!data) return [];
    if (isFiltering) return searchResults || [];
    let files = data.files;
    if (selectedFolderId === "ALL") {
      // no filter
    } else if (selectedFolderId === null) {
      files = files.filter((f) => !f.folderId);
    } else {
      files = files.filter((f) => String(f.folderId) === String(selectedFolderId));
    }
    const dir = sortDir === "desc" ? -1 : 1;
    const keyFn =
      { name: (f) => f.name.toLowerCase(), size: (f) => f.sizeBytes, mtime: (f) => f.mtime, site: (f) => (f.site || "").toLowerCase(), family: (f) => f.family || "" }[
        sortBy
      ] || ((f) => f.name.toLowerCase());
    return [...files].sort((a, b) => (keyFn(a) > keyFn(b) ? 1 : keyFn(a) < keyFn(b) ? -1 : 0) * dir);
  }, [data, isFiltering, searchResults, selectedFolderId, sortBy, sortDir]);

  // Search/filters intentionally override the folder view (see visibleFiles
  // below) so results can span every folder -- but that means clicking a
  // folder while a search/filter is still active would otherwise appear to
  // do nothing at all (still showing search results, unscoped to any
  // folder), which reads as "this folder shows every file." Clicking a
  // folder always means "show me what's in here," so it clears any active
  // search/filter first.
  const handleSelectFolder = (id) => {
    setSelectedFolderId(id);
    setQuery("");
    setTagFilter("");
    setSiteFilter("");
    setFamilyFilter("");
  };

  const handleDropFile = (filename, source, folderId) => {
    updateFileMeta(filename, { source, folderId })
      .then(() => {
        // Jump straight to the folder you just dropped into, so the result
        // is immediately visible rather than relying on a separate click
        // afterward -- also sidesteps ever landing on a stale search/filter
        // view right after a drop.
        handleSelectFolder(folderId);
        return refresh();
      })
      .catch((e) => addToast(String(e.message || e), "error"));
  };
  const handleDropFolder = (folderId, parentId) => {
    updateFolder(folderId, { parentId })
      .then(refresh)
      .catch((e) => addToast(String(e.message || e), "error"));
  };

  const handleCreateFolder = (parentId) => {
    setPromptDialog({
      title: "New folder",
      message: "Folder name:",
      initialValue: "",
      confirmLabel: "Create",
      onConfirm: (name) => {
        setPromptDialog(null);
        createFolder(name, parentId).then(refresh).catch((e) => addToast(String(e.message || e), "error"));
      },
    });
  };

  const handleRenameFolder = (folder) => {
    setPromptDialog({
      title: "Rename folder",
      message: `New name for ${folder.name}:`,
      initialValue: folder.name,
      confirmLabel: "Rename",
      onConfirm: (name) => {
        setPromptDialog(null);
        updateFolder(folder.id, { name }).then(refresh).catch((e) => addToast(String(e.message || e), "error"));
      },
    });
  };

  const handleDeleteFolder = (folder) => {
    setConfirmDialog({
      title: "Delete folder",
      message: `Delete "${folder.name}"? Nested folders are removed too, but files inside are only un-filed -- never deleted.`,
      confirmLabel: "Delete",
      danger: true,
      onConfirm: () => {
        setConfirmDialog(null);
        deleteFolder(folder.id)
          .then(() => {
            if (selectedFolderId === folder.id) setSelectedFolderId("ALL");
            return refresh();
          })
          .catch((e) => addToast(String(e.message || e), "error"));
      },
    });
  };

  const handleFolderContextMenu = (e, folder) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { type: "label", label: folder.name },
        { label: "New subfolder…", onClick: () => handleCreateFolder(folder.id) },
        { label: "Rename…", onClick: () => handleRenameFolder(folder) },
        { label: "Delete folder", danger: true, onClick: () => handleDeleteFolder(folder) },
      ],
    });
  };

  const handleRootContextMenu = (e) => {
    e.preventDefault();
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      items: [{ label: "New top-level folder…", onClick: () => handleCreateFolder(null) }],
    });
  };

  const handleFileContextMenu = (e, file) => {
    e.preventDefault();
    e.stopPropagation();
    const items = [
      { type: "label", label: file.name },
      {
        label: "Open",
        onClick: () => {
          onOpenFile(file.name);
          onClose();
        },
      },
    ];
    if (file.folderId) {
      items.push({ label: "Remove from folder", onClick: () => handleDropFile(file.name, file.source, null) });
    }
    setContextMenu({ x: e.clientX, y: e.clientY, items });
  };

  const commitTags = (f) => {
    const tags = tagDraft.split(",").map((t) => t.trim()).filter(Boolean);
    updateFileMeta(f.name, { source: f.source, tags })
      .then(() => {
        setEditingTagsFor(null);
        return refresh();
      })
      .catch((e) => addToast(String(e.message || e), "error"));
  };
  const commitSite = (f) => {
    updateFileMeta(f.name, { source: f.source, site: siteDraft.trim() })
      .then(() => {
        setEditingSiteFor(null);
        return refresh();
      })
      .catch((e) => addToast(String(e.message || e), "error"));
  };

  return (
    <>
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal sitemgmt-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h3>Site Management</h3>
            <button className="close-btn" onClick={onClose}>
              ×
            </button>
          </div>

          <div className="sitemgmt-toolbar">
            <input
              className="search-box"
              style={{ margin: 0, flex: 1 }}
              placeholder="Search file names, tags, site, or inside file contents…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoFocus
            />
            <select value={tagFilter} onChange={(e) => setTagFilter(e.target.value)}>
              <option value="">All tags</option>
              {(data?.allTags || []).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select value={siteFilter} onChange={(e) => setSiteFilter(e.target.value)}>
              <option value="">All sites</option>
              {(data?.allSites || []).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select value={familyFilter} onChange={(e) => setFamilyFilter(e.target.value)}>
              <option value="">All types</option>
              <option value="sran">SRAN</option>
              <option value="legacy">Legacy</option>
              <option value="mixed">Mixed</option>
              <option value="unknown">Unknown</option>
            </select>
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="name">Sort: Name</option>
              <option value="size">Sort: Size</option>
              <option value="mtime">Sort: Modified</option>
              <option value="site">Sort: Site</option>
              <option value="family">Sort: Type</option>
            </select>
            <button
              className="btn icon-btn"
              onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
              title="Toggle sort direction"
            >
              {sortDir === "asc" ? "↑" : "↓"}
            </button>
          </div>

          <div className="sitemgmt-body">
            {loading ? (
              <div className="placeholder">Loading…</div>
            ) : error ? (
              <div className="placeholder error">{error}</div>
            ) : (
              <>
                <div className="sitemgmt-sidebar">
                  <div className="sitemgmt-sidebar-header">
                    <span>Folders</span>
                    <button className="btn" onClick={() => handleCreateFolder(null)} title="New top-level folder">
                      + Folder
                    </button>
                  </div>
                  <FolderTree
                    folders={data.folders}
                    files={data.files}
                    selectedId={isFiltering ? "SEARCHING" : selectedFolderId}
                    onSelect={handleSelectFolder}
                    onDropFile={handleDropFile}
                    onDropFolder={handleDropFolder}
                    onContextMenu={handleFolderContextMenu}
                    onContextMenuRoot={handleRootContextMenu}
                  />
                </div>

                <div className="sitemgmt-files">
                  {isFiltering && (
                    <div className="sitemgmt-search-status">
                      {searching ? "Searching…" : `${visibleFiles.length} result${visibleFiles.length === 1 ? "" : "s"}`}
                    </div>
                  )}
                  {visibleFiles.length === 0 && !searching && (
                    <div className="placeholder">
                      {isFiltering ? "No files match." : "No files here yet -- drag one onto this folder, or pick another."}
                    </div>
                  )}
                  <ul className="sitemgmt-file-list">
                    {visibleFiles.map((f) => (
                      <li
                        key={fileKey(f)}
                        className="sitemgmt-file-row"
                        draggable
                        onDragStart={(e) => e.dataTransfer.setData(FILE_MIME, JSON.stringify({ name: f.name, source: f.source }))}
                        onContextMenu={(e) => handleFileContextMenu(e, f)}
                      >
                        <div className="sitemgmt-file-main">
                          <span
                            className={"family-badge family-" + f.family}
                            title={`Object model: ${FAMILY_LABELS[f.family] || f.family}`}
                          >
                            {FAMILY_LABELS[f.family] || f.family}
                          </span>
                          <span className={"source-badge source-" + f.source}>{f.source}</span>
                          <span className="sitemgmt-file-name" onClick={() => { onOpenFile(f.name); onClose(); }} title="Click to open">
                            {f.name}
                          </span>
                          <span className="sitemgmt-file-size">{formatBytes(f.sizeBytes)}</span>
                        </div>
                        <div className="sitemgmt-file-meta">
                          <span className="sitemgmt-meta-label">Site:</span>
                          {editingSiteFor === fileKey(f) ? (
                            <input
                              className="mono"
                              autoFocus
                              list="sitemgmt-site-options"
                              value={siteDraft}
                              onChange={(e) => setSiteDraft(e.target.value)}
                              onBlur={() => commitSite(f)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") commitSite(f);
                                if (e.key === "Escape") setEditingSiteFor(null);
                              }}
                            />
                          ) : (
                            <span
                              className="sitemgmt-editable"
                              onClick={() => {
                                setEditingSiteFor(fileKey(f));
                                setSiteDraft(f.site || "");
                              }}
                            >
                              {f.site || <span className="value empty">+ add</span>}
                            </span>
                          )}
                          <span className="sitemgmt-meta-label">Tags:</span>
                          {editingTagsFor === fileKey(f) ? (
                            <input
                              className="mono"
                              autoFocus
                              list="sitemgmt-tag-options"
                              value={tagDraft}
                              placeholder="tag1, tag2"
                              onChange={(e) => setTagDraft(e.target.value)}
                              onBlur={() => commitTags(f)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") commitTags(f);
                                if (e.key === "Escape") setEditingTagsFor(null);
                              }}
                            />
                          ) : (
                            <span
                              className="sitemgmt-editable sitemgmt-tags"
                              onClick={() => {
                                setEditingTagsFor(fileKey(f));
                                setTagDraft((f.tags || []).join(", "));
                              }}
                            >
                              {f.tags && f.tags.length > 0 ? (
                                f.tags.map((t) => (
                                  <span key={t} className="tag-chip">
                                    {t}
                                  </span>
                                ))
                              ) : (
                                <span className="value empty">+ add</span>
                              )}
                            </span>
                          )}
                        </div>
                        {f.matchedIn === "content" && f.matchSnippet && (
                          <div className="sitemgmt-snippet" title="Matched inside file content">
                            “{f.matchSnippet}”
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              </>
            )}
          </div>

          <datalist id="sitemgmt-tag-options">
            {(data?.allTags || []).map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
          <datalist id="sitemgmt-site-options">
            {(data?.allSites || []).map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        </div>
      </div>

      {contextMenu && (
        <ContextMenu x={contextMenu.x} y={contextMenu.y} items={contextMenu.items} onClose={() => setContextMenu(null)} />
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
          confirmLabel={promptDialog.confirmLabel}
          onConfirm={promptDialog.onConfirm}
          onCancel={() => setPromptDialog(null)}
        />
      )}
    </>
  );
}

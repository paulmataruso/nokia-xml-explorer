import React from "react";

const FILE_MIME = "application/x-sitemgmt-file";
const FOLDER_MIME = "application/x-sitemgmt-folder";

// FILE_MIME's payload is JSON {name, source} rather than a bare filename --
// some filenames exist in more than one source (example/ deliberately
// mirrors a few real scp/ files), so the name alone doesn't say which
// physical file is being dragged.
function parseFilePayload(raw) {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return parsed && parsed.name ? parsed : null;
  } catch {
    return null;
  }
}

function FolderRow({ folder, depth, childrenByParent, selectedId, onSelect, dragOverId, setDragOverId, onDropFile, onDropFolder, onContextMenu, fileCounts }) {
  const kids = childrenByParent.get(folder.id) || [];
  const count = fileCounts.get(folder.id) || 0;

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOverId(folder.id);
  };
  const handleDrop = (e) => {
    e.preventDefault();
    setDragOverId(null);
    const file = parseFilePayload(e.dataTransfer.getData(FILE_MIME));
    if (file) {
      onDropFile(file.name, file.source, folder.id);
      return;
    }
    const fid = e.dataTransfer.getData(FOLDER_MIME);
    if (fid && fid !== folder.id) onDropFolder(fid, folder.id);
  };

  return (
    <li>
      <div
        className={"folder-row" + (selectedId === folder.id ? " selected" : "") + (dragOverId === folder.id ? " drag-over" : "")}
        style={{ paddingLeft: 8 + depth * 16 }}
        onClick={() => onSelect(folder.id)}
        draggable
        onDragStart={(e) => e.dataTransfer.setData(FOLDER_MIME, folder.id)}
        onDragOver={handleDragOver}
        onDragLeave={() => setDragOverId((cur) => (cur === folder.id ? null : cur))}
        onDrop={handleDrop}
        onContextMenu={(e) => onContextMenu(e, folder)}
        title={folder.name}
      >
        <span className="folder-icon">📁</span>
        <span className="folder-name">{folder.name}</span>
        {count > 0 && <span className="folder-count">{count}</span>}
      </div>
      {kids.length > 0 && (
        <ul className="folder-level">
          {kids.map((k) => (
            <FolderRow
              key={k.id}
              folder={k}
              depth={depth + 1}
              childrenByParent={childrenByParent}
              selectedId={selectedId}
              onSelect={onSelect}
              dragOverId={dragOverId}
              setDragOverId={setDragOverId}
              onDropFile={onDropFile}
              onDropFolder={onDropFolder}
              onContextMenu={onContextMenu}
              fileCounts={fileCounts}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

/**
 * Left-hand folder sidebar for Site Management. Folders are purely
 * organizational metadata (see backend/app/sitemgmt.py) -- dragging a file
 * or folder here never touches a real file, just updates its folderId/
 * parentId. "All files" (id null, sentinel "ALL") and "Unfiled" (id null,
 * real null) are both fixed pseudo-folders above the real tree.
 */
export function FolderTree({ folders, files, selectedId, onSelect, onDropFile, onDropFolder, onContextMenu, onContextMenuRoot }) {
  const [dragOverId, setDragOverId] = React.useState(null);

  const childrenByParent = new Map();
  for (const f of folders) {
    const key = f.parentId || null;
    if (!childrenByParent.has(key)) childrenByParent.set(key, []);
    childrenByParent.get(key).push(f);
  }
  for (const list of childrenByParent.values()) {
    list.sort((a, b) => a.name.localeCompare(b.name));
  }

  const fileCounts = new Map();
  for (const f of files) {
    if (f.folderId) fileCounts.set(f.folderId, (fileCounts.get(f.folderId) || 0) + 1);
  }
  const unfiledCount = files.filter((f) => !f.folderId).length;

  const rootFolders = childrenByParent.get(null) || [];

  const handleRootDrop = (e, target) => {
    e.preventDefault();
    setDragOverId(null);
    const file = parseFilePayload(e.dataTransfer.getData(FILE_MIME));
    if (file) {
      onDropFile(file.name, file.source, null);
      return;
    }
    const fid = e.dataTransfer.getData(FOLDER_MIME);
    if (fid) onDropFolder(fid, null);
  };

  return (
    <div className="folder-tree">
      <ul className="folder-level">
        <li>
          <div
            className={"folder-row" + (selectedId === "ALL" ? " selected" : "")}
            onClick={() => onSelect("ALL")}
          >
            <span className="folder-icon">🗂</span>
            <span className="folder-name">All files</span>
            <span className="folder-count">{files.length}</span>
          </div>
        </li>
        <li>
          <div
            className={"folder-row" + (selectedId === null ? " selected" : "") + (dragOverId === "UNFILED" ? " drag-over" : "")}
            onClick={() => onSelect(null)}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOverId("UNFILED");
            }}
            onDragLeave={() => setDragOverId((cur) => (cur === "UNFILED" ? null : cur))}
            onDrop={handleRootDrop}
          >
            <span className="folder-icon">📄</span>
            <span className="folder-name">Unfiled</span>
            {unfiledCount > 0 && <span className="folder-count">{unfiledCount}</span>}
          </div>
        </li>
        {rootFolders.map((f) => (
          <FolderRow
            key={f.id}
            folder={f}
            depth={0}
            childrenByParent={childrenByParent}
            selectedId={selectedId}
            onSelect={onSelect}
            dragOverId={dragOverId}
            setDragOverId={setDragOverId}
            onDropFile={onDropFile}
            onDropFolder={onDropFolder}
            onContextMenu={onContextMenu}
            fileCounts={fileCounts}
          />
        ))}
      </ul>
      <div
        className={"folder-tree-root-drop" + (dragOverId === "ROOT" ? " drag-over" : "")}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOverId("ROOT");
        }}
        onDragLeave={() => setDragOverId((cur) => (cur === "ROOT" ? null : cur))}
        onDrop={handleRootDrop}
        onContextMenu={onContextMenuRoot}
        title="Right-click to create a top-level folder, or drop a folder here to un-nest it"
      >
        {dragOverId === "ROOT" && <span className="drag-hint">Drop to move to top level</span>}
      </div>
    </div>
  );
}

export { FILE_MIME, FOLDER_MIME };

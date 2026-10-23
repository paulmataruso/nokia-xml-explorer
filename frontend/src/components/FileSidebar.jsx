import React, { useRef, useState } from "react";
import { uploadFiles } from "../api.js";
import { formatBytes } from "../utils.js";
import { Icon } from "./Icon.jsx";
import { FileMeta } from "./FileMeta.jsx";
import { FileSection } from "./FileSection.jsx";
import { MiddleTruncate } from "./MiddleTruncate.jsx";
import { VersionFilter } from "./VersionFilter.jsx";

function FileRow({ file, selected, onSelect, onMenu, hint }) {
  const unsupported = !file.supported;
  // The row (not just the button) opens the file, so clicking the chips
  // under the name works too; the button is the row's keyboard handle and
  // its click simply bubbles up here. FileMeta's own toggles stop
  // propagation, so expanding a frequency list never opens the file.
  return (
    <li
      className={"file-item" + (selected ? " selected" : "") + (unsupported ? " unsupported" : "")}
      onClick={() => !unsupported && onSelect(file.name)}
      onContextMenu={onMenu ? (e) => onMenu(e, file) : undefined}
    >
      <button
        className="file-open"
        disabled={unsupported}
        aria-current={selected ? "true" : undefined}
        title={unsupported ? "Unsupported file type — not a RAML XML file" : `${file.name} · ${formatBytes(file.sizeBytes)}${hint ? ` · ${hint}` : ""}`}
      >
        <span className="file-name">
          <MiddleTruncate text={file.name} />
        </span>
        <span className="file-size">{formatBytes(file.sizeBytes)}</span>
      </button>
      <FileMeta file={file} />
      {onMenu && (
        <button
          className="icon-btn file-more"
          aria-label={`Actions for ${file.name}`}
          title="Download or delete"
          onClick={(e) => {
            e.stopPropagation();
            onMenu(e, file);
          }}
        >
          <Icon name="more" />
        </button>
      )}
    </li>
  );
}

/**
 * The file list: every .xml the app knows about, grouped by where it lives
 * (your uploads, the scp/ commissioning mount, the bundled examples), with
 * the text and software-release filters that narrow it right above it.
 * The whole sidebar is an upload drop target.
 */
export function FileSidebar({
  width,
  allFiles,
  uploadedFiles,
  scpFiles,
  exampleFiles,
  selectedFile,
  onSelectFile,
  fileFilter,
  onFileFilterChange,
  versionFilter,
  onVersionFilterChange,
  collapsedSections,
  onToggleSection,
  onNewFile,
  onUploaded,
  onFileMenu,
  filesError,
  addToast,
  onCollapse,
}) {
  const inputRef = useRef(null);
  const dragDepth = useRef(0);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const filtering = fileFilter.trim() !== "" || versionFilter.size > 0;

  const doUpload = async (fileList) => {
    const all = Array.from(fileList || []);
    const xml = all.filter((f) => f.name.toLowerCase().endsWith(".xml"));
    const rejected = all.filter((f) => !f.name.toLowerCase().endsWith(".xml"));
    rejected.forEach((f) => addToast(`Skipped ${f.name}: only .xml files can be uploaded.`, "error"));
    if (xml.length === 0) return;
    setUploading(true);
    try {
      const res = await uploadFiles(xml);
      const ok = res.results.filter((r) => r.ok);
      res.results
        .filter((r) => !r.ok)
        .forEach((r) => addToast(`Couldn't upload ${r.name}: ${r.error}`, "error", 10000));
      if (ok.length > 0) {
        addToast(ok.length === 1 ? `Uploaded ${ok[0].name}.` : `Uploaded ${ok.length} files.`, "success");
        onUploaded(ok.length === 1 ? ok[0].name : null);
      }
    } catch (e) {
      addToast(`Upload failed: ${String(e.message || e)}`, "error", 10000);
    } finally {
      setUploading(false);
    }
  };

  const hasFiles = (e) => Array.from(e.dataTransfer?.types || []).includes("Files");

  return (
    <aside
      className={"sidebar" + (dragOver ? " is-drop-target" : "")}
      style={{ width }}
      aria-label="Files"
      onDragEnter={(e) => {
        if (!hasFiles(e)) return;
        dragDepth.current += 1;
        setDragOver(true);
      }}
      onDragOver={(e) => {
        if (hasFiles(e)) e.preventDefault();
      }}
      onDragLeave={(e) => {
        if (!hasFiles(e)) return;
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (dragDepth.current === 0) setDragOver(false);
      }}
      onDrop={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        dragDepth.current = 0;
        setDragOver(false);
        if (!uploading) doUpload(e.dataTransfer.files);
      }}
    >
      <div className="pane-header">
        <span className="pane-title">Files</span>
        <div className="pane-header-actions">
          <button className="icon-btn" onClick={onNewFile} aria-label="New file" title="Start a new, empty commissioning file">
            <Icon name="plus" />
          </button>
          <button
            className="icon-btn"
            onClick={() => inputRef.current && inputRef.current.click()}
            disabled={uploading}
            aria-label="Upload .xml files"
            title="Upload .xml files (or drop them anywhere on this list)"
          >
            <Icon name="upload" />
          </button>
          <button className="icon-btn" onClick={onCollapse} aria-label="Hide file list" title="Hide file list">
            <Icon name="panel-left" />
          </button>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".xml"
          multiple
          hidden
          onChange={(e) => {
            doUpload(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      <div className="sidebar-filters">
        <label className="input-with-icon">
          <Icon name="search" />
          <input
            className="input"
            placeholder="Filter files"
            value={fileFilter}
            onChange={(e) => onFileFilterChange(e.target.value)}
            aria-label="Filter files by name"
          />
        </label>
        <VersionFilter files={allFiles} selected={versionFilter} onChange={onVersionFilterChange} />
      </div>

      {uploading && <div className="sidebar-status">Uploading…</div>}
      {filesError && <div className="sidebar-status is-error">{filesError}</div>}

      <div className="file-sections">
        {uploadedFiles.length > 0 && (
          <FileSection
            id="upload"
            icon="pencil"
            title="Your uploads"
            hint="editable"
            count={uploadedFiles.length}
            collapsed={collapsedSections.has("upload")}
            onToggle={() => onToggleSection("upload")}
          >
            {uploadedFiles.map((f) => (
              <FileRow key={f.name} file={f} selected={selectedFile === f.name} onSelect={onSelectFile} onMenu={onFileMenu} />
            ))}
          </FileSection>
        )}

        <FileSection
          id="scp"
          icon="mast"
          title="Commissioning files"
          hint="read-only"
          count={scpFiles.length}
          collapsed={collapsedSections.has("scp")}
          onToggle={() => onToggleSection("scp")}
        >
          {scpFiles.length === 0 ? (
            <li className="file-section-empty">
              {filtering
                ? "No commissioning files match."
                : "Nothing in scp/ yet. Mount your commissioning folder there and its files appear here."}
            </li>
          ) : (
            scpFiles.map((f) => (
              <FileRow key={f.name} file={f} selected={selectedFile === f.name} onSelect={onSelectFile} />
            ))
          )}
        </FileSection>

        {exampleFiles.length > 0 && (
          <FileSection
            id="example"
            icon="book"
            title="Example files"
            hint="read-only"
            count={exampleFiles.length}
            collapsed={collapsedSections.has("example")}
            onToggle={() => onToggleSection("example")}
          >
            {exampleFiles.map((f) => (
              <FileRow
                key={f.name}
                file={f}
                selected={selectedFile === f.name}
                onSelect={onSelectFile}
                hint="bundled sample file"
              />
            ))}
          </FileSection>
        )}

        {filtering && uploadedFiles.length + scpFiles.length + exampleFiles.length === 0 && (
          <p className="file-sections-empty">No files match these filters.</p>
        )}
      </div>

      {dragOver && (
        <div className="drop-overlay" aria-hidden="true">
          <Icon name="upload" size={20} />
          Drop .xml files to upload
        </div>
      )}
    </aside>
  );
}

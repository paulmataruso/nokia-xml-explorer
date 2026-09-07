import React, { useRef, useState } from "react";
import { uploadFiles } from "../api.js";

export function UploadCard({ onUploaded }) {
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState(null);

  const doUpload = async (fileList) => {
    const files = Array.from(fileList || []).filter((f) => f.name.toLowerCase().endsWith(".xml"));
    const rejected = Array.from(fileList || []).filter((f) => !f.name.toLowerCase().endsWith(".xml"));
    if (files.length === 0) {
      setResults(rejected.map((f) => ({ name: f.name, ok: false, error: "Only .xml files are accepted" })));
      return;
    }
    setBusy(true);
    setResults(null);
    try {
      const res = await uploadFiles(files);
      const combined = [
        ...res.results,
        ...rejected.map((f) => ({ name: f.name, ok: false, error: "Only .xml files are accepted" })),
      ];
      setResults(combined);
      if (combined.some((r) => r.ok)) onUploaded();
    } catch (e) {
      setResults([{ name: "Upload failed", ok: false, error: String(e.message || e) }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="upload-card">
      <div
        className={"drop-zone" + (dragOver ? " drag-over" : "") + (busy ? " busy" : "")}
        onClick={() => !busy && inputRef.current && inputRef.current.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (!busy) doUpload(e.dataTransfer.files);
        }}
      >
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
        <div className="drop-zone-text">
          {busy ? "Uploading…" : "Drag & drop .xml files here, or click to browse"}
        </div>
      </div>
      {results && (
        <ul className="upload-results">
          {results.map((r, i) => (
            <li key={i} className={r.ok ? "upload-ok" : "upload-fail"}>
              {r.ok ? "✓" : "✗"} {r.name}
              {!r.ok && r.error && <span className="upload-error"> — {r.error}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

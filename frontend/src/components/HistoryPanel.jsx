import React from "react";

function parseSnapshotId(id) {
  // "20260907T041316.366Z" -> a real Date
  const m = id.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})\.(\d+)Z$/);
  if (!m) return null;
  const [, y, mo, d, h, mi, s, ms] = m;
  return new Date(`${y}-${mo}-${d}T${h}:${mi}:${s}.${ms}Z`);
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  return `${(n / 1024).toFixed(1)} KB`;
}

export function HistoryPanel({ snapshots, loading, error, onRestore, restoringId }) {
  return (
    <div className="history-panel">
      <div className="history-panel-title">Version history</div>
      <p className="history-panel-hint">Each entry puts the file back to just before that change.</p>
      {loading && <div className="history-empty">Loading…</div>}
      {error && <div className="history-empty error">{error}</div>}
      {!loading && !error && snapshots.length === 0 && (
        <div className="history-empty">No changes yet. Every edit saves a snapshot here first.</div>
      )}
      {!loading && !error && snapshots.length > 0 && (
        <ul className="history-list">
          {snapshots.map((s) => {
            const date = parseSnapshotId(s.id);
            return (
              <li key={s.id} className="history-item">
                <div className="history-item-info">
                  {/* Snapshots saved before labels existed have none. */}
                  <span className="history-item-label">{s.label || "Earlier edit"}</span>
                  <span className="history-item-meta">
                    {date ? date.toLocaleString() : s.id} · {formatBytes(s.sizeBytes)}
                  </span>
                </div>
                <button
                  className="btn"
                  onClick={() => onRestore(s.id)}
                  disabled={restoringId === s.id}
                  title="Put the file back to how it was just before this change"
                >
                  {restoringId === s.id ? "Restoring…" : "Restore"}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

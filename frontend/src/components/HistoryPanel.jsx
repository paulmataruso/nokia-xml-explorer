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
      {loading && <div className="history-empty">Loading…</div>}
      {error && <div className="history-empty error">{error}</div>}
      {!loading && !error && snapshots.length === 0 && (
        <div className="history-empty">No edits yet — snapshots appear here once you make a change.</div>
      )}
      {!loading && !error && snapshots.length > 0 && (
        <ul className="history-list">
          {snapshots.map((s, i) => {
            const date = parseSnapshotId(s.id);
            return (
              <li key={s.id} className="history-item">
                <div className="history-item-info">
                  <span className="history-item-date">
                    {date ? date.toLocaleString() : s.id}
                  </span>
                  <span className="history-item-meta">
                    {i === 0 ? "most recent checkpoint" : ""} · {formatBytes(s.sizeBytes)}
                  </span>
                </div>
                <button
                  className="btn"
                  onClick={() => onRestore(s.id)}
                  disabled={restoringId === s.id}
                  title="Restore the file to this saved state"
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

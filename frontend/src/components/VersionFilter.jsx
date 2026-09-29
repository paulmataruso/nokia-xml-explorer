import React, { useEffect, useMemo, useRef, useState } from "react";

export const UNKNOWN_VERSION = "__unknown__";

// Display order for software families; anything else sorts alphabetically
// after these, with files that have no detectable version last.
const FAMILY_ORDER = ["SBTS", "FL", "TL", "FLF", "TLF", "FLC", "TLC", "xL"];

export function versionKey(file) {
  return file.swVersion || UNKNOWN_VERSION;
}

function familyOf(key) {
  if (key === UNKNOWN_VERSION) return "Unknown";
  const m = key.match(/^[A-Za-z]+/);
  return m ? m[0] : key;
}

function familyRank(family) {
  if (family === "Unknown") return [2, family];
  const i = FAMILY_ORDER.indexOf(family);
  return i === -1 ? [1, family] : [0, String(i).padStart(3, "0")];
}

/**
 * Top-bar "Filter" button + dropdown listing every BTS software release
 * found across the file list (the `swVersion` the backend extracts from
 * each file's managedObject `version` attributes, e.g. "SBTS20C"), grouped
 * by family. Checked releases are the only ones shown in the sidebar; with
 * nothing checked, no filter applies.
 */
export function VersionFilter({ files, selected, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const handleKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handlePointerDown, true);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown, true);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  const groups = useMemo(() => {
    const counts = new Map();
    for (const f of files) {
      if (!f.supported) continue;
      const key = versionKey(f);
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    const byFamily = new Map();
    for (const [key, count] of counts) {
      const fam = familyOf(key);
      if (!byFamily.has(fam)) byFamily.set(fam, []);
      byFamily.get(fam).push({ key, count });
    }
    return [...byFamily.entries()]
      .map(([family, versions]) => ({
        family,
        versions: versions.sort((a, b) => a.key.localeCompare(b.key, undefined, { numeric: true })),
      }))
      .sort((a, b) => {
        const [ra, sa] = familyRank(a.family);
        const [rb, sb] = familyRank(b.family);
        return ra - rb || sa.localeCompare(sb);
      });
  }, [files]);

  const toggle = (key) => {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onChange(next);
  };

  const toggleFamily = (versions) => {
    const allOn = versions.every((v) => selected.has(v.key));
    const next = new Set(selected);
    for (const v of versions) {
      if (allOn) next.delete(v.key);
      else next.add(v.key);
    }
    onChange(next);
  };

  const active = selected.size > 0;

  return (
    <div className="version-filter" ref={ref}>
      <button
        className={"site-mgmt-link" + (active ? " version-filter-active" : "")}
        onClick={() => setOpen((o) => !o)}
        title="Show only files from specific BTS software releases"
      >
        ⏷ Filter{active ? ` (${selected.size})` : ""}
      </button>
      {open && (
        <div className="version-filter-menu">
          <div className="version-filter-header">
            <span>Software version</span>
            <button className="version-filter-clear" onClick={() => onChange(new Set())} disabled={!active}>
              Show all
            </button>
          </div>
          {groups.length === 0 && <div className="version-filter-empty">No XML files found.</div>}
          {groups.map(({ family, versions }) => {
            const checkedCount = versions.filter((v) => selected.has(v.key)).length;
            return (
              <div key={family} className="version-filter-group">
                <label className="version-filter-family">
                  <input
                    type="checkbox"
                    checked={checkedCount === versions.length}
                    ref={(el) => {
                      if (el) el.indeterminate = checkedCount > 0 && checkedCount < versions.length;
                    }}
                    onChange={() => toggleFamily(versions)}
                  />
                  <span>{family}</span>
                </label>
                {versions.map((v) => (
                  <label key={v.key} className="version-filter-item">
                    <input type="checkbox" checked={selected.has(v.key)} onChange={() => toggle(v.key)} />
                    <span className="mono">{v.key === UNKNOWN_VERSION ? "No version detected" : v.key}</span>
                    <span className="version-filter-count">{v.count}</span>
                  </label>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

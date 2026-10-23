import React, { useState } from "react";
import { parseFileName } from "../utils.js";
import { Icon } from "./Icon.jsx";

/**
 * A carrier-frequency tag: shows the first value, and when a file has more
 * than one carrier, becomes a toggle ("+N") that expands to list them all.
 * Clicks don't bubble, so expanding never opens the file itself.
 */
function FrequencyChip({ label, values, title }) {
  const [open, setOpen] = useState(false);
  if (values.length === 0) return null;
  if (values.length === 1) {
    return (
      <span className="file-chip file-chip-freq" title={title}>
        {label} {values[0]}
      </span>
    );
  }
  return (
    <span className={"file-chip-freq-group" + (open ? " open" : "")}>
      <button
        className="file-chip file-chip-freq file-chip-toggle"
        title={open ? `Hide all ${values.length} ${label}s` : `Show all ${values.length} ${label}s`}
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
      >
        {label} {open ? `×${values.length}` : `${values[0]} +${values.length - 1}`}
        <Icon name={open ? "chevron-up" : "chevron-down"} size={12} />
      </button>
      {open &&
        values.map((v) => (
          <span key={v} className="file-chip file-chip-freq" title={title}>
            {v}
          </span>
        ))}
    </span>
  );
}

/**
 * The tags under a file name in the sidebar: BTS software release and
 * serving-cell EARFCNs/NR-ARFCNs (read from the file's contents by the
 * backend), plus band(s) parsed from the file name.
 */
export function FileMeta({ file }) {
  if (!file.supported) return null;
  // The export date is parsed from the file name too, but the name's tail
  // (always visible, see MiddleTruncate) already shows it, so it isn't
  // repeated as a chip.
  const { bands } = parseFileName(file.name);
  const earfcns = file.earfcns || [];
  const nrarfcns = file.nrarfcns || [];
  if (!file.swVersion && bands.length === 0 && earfcns.length === 0 && nrarfcns.length === 0) {
    return null;
  }
  return (
    <span className="file-meta">
      {file.swVersion && (
        <span className="file-chip file-chip-version" title="BTS software release (from file contents)">
          {file.swVersion}
        </span>
      )}
      {bands.map((b) => (
        <span key={b} className="file-chip" title="Band (from file name)">
          {b}
        </span>
      ))}
      <FrequencyChip label="EARFCN" values={earfcns} title="LTE cell DL EARFCN (from file contents)" />
      <FrequencyChip label="NR-ARFCN" values={nrarfcns} title="NR cell DL NR-ARFCN (from file contents)" />
    </span>
  );
}

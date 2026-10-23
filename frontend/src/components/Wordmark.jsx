import React from "react";

/**
 * App-bar wordmark: a small Trace glyph beside the product name. The glyph
 * is a lit route stepping down two levels in the first fiber-code hues and
 * ending on the selected row (the dot), as the tree draws it. Deliberately
 * nothing like a Nokia mark: the name stays plain text in the UI face.
 */
export function Wordmark() {
  return (
    <span className="wordmark">
      <svg className="wordmark-glyph" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
        <path className="wm-1" d="M3 2v6h5" />
        <path className="wm-2" d="M8 8v6h4" />
        <circle className="wm-3" cx="14.5" cy="14" r="2.25" />
      </svg>
      <span className="wordmark-name">
        <span className="wordmark-scope">Nokia AirScale / Flexi Zone</span> XML Explorer
      </span>
    </span>
  );
}

import React from "react";

export function highlightSegments(text, query) {
  const t = String(text ?? "");
  const q = (query || "").trim();
  if (!q) return [{ text: t, match: false }];
  const ql = q.toLowerCase();
  const tl = t.toLowerCase();
  const segments = [];
  let i = 0;
  while (i < t.length) {
    const idx = tl.indexOf(ql, i);
    if (idx === -1) {
      segments.push({ text: t.slice(i), match: false });
      break;
    }
    if (idx > i) segments.push({ text: t.slice(i, idx), match: false });
    segments.push({ text: t.slice(idx, idx + ql.length), match: true });
    i = idx + ql.length;
  }
  return segments;
}

/** Renders `text` with every case-insensitive occurrence of `query` wrapped
 * in <mark>. Passes `text` through unchanged (as a single span) when there's
 * no query. */
export function Highlight({ text, query, className }) {
  const segments = highlightSegments(text, query);
  return (
    <span className={className}>
      {segments.map((s, i) =>
        s.match ? <mark key={i}>{s.text}</mark> : <React.Fragment key={i}>{s.text}</React.Fragment>
      )}
    </span>
  );
}

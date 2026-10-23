import React from "react";

/**
 * Truncates in the middle instead of at the end. Nokia export names share
 * long prefixes ("Configuration_scf_MRBTS-1_DHI_NR_n78_…") and differ only
 * at the tail (date, "-V3", "(copy) (1)"), so end-truncation made dozens of
 * files read identically. The head shrinks with an ellipsis; the tail
 * always stays visible. The tail starts at the last "_" or space that
 * leaves it between 10 and 30 characters, so a date like 20260414-0827
 * is never cut in half.
 */
function splitPoint(s) {
  const minTail = 10;
  const maxTail = 30;
  for (let i = s.length - minTail; i >= s.length - maxTail && i > 0; i--) {
    if (s[i] === "_" || s[i] === " ") return i;
  }
  return s.length - 16;
}

export function MiddleTruncate({ text }) {
  const s = String(text ?? "");
  if (s.length <= 24) return <span className="mt">{s}</span>;
  const at = splitPoint(s);
  return (
    <span className="mt">
      <span className="mt-head">{s.slice(0, at)}</span>
      <span className="mt-tail">{s.slice(at)}</span>
    </span>
  );
}

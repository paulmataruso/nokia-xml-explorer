import { useState } from "react";

const PREFIX = "nokiaXmlExplorer.";

/**
 * useState that remembers its value in this browser (pane widths, split
 * ratio, layout, toggles) so the workspace comes back the way it was left.
 * Storage can be unavailable (private mode, blocked site data), so every
 * read and write is guarded and a failure just falls back to the default /
 * an in-memory value for this session.
 */
export function usePersistentState(key, defaultValue) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(PREFIX + key);
      return raw == null ? defaultValue : JSON.parse(raw);
    } catch {
      return defaultValue;
    }
  });
  const setAndStore = (next) =>
    setValue((prev) => {
      const resolved = typeof next === "function" ? next(prev) : next;
      try {
        localStorage.setItem(PREFIX + key, JSON.stringify(resolved));
      } catch {
        // Not persisted this time; the in-memory state still applies.
      }
      return resolved;
    });
  return [value, setAndStore];
}

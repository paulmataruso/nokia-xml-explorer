import React, { useRef, useState } from "react";

/**
 * Click-to-edit inline value, shared by the logical tree and the raw XML
 * pane so a parameter edits the same way in either place. Manages its own
 * open/draft/saving/error state; `onSave(newValue)` must return a Promise
 * (resolved on success, rejected with an Error on failure).
 *
 * `knownValues`, when non-empty, means the backend was able to determine
 * the FULL closed set of legal values for this parameter (boolean, or an
 * enum with either a documented range or corpus-observed values -- see
 * resolve_known_values in build_class_catalog.py) -- renders a dropdown
 * instead of free text in that case, since typos/invalid values aren't a
 * risk worth free-text entry for a field where every legal option is
 * already known.
 */
export function EditableValue({ value, onSave, placeholder, knownValues }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const cancelingRef = useRef(false);

  const startEdit = (e) => {
    e.stopPropagation();
    cancelingRef.current = false;
    setDraft(value ?? "");
    setError(null);
    setEditing(true);
  };

  const cancel = () => {
    cancelingRef.current = true;
    setEditing(false);
    setError(null);
  };

  const commit = (overrideDraft) => {
    if (cancelingRef.current) {
      cancelingRef.current = false;
      return;
    }
    const finalValue = overrideDraft !== undefined ? overrideDraft : draft;
    if (finalValue === (value ?? "")) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setError(null);
    onSave(finalValue)
      .then(() => {
        setSaving(false);
        setEditing(false);
      })
      .catch((e) => {
        setSaving(false);
        setError(String(e.message || e));
      });
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancel();
    }
  };

  if (editing) {
    const hasKnownValues = knownValues && knownValues.length > 0;
    return (
      <span className="editable-value editing" onClick={(e) => e.stopPropagation()}>
        {hasKnownValues ? (
          <select
            className="edit-input"
            value={draft}
            disabled={saving}
            autoFocus
            onBlur={commit}
            onChange={(e) => {
              const v = e.target.value;
              setDraft(v);
              commit(v);
            }}
          >
            <option value="">— select —</option>
            {(knownValues.includes(draft) || draft === "" ? knownValues : [draft, ...knownValues]).map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        ) : (
          <input
            className="edit-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={commit}
            disabled={saving}
            autoFocus
            onFocus={(e) => e.target.select()}
          />
        )}
        {saving && <span className="edit-status">saving…</span>}
        {error && (
          <span className="edit-error" title={error}>
            ⚠ save failed
          </span>
        )}
      </span>
    );
  }

  return (
    <span className="editable-value" onClick={startEdit} title="Click to edit">
      {value != null && value !== "" ? value : <span className="value empty">{placeholder || "(empty)"}</span>}
    </span>
  );
}

import React, { useRef, useState } from "react";

/**
 * Click-to-edit inline text value, shared by the logical tree and the raw
 * XML pane so a parameter edits the same way in either place. Manages its
 * own open/draft/saving/error state; `onSave(newValue)` must return a
 * Promise (resolved on success, rejected with an Error on failure).
 */
export function EditableValue({ value, onSave, placeholder }) {
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

  const commit = () => {
    if (cancelingRef.current) {
      cancelingRef.current = false;
      return;
    }
    if (draft === (value ?? "")) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setError(null);
    onSave(draft)
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
    return (
      <span className="editable-value editing" onClick={(e) => e.stopPropagation()}>
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

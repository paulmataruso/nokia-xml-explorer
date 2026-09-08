import React, { useState } from "react";

/**
 * In-app replacement for window.prompt() -- a toast can't collect text
 * input, so text-entry cases (rename, new file name) get this small modal
 * instead, styled consistently with ConfirmDialog rather than a browser
 * popup.
 */
export function PromptDialog({ title, message, initialValue = "", placeholder, confirmLabel = "OK", onConfirm, onCancel }) {
  const [value, setValue] = useState(initialValue);

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    onConfirm(trimmed);
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal confirm-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="close-btn" onClick={onCancel}>
            ×
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {message && <p>{message}</p>}
            <input
              type="text"
              className="mono prompt-input"
              value={value}
              placeholder={placeholder}
              autoFocus
              onFocus={(e) => e.target.select()}
              onChange={(e) => setValue(e.target.value)}
            />
          </div>
          <div className="modal-footer">
            <button type="button" className="btn" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="btn active" disabled={!value.trim()}>
              {confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

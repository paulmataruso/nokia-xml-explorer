import React, { useId, useState } from "react";
import { Modal } from "./Modal.jsx";

/**
 * In-app replacement for window.prompt() -- a toast can't collect text
 * input, so text-entry cases (rename, new file name) get this small modal
 * instead, styled consistently with ConfirmDialog rather than a browser
 * popup.
 */
export function PromptDialog({ title, message, initialValue = "", placeholder, confirmLabel = "OK", onConfirm, onCancel }) {
  const [value, setValue] = useState(initialValue);
  const inputId = useId();

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    onConfirm(trimmed);
  };

  return (
    <Modal title={title} className="confirm-dialog" onClose={onCancel}>
      <form onSubmit={handleSubmit}>
        <div className="modal-body">
          {message && (
            <p>
              <label htmlFor={inputId}>{message}</label>
            </p>
          )}
          <input
            id={inputId}
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
          <button type="submit" className="btn btn-primary" disabled={!value.trim()}>
            {confirmLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}

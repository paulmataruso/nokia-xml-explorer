import React from "react";

/**
 * In-app replacement for window.confirm() -- destructive actions (delete)
 * still get an explicit confirmation step, just styled consistently with
 * the rest of the app instead of a browser-chrome popup.
 */
export function ConfirmDialog({ title, message, confirmLabel = "Confirm", danger, onConfirm, onCancel }) {
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal confirm-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="close-btn" onClick={onCancel}>
            ×
          </button>
        </div>
        <div className="modal-body">
          <p>{message}</p>
        </div>
        <div className="modal-footer">
          <button className="btn" onClick={onCancel}>
            Cancel
          </button>
          <button className={"btn" + (danger ? " btn-danger" : " active")} onClick={onConfirm} autoFocus>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

import React from "react";
import { Modal } from "./Modal.jsx";

/**
 * In-app replacement for window.confirm() -- destructive actions (delete)
 * still get an explicit confirmation step, just styled consistently with
 * the rest of the app instead of a browser-chrome popup. Focus starts on
 * Cancel for a destructive action (so Enter never deletes by accident) and
 * on the confirm button otherwise; Esc cancels.
 */
export function ConfirmDialog({ title, message, confirmLabel = "Confirm", danger, onConfirm, onCancel }) {
  return (
    <Modal
      title={title}
      className="confirm-dialog"
      onClose={onCancel}
      footer={
        <>
          <button className="btn" onClick={onCancel} autoFocus={danger}>
            Cancel
          </button>
          <button className={"btn" + (danger ? " btn-danger" : " btn-primary")} onClick={onConfirm} autoFocus={!danger}>
            {confirmLabel}
          </button>
        </>
      }
    >
      <div className="modal-body">
        <p>{message}</p>
      </div>
    </Modal>
  );
}

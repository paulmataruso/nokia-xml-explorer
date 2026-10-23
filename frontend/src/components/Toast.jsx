import React from "react";
import { Icon } from "./Icon.jsx";

const TYPE_ICON = { success: "check-circle", error: "alert", info: "info" };

/**
 * In-app replacement for window.alert() -- keeps error/success feedback
 * inside the app's own visual language instead of a browser-chrome popup.
 * Stacks bottom-right, auto-dismisses, click to dismiss early. A toast may
 * carry one action (e.g. "Undo" after an edit); pressing it runs the
 * action and dismisses the toast. The stack is a polite live region, so
 * screen readers announce each result as it lands.
 */
export function ToastStack({ toasts, onDismiss }) {
  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={"toast" + (t.type ? ` toast-${t.type}` : "")}>
          <Icon name={TYPE_ICON[t.type] || "info"} className="toast-icon" />
          <span className="toast-message">{t.message}</span>
          {t.action && (
            <button
              className="btn btn-quiet toast-action"
              onClick={() => {
                t.action.onClick();
                onDismiss(t.id);
              }}
            >
              {t.action.icon && <Icon name={t.action.icon} />}
              {t.action.label}
            </button>
          )}
          <button className="icon-btn toast-close" onClick={() => onDismiss(t.id)} aria-label="Dismiss">
            <Icon name="x" size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}

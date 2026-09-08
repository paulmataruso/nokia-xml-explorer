import React from "react";

/**
 * In-app replacement for window.alert() -- keeps error/success feedback
 * inside the app's own visual language instead of a browser-chrome popup.
 * Stacks bottom-right, auto-dismisses, click to dismiss early.
 */
export function ToastStack({ toasts, onDismiss }) {
  if (toasts.length === 0) return null;
  return (
    <div className="toast-stack">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={"toast" + (t.type ? ` toast-${t.type}` : "")}
          onClick={() => onDismiss(t.id)}
          title="Click to dismiss"
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}

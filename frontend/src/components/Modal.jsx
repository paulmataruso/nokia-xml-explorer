import React, { useEffect, useId, useRef, useState } from "react";
import { Icon } from "./Icon.jsx";

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * The one dialog shell every modal uses: role="dialog" + aria-modal with
 * its title as the accessible name, Esc to close, Tab kept inside while
 * it's open, focus moved in on open (to the first [autofocus] element, or
 * the first focusable one) and handed back to whatever opened it on close.
 * A click on the backdrop closes it, as before.
 */
export function Modal({ title, className = "", onClose, children, footer, headerExtra }) {
  const ref = useRef(null);
  const titleId = useId();
  // Captured during the first render, before any child's autoFocus runs,
  // so it really is whatever opened the dialog.
  const [opener] = useState(() => document.activeElement);

  useEffect(() => {
    const el = ref.current;
    // A child with autoFocus has already taken focus by now; otherwise start
    // on the first control in the body (not the header's close button).
    if (el && !el.contains(document.activeElement)) {
      const first = el.querySelector(".modal-body " + FOCUSABLE.split(", ").join(", .modal-body ")) || el.querySelector(FOCUSABLE);
      (first || el).focus();
    }
    return () => {
      if (opener && typeof opener.focus === "function" && document.contains(opener)) opener.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleKeyDown = (e) => {
    if (e.key === "Escape") {
      // A nested dialog (e.g. a confirm inside Site Management) handles its
      // own Esc first; don't close the outer one too.
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== "Tab") return;
    const items = [...ref.current.querySelectorAll(FOCUSABLE)].filter((n) => n.offsetParent !== null);
    if (items.length === 0) return;
    const firstItem = items[0];
    const lastItem = items[items.length - 1];
    if (e.shiftKey && document.activeElement === firstItem) {
      e.preventDefault();
      lastItem.focus();
    } else if (!e.shiftKey && document.activeElement === lastItem) {
      e.preventDefault();
      firstItem.focus();
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        ref={ref}
        className={"modal" + (className ? ` ${className}` : "")}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <div className="modal-header">
          <h2 id={titleId}>{title}</h2>
          {headerExtra}
          <button className="icon-btn" onClick={onClose} aria-label="Close" title="Close (Esc)">
            <Icon name="x" />
          </button>
        </div>
        {children}
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}

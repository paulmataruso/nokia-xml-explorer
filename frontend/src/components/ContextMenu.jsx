import React, { useEffect, useRef, useState } from "react";

/**
 * Small fixed-position right-click menu. Renders wherever the click
 * happened rather than inline in the row -- unlike the inline delete
 * buttons, its position doesn't depend on how wide the row's content is or
 * how far the tree pane has scrolled, so it's always reachable even for
 * long rows.
 */
export function ContextMenu({ x, y, items, onClose }) {
  const ref = useRef(null);
  const [pos, setPos] = useState({ left: x, top: y, visibility: "hidden" });

  useEffect(() => {
    const handlePointerDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    const handleKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", handlePointerDown, true);
    document.addEventListener("keydown", handleKey);
    document.addEventListener("scroll", onClose, true);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown, true);
      document.removeEventListener("keydown", handleKey);
      document.removeEventListener("scroll", onClose, true);
    };
  }, [onClose]);

  // Clamp after the first paint, once we know the menu's actual size --
  // keeps it fully on-screen when you right-click near an edge.
  useEffect(() => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const left = Math.min(x, window.innerWidth - rect.width - 8);
    const top = Math.min(y, window.innerHeight - rect.height - 8);
    setPos({ left: Math.max(4, left), top: Math.max(4, top), visibility: "visible" });
  }, [x, y]);

  return (
    <div className="context-menu" style={pos} ref={ref}>
      {items.map((item, i) =>
        item.type === "label" ? (
          <div key={i} className="context-menu-label">
            {item.label}
          </div>
        ) : (
          <button
            key={i}
            className={item.danger ? "danger" : ""}
            disabled={item.disabled}
            title={item.title}
            onClick={() => {
              item.onClick();
              onClose();
            }}
          >
            {item.label}
          </button>
        )
      )}
    </div>
  );
}

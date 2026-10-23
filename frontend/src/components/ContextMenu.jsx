import React, { useEffect, useRef, useState } from "react";

/**
 * Small fixed-position right-click menu. Renders wherever the click
 * happened rather than inline in the row -- unlike the inline delete
 * buttons, its position doesn't depend on how wide the row's content is or
 * how far the tree pane has scrolled, so it's always reachable even for
 * long rows.
 *
 * A real menu for the keyboard too (it also opens from Shift+F10 / the menu
 * key on a tree row): focus moves to the first item, arrows and Home/End
 * move between items, Esc or Tab closes it, and focus goes back to whatever
 * opened it.
 */
export function ContextMenu({ x, y, items, onClose }) {
  const ref = useRef(null);
  const [pos, setPos] = useState({ left: x, top: y, visibility: "hidden" });
  const [opener] = useState(() => document.activeElement);

  useEffect(() => {
    const handlePointerDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    // Close on the user's own scroll gestures (wheel / touch), not on any
    // "scroll" event: the tree's smooth scroll-sync from the click that
    // came just before a right-click fires scroll events too, and used to
    // close the menu the instant it opened.
    // Esc closes it from anywhere -- including when no item can take focus
    // (e.g. a menu whose only action is disabled).
    const handleKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    document.addEventListener("mousedown", handlePointerDown, true);
    document.addEventListener("wheel", onClose, { capture: true, passive: true });
    document.addEventListener("touchmove", onClose, { capture: true, passive: true });
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.removeEventListener("mousedown", handlePointerDown, true);
      document.removeEventListener("wheel", onClose, { capture: true });
      document.removeEventListener("touchmove", onClose, { capture: true });
    };
  }, [onClose]);

  // Hand focus back only when the menu actually closes (unmount) -- not
  // when the effect above re-runs because the parent passed a new onClose.
  useEffect(
    () => () => {
      if (opener && typeof opener.focus === "function" && document.contains(opener)) opener.focus();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  // Clamp after the first paint, once we know the menu's actual size --
  // keeps it fully on-screen when you right-click near an edge.
  useEffect(() => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const left = Math.min(x, window.innerWidth - rect.width - 8);
    const top = Math.min(y, window.innerHeight - rect.height - 8);
    setPos({ left: Math.max(4, left), top: Math.max(4, top), visibility: "visible" });
  }, [x, y]);

  // Move focus in once the menu is visible: it renders hidden until it has
  // measured and clamped itself, and a hidden element can't take focus.
  useEffect(() => {
    if (pos.visibility === "visible") ref.current?.querySelector('[role="menuitem"]:not(:disabled)')?.focus();
  }, [pos.visibility]);

  const handleKeyDown = (e) => {
    const menuItems = [...ref.current.querySelectorAll('[role="menuitem"]:not(:disabled)')];
    const i = menuItems.indexOf(document.activeElement);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const next = e.key === "ArrowDown" ? (i + 1) % menuItems.length : (i - 1 + menuItems.length) % menuItems.length;
      menuItems[next]?.focus();
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      menuItems[e.key === "Home" ? 0 : menuItems.length - 1]?.focus();
    } else if (e.key === "Escape" || e.key === "Tab") {
      e.preventDefault();
      e.stopPropagation();
      onClose();
    }
  };

  return (
    <div className="context-menu" style={pos} ref={ref} role="menu" onKeyDown={handleKeyDown}>
      {items.map((item, i) =>
        item.type === "label" ? (
          <div key={i} className="context-menu-label" role="presentation">
            {item.label}
          </div>
        ) : (
          <button
            key={i}
            role="menuitem"
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

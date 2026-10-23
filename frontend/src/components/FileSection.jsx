import React from "react";
import { Icon } from "./Icon.jsx";

/**
 * One titled group in the sidebar file list ("Your uploads", "Commissioning
 * files", "Example files"). The header is a real button that collapses or
 * expands the group; it stays stuck to the top of the list while you
 * scroll through that group, so you always know which source you're in.
 */
export function FileSection({ id, icon, title, hint, count, collapsed, onToggle, children }) {
  const listId = `file-section-${id}`;
  return (
    <section className={"file-section" + (collapsed ? " collapsed" : "")} aria-label={title}>
      <h2 className="file-section-heading">
        <button
          className="file-section-header"
          aria-expanded={!collapsed}
          aria-controls={listId}
          onClick={onToggle}
          title={collapsed ? `Show ${title.toLowerCase()}` : `Hide ${title.toLowerCase()}`}
        >
          <Icon name={collapsed ? "chevron-right" : "chevron-down"} size={12} className="file-section-chevron" />
          <Icon name={icon} size={14} className="file-section-icon" />
          <span className="file-section-title">{title}</span>
          {hint && <span className="file-section-hint">{hint}</span>}
          <span className="file-section-count">{count}</span>
        </button>
      </h2>
      {!collapsed && (
        <ul className="file-list" id={listId}>
          {children}
        </ul>
      )}
    </section>
  );
}

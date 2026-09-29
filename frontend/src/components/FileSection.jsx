import React from "react";

/**
 * One titled group in the sidebar file list ("Your uploads", "Commissioning
 * files", "Example files"). Clicking the header collapses/expands it.
 */
export function FileSection({ className, listClassName, icon, title, count, collapsed, onToggle, children }) {
  return (
    <div className={`file-section ${className}` + (collapsed ? " collapsed" : "")}>
      <div
        className="file-section-header"
        role="button"
        tabIndex={0}
        aria-expanded={!collapsed}
        title={collapsed ? `Show ${title.toLowerCase()}` : `Hide ${title.toLowerCase()}`}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onToggle();
          }
        }}
      >
        <span className="file-section-chevron">{collapsed ? "▸" : "▾"}</span>
        <span className="file-section-icon">{icon}</span>
        <span>{title}</span>
        <span className="file-section-count">{count}</span>
      </div>
      {!collapsed && <ul className={"file-list" + (listClassName ? ` ${listClassName}` : "")}>{children}</ul>}
    </div>
  );
}

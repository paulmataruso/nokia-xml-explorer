import React from "react";

export const THEMES = [
  { id: "night", label: "Night", hint: "Indigo panels with neon-pastel accents (default)" },
  { id: "slate", label: "Slate", hint: "Lifted cool slate with vivid accents" },
  { id: "github", label: "GitHub", hint: "Close to the original look, punchier" },
];

/**
 * App-bar colour theme picker: a radio group of the three dark themes (see
 * the theme blocks at the top of styles.css). Each option's swatch is a
 * .theme-preview carrying that theme's data-theme, so its chips are drawn
 * from the theme's own tokens rather than hard-coded copies.
 */
export function ThemeSwitcher({ value, onChange }) {
  const handleKeyDown = (e) => {
    const i = THEMES.findIndex((t) => t.id === value);
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      onChange(THEMES[(i + 1) % THEMES.length].id);
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      onChange(THEMES[(i - 1 + THEMES.length) % THEMES.length].id);
    }
  };
  return (
    <div className="theme-switch" role="radiogroup" aria-label="Colour theme" onKeyDown={handleKeyDown}>
      {THEMES.map((t) => (
        <button
          key={t.id}
          role="radio"
          aria-checked={value === t.id}
          tabIndex={value === t.id ? 0 : -1}
          className="theme-option"
          onClick={() => onChange(t.id)}
          title={t.hint}
        >
          <span className="theme-preview" data-theme={t.id} aria-hidden="true">
            <span className="tp-bg" />
            <span className="tp-signal" />
            <span className="tp-official" />
          </span>
          {t.label}
        </button>
      ))}
    </div>
  );
}

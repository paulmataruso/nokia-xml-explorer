import React from "react";

/**
 * The app's one icon set: hand-authored 16x16 strokes (1.5px, round caps),
 * drawn in currentColor so an icon always takes its control's ink. Replaces
 * the emoji/unicode glyphs the UI used to lean on, which rendered as empty
 * boxes on machines without an emoji font and read as "black left-pointing
 * triangle" to screen readers. Icons are decorative (aria-hidden); the
 * control that holds one carries the accessible name.
 */
const PATHS = {
  "chevron-right": <path d="M6 3.5 10.5 8 6 12.5" />,
  "chevron-down": <path d="M3.5 6 8 10.5 12.5 6" />,
  "chevron-up": <path d="M3.5 10 8 5.5l4.5 4.5" />,
  "chevron-left": <path d="M10 3.5 5.5 8l4.5 4.5" />,
  x: <path d="m4 4 8 8M12 4l-8 8" />,
  plus: <path d="M8 3v10M3 8h10" />,
  search: (
    <>
      <circle cx="7" cy="7" r="4.25" />
      <path d="m10.25 10.25 3.25 3.25" />
    </>
  ),
  upload: <path d="M8 10.5v-8M5 5.5l3-3 3 3M2.75 10.5v1.75c0 .69.56 1.25 1.25 1.25h8c.69 0 1.25-.56 1.25-1.25V10.5" />,
  download: <path d="M8 2.5v8M5 7.5l3 3 3-3M2.75 10.5v1.75c0 .69.56 1.25 1.25 1.25h8c.69 0 1.25-.56 1.25-1.25V10.5" />,
  filter: <path d="M2.5 3.5h11L9.25 8.5v3.75l-2.5 1.25v-5z" />,
  history: (
    <>
      <path d="M2.9 9.5A5.25 5.25 0 1 0 4 4.4" />
      <path d="M2.5 2.5v2.75h2.75M8 5.25V8l2 1.25" />
    </>
  ),
  pencil: <path d="m10.25 2.75 3 3L6 13H3v-3z" />,
  copy: (
    <>
      <rect x="5.5" y="5.5" width="8" height="8" rx="1.25" />
      <path d="M10.5 5.5V3.75c0-.69-.56-1.25-1.25-1.25h-5.5c-.69 0-1.25.56-1.25 1.25v5.5c0 .69.56 1.25 1.25 1.25H5.5" />
    </>
  ),
  folders: (
    <>
      <path d="M4.5 4.75V4c0-.55.45-1 1-1h2.25l1.25 1.5h4c.55 0 1 .45 1 1v5c0 .55-.45 1-1 1h-.75" />
      <path d="M1.5 6.5c0-.55.45-1 1-1h2.25L6 7h4.5c.55 0 1 .45 1 1v4.5c0 .55-.45 1-1 1h-8c-.55 0-1-.45-1-1z" />
    </>
  ),
  folder: <path d="M2 4.25C2 3.56 2.56 3 3.25 3H6l1.5 1.75h5.25c.69 0 1.25.56 1.25 1.25v5.75c0 .69-.56 1.25-1.25 1.25h-9.5C2.56 13 2 12.44 2 11.75z" />,
  file: (
    <>
      <path d="M4 2.5h5l3 3v8H4z" />
      <path d="M9 2.5v3h3" />
    </>
  ),
  trash: <path d="M2.75 4.25h10.5M6 4.25V2.75h4v1.5M4 4.25l.75 9h6.5l.75-9M6.75 6.75v4M9.25 6.75v4" />,
  more: (
    <>
      <circle cx="3.5" cy="8" r=".9" fill="currentColor" stroke="none" />
      <circle cx="8" cy="8" r=".9" fill="currentColor" stroke="none" />
      <circle cx="12.5" cy="8" r=".9" fill="currentColor" stroke="none" />
    </>
  ),
  check: <path d="m3 8.5 3 3 7-7" />,
  "check-circle": (
    <>
      <circle cx="8" cy="8" r="5.75" />
      <path d="m5.5 8.25 1.75 1.75 3.25-3.5" />
    </>
  ),
  alert: <path d="M8 2.5 14 13H2zM8 6.75v2.75M8 11.25v.01" />,
  info: (
    <>
      <circle cx="8" cy="8" r="5.75" />
      <path d="M8 7.25v3.5M8 5.1v.01" />
    </>
  ),
  "arrow-up": <path d="M8 13V3M4 7l4-4 4 4" />,
  "arrow-down": <path d="M8 3v10M4 9l4 4 4-4" />,
  "layout-stacked": (
    <>
      <rect x="2.5" y="2.5" width="11" height="11" rx="1.25" />
      <path d="M2.5 8h11" />
    </>
  ),
  "layout-side": (
    <>
      <rect x="2.5" y="2.5" width="11" height="11" rx="1.25" />
      <path d="M8 2.5v11" />
    </>
  ),
  "expand-all": <path d="M5 6 8 3l3 3M5 10l3 3 3-3" />,
  "collapse-all": <path d="m5 3 3 3 3-3M5 13l3-3 3 3" />,
  "panel-left": (
    <>
      <rect x="2.5" y="2.5" width="11" height="11" rx="1.25" />
      <path d="M6.25 2.5v11" />
    </>
  ),
  "panel-right": (
    <>
      <rect x="2.5" y="2.5" width="11" height="11" rx="1.25" />
      <path d="M9.75 2.5v11" />
    </>
  ),
  flag: <path d="M3.5 13.5V2.75M3.5 3h8L9.75 5.75 11.5 8.5h-8" />,
  undo: <path d="M4.5 6.5H10a3 3 0 0 1 0 6H6M6.5 4 4 6.5 6.5 9" />,
  external: <path d="M9 2.75h4.25V7M13.25 2.75 7.5 8.5M11 9.5v2.75c0 .41-.34.75-.75.75h-6.5a.75.75 0 0 1-.75-.75v-6.5c0-.41.34-.75.75-.75H6.5" />,
  table: (
    <>
      <rect x="2.5" y="3" width="11" height="10" rx="1" />
      <path d="M2.5 6.5h11M6.5 6.5V13" />
    </>
  ),
  mast: <path d="M8 7v6.5M6 13.5h4M5.4 4.3a3.6 3.6 0 0 0 0 5.4M10.6 4.3a3.6 3.6 0 0 1 0 5.4M8 6.95v.01" />,
  book: <path d="M3 3.75c0-.69.56-1.25 1.25-1.25H13v9.25H4.25c-.69 0-1.25.56-1.25 1.25zM3 13c0 .69.56 1.25 1.25 1.25H13" />,
  dot: <circle cx="8" cy="8" r="2.5" fill="currentColor" stroke="none" />,
  bolt: <path d="M9 1.75 3.75 9h4.25l-1 5.25L12.25 7H8z" />,
  link: (
    <path d="M6.9 9.1a2.6 2.6 0 0 0 3.7 0l2.1-2.1a2.6 2.6 0 0 0-3.7-3.7l-.8.8M9.1 6.9a2.6 2.6 0 0 0-3.7 0L3.3 9a2.6 2.6 0 0 0 3.7 3.7l.8-.8" />
  ),
  // The Tree view: rows stepping in from one guide.
  tree: <path d="M3.5 3h3M3.5 3v9.5M3.5 7.5h2.5M3.5 12.5h2.5M8.5 3h4M8.5 7.5h4M8.5 12.5h4" />,
  // The Map view: one object, what points at it above, what it points at below.
  map: (
    <>
      <rect x="5.75" y="6.5" width="4.5" height="3" rx=".75" />
      <path d="M8 6.5V4.75M8 9.5v1.75M4 11.25h8M4 11.25v1.5M12 11.25v1.5M5.25 2.5h5.5" />
    </>
  ),
  // Centre the map on an object.
  target: (
    <>
      <circle cx="8" cy="8" r="4.75" />
      <circle cx="8" cy="8" r="1.25" />
      <path d="M8 1.75v1.5M8 12.75v1.5M1.75 8h1.5M12.75 8h1.5" />
    </>
  ),
  fit: <path d="M2.75 5.75v-3h3M10.25 2.75h3v3M13.25 10.25v3h-3M5.75 13.25h-3v-3" />,
  minus: <path d="M3 8h10" />,
  "arrow-left": <path d="M13 8H3M7 4 3 8l4 4" />,
  "arrow-right": <path d="M3 8h10M9 4l4 4-4 4" />,
};

export function Icon({ name, size = 16, className }) {
  const body = PATHS[name];
  if (!body) return null;
  return (
    <svg
      className={"icon" + (className ? ` ${className}` : "")}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {body}
    </svg>
  );
}

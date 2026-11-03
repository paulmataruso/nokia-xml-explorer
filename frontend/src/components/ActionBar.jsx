import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { listActions } from "../api.js";
import { Icon } from "./Icon.jsx";
import { Modal } from "./Modal.jsx";

const matches = (a, q) =>
  !q || q.split(/\s+/).every((t) => `${a.title} ${a.summary} ${a.group} ${a.keywords}`.toLowerCase().includes(t));

// Title matches first: "ip address" finds "Change a BTS IP address" before the MME action, whose keywords say IP.
const rank = (a, q) => (q && q.split(/\s+/).every((t) => a.title.toLowerCase().includes(t)) ? 0 : 1);

/**
 * The action bar (Ctrl+K, or Actions in the app bar): every site action for
 * the open file, grouped and searchable. Actions that can't run on this
 * file stay listed, dimmed, with the reason, so the bar also says what the
 * file lacks. A combobox over a listbox: arrows move, Enter runs.
 * `onRun(action)` gets the backend's catalog entry (id, title, ui, ...).
 */
export function ActionBar({ filename, onRun, onClose }) {
  const [data, setData] = useState(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listId = useId();
  const listRef = useRef(null);

  useEffect(() => {
    if (!filename) return;
    let cancelled = false;
    listActions(filename)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setData({ error: String(e.message || e) }));
    return () => {
      cancelled = true;
    };
  }, [filename]);

  const q = query.trim().toLowerCase();
  const shown = useMemo(
    () => (data?.actions || []).filter((a) => matches(a, q)).sort((x, y) => rank(x, q) - rank(y, q)),
    [data, q],
  );
  // Runnable ones first within each group; groups keep the backend's order, after title matches.
  const groups = useMemo(() => {
    const out = [];
    for (const a of shown) {
      let g = out.find((x) => x.name === a.group);
      if (!g) out.push((g = { name: a.group, items: [] }));
      g.items.push(a);
    }
    for (const g of out) g.items.sort((x, y) => Number(y.available) - Number(x.available));
    return out;
  }, [shown]);
  const runnable = groups.flatMap((g) => g.items.filter((a) => a.available));

  useEffect(() => setActive(0), [q]);
  useEffect(() => {
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!runnable.length) return;
      const d = e.key === "ArrowDown" ? 1 : -1;
      setActive((i) => (i + d + runnable.length) % runnable.length);
    } else if (e.key === "Enter" && runnable[active]) {
      e.preventDefault();
      onRun(runnable[active]);
    }
  };

  const activeId = runnable[active] ? `${listId}-${runnable[active].id}` : undefined;
  let body;
  if (!filename) body = <div className="placeholder">Open a file to see what can be done to it.</div>;
  else if (!data) body = <div className="placeholder">Reading the file…</div>;
  else if (data.error) body = <div className="notice is-error">{data.error}</div>;
  else if (!shown.length) body = <div className="placeholder">No action matches “{query}”.</div>;
  else
    body = (
      <ul className="ab-list" role="listbox" id={listId} ref={listRef} aria-label="Actions">
        {groups.map((g) => (
          <li key={g.name} role="presentation">
            <div className="ab-group" role="presentation">
              {g.name}
            </div>
            <ul role="group" aria-label={g.name} className="ab-group-list">
              {g.items.map((a) => {
                const selected = a.available && runnable[active]?.id === a.id;
                return (
                  <li
                    key={a.id}
                    id={`${listId}-${a.id}`}
                    role="option"
                    aria-selected={selected}
                    aria-disabled={!a.available}
                    className={"ab-item" + (selected ? " is-active" : "") + (a.available ? "" : " is-unavailable")}
                    onMouseMove={() => a.available && setActive(runnable.indexOf(a))}
                    onClick={() => a.available && onRun(a)}
                  >
                    <Icon name="bolt" />
                    <span className="ab-item-main">
                      <span className="ab-item-title">{a.title}</span>
                      <span className="ab-item-sub">{a.available ? a.summary : a.reason}</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ul>
    );

  return (
    <Modal title="Actions" className="action-bar-modal" onClose={onClose}>
      <label className="input-with-icon ab-search">
        <Icon name="search" />
        <input
          type="text"
          className="input"
          autoFocus
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-activedescendant={activeId}
          aria-label="Search actions"
          placeholder="Search actions"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
        />
      </label>
      <div className="modal-body ab-body">{body}</div>
      {data && !data.error && !data.editable && (
        <div className="ab-foot">
          This file is read-only: an action writes its change into an editable copy in Your uploads.
        </div>
      )}
    </Modal>
  );
}

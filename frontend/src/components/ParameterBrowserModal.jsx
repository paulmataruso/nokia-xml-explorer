import React, { useEffect, useMemo, useRef, useState } from "react";
import { Modal } from "./Modal.jsx";
import { Icon } from "./Icon.jsx";
import { Highlight } from "./Highlight.jsx";
import { CONFIDENCE_META, THREEGPP_STATUS_META } from "./ExplainPanel.jsx";
import { browseParameters, getCatalogClasses, getParameterDetail } from "../api.js";
import { parseThreeGppRefs } from "../utils.js";

const PAGE_SIZE = 200;
const RANGE_PREVIEW = 10;

// A name alone isn't unique: pMax lives on LNCEL and NRCELL, and a table
// can share its name with a scalar elsewhere.
const rowKey = (r) => `${r.kind}:${r.class || ""}:${r.name}`;

const KIND_LABELS = { param: "Parameter", list: "Table", field: "Table field" };
const REQUIRED_LABELS = { Mandatory: "Mandatory", Optional: "Optional", "Value set by the system": "Set by system" };
const SOURCE_SHORT = { official: "Official", high: "High", medium: "Medium", low: "Low", heuristic: "Auto" };

function requiredLabel(row) {
  if (row.instanceId && row.required === "Mandatory") return "Id";
  return REQUIRED_LABELS[row.required] || "—";
}

// "LNCEL pMax" finds LNCEL's pMax; mark the pMax part, not the whole query.
function nameHighlight(row, q) {
  const tokens = q.toLowerCase().split(/[\s./]+/).filter(Boolean);
  const cls = (row.class || "").toLowerCase();
  if (tokens.length > 1 && cls && tokens.includes(cls)) return tokens.filter((t) => t !== cls).join(" ");
  return q;
}

function typeLabel(row) {
  if (row.kind === "list") return "table";
  return [row.dataType, row.unit].filter(Boolean).join(" · ") || "—";
}

function subtitleFor(d) {
  if (d.kind === "field") return "Field inside a table parameter; the knowledge base doesn't record which table";
  return `${KIND_LABELS[d.kind]} on ${d.class}`;
}

// The dictionaries store some defaults as numbers (5.0) and the real-file
// value as text ("5"); those are the same default.
function sameValue(a, b) {
  const x = String(a).trim();
  const y = String(b).trim();
  return x === y || (x !== "" && y !== "" && Number(x) === Number(y));
}

function KV({ k, children, mono }) {
  return (
    <div className="kv-row">
      <span className="k">{k}</span>
      <span className={"v" + (mono ? " mono" : "")}>{children}</span>
    </div>
  );
}

function ParamDetail({ detail, loading, error, onPick, onFilterClass }) {
  const [rangeOpen, setRangeOpen] = useState(false);
  useEffect(() => setRangeOpen(false), [detail]);

  if (error) {
    return (
      <div className="param-detail">
        <div className="placeholder error">{error}</div>
      </div>
    );
  }
  if (!detail) {
    return (
      <div className="param-detail">
        <div className="placeholder">
          {loading
            ? "Loading…"
            : "Pick a parameter to see everything known about it: official name, range, defaults, how it can be changed and what your files set it to."}
        </div>
      </div>
    );
  }

  const conf = CONFIDENCE_META[detail.confidence];
  const docClass = detail.docClass ? detail.docClass.split("/").pop() : null;
  const borrowed = !detail.docIsOwn && docClass;
  const rangeLines = detail.officialRange ? detail.officialRange.split("\n") : [];
  const refLinks = parseThreeGppRefs(detail.threeGppRef);
  const shownDefault = detail.officialDefault || detail.resolvedDefault;

  return (
    <div className="param-detail">
      <h3 className="mono">{detail.name}</h3>
      <div className="explain-subtitle">{subtitleFor(detail)}</div>
      {conf && <div className={`badge badge-${conf.tone} explain-badge`}>{conf.label}</div>}

      {borrowed && (
        <div className="notice is-note explain-borrowed" role="note">
          <Icon name="info" />
          <span className="notice-text">
            The modification, features and 3GPP notes below were written for{" "}
            <span className="mono">
              {docClass}.{detail.name}
            </span>
            , the same name on another class. Check that they apply to <span className="mono">{detail.class}</span>.
          </span>
        </div>
      )}

      <div className="param-detail-kv">
        {detail.fullName && <KV k="Official name">{detail.fullName}</KV>}
        {detail.class && (
          <KV k="Class">
            <span className="mono">{detail.class}</span>
            {detail.classFullName && <span className="param-detail-aside"> {detail.classFullName}</span>}
          </KV>
        )}
        {detail.parentClass && (
          <KV k="Parent class" mono>
            {detail.parentClass}
          </KV>
        )}
        <KV k="Kind">{KIND_LABELS[detail.kind]}</KV>
        {detail.dataType && detail.kind !== "list" && <KV k="Data type">{detail.dataType}</KV>}
        {detail.unit && <KV k="Unit">{detail.unit}</KV>}
        {detail.required && <KV k="Required on creation">{detail.required}</KV>}
        {shownDefault && (
          <KV k="Default" mono>
            {shownDefault}
          </KV>
        )}
        {detail.resolvedDefault && detail.officialDefault != null && !sameValue(detail.resolvedDefault, detail.officialDefault) && (
          <KV k="Add Object writes" mono>
            {detail.resolvedDefault}
          </KV>
        )}
        {detail.modification && <KV k="Modification">{detail.modification}</KV>}
        {detail.observed != null && (
          <KV k="Set in your files">
            {detail.observed ? `${detail.occurrences.toLocaleString()} time${detail.occurrences === 1 ? "" : "s"}` : "Never"}
          </KV>
        )}
      </div>

      {detail.instanceId && detail.required === "Mandatory" && (
        <div className="explain-notes">
          This is the class's own instance id. The dictionary calls it Mandatory, but the id lives in the object's
          distName, so Add Object doesn't write it and it's never flagged as missing.
        </div>
      )}

      <div className="explain-description">{detail.description || "No description available."}</div>

      {detail.officialRange && (
        <div className="kv-block">
          <div className="k">Valid range</div>
          <div className="v-block mono">
            {rangeOpen || rangeLines.length <= RANGE_PREVIEW ? detail.officialRange : rangeLines.slice(0, RANGE_PREVIEW).join("\n")}
          </div>
          {rangeLines.length > RANGE_PREVIEW && (
            <button className="link-btn range-toggle" onClick={() => setRangeOpen((o) => !o)}>
              {rangeOpen ? "Show fewer" : `Show all ${rangeLines.length} lines`}
            </button>
          )}
        </div>
      )}
      {!detail.officialRange && detail.knownValues.length > 0 && (
        <div className="kv-block">
          <div className="k">Known values</div>
          <div className="v-block mono">{detail.knownValues.join(", ")}</div>
        </div>
      )}
      {detail.exampleValues.length > 0 && (
        <div className="kv-block">
          <div className="k">Values in your files</div>
          <div className="v-block mono">{detail.exampleValues.join(", ")}</div>
        </div>
      )}
      {detail.relatedFeatures && (
        <div className="kv-block">
          <div className="k">Requires feature/license</div>
          <div className="v-block">{detail.relatedFeatures}</div>
        </div>
      )}
      {(detail.threeGppName || detail.threeGppRef) && (
        <div className="kv-block">
          <div className="k">3GPP</div>
          <div className="v-block">
            {detail.threeGppName && <div>{detail.threeGppName}</div>}
            {refLinks.length > 0
              ? refLinks.map(({ spec, url }, i) => (
                  <React.Fragment key={spec}>
                    {i > 0 && ", "}
                    <a href={url} target="_blank" rel="noopener noreferrer">
                      3GPP TS {spec}
                    </a>
                  </React.Fragment>
                ))
              : detail.threeGppRef}
          </div>
        </div>
      )}
      {detail.threeGpp && (
        <div className="attr-table threegpp-block">
          <div className="attr-table-title">3GPP standardization</div>
          <div className={`badge badge-${THREEGPP_STATUS_META[detail.threeGpp.status]?.tone || "quiet"}`}>
            {THREEGPP_STATUS_META[detail.threeGpp.status]?.label || detail.threeGpp.status}
          </div>
          {detail.threeGpp.specs?.length > 0 && (
            <div className="kv-block">
              {detail.threeGpp.specs.map((s) => (
                <div key={s.spec}>
                  <a href={s.url} target="_blank" rel="noopener noreferrer">
                    {s.spec}
                  </a>
                  {" — "}
                  {s.title}
                </div>
              ))}
            </div>
          )}
          {detail.threeGpp.note && <div className="kv-block">{detail.threeGpp.note}</div>}
        </div>
      )}
      {detail.notes && (
        <div className="explain-notes">
          <strong>Notes:</strong> {detail.notes}
        </div>
      )}

      {(detail.class || detail.alsoOn.length > 0) && (
        <div className="attr-table">
          <div className="attr-table-title">Browse</div>
          <div className="param-detail-links">
            {detail.class && (
              <button className="btn" onClick={() => onFilterClass(detail.class)}>
                <Icon name="filter" />
                Everything on {detail.class}
              </button>
            )}
          </div>
          {detail.alsoOn.length > 0 && (
            <div className="kv-block">
              <div className="k">Same name on</div>
              <div className="param-detail-links">
                {detail.alsoOn.map((o) => (
                  <button
                    key={`${o.kind}:${o.class}`}
                    className="link-btn mono"
                    onClick={() => onPick({ name: detail.name, class: o.class, kind: o.kind })}
                    title={o.kind === "list" ? "A table there" : undefined}
                  >
                    {o.class}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      {detail.sourceName && <div className="param-detail-source">Source: {detail.sourceName}</div>}
    </div>
  );
}

/**
 * Parameter Browser: every parameter the knowledge base knows, one row per
 * class it lives on, searchable and filterable. Backed by GET
 * /api/parameters (search, best match first) and /api/parameters/detail
 * (the full record for one row). Read-only; nothing here touches a file.
 */
export function ParameterBrowserModal({ onClose }) {
  const [query, setQuery] = useState("");
  const [classText, setClassText] = useState("");
  const [kind, setKind] = useState("");
  const [required, setRequired] = useState("");
  const [source, setSource] = useState("");
  const [seen, setSeen] = useState("");
  const [classes, setClasses] = useState([]);
  const [result, setResult] = useState({ total: 0, rows: [] });
  const [searching, setSearching] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const requestRef = useRef(0);
  const selectedRef = useRef(null);
  const detailCache = useRef(new Map());
  const listRef = useRef(null);

  useEffect(() => {
    getCatalogClasses()
      .then((list) => setClasses([...list].sort((a, b) => a.shortName.localeCompare(b.shortName))))
      .catch(() => setClasses([]));
  }, []);

  // The class filter applies only once the text names a real class, so
  // typing "LNC" on the way to "LNCEL" doesn't empty the list.
  const classFilter = useMemo(() => {
    const t = classText.trim().toLowerCase();
    if (!t) return "";
    return classes.find((c) => c.shortName.toLowerCase() === t)?.shortName || null;
  }, [classText, classes]);

  const filters = { q: query.trim(), cls: classFilter || "", kind, required, source, seen };

  useEffect(() => {
    const id = ++requestRef.current;
    setSearching(true);
    const handle = setTimeout(() => {
      browseParameters({ ...filters, limit: PAGE_SIZE })
        .then((res) => {
          if (id !== requestRef.current) return;
          setResult(res);
          setError(null);
          if (listRef.current) listRef.current.scrollTop = 0;
        })
        .catch((e) => id === requestRef.current && setError(String(e.message || e)))
        .finally(() => id === requestRef.current && setSearching(false));
    }, 180);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.q, filters.cls, kind, required, source, seen]);

  const loadMore = () => {
    const id = requestRef.current;
    setLoadingMore(true);
    browseParameters({ ...filters, offset: result.rows.length, limit: PAGE_SIZE })
      .then((res) => {
        if (id !== requestRef.current) return;
        setResult((prev) => ({ total: res.total, rows: [...prev.rows, ...res.rows] }));
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoadingMore(false));
  };

  const pick = (row) => {
    const key = rowKey(row);
    selectedRef.current = key;
    setSelected(key);
    setDetailError(null);
    const cached = detailCache.current.get(key);
    if (cached) {
      setDetail(cached);
      setDetailLoading(false);
      return;
    }
    setDetailLoading(true);
    setDetail(null);
    getParameterDetail({ name: row.name, cls: row.class, kind: row.kind })
      .then((d) => {
        detailCache.current.set(key, d);
        if (selectedRef.current === key) setDetail(d);
      })
      .catch((e) => selectedRef.current === key && setDetailError(String(e.message || e)))
      .finally(() => selectedRef.current === key && setDetailLoading(false));
  };

  const focusRow = (index) => {
    const rows = result.rows;
    if (rows.length === 0) return;
    const i = Math.max(0, Math.min(rows.length - 1, index));
    pick(rows[i]);
    const el = listRef.current?.querySelector(`[data-row-index="${i}"]`);
    if (el) {
      el.focus();
      el.scrollIntoView({ block: "nearest" });
    }
  };

  const selectedIndex = result.rows.findIndex((r) => rowKey(r) === selected);
  const tabbableIndex = selectedIndex >= 0 ? selectedIndex : 0;

  const handleListKeyDown = (e) => {
    const steps = { ArrowDown: 1, ArrowUp: -1, PageDown: 10, PageUp: -10 };
    const from = selectedIndex >= 0 ? selectedIndex : 0;
    if (e.key in steps) {
      e.preventDefault();
      focusRow(selectedIndex < 0 && steps[e.key] > 0 ? 0 : from + steps[e.key]);
    } else if (e.key === "Home") {
      e.preventDefault();
      focusRow(0);
    } else if (e.key === "End") {
      e.preventDefault();
      focusRow(result.rows.length - 1);
    }
  };

  const handleSearchKeyDown = (e) => {
    if (e.key === "ArrowDown" || e.key === "Enter") {
      e.preventDefault();
      focusRow(selectedIndex >= 0 ? selectedIndex : 0);
    } else if (e.key === "Escape" && query) {
      // First Esc clears the search; the next one closes the dialog.
      e.stopPropagation();
      setQuery("");
    }
  };

  const filterClass = (cls) => {
    setClassText(cls);
    setQuery("");
  };

  const filtering = Boolean(filters.q || filters.cls || kind || required || source || seen);
  const clearAll = () => {
    setQuery("");
    setClassText("");
    setKind("");
    setRequired("");
    setSource("");
    setSeen("");
  };

  let status;
  if (classFilter === null) status = `No class is named “${classText.trim()}”, so the class filter is off. Pick one from the list.`;
  else if (searching && result.rows.length === 0) status = "Searching…";
  else if (result.total === 0) status = "No parameters match.";
  else {
    const noun = filtering ? (result.total === 1 ? "match" : "matches") : "parameters";
    status =
      `${result.total.toLocaleString()} ${noun}` +
      (result.rows.length < result.total ? `, showing ${result.rows.length.toLocaleString()}` : "") +
      (filters.q ? ", best match first" : "");
  }

  return (
    <Modal title="Parameter Browser" className="parambrowser-modal" onClose={onClose}>
      <div className="parambrowser-toolbar">
        <label className="input-with-icon parambrowser-search">
          <Icon name="search" />
          <input
            className="input"
            placeholder="Search names, official names, classes and descriptions (try “LNCEL pMax”)"
            aria-label="Search parameters"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            autoFocus
          />
          {query && (
            <button className="icon-btn input-clear" onClick={() => setQuery("")} aria-label="Clear search">
              <Icon name="x" />
            </button>
          )}
        </label>
        <input
          className={"input mono parambrowser-class" + (classFilter === null ? " is-invalid" : "")}
          list="parambrowser-classes"
          placeholder="Any class"
          aria-label="Class"
          value={classText}
          onChange={(e) => setClassText(e.target.value)}
        />
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind">
          <option value="">All kinds</option>
          <option value="param">Parameters</option>
          <option value="list">Tables</option>
          <option value="field">Table fields</option>
        </select>
        <select value={required} onChange={(e) => setRequired(e.target.value)} aria-label="Required on creation">
          <option value="">Any requirement</option>
          <option value="mandatory">Mandatory</option>
          <option value="optional">Optional</option>
          <option value="system">Set by system</option>
        </select>
        <select value={source} onChange={(e) => setSource(e.target.value)} aria-label="Source">
          <option value="">Any source</option>
          <option value="official">Official docs</option>
          <option value="curated">Researched</option>
          <option value="heuristic">Auto-generated</option>
        </select>
        <select value={seen} onChange={(e) => setSeen(e.target.value)} aria-label="Set in your files">
          <option value="">In your files or not</option>
          <option value="yes">Set in your files</option>
          <option value="no">Never set in your files</option>
        </select>
        <button className="btn btn-quiet" onClick={clearAll} disabled={!filtering && !classText}>
          Clear
        </button>
      </div>

      <div className="parambrowser-body">
        <div className="parambrowser-results">
          <div className={"parambrowser-status" + (classFilter === null ? " is-warning" : "")} role="status">
            {status}
          </div>
          {error && <div className="notice is-error">{error}</div>}
          <div className="parambrowser-head" aria-hidden="true">
            <span>Parameter</span>
            <span>Class</span>
            <span>Type</span>
            <span>Required</span>
            <span>Default</span>
            <span>Source</span>
            <span className="num">In files</span>
          </div>
          <div
            ref={listRef}
            className={"parambrowser-list" + (searching ? " is-stale" : "")}
            role="listbox"
            aria-label="Parameters"
            onKeyDown={handleListKeyDown}
          >
            {result.rows.map((row, i) => {
              const key = rowKey(row);
              const isSelected = key === selected;
              return (
                <div
                  key={key}
                  role="option"
                  aria-selected={isSelected}
                  tabIndex={i === tabbableIndex ? 0 : -1}
                  data-row-index={i}
                  className={"parambrowser-row" + (isSelected ? " selected" : "")}
                  onClick={() => pick(row)}
                >
                  <span className="pb-name">
                    <Highlight className="mono" text={row.name} query={nameHighlight(row, filters.q)} />
                    {row.fullName && <span className="pb-fullname">{row.fullName}</span>}
                  </span>
                  <span className="mono pb-muted">{row.class || "—"}</span>
                  <span className="pb-muted">{typeLabel(row)}</span>
                  <span
                    className={row.mandatory ? "pb-required" : "pb-muted"}
                    title={row.instanceId && row.required === "Mandatory" ? "The object's own id, carried by its distName" : undefined}
                  >
                    {requiredLabel(row)}
                  </span>
                  <span className="mono pb-muted pb-default" title={row.default || ""}>
                    {row.default || "—"}
                  </span>
                  <span className={row.confidence === "official" ? "pb-official" : "pb-muted"}>
                    {SOURCE_SHORT[row.confidence] || "—"}
                  </span>
                  <span className="num pb-muted">
                    {row.observed ? row.occurrences.toLocaleString() : row.observed === false ? "0" : "—"}
                  </span>
                </div>
              );
            })}
            {result.rows.length < result.total && (
              <div className="parambrowser-more">
                <button className="btn" onClick={loadMore} disabled={loadingMore}>
                  {loadingMore
                    ? "Loading…"
                    : `Show ${Math.min(PAGE_SIZE, result.total - result.rows.length).toLocaleString()} more`}
                </button>
              </div>
            )}
          </div>
        </div>
        <ParamDetail
          detail={detail}
          loading={detailLoading}
          error={detailError}
          onPick={pick}
          onFilterClass={filterClass}
        />
      </div>

      <datalist id="parambrowser-classes">
        {classes.map((c) => (
          <option key={c.shortName} value={c.shortName}>
            {c.officialFullName || ""}
          </option>
        ))}
      </datalist>
    </Modal>
  );
}

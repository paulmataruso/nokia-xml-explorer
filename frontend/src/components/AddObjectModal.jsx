import React, { useEffect, useMemo, useState } from "react";
import { getCatalogClasses, getCatalogClassDetail, addObject } from "../api.js";
import { sortParamNames, fieldForParam } from "./paramFields.jsx";

const DEFAULT_VISIBLE_PARAMS = 25;

export function AddObjectModal({ filename, defaultParentDistName, onClose, onCreated }) {
  const [classes, setClasses] = useState([]);
  const [classesError, setClassesError] = useState(null);
  const [parentDistName, setParentDistName] = useState(defaultParentDistName || "");
  const [classSearch, setClassSearch] = useState("");
  const [selectedClass, setSelectedClass] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [visibleCount, setVisibleCount] = useState(DEFAULT_VISIBLE_PARAMS);
  const [paramSearch, setParamSearch] = useState("");
  const [values, setValues] = useState({});
  const [instanceId, setInstanceId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    getCatalogClasses()
      .then(setClasses)
      .catch((e) => setClassesError(String(e.message || e)));
  }, []);

  const parentShortClass = useMemo(() => {
    if (!parentDistName) return null;
    const last = parentDistName.split("/").pop() || "";
    return last.includes("-") ? last.slice(0, last.lastIndexOf("-")) : last;
  }, [parentDistName]);

  const filteredClasses = useMemo(() => {
    const q = classSearch.trim().toLowerCase();
    let pool = classes;
    if (parentShortClass) {
      const constrained = classes.filter(
        (c) => c.directParent === parentShortClass || (c.observedParents || []).includes(parentShortClass)
      );
      if (constrained.length > 0) pool = constrained;
    } else {
      pool = classes.filter((c) => !c.directParent);
    }
    if (q) {
      pool = pool.filter(
        (c) => c.shortName.toLowerCase().includes(q) || (c.officialFullName || "").toLowerCase().includes(q)
      );
    }
    // Classes actually seen in your files first -- safer, more relevant
    // defaults than official-only ones you've never actually used.
    return [...pool].sort((a, b) => (b.observedInCorpus ? 1 : 0) - (a.observedInCorpus ? 1 : 0));
  }, [classes, classSearch, parentShortClass]);

  const selectClass = (shortName) => {
    setSelectedClass(shortName);
    setDetail(null);
    setValues({});
    setVisibleCount(DEFAULT_VISIBLE_PARAMS);
    setParamSearch("");
    setDetailLoading(true);
    getCatalogClassDetail(shortName)
      .then((d) => {
        setDetail(d);
        // Truly-required fields (Mandatory, no system default) sort first,
        // but never let the default cutoff hide one of them.
        const trulyRequiredCount = Object.values(d.params || {}).filter((p) => p.trulyRequired).length;
        setVisibleCount((n) => Math.max(n, trulyRequiredCount));
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setDetailLoading(false));
  };

  const sortedParams = useMemo(() => (detail ? sortParamNames(detail.params) : []), [detail]);
  const visibleParams = sortedParams.slice(0, visibleCount);
  const searchMatches = useMemo(() => {
    const q = paramSearch.trim().toLowerCase();
    if (!q) return [];
    return sortedParams.filter(([name]) => name.toLowerCase().includes(q)).slice(0, 20);
  }, [paramSearch, sortedParams]);

  const setValue = (name, v) => setValues((prev) => ({ ...prev, [name]: v }));

  const handleSubmit = () => {
    if (!selectedClass) return;
    setSubmitting(true);
    setError(null);
    const nonEmpty = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== "" && v != null));
    addObject(filename, {
      parentDistName: parentDistName || null,
      className: selectedClass,
      instanceId: instanceId.trim() || null,
      params: nonEmpty,
    })
      .then((res) => onCreated(res))
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setSubmitting(false));
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal add-object-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add managed object</h3>
          <button className="close-btn" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="modal-body">
          <label className="field-row">
            <span className="field-label">Parent distName</span>
            <input
              type="text"
              className="mono"
              value={parentDistName}
              placeholder="(none — top-level object)"
              onChange={(e) => {
                setParentDistName(e.target.value);
                setSelectedClass(null);
                setDetail(null);
              }}
            />
          </label>

          {classesError && <div className="placeholder error">{classesError}</div>}

          {!selectedClass && (
            <>
              <input
                className="search-box"
                style={{ margin: "8px 0" }}
                placeholder="Search managed object class…"
                value={classSearch}
                onChange={(e) => setClassSearch(e.target.value)}
              />
              <ul className="class-pick-list">
                {filteredClasses.slice(0, 60).map((c) => (
                  <li key={c.shortName} onClick={() => selectClass(c.shortName)}>
                    <span className="mono">
                      {c.shortName}
                      {!c.observedInCorpus && (
                        <span
                          className="official-only-badge"
                          title="Valid per Nokia's official dictionary, but this class never appeared in any of your sample files"
                        >
                          {" "}
                          ⚑
                        </span>
                      )}
                    </span>
                    <span className="class-pick-fullname">{c.officialFullName || c.description?.slice(0, 60)}</span>
                  </li>
                ))}
                {filteredClasses.length === 0 && (
                  <li className="class-pick-empty">
                    No known classes {parentShortClass ? `under ${parentShortClass}` : "at top level"} in either
                    official dictionary.
                  </li>
                )}
              </ul>
            </>
          )}

          {selectedClass && (
            <>
              <div className="selected-class-bar">
                <span className="mono">{selectedClass}</span>
                {detail && <span className="class-pick-fullname">{detail.params && sortedParams.length} known parameters</span>}
                <button className="btn" onClick={() => setSelectedClass(null)}>
                  Change class
                </button>
              </div>

              <label className="field-row">
                <span className="field-label">Instance ID</span>
                <input
                  type="text"
                  className="mono"
                  placeholder="(auto-assign next available)"
                  value={instanceId}
                  onChange={(e) => setInstanceId(e.target.value)}
                />
              </label>

              {detailLoading && <div className="placeholder">Loading parameter catalog…</div>}

              {detail && (
                <>
                  <div className="param-form">
                    {visibleParams.map(([name, meta]) =>
                      <div key={name}>{fieldForParam(name, meta, values[name], (v) => setValue(name, v))}</div>
                    )}
                  </div>
                  {visibleCount < sortedParams.length && (
                    <button className="btn" onClick={() => setVisibleCount((n) => n + 50)}>
                      Show more parameters ({sortedParams.length - visibleCount} remaining)
                    </button>
                  )}

                  <div className="param-search-add">
                    <input
                      className="search-box"
                      placeholder="Find another parameter to set…"
                      value={paramSearch}
                      onChange={(e) => setParamSearch(e.target.value)}
                    />
                    {searchMatches.length > 0 && (
                      <ul className="class-pick-list">
                        {searchMatches.map(([name, meta]) => (
                          <li
                            key={name}
                            onClick={() => {
                              setValue(name, values[name] ?? "");
                              setVisibleCount((n) => Math.max(n, sortedParams.findIndex((p) => p[0] === name) + 1));
                              setParamSearch("");
                            }}
                          >
                            <span className="mono">{name}</span>
                            <span className="class-pick-fullname">{meta.description?.slice(0, 70)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </>
              )}
            </>
          )}

          {error && <div className="placeholder error">{error}</div>}
        </div>

        <div className="modal-footer">
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn active" onClick={handleSubmit} disabled={!selectedClass || submitting}>
            {submitting ? "Creating…" : "Create object"}
          </button>
        </div>
      </div>
    </div>
  );
}

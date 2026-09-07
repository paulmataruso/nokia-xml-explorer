import React, { useEffect, useMemo, useState } from "react";
import { getCatalogClassDetail, setObjectParam } from "../api.js";
import { sortParamNames, fieldForParam } from "./paramFields.jsx";

/**
 * Adds a parameter to an EXISTING managed object. The "Add Object" form
 * deliberately only sets what you fill in up front (some classes have 500+
 * known parameters -- forcing all of them at creation time isn't
 * realistic), so this is how you come back later and set more, one at a
 * time, without recreating the object.
 */
export function AddParamModal({ filename, distName, className, existingParamNames, onClose, onAdded }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedName, setSelectedName] = useState(null);
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getCatalogClassDetail(className)
      .then(setDetail)
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));
  }, [className]);

  const availableParams = useMemo(() => {
    if (!detail) return [];
    const existing = new Set(existingParamNames || []);
    const notYetSet = Object.fromEntries(Object.entries(detail.params).filter(([name]) => !existing.has(name)));
    return sortParamNames(notYetSet);
  }, [detail, existingParamNames]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return availableParams.slice(0, 60);
    return availableParams.filter(([name]) => name.toLowerCase().includes(q)).slice(0, 60);
  }, [availableParams, search]);

  const selectedMeta = selectedName ? detail?.params[selectedName] : null;

  const handleSubmit = () => {
    if (!selectedName) return;
    setSubmitting(true);
    setError(null);
    setObjectParam(filename, distName, selectedName, value)
      .then(() => onAdded())
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setSubmitting(false));
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add parameter to {distName.split("/").pop()}</h3>
          <button className="close-btn" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="modal-body">
          {loading && <div className="placeholder">Loading parameter catalog…</div>}
          {error && <div className="placeholder error">{error}</div>}

          {!loading && !selectedName && (
            <>
              <input
                className="search-box"
                style={{ margin: "0 0 8px" }}
                placeholder={`Search ${className} parameters…`}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                autoFocus
              />
              <ul className="class-pick-list">
                {filtered.map(([name, meta]) => (
                  <li key={name} onClick={() => { setSelectedName(name); setValue(""); }}>
                    <span className="mono">{name}</span>
                    <span className="class-pick-fullname">{meta.description?.slice(0, 70)}</span>
                  </li>
                ))}
                {filtered.length === 0 && (
                  <li className="class-pick-empty">
                    {availableParams.length === 0
                      ? "Every known parameter for this class is already set on this object."
                      : "No matches."}
                  </li>
                )}
              </ul>
            </>
          )}

          {selectedMeta && (
            <>
              <div className="selected-class-bar">
                <span className="mono">{selectedName}</span>
                <button className="btn" onClick={() => setSelectedName(null)}>
                  Choose different parameter
                </button>
              </div>
              <div className="param-form">{fieldForParam(selectedName, selectedMeta, value, setValue)}</div>
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn active" onClick={handleSubmit} disabled={!selectedName || submitting}>
            {submitting ? "Adding…" : "Add parameter"}
          </button>
        </div>
      </div>
    </div>
  );
}

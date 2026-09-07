import React, { useState } from "react";
import { setObjectParam } from "../api.js";
import { fieldInputForParam } from "./paramFields.jsx";

const rowKey = (r) => `${r.distName}::${r.paramName}`;

function ExplainSidePanel({ row }) {
  if (!row) {
    return (
      <div className="required-fields-explain">
        <div className="placeholder">Click a row to see its full explanation here.</div>
      </div>
    );
  }
  return (
    <div className="required-fields-explain">
      <h3 className="mono">{row.paramName}</h3>
      <div className="kv-row">
        <span className="k">Object</span>
        <span className="v mono">{row.distName}</span>
      </div>
      <div className="kv-row">
        <span className="k">Class</span>
        <span className="v mono">{row.class}</span>
      </div>
      {row.dataType && (
        <div className="kv-row">
          <span className="k">Data type</span>
          <span className="v">{row.dataType}</span>
        </div>
      )}
      {row.unit && (
        <div className="kv-row">
          <span className="k">Unit</span>
          <span className="v">{row.unit}</span>
        </div>
      )}
      <div className="explain-description">{row.description || "No description available."}</div>
      {row.officialRange && (
        <div className="kv-block">
          <div className="k">Valid range</div>
          <div className="v-block mono">{row.officialRange}</div>
        </div>
      )}
      {row.exampleValues && row.exampleValues.length > 0 && (
        <div className="kv-block">
          <div className="k">Seen in your files</div>
          <div className="v-block mono">{row.exampleValues.join(", ")}</div>
        </div>
      )}
      {row.observed === false && (
        <div className="explain-notes">
          Valid per Nokia's official dictionary, but this parameter was never seen in any of your sample
          files -- there's no real-file example to ground a suggested value in.
        </div>
      )}
    </div>
  );
}

/**
 * Every Mandatory parameter (per the official Nokia docs), anywhere in this
 * file, that currently has no value -- whether "+ Add Object" wrote it as a
 * blank placeholder or it was simply never set. Backed by
 * GET /api/files/{filename}/missing-required (see main.py's
 * _is_required_missing). One table, fill in from wherever, no hunting
 * through the tree for red flags one at a time. Clicking a row shows its
 * full explanation in the side panel, same data ExplainPanel would show.
 */
export function RequiredFieldsModal({ filename, rows, onClose, onSaved }) {
  const [pending, setPending] = useState({});
  const [savingKey, setSavingKey] = useState(null);
  const [error, setError] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);

  const selectedRow = rows.find((r) => rowKey(r) === selectedKey) || null;

  const handleSave = (row) => {
    const key = rowKey(row);
    const value = pending[key];
    if (value == null || value === "") return;
    setSavingKey(key);
    setError(null);
    setObjectParam(filename, row.distName, row.paramName, value)
      .then(() => {
        setPending((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
        onSaved();
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setSavingKey(null));
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal required-fields-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Required fields not yet filled in ({rows.length})</h3>
          <button className="close-btn" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="modal-body required-fields-body">
          <div className="required-fields-table-wrap">
            {error && <div className="placeholder error">{error}</div>}
            {rows.length === 0 ? (
              <div className="placeholder">
                Every Mandatory parameter in this file currently has a value. Nothing left to fill in.
              </div>
            ) : (
              <table className="required-fields-table">
                <thead>
                  <tr>
                    <th>Object</th>
                    <th>Class</th>
                    <th>Parameter</th>
                    <th>Value</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const key = rowKey(row);
                    const value = pending[key] ?? "";
                    const meta = {
                      dataType: row.dataType,
                      exampleValues: row.exampleValues,
                      officialRange: row.officialRange,
                    };
                    return (
                      <tr
                        key={key}
                        className={key === selectedKey ? "selected-row" : ""}
                        onClick={() => setSelectedKey(key)}
                      >
                        <td className="mono" title={row.distName}>
                          {row.distName.split("/").pop()}
                        </td>
                        <td className="mono">{row.class}</td>
                        <td className="mono" title={row.description || ""}>
                          {row.paramName}
                        </td>
                        <td onClick={(e) => e.stopPropagation()}>
                          {fieldInputForParam(meta, value, (v) =>
                            setPending((prev) => ({ ...prev, [key]: v }))
                          )}
                        </td>
                        <td onClick={(e) => e.stopPropagation()}>
                          <button
                            className="btn"
                            disabled={!value || savingKey === key}
                            onClick={() => handleSave(row)}
                          >
                            {savingKey === key ? "Saving…" : "Save"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
          <ExplainSidePanel row={selectedRow} />
        </div>

        <div className="modal-footer">
          <button className="btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

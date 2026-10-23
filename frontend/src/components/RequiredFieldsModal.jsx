import React, { useState } from "react";
import { Icon } from "./Icon.jsx";
import { Modal } from "./Modal.jsx";
import { setObjectParam } from "../api.js";
import { fieldInputForParam } from "./paramFields.jsx";

const rowKey = (r) => `${r.distName}::${r.paramName}`;

function ExplainSidePanel({ row }) {
  if (!row) {
    return (
      <div className="required-fields-explain">
        <div className="placeholder">Click a row to see what that parameter is and which values real files use.</div>
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
          Valid per Nokia's official dictionary, but never seen in any of your sample files, so there's no
          real-file value to suggest.
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
 *
 * Split in two, because they mean different things: "gaps" are parameters
 * real exports actually set (seen in the sample files), so a blank one is
 * very likely a real omission; "unverified" ones are documented as
 * Mandatory but never observed in any real file, so the docs may not
 * reflect what a working export needs. Rows are grouped by object, under
 * the object's full distName.
 */
export function RequiredFieldsModal({ filename, rows, readOnly, onClose, onSaved, onShowInTree }) {
  const [pending, setPending] = useState({});
  const [savingKey, setSavingKey] = useState(null);
  const [error, setError] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);
  const gaps = rows.filter((r) => r.observed !== false);
  const unverified = rows.filter((r) => r.observed === false);
  const [tab, setTab] = useState(gaps.length > 0 || unverified.length === 0 ? "gaps" : "unverified");

  const shown = tab === "gaps" ? gaps : unverified;
  const groups = [];
  for (const row of shown) {
    const last = groups[groups.length - 1];
    if (last && last.distName === row.distName) last.rows.push(row);
    else groups.push({ distName: row.distName, cls: row.class, rows: [row] });
  }
  const selectedRow = rows.find((r) => rowKey(r) === selectedKey) || null;

  const handleSave = (row) => {
    const key = rowKey(row);
    const value = pending[key];
    if (value == null || value === "") return;
    setSavingKey(key);
    setError(null);
    setObjectParam(filename, row.distName, row.paramName, value)
      .then((res) => {
        setPending((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
        return onSaved(res, row.distName, row.paramName, value);
      })
      .catch((e) => setError(`Couldn't save ${row.paramName}: ${String(e.message || e)}`))
      .finally(() => setSavingKey(null));
  };

  const columns = readOnly ? 3 : 5;

  return (
    <Modal title="Required fields without a value" className="required-fields-modal" onClose={onClose}>

        <div className="required-fields-tabs" role="tablist" aria-label="Which required fields">
          <button
            role="tab"
            aria-selected={tab === "gaps"}
            className="rf-tab"
            onClick={() => setTab("gaps")}
            title="Mandatory parameters that real exports set, still blank here"
          >
            Gaps <span className="rf-tab-count">{gaps.length}</span>
          </button>
          <button
            role="tab"
            aria-selected={tab === "unverified"}
            className="rf-tab"
            onClick={() => setTab("unverified")}
            title="Documented as Mandatory, but never seen set in any real sample file"
          >
            Unverified <span className="rf-tab-count">{unverified.length}</span>
          </button>
          <span className="rf-tab-hint">
            {tab === "gaps"
              ? "Seen set in real exports, so a blank one is likely a real omission."
              : "Documented as Mandatory but never seen in a real file. Check before filling in."}
          </span>
        </div>

        <div className="modal-body required-fields-body">
          <div className="required-fields-table-wrap">
            {readOnly && rows.length > 0 && (
              <div className="notice is-quiet">
                This file is read-only. Use "Edit a copy" in the file header to fill these in.
              </div>
            )}
            {error && <div className="notice is-error">{error}</div>}
            {shown.length === 0 ? (
              <div className="placeholder">
                {tab === "gaps"
                  ? "No gaps: every Mandatory parameter that real exports set has a value here."
                  : "Nothing unverified is missing."}
              </div>
            ) : (
              <table className="required-fields-table">
                <thead>
                  <tr>
                    <th>Parameter</th>
                    <th>Class</th>
                    {!readOnly && <th>Value</th>}
                    {!readOnly && <th aria-label="Save" />}
                    <th aria-label="Show in tree" />
                  </tr>
                </thead>
                {groups.map((g) => (
                  <tbody key={g.distName}>
                    <tr className="rf-group">
                      <th colSpan={columns} scope="rowgroup" className="mono">
                        {g.distName}
                      </th>
                    </tr>
                    {g.rows.map((row) => {
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
                          <td className="mono" title={row.description || ""}>
                            {row.paramName}
                          </td>
                          <td className="mono rf-class">{row.class}</td>
                          {!readOnly && (
                            <td onClick={(e) => e.stopPropagation()}>
                              {fieldInputForParam(meta, value, (v) =>
                                setPending((prev) => ({ ...prev, [key]: v }))
                              )}
                            </td>
                          )}
                          {!readOnly && (
                            <td onClick={(e) => e.stopPropagation()}>
                              <button
                                className="btn"
                                disabled={!value || savingKey === key}
                                onClick={() => handleSave(row)}
                              >
                                {savingKey === key ? "Saving…" : "Save"}
                              </button>
                            </td>
                          )}
                          <td onClick={(e) => e.stopPropagation()}>
                            <button
                              className="icon-btn"
                              onClick={() => onShowInTree(row.distName, row.paramName)}
                              aria-label={`Show ${row.paramName} on ${row.distName.split("/").pop()} in the tree`}
                              title="Show in tree"
                            >
                              <Icon name="external" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                ))}
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
    </Modal>
  );
}

import React, { useEffect, useState } from "react";
import { explainNode } from "../knowledge.js";
import { explainParamFallback } from "../api.js";
import { AddParamModal } from "./AddParamModal.jsx";
import { parseThreeGppRefs } from "../utils.js";

const THREEGPP_STATUS_META = {
  standardized: { label: "3GPP-standardized", color: "#3fb950" },
  unverified: { label: "Possibly standardized — not individually verified", color: "#58a6ff" },
  "other-standard": { label: "Standardized (not by 3GPP)", color: "#d29922" },
  "vendor-specific": { label: "Nokia-specific — no 3GPP reference", color: "#8b949e" },
};

const CONFIDENCE_META = {
  official: { label: "Official Nokia documentation", color: "#58a6ff" },
  high: { label: "High confidence", color: "#3fb950" },
  medium: { label: "Medium confidence", color: "#d29922" },
  low: { label: "Low confidence", color: "#e0823d" },
  heuristic: { label: "Auto-generated — unverified", color: "#8b949e" },
};

export function ExplainPanel({ node, kb, onClose, editable, filename, onParamAdded }) {
  const [info, setInfo] = useState(null);
  const [addParamOpen, setAddParamOpen] = useState(false);

  useEffect(() => {
    setAddParamOpen(false);
    if (!node) {
      setInfo(null);
      return;
    }
    const initial = explainNode(node, kb);
    setInfo(initial);

    if (initial.needsFallback) {
      explainParamFallback(node.label, node.class, node.value)
        .then((res) => {
          setInfo((prev) =>
            prev && prev.title === initial.title
              ? {
                  ...prev,
                  description: res.description,
                  confidence: res.confidence,
                  dataType: res.dataType,
                  unit: res.unit,
                  notes: res.notes,
                  needsFallback: false,
                }
              : prev
          );
        })
        .catch(() => {
          setInfo((prev) =>
            prev && prev.title === initial.title
              ? { ...prev, description: "No description available.", needsFallback: false }
              : prev
          );
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [node]);

  if (!node || !info) {
    return (
      <div className="explain-panel empty">
        <p>Double-click any item in the tree to see a full explanation here.</p>
      </div>
    );
  }

  const conf = info.confidence ? CONFIDENCE_META[info.confidence] : null;

  return (
    <div className="explain-panel">
      <div className="explain-header">
        <div>
          <div className="explain-kind">{info.kindLabel}</div>
          <h2 className="mono">{info.title}</h2>
          {info.subtitle && <div className="explain-subtitle mono">{info.subtitle}</div>}
        </div>
        <button className="close-btn" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>

      {conf && (
        <div className="confidence-badge" style={{ borderColor: conf.color, color: conf.color }}>
          {conf.label}
        </div>
      )}

      {editable && node.kind === "mo" && (
        <button className="btn add-param-btn" onClick={() => setAddParamOpen(true)}>
          + Add parameter
        </button>
      )}

      {info.fullName && (
        <div className="kv-row">
          <span className="k">Official name</span>
          <span className="v">{info.fullName}</span>
        </div>
      )}
      {info.officialFullName && (
        <div className="kv-row">
          <span className="k">Official name</span>
          <span className="v">{info.officialFullName}</span>
        </div>
      )}
      {info.officialHierarchy && info.officialHierarchy.length > 1 && (
        <div className="kv-row">
          <span className="k">Verified hierarchy</span>
          <span className="v mono">{info.officialHierarchy.join(" → ")}</span>
        </div>
      )}

      {info.value !== undefined && (
        <div className="kv-row">
          <span className="k">Value in file</span>
          <span className="v mono">{info.value ?? "(empty)"}</span>
        </div>
      )}
      {info.dataType && (
        <div className="kv-row">
          <span className="k">Data type</span>
          <span className="v">{info.dataType}</span>
        </div>
      )}
      {info.unit && (
        <div className="kv-row">
          <span className="k">Unit</span>
          <span className="v">{info.unit}</span>
        </div>
      )}
      {info.category && (
        <div className="kv-row">
          <span className="k">Category</span>
          <span className="v">{info.category}</span>
        </div>
      )}

      <div className="explain-description">
        {info.description || (info.needsFallback ? "Looking up an explanation…" : "No description available.")}
      </div>

      {(info.range || info.defaultValue || info.modification || info.requiredOnCreation) && (
        <div className="attr-table">
          <div className="attr-table-title">Nokia parameter dictionary</div>
          {info.defaultValue && (
            <div className="kv-row">
              <span className="k">Default value</span>
              <span className="v mono">{info.defaultValue}</span>
            </div>
          )}
          {info.modification && (
            <div className="kv-row">
              <span className="k">Modification</span>
              <span className="v">{info.modification}</span>
            </div>
          )}
          {info.requiredOnCreation && (
            <div className="kv-row">
              <span className="k">Required on creation</span>
              <span className="v">{info.requiredOnCreation}</span>
            </div>
          )}
          {info.officialMoClass && (
            <div className="kv-row">
              <span className="k">Defined on</span>
              <span className="v mono">{info.officialMoClass}</span>
            </div>
          )}
          {info.threeGppName && (
            <div className="kv-row">
              <span className="k">3GPP name</span>
              <span className="v">{info.threeGppName}</span>
            </div>
          )}
          {info.range && (
            <div className="kv-block">
              <div className="k">Valid range</div>
              <div className="v-block mono">{info.range}</div>
            </div>
          )}
          {info.relatedFeatures && (
            <div className="kv-block">
              <div className="k">Requires feature/license</div>
              <div className="v-block">{info.relatedFeatures}</div>
            </div>
          )}
          {info.threeGppRef && (
            <div className="kv-block">
              <div className="k">3GPP reference</div>
              <div className="v-block">
                {(() => {
                  const links = parseThreeGppRefs(info.threeGppRef);
                  if (links.length === 0) return info.threeGppRef;
                  return links.map(({ spec, url }, i) => (
                    <React.Fragment key={spec}>
                      {i > 0 && ", "}
                      <a href={url} target="_blank" rel="noopener noreferrer">
                        3GPP TS {spec}
                      </a>
                    </React.Fragment>
                  ));
                })()}
              </div>
            </div>
          )}
        </div>
      )}

      {info.threeGpp && (
        <div className="attr-table threegpp-block">
          <div className="attr-table-title">3GPP standardization</div>
          <div
            className="threegpp-status-badge"
            style={{ borderColor: THREEGPP_STATUS_META[info.threeGpp.status]?.color }}
          >
            {THREEGPP_STATUS_META[info.threeGpp.status]?.label || info.threeGpp.status}
          </div>
          {info.threeGpp.specs && info.threeGpp.specs.length > 0 && (
            <div className="kv-block">
              <div className="k">Spec{info.threeGpp.specs.length > 1 ? "s" : ""}</div>
              <div className="v-block">
                {info.threeGpp.specs.map((s, i) => (
                  <div key={s.spec}>
                    <a href={s.url} target="_blank" rel="noopener noreferrer">
                      {s.spec}
                    </a>
                    {" — "}
                    {s.title}
                  </div>
                ))}
              </div>
            </div>
          )}
          {info.threeGpp.note && (
            <div className="kv-block">
              <div className="v-block">{info.threeGpp.note}</div>
            </div>
          )}
        </div>
      )}

      {info.notes && (
        <div className="explain-notes">
          <strong>Notes:</strong> {info.notes}
        </div>
      )}

      {info.attributes && info.attributes.length > 0 && (
        <div className="attr-table">
          <div className="attr-table-title">Attributes</div>
          {info.attributes.map((a) => (
            <div className="attr-row" key={a.key}>
              <div className="attr-kv">
                <span className="k mono">{a.key}</span>
                <span className="v mono">{String(a.value)}</span>
              </div>
              {a.help && <div className="attr-help">{a.help}</div>}
            </div>
          ))}
        </div>
      )}

      {addParamOpen && node.kind === "mo" && (
        <AddParamModal
          filename={filename}
          distName={node.distName}
          className={node.class}
          existingParamNames={node.children.filter((c) => c.kind === "param").map((c) => c.label)}
          onClose={() => setAddParamOpen(false)}
          onAdded={() => {
            setAddParamOpen(false);
            onParamAdded && onParamAdded();
          }}
        />
      )}
    </div>
  );
}

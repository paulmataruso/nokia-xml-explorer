import React, { useEffect, useState } from "react";
import { Icon } from "./Icon.jsx";
import { explainNode } from "../knowledge.js";
import { explainParamFallback } from "../api.js";
import { AddParamModal } from "./AddParamModal.jsx";
import { parseThreeGppRefs } from "../utils.js";

// Badge tone classes (see .badge-* in styles.css) instead of per-tier
// hex colours: Official takes the Official aqua, everything else stays in
// the single ink at decreasing strength, so provenance never competes with
// the signal colour the user's focus uses.
const THREEGPP_STATUS_META = {
  standardized: { label: "3GPP-standardized", tone: "strong" },
  unverified: { label: "Possibly standardized — not individually verified", tone: "unverified" },
  "other-standard": { label: "Standardized (not by 3GPP)", tone: "mid" },
  "vendor-specific": { label: "Nokia-specific — no 3GPP reference", tone: "quiet" },
};

const CONFIDENCE_META = {
  official: { label: "Official Nokia documentation", tone: "official" },
  high: { label: "High confidence", tone: "strong" },
  medium: { label: "Medium confidence", tone: "mid" },
  low: { label: "Low confidence", tone: "unverified" },
  heuristic: { label: "Auto-generated — unverified", tone: "unverified" },
};

// Kinds whose subtitle doesn't already say what they are ("Parameter on
// NRCELL" does; a bare class string or "raml / cmData / header" doesn't).
const KIND_IN_SUBTITLE = new Set(["mo", "mo-placeholder", "fileinfo"]);

export function ExplainPanel({ node, kb, onClose, editable, filename, onParamAdded }) {
  const [info, setInfo] = useState(null);
  const [addParamOpen, setAddParamOpen] = useState(false);
  const [rangeOpen, setRangeOpen] = useState(false);

  useEffect(() => {
    setAddParamOpen(false);
    setRangeOpen(false);
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
        <p>Click any row in the tree or the raw XML to see what it means, how sure the source is, and where it comes from.</p>
      </div>
    );
  }

  const conf = info.confidence ? CONFIDENCE_META[info.confidence] : null;
  // The knowledge base is keyed by parameter name. When the dictionary
  // entry it found was written for a different class (NRCELL.pMax showing
  // LNCEL.pMax's text), say so: the range, default and unit may not apply.
  const docClass = info.officialMoClass ? info.officialMoClass.split("/").pop() : null;
  const borrowedDoc = node.kind === "param" && docClass && node.class && docClass !== node.class;
  const rangeLines = info.range ? info.range.split("\n") : [];
  const RANGE_PREVIEW = 10;

  return (
    <div className="explain-panel">
      <div className="explain-header">
        <div>
          <h2 className="mono">{info.title}</h2>
          <div className="explain-subtitle">
            {KIND_IN_SUBTITLE.has(node.kind) && info.kindLabel}
            {KIND_IN_SUBTITLE.has(node.kind) && info.subtitle && " · "}
            {info.subtitle && <span className="mono">{info.subtitle}</span>}
          </div>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Clear selection" title="Clear selection">
          <Icon name="x" />
        </button>
      </div>

      {conf && <div className={`badge badge-${conf.tone} explain-badge`}>{conf.label}</div>}

      {editable && node.kind === "mo" && (
        <button className="btn add-param-btn" onClick={() => setAddParamOpen(true)}>
          <Icon name="plus" />
          Add parameter
        </button>
      )}

      {borrowedDoc && (
        <div className="notice is-note explain-borrowed" role="note">
          <Icon name="info" />
          <span className="notice-text">
            Documented on <span className="mono">{docClass}.{info.title}</span>, the same parameter name on another
            class. Check that the range, default and unit apply to <span className="mono">{node.class}</span>.
          </span>
        </div>
      )}

      {(info.fullName || info.officialFullName) && (
        <div className="kv-row">
          <span className="k">Official name</span>
          <span className="v">{info.fullName || info.officialFullName}</span>
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
              <div className="v-block mono">
                {rangeOpen || rangeLines.length <= RANGE_PREVIEW
                  ? info.range
                  : rangeLines.slice(0, RANGE_PREVIEW).join("\n")}
              </div>
              {rangeLines.length > RANGE_PREVIEW && (
                <button className="link-btn range-toggle" onClick={() => setRangeOpen((o) => !o)}>
                  {rangeOpen ? "Show fewer" : `Show all ${rangeLines.length} lines`}
                </button>
              )}
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
          <div className={`badge badge-${THREEGPP_STATUS_META[info.threeGpp.status]?.tone || "quiet"}`}>
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
          onAdded={(res, paramName, value) => {
            setAddParamOpen(false);
            onParamAdded && onParamAdded(res, node.distName, paramName, value);
          }}
        />
      )}
    </div>
  );
}

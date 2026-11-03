import React, { useState } from "react";
import { plural } from "./ActionParts.jsx";
import { BasisBadge, Findings } from "./CaCheckModal.jsx";
import { Modal } from "./Modal.jsx";

const KIND_LABELS = {
  reference: "Reference",
  id: "Matching ids",
  value: "Matching values",
  companion: "Companion objects",
};

const TABS = [
  ["findings", "Findings"],
  ["rules", "Rules"],
];

function Rules({ rules, findings }) {
  const hits = {};
  for (const f of findings) hits[f.ruleId] = (hits[f.ruleId] || 0) + 1;
  return (
    <ul className="ca-findings sc-rules">
      {rules.map((r) => (
        <li key={r.id} className={"ca-finding is-" + (hits[r.id] ? r.severity : "clear")}>
          <div className="ca-finding-main">
            <div className="ca-finding-head">
              <span className="ca-finding-title">{r.title}</span>
              <span className="tag">{KIND_LABELS[r.kind] || r.kind}</span>
              <BasisBadge finding={r} />
              <span className="sc-rule-hits">{hits[r.id] ? plural(hits[r.id], "finding") : "Passes"}</span>
            </div>
            <p className="ca-finding-detail">{r.evidence}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

/**
 * The site check (GET /api/files/{f}/check): whether the objects in the
 * file point at each other correctly -- references to objects that exist,
 * cells mapped to their LCELs, relations matching their neighbours, and
 * objects that every sibling has but one lacks. Every action runs the same
 * check on its preview.
 */
export function SiteCheckModal({ data, onClose, onShowInTree }) {
  const [tab, setTab] = useState("findings");
  const { summary, findings, rules } = data;
  return (
    <Modal title="Site check" className="ca-check-modal" onClose={onClose}>
      <div className="required-fields-tabs" role="tablist" aria-label="Site check">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            role="tab"
            className="rf-tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
          >
            {label}
            <span className="rf-tab-count">{key === "findings" ? findings.length : rules.length}</span>
          </button>
        ))}
      </div>
      <div className="modal-body">
        <div className="ca-summary">
          <span className="ca-fact">
            <strong className={summary.errors ? "ca-missing" : undefined}>{plural(summary.errors, "error")}</strong>
          </span>
          <span className="ca-fact">{plural(summary.warnings, "warning")}</span>
          {summary.infos > 0 && <span className="ca-fact">{plural(summary.infos, "note")}</span>}
          <span className="ca-fact">{plural(rules.length, "rule")} checked</span>
        </div>
        {tab === "findings" ? (
          <Findings
            enbs={[{ label: "", findings }]}
            onShowInTree={onShowInTree}
            emptyText="No problems found. Every reference points at an object in the file, and the cells, relations and profiles match each other."
          />
        ) : (
          <Rules rules={rules} findings={findings} />
        )}
      </div>
    </Modal>
  );
}

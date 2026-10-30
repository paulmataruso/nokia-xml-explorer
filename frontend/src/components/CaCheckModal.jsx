import React, { useState } from "react";
import { Icon } from "./Icon.jsx";
import { Modal } from "./Modal.jsx";

const SEVERITY = {
  error: { label: "Error", icon: "alert" },
  warning: { label: "Warning", icon: "alert" },
  info: { label: "Note", icon: "info" },
};

const ROLE_LABELS = { pcell: "PCell", scell: "SCell", both: "PCell + SCell", none: "Not in CA" };

const last = (dn) => (dn ? dn.split("/").pop() : "");

/** Where a finding's rule comes from. Official rules carry the dictionary's
 * own parameter and rule number so they can be looked up; patterns learned
 * from the corpus get the dashed "weaker claim" badge. */
function BasisBadge({ finding }) {
  if (finding.basis === "official") {
    const r = finding.rule;
    return (
      <span
        className="badge badge-official"
        title="From Nokia's official parameter dictionary (LTE18 / SBTS18A). Newer releases may differ."
      >
        Nokia rule{r ? ` · ${r.param}${r.number ? ` ${r.number}` : ""}` : ""}
      </span>
    );
  }
  if (finding.basis === "files") {
    return (
      <span
        className="badge badge-unverified"
        title="Learned by comparing the CA files in your corpus with each other. Not an official rule."
      >
        Seen in your files
      </span>
    );
  }
  return null;
}

function TargetLinks({ targets, onShowInTree }) {
  if (!targets.length) return null;
  return (
    <div className="ca-targets">
      {targets.map((t) => (
        <button key={t.id} className="ca-target" onClick={() => onShowInTree(t.id)} title="Show in tree">
          <Icon name="external" size={12} />
          <span className="mono">{t.label}</span>
        </button>
      ))}
    </div>
  );
}

function Findings({ enbs, onShowInTree }) {
  const all = enbs.flatMap((e) => e.findings.map((f) => ({ ...f, enb: e.label })));
  if (all.length === 0) {
    return (
      <div className="placeholder">
        No problems found. The setup passes every official CA rule this tool checks and matches the patterns seen in
        your working CA files.
      </div>
    );
  }
  return (
    <ul className="ca-findings">
      {all.map((f, i) => (
        <li key={i} className={"ca-finding is-" + f.severity}>
          <Icon name={SEVERITY[f.severity].icon} />
          <div className="ca-finding-main">
            <div className="ca-finding-head">
              <span className="visually-hidden">{SEVERITY[f.severity].label}: </span>
              <span className="ca-finding-title">{f.title}</span>
              {enbs.length > 1 && <span className="ca-finding-enb mono">{f.enb}</span>}
              <BasisBadge finding={f} />
            </div>
            <p className="ca-finding-detail">{f.detail}</p>
            <TargetLinks targets={f.targets} onShowInTree={onShowInTree} />
          </div>
        </li>
      ))}
    </ul>
  );
}

const unset = <span className="ca-unset">not set</span>;

function CellsTable({ enb, onShowInTree }) {
  if (enb.cells.length === 0) return <div className="placeholder">{enb.label} has no LNCEL cells.</div>;
  return (
    <table className="ca-table">
      <thead>
        <tr>
          <th>Cell</th>
          <th>Role</th>
          <th>lcrId</th>
          <th>Carrier</th>
          <th>Bandwidth</th>
          <th title="TDD frame config / special subframe config">TDD</th>
          <th>caPoolId</th>
          <th title="Highest downlink modulation (actModulationSchemeDl)">DL max</th>
          <th title="SIB cellBarred, and the cell's reselection priority">Camping</th>
          <th aria-label="Show in tree" />
        </tr>
      </thead>
      <tbody>
        {enb.cells.map((c) => (
          <tr key={c.id}>
            <td>
              <div className="mono ca-cell-label">{c.label}</div>
              {c.name && <div className="ca-sub">{c.name}</div>}
            </td>
            <td className={"ca-role is-" + c.role}>{ROLE_LABELS[c.role]}</td>
            <td className="mono">{c.lcrId ?? unset}</td>
            <td className="mono">
              {c.band != null ? `B${c.band} · ` : ""}
              {c.earfcn ?? unset}
              <span className="ca-sub"> {c.tech}{c.cbrs ? " · CBRS" : ""}</span>
            </td>
            <td className="mono">{c.bandwidth ?? unset}</td>
            <td className="mono">{c.tdd ?? <span className="ca-unset">–</span>}</td>
            <td className="mono">{c.caPoolId ?? unset}</td>
            <td className="mono">{c.modulationDl ?? unset}</td>
            <td>
              {c.barred == null ? unset : c.barred ? "Barred" : "Open"}
              {c.reselPrio != null && <span className="ca-sub"> · prio {c.reselPrio}</span>}
            </td>
            <td>
              <button
                className="icon-btn"
                onClick={() => onShowInTree(c.id)}
                aria-label={`Show ${c.label} in the tree`}
                title="Show in tree"
              >
                <Icon name="external" />
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RelationsTable({ enb, onShowInTree }) {
  return (
    <>
      {enb.relations.length === 0 ? (
        <div className="placeholder">No cell on {enb.label} has a CAREL relation, so no PCell/SCell pair is defined.</div>
      ) : (
        <table className="ca-table">
          <thead>
            <tr>
              <th>PCell</th>
              <th>Relation</th>
              <th>SCell</th>
              <th title="scellPrio: lower is tried first">Priority</th>
              <th title="maxNumOfSuppMimoLayer">MIMO layers</th>
              <th aria-label="Show in tree" />
            </tr>
          </thead>
          <tbody>
            {enb.relations.map((r) => (
              <tr key={r.id}>
                <td className="mono">{last(r.pcell)}</td>
                <td className="mono">{r.label}</td>
                <td>
                  {r.scell ? (
                    <span className="mono">{last(r.scell)}</span>
                  ) : r.foreign ? (
                    <span>
                      lcrId <span className="mono">{r.lcrId}</span> on eNB <span className="mono">{r.lnBtsId}</span>
                    </span>
                  ) : (
                    <span className="ca-missing">
                      No cell with lcrId <span className="mono">{r.lcrId}</span>
                    </span>
                  )}
                  <span className="ca-sub"> · lcrId {r.lcrId}</span>
                </td>
                <td className="mono">{r.scellPrio ?? unset}</td>
                <td className="mono">{r.mimoLayers ?? unset}</td>
                <td>
                  <button
                    className="icon-btn"
                    onClick={() => onShowInTree(r.id)}
                    aria-label={`Show ${last(r.pcell)}/${r.label} in the tree`}
                    title="Show in tree"
                  >
                    <Icon name="external" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3 className="ca-section-title">CA objects</h3>
      {enb.caObjects.length === 0 ? (
        <div className="ca-sub">None of CAGENB, CADPR, CAPR or CAREL exist on {enb.label}.</div>
      ) : (
        <TargetLinks
          targets={enb.caObjects.flatMap((o) =>
            o.ids.map((id) => ({ id, label: id.split("/").slice(-2).join("/") }))
          )}
          onShowInTree={onShowInTree}
        />
      )}
    </>
  );
}

function EnbSummary({ enb }) {
  const ul = enb.ulOn ? enb.ul : "off";
  return (
    <div className="ca-summary">
      <span className="ca-fact mono">{enb.label}</span>
      {enb.version && <span className="ca-fact mono">{enb.version.split("_")[0]}</span>}
      <span className="ca-fact">
        Downlink CA <strong>{enb.dl ? "on" : "off"}</strong>
      </span>
      <span className="ca-fact">
        Uplink CA <strong className={enb.ulOn ? "mono" : undefined}>{ul}</strong>
      </span>
      <span className="ca-fact">
        Flexible SCell selection <strong>{enb.flexScellSelect ? "on" : "off"}</strong>
      </span>
      {enb.supportedCellTechnology && (
        <span className="ca-fact">
          Cells <strong className="mono">{enb.supportedCellTechnology}</strong>
        </span>
      )}
    </div>
  );
}

/**
 * Read-only LTE carrier aggregation check for one file (GET
 * /api/files/{filename}/ca, see backend ca.py): the eNB's CA switches, its
 * cells and CAREL relations, and every problem found. Each finding says
 * where its rule comes from -- Nokia's dictionary (with the rule number)
 * or a pattern learned from the corpus's own CA files -- and links to the
 * rows it's about. Phase 1 of the CA wizard; nothing here edits the file.
 */
export function CaCheckModal({ data, onClose, onShowInTree }) {
  const enbs = data?.enbs || [];
  const findingCount = enbs.reduce((n, e) => n + e.findings.length, 0);
  const cellCount = enbs.reduce((n, e) => n + e.cells.length, 0);
  const relationCount = enbs.reduce((n, e) => n + e.relations.length, 0);
  const [tab, setTab] = useState(findingCount > 0 ? "findings" : "cells");

  let body;
  if (!data) body = <div className="placeholder">Checking carrier aggregation…</div>;
  else if (data.error) body = <div className="notice is-error">{data.error}</div>;
  else if (enbs.length === 0)
    body = (
      <div className="placeholder">
        This file has no LTE eNB (LNBTS). The CA check covers LTE carrier aggregation only.
      </div>
    );
  else if (tab === "findings")
    body = (
      <>
        {enbs.length === 1 && <EnbSummary enb={enbs[0]} />}
        <Findings enbs={enbs} onShowInTree={onShowInTree} />
      </>
    );
  else
    body = enbs.map((enb) => (
      <section key={enb.id} className="ca-enb">
        <EnbSummary enb={enb} />
        {tab === "cells" ? (
          <CellsTable enb={enb} onShowInTree={onShowInTree} />
        ) : (
          <RelationsTable enb={enb} onShowInTree={onShowInTree} />
        )}
      </section>
    ));

  const tabs = [
    ["findings", "Findings", findingCount],
    ["cells", "Cells", cellCount],
    ["relations", "Relations", relationCount],
  ];

  return (
    <Modal
      title="Carrier aggregation check"
      className="ca-check-modal"
      onClose={onClose}
      footer={
        <>
          <span className="ca-footer-hint">
            Read-only. "Nokia rule" checks come from the LTE18 / SBTS18A dictionaries; "Seen in your files" checks
            come from comparing your own CA files. Neither proves CA works on air.
          </span>
          <button className="btn" onClick={onClose}>
            Close
          </button>
        </>
      }
    >
      {enbs.length > 0 && (
        <div className="required-fields-tabs" role="tablist" aria-label="CA check sections">
          {tabs.map(([key, label, count]) => (
            <button key={key} role="tab" aria-selected={tab === key} className="rf-tab" onClick={() => setTab(key)}>
              {label} <span className="rf-tab-count">{count}</span>
            </button>
          ))}
        </div>
      )}
      <div className="modal-body ca-check-body">{body}</div>
    </Modal>
  );
}

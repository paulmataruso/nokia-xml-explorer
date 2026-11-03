import React, { useEffect, useMemo, useRef, useState } from "react";
import { applyCa, duplicateToUploads, getCaWizard, previewCa } from "../api.js";
import { ChangeRow, ConfirmList, PlanProblems, plural, toggleIn } from "./ActionParts.jsx";
import { Findings } from "./CaCheckModal.jsx";
import { Icon } from "./Icon.jsx";
import { Modal } from "./Modal.jsx";

const STEPS = [
  ["pairs", "1 · Pairs"],
  ["values", "2 · Values"],
  ["review", "3 · Review"],
];

const OPTIONS = [
  ["fillMissing", "Add CA tuning this file lacks", "Copies the donor's value for each CA tuning parameter this file doesn't set."],
  [
    "copyTuning",
    "Replace CA tuning that differs",
    "Also overwrites CA tuning (thresholds, timers, CAREL weights) this file sets to something else.",
  ],
  [
    "raiseModulation",
    "Raise SCell modulation to the PCell's",
    "An SCell only adds downlink, so a lower modulation cap (actModulationSchemeDl) limits what CA gains.",
  ],
  [
    "barScellOnly",
    "Bar cells that are only SCells",
    "Phones then reach those cells only through CA. With CBRS, a barred SCell takes the site down if the PCell loses its grant.",
  ],
  [
    "cleanStale",
    "Clean up leftovers",
    "Retargets or removes CA profiles and idle-mode entries that point at carriers no cell uses.",
  ],
];

const GROUPS = [
  ["switches", "CA switches"],
  ["objects", "eNB CA objects"],
  ["relations", "Relations and CA profiles"],
  ["cells", "Cell settings"],
  ["fill", "Tuning added from the donor"],
  ["tuning", "Tuning replaced with the donor's"],
  ["cleanup", "Leftovers"],
];

const last = (dn) => (dn ? dn.split("/").pop() : "");

function pairsFrom(relations) {
  return Object.fromEntries((relations || []).map((r) => [r.pcell, [...r.scells]]));
}

function relationsFrom(pairs, cells) {
  return cells.map((c) => ({ pcell: c.id, scells: pairs[c.id] || [] })).filter((r) => r.scells.length > 0);
}

/** The per-PCell limits the backend enforces, checked as the user ticks. */
function limitProblem(cell, scellIds, byId) {
  const lim = cell.limits;
  if (lim.total != null && scellIds.length > lim.total) return `At most ${lim.total} SCells`;
  const perCarrier = {};
  scellIds.forEach((id) => {
    const e = byId[id]?.earfcn;
    perCarrier[e] = (perCarrier[e] || 0) + 1;
  });
  const carriers = Object.keys(perCarrier);
  if (carriers.some((e) => perCarrier[e] > lim.perCarrier)) return `At most ${lim.perCarrier} per carrier`;
  if (carriers.length > lim.carriers) return `At most ${lim.carriers} carriers`;
  return null;
}

function cellFacts(c) {
  return [c.band != null ? `B${c.band}` : null, c.earfcn, c.tech, c.bandwidth, c.cbrs ? "CBRS" : null]
    .filter(Boolean)
    .join(" · ");
}

function PairGrid({ enb, pairs, onToggle }) {
  const byId = useMemo(() => Object.fromEntries(enb.cells.map((c) => [c.id, c])), [enb]);
  const blockedList = useMemo(() => {
    const byReason = {};
    Object.entries(enb.blocked).forEach(([p, row]) =>
      Object.entries(row).forEach(([s, reason]) => {
        (byReason[reason] = byReason[reason] || []).push(`${last(p)} → ${last(s)}`);
      })
    );
    return Object.entries(byReason);
  }, [enb]);

  return (
    <>
      <div className="cw-grid-wrap">
        <table className="ca-table cw-grid">
          <thead>
            <tr>
              <th scope="col">PCell</th>
              {enb.cells.map((s) => (
                <th key={s.id} scope="col" className="cw-col" title={cellFacts(s)}>
                  <span className="mono">{s.label}</span>
                  <span className="ca-sub">{s.band != null ? `B${s.band}` : s.earfcn}</span>
                </th>
              ))}
              <th scope="col">SCells</th>
            </tr>
          </thead>
          <tbody>
            {enb.cells.map((p) => {
              const chosen = pairs[p.id] || [];
              const problem = limitProblem(p, chosen, byId);
              return (
                <tr key={p.id}>
                  <th scope="row">
                    <div className="mono ca-cell-label">{p.label}</div>
                    <div className="ca-sub">
                      {cellFacts(p)}
                      {p.radio ? ` · ${p.radio}` : ""}
                    </div>
                  </th>
                  {enb.cells.map((s) => {
                    if (s.id === p.id) return <td key={s.id} className="cw-self" aria-label="Same cell" />;
                    const reason = enb.blocked[p.id]?.[s.id];
                    if (reason)
                      return (
                        <td key={s.id} className="cw-blocked" title={reason}>
                          <Icon name="x" size={12} />
                          <span className="visually-hidden">
                            {p.label} → {s.label}: {reason}
                          </span>
                        </td>
                      );
                    const prio = chosen.indexOf(s.id) + 1;
                    return (
                      <td key={s.id} className={"cw-pick" + (prio ? " is-on" : "")}>
                        <label title={`${s.label} as an SCell of ${p.label}`}>
                          <input
                            type="checkbox"
                            checked={prio > 0}
                            onChange={() => onToggle(p.id, s.id)}
                            aria-label={`${s.label} as an SCell of ${p.label}`}
                          />
                          {prio > 0 && <span className="cw-prio mono" title="Priority (scellPrio)">{prio}</span>}
                        </label>
                      </td>
                    );
                  })}
                  <td className={"cw-count " + (problem ? "ca-missing" : "mono")}>
                    {problem || (chosen.length ? `${chosen.length} of ${p.limits.total ?? p.limits.carriers}` : "–")}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="cw-hint">
        Tick a box to make the column's cell an SCell of the row's cell. The number is its place in that PCell's
        priority order (scellPrio, tried first at 1), in the order you tick them; relations you keep in the same order
        keep their current scellPrio. A cell can be both a PCell and an SCell.
      </p>
      {blockedList.length > 0 && (
        <details className="cw-details">
          <summary>
            Why some pairs can't be picked ({blockedList.reduce((n, [, ps]) => n + ps.length, 0)})
          </summary>
          <ul className="cw-blocked-list">
            {blockedList.map(([reason, ps]) => (
              <li key={reason}>
                <span className="cw-blocked-reason">{reason}:</span> <span className="mono">{ps.join(", ")}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

function DonorList({ donors, value, ul, onChange }) {
  if (donors.length === 0)
    return (
      <div className="notice is-error">
        <Icon name="alert" />
        <span className="notice-text">
          No working CA export was found among your files (downlink CA on, CAREL relations, no errors in the CA
          check). Add one to uploads to use it as the donor.
        </span>
      </div>
    );
  return (
    <ul className="cw-donors" role="radiogroup" aria-label="Donor file">
      {donors.map((d) => {
        const key = `${d.source}:${d.name}`;
        const disabled = ul && !d.ul;
        const facts = [
          d.release,
          d.techs.join(" + "),
          d.bands.length ? d.bands.map((b) => `B${b}`).join(", ") : null,
          plural(d.cells, "cell"),
          plural(d.relations, "relation"),
          d.pattern,
          d.ul ? `UL ${d.ul}` : "DL only",
          d.cbrs ? "CBRS profile" : null,
        ].filter(Boolean);
        return (
          <li key={key} className={"cw-donor" + (value === key ? " is-selected" : "") + (disabled ? " is-disabled" : "")}>
            <label>
              <input
                type="radio"
                name="ca-donor"
                checked={value === key}
                disabled={disabled}
                onChange={() => onChange(key)}
              />
              <span className="cw-donor-main">
                <span className="cw-donor-name">
                  <span className="mono">{d.name}</span>
                  <span className="tag">{d.self ? "this file" : d.source}</span>
                </span>
                <span className="cw-donor-facts mono">{facts.join(" · ")}</span>
                <span className="cw-donor-why">
                  {disabled
                    ? "Runs downlink CA only, so it has no uplink mode to copy."
                    : d.reasons.length
                      ? d.reasons.join(" · ")
                      : "Nothing in common with this file beyond CA itself."}
                </span>
              </span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}

function Review({ plan, enbLabel, confirmed, onConfirm }) {
  const restarts = plan.changes.filter((c) => /restart/i.test(c.modification || "")).length;
  const locking = plan.changes.filter((c) => /locking/i.test(c.modification || "")).length;
  const counts = (s) =>
    `${plural(s.errors, "error")}, ${plural(s.warnings, "warning")}` + (s.infos ? `, ${plural(s.infos, "note")}` : "");
  return (
    <>
      <div className="ca-summary">
        <span className="ca-fact">
          <strong>{plural(plan.changes.length, "change")}</strong> on <span className="mono">{enbLabel}</span>
        </span>
        <span className="ca-fact">
          Values from <strong className="mono">{plan.donor.name}</strong> ({plan.donor.release})
        </span>
        <span className="ca-fact">
          CA check: now {counts(plan.before)} · after{" "}
          <strong className={plan.after.errors ? "ca-missing" : undefined}>{counts(plan.after)}</strong>
        </span>
      </div>
      {(restarts > 0 || locking > 0) && (
        <div className="notice is-note cw-notice">
          <Icon name="info" />
          <span className="notice-text">
            {restarts > 0 && `${plural(restarts, "change")} may need a BTS restart (marked below). `}
            {locking > 0 && `${plural(locking, "change")} need the object locked first. `}
            Plan the load for a maintenance window.
          </span>
        </div>
      )}
      {plan.changes.length === 0 && (
        <div className="notice is-note cw-notice">
          <Icon name="check-circle" />
          <span className="notice-text">This setup is already in the file. Nothing to change.</span>
        </div>
      )}
      {plan.notes.map((n, i) => (
        <div key={i} className="notice is-note cw-notice">
          <Icon name="info" />
          <span className="notice-text">{n}</span>
        </div>
      ))}

      {GROUPS.map(([key, title]) => {
        const items = plan.changes.filter((c) => c.group === key);
        if (!items.length) return null;
        return (
          <section key={key}>
            <h3 className="ca-section-title">
              {title} <span className="rf-tab-count">{items.length}</span>
            </h3>
            <ul className="cw-changes">
              {items.map((c, i) => (
                <ChangeRow key={i} c={c} rootId={plan.enb} donorName={plan.donor.name} />
              ))}
            </ul>
          </section>
        );
      })}

      {(plan.skipped.length > 0 || plan.unverifiedClasses.length > 0) && (
        <>
          <h3 className="ca-section-title">Release filter</h3>
          {plan.skipped.length > 0 && (
            <details className="cw-details">
              <summary>
                {plural(plan.skipped.length, "donor value")} left out: no {plan.release} file in your corpus sets them
              </summary>
              <ul className="cw-skipped mono">
                {plan.skipped.map((s) => (
                  <li key={`${s.class}.${s.param}`}>
                    {s.class}.{s.param} = {s.value}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {plan.unverifiedClasses.length > 0 && (
            <p className="cw-hint">
              No {plan.release} file in your corpus has <span className="mono">{plan.unverifiedClasses.join(", ")}</span>,
              so those values were copied from the donor without the release filter.
            </p>
          )}
        </>
      )}

      <h3 className="ca-section-title">CA check after the change</h3>
      <Findings
        enbs={[{ label: enbLabel, findings: plan.after.findings }]}
        emptyText="No problems: the result passes every official CA rule this tool checks and matches the patterns in your working CA files."
      />

      <h3 className="ca-section-title">Before you load it</h3>
      <p className="cw-hint">
        This plan follows Nokia's dictionary rules and your working files; it isn't proven on air. Check what the file
        can't show:
      </p>
      <ConfirmList items={plan.confirm} confirmed={confirmed} onToggle={onConfirm} />
    </>
  );
}

/**
 * The CA wizard (phases 2 and 3, backend ca_wizard.py): pick PCell/SCell
 * pairs, a donor file whose working CA setup supplies the values, and
 * options; review every change with its reason and when it takes effect;
 * apply it as one undoable edit. A read-only file gets an editable copy
 * first. `onApplied(result)` gets the apply response plus `file` (where it
 * was written), `copied` and `changeIds` (rows to mark as edited).
 */
export function CaWizardModal({ filename, editable, onClose, onApplied, onCopyLeft }) {
  const [setup, setSetup] = useState(null);
  const [enbId, setEnbId] = useState(null);
  const [step, setStep] = useState("pairs");
  const [pairs, setPairs] = useState({});
  const [presetKey, setPresetKey] = useState(null);
  const [donorKey, setDonorKey] = useState(null);
  const [ul, setUl] = useState(false);
  const [options, setOptions] = useState({});
  const [plan, setPlan] = useState(null);
  const [planRequest, setPlanRequest] = useState(null);
  const [error, setError] = useState(null); // { message, problems }
  const [confirmed, setConfirmed] = useState(() => new Set());
  const [applying, setApplying] = useState(false);
  const headingRef = useRef(null);

  const enb = setup?.enbs.find((e) => e.id === enbId) || null;

  const pickEnb = (e) => {
    setEnbId(e.id);
    const preset = e.presets.find((p) => p.key === e.defaultPreset);
    setPairs(pairsFrom(preset?.relations));
    setPresetKey(preset?.key || null);
    const canUl = e.ulOn && e.ulBlockedBy.length === 0 && e.donors.some((d) => d.ul);
    setUl(canUl);
    const donor = e.donors.find((d) => !canUl || d.ul);
    setDonorKey(donor ? `${donor.source}:${donor.name}` : null);
  };

  useEffect(() => {
    let cancelled = false;
    getCaWizard(filename)
      .then((s) => {
        if (cancelled) return;
        setSetup(s);
        const first = s.enbs.find((e) => e.cells.length > 1) || s.enbs[0];
        if (first) pickEnb(first);
      })
      .catch((e) => !cancelled && setSetup({ error: String(e.message || e) }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filename]);

  useEffect(() => {
    headingRef.current?.focus();
  }, [step]);

  const relations = enb ? relationsFrom(pairs, enb.cells) : [];
  const donor = enb?.donors.find((d) => `${d.source}:${d.name}` === donorKey) || null;
  const effectiveOptions = { ...(setup?.defaultOptions || {}), ...options };
  const request = enb &&
    donor && {
      enb: enb.id,
      relations,
      ul,
      options: effectiveOptions,
      donor: { name: donor.name, source: donor.source },
    };

  const toggle = (p, s) => {
    setPairs((prev) => {
      const cur = prev[p] || [];
      return { ...prev, [p]: cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s] };
    });
    setPresetKey(null);
  };

  const goReview = () => {
    setStep("review");
    setPlan(null);
    setError(null);
    setConfirmed(new Set());
    setPlanRequest(request);
    previewCa(filename, request)
      .then(setPlan)
      .catch((e) => setError({ message: String(e.message || e), problems: e.problems || null }));
  };

  const apply = async () => {
    setApplying(true);
    setError(null);
    let target = filename;
    let copied = false;
    try {
      if (!editable) {
        target = (await duplicateToUploads(filename)).name;
        copied = true;
      }
      const res = await applyCa(target, planRequest);
      const changeIds = plan.changes.filter((c) => c.op !== "delete").map((c) => c.id);
      onApplied({ ...res, file: target, copied, changeIds });
    } catch (e) {
      const message = String(e.message || e);
      setError({
        message: copied ? `Made the copy ${target}, but couldn't set up CA on it: ${message}` : message,
        problems: e.problems || null,
      });
      if (copied) onCopyLeft?.(target);
    } finally {
      setApplying(false);
    }
  };

  const allConfirmed = plan && plan.confirm.every((_, i) => confirmed.has(i));
  const nothingToDo = plan && plan.changes.length === 0;
  const anyPairs = relations.length > 0;
  const overLimit =
    enb && enb.cells.some((c) => limitProblem(c, pairs[c.id] || [], Object.fromEntries(enb.cells.map((x) => [x.id, x]))));

  let body;
  if (!setup) body = <div className="placeholder">Reading the file and your CA exports…</div>;
  else if (setup.error) body = <div className="notice is-error">{setup.error}</div>;
  else if (!enb)
    body = <div className="placeholder">This file has no LTE eNB (LNBTS). The CA wizard covers LTE only.</div>;
  else if (enb.cells.length < 2)
    body = (
      <div className="placeholder">
        {enb.label} has {plural(enb.cells.length, "cell")}. Carrier aggregation needs at least two cells on different
        carriers.
      </div>
    );
  else if (step === "pairs") {
    const preset = enb.presets.find((p) => p.key === presetKey);
    body = (
      <>
        <h3 className="cw-step-title" ref={headingRef} tabIndex={-1}>
          Which cells pair up?
        </h3>
        <div className="ca-summary">
          {setup.enbs.length > 1 ? (
            <select
              className="cw-enb-select"
              value={enb.id}
              onChange={(e) => pickEnb(setup.enbs.find((x) => x.id === e.target.value))}
              aria-label="eNB"
            >
              {setup.enbs.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.label}
                </option>
              ))}
            </select>
          ) : (
            <span className="ca-fact mono">{enb.label}</span>
          )}
          {enb.release && <span className="ca-fact mono">{enb.release}</span>}
          <span className="ca-fact">
            Downlink CA now <strong>{enb.dl ? "on" : "off"}</strong>
          </span>
          <span className="ca-fact">
            Flexible SCell selection <strong>{enb.flexScellSelect ? "on" : "off"}</strong>
          </span>
          {enb.foreignRelations > 0 && (
            <span className="ca-fact">
              <strong>{plural(enb.foreignRelations, "relation")}</strong> to other eNBs, left as they are
            </span>
          )}
        </div>
        <div className="cw-presets" role="group" aria-label="Presets">
          {enb.presets.map((p) => (
            <button
              key={p.key}
              className="btn btn-toggle"
              aria-pressed={presetKey === p.key}
              onClick={() => {
                setPairs(pairsFrom(p.relations));
                setPresetKey(p.key);
              }}
            >
              {p.label}
            </button>
          ))}
          <button
            className="btn btn-quiet"
            onClick={() => {
              setPairs({});
              setPresetKey(null);
            }}
          >
            Clear
          </button>
        </div>
        <p className="cw-hint">
          {preset ? preset.detail : anyPairs ? "Your own pairs." : "Pick a preset, or tick pairs in the grid."}
        </p>
        <PairGrid enb={enb} pairs={pairs} onToggle={toggle} />
      </>
    );
  } else if (step === "values") {
    const ulDisabledWhy =
      enb.ulBlockedBy.length > 0
        ? `Uplink CA can't be on while actFlexDupGap is true on ${enb.ulBlockedBy.join(", ")}.`
        : !enb.donors.some((d) => d.ul)
          ? "None of your working CA exports runs uplink CA, so there's no uplink mode to copy."
          : null;
    body = (
      <>
        <h3 className="cw-step-title" ref={headingRef} tabIndex={-1}>
          Where the values come from
        </h3>
        <div className="cw-row">
          <span className="cw-label">Direction</span>
          <div className="cw-presets" role="group" aria-label="Direction">
            <button className="btn btn-toggle" aria-pressed={!ul} onClick={() => setUl(false)}>
              Downlink only
            </button>
            <button
              className="btn btn-toggle"
              aria-pressed={ul}
              disabled={!!ulDisabledWhy}
              onClick={() => {
                setUl(true);
                if (donor && !donor.ul) {
                  const d = enb.donors.find((x) => x.ul);
                  setDonorKey(d ? `${d.source}:${d.name}` : null);
                }
              }}
            >
              Downlink + uplink
            </button>
          </div>
          {ulDisabledWhy && <span className="cw-hint">{ulDisabledWhy}</span>}
        </div>
        <h3 className="ca-section-title">Donor: a working CA export to copy values from</h3>
        <DonorList donors={enb.donors} value={donorKey} ul={ul} onChange={setDonorKey} />
        <p className="cw-hint">
          Best match first. Donor values are only written where some file of this file's release ({enb.release}) in
          your corpus sets that parameter, so a newer donor can't add parameters an older BTS won't know.
        </p>
        <h3 className="ca-section-title">Options</h3>
        <ul className="cw-options">
          {OPTIONS.map(([key, label, help]) => {
            const on = !!effectiveOptions[key];
            return (
              <li key={key}>
                <label>
                  <input type="checkbox" checked={on} onChange={() => setOptions((o) => ({ ...o, [key]: !on }))} />
                  <span>
                    <span className="cw-option-label">{label}</span>
                    <span className="cw-option-help">{help}</span>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      </>
    );
  } else {
    body = (
      <>
        <h3 className="cw-step-title" ref={headingRef} tabIndex={-1}>
          Review the changes
        </h3>
        {error ? (
          <PlanProblems error={error} lead="The wizard can't plan this:" />
        ) : !plan ? (
          <div className="placeholder">Planning the changes…</div>
        ) : (
          <Review
            plan={plan}
            enbLabel={enb.label}
            confirmed={confirmed}
            onConfirm={(i) => setConfirmed((prev) => toggleIn(prev, i))}
          />
        )}
      </>
    );
  }

  const stepIndex = STEPS.findIndex(([k]) => k === step);
  const ready = enb && enb.cells.length > 1;
  const canNext = step === "pairs" ? anyPairs && !overLimit : step === "values" ? !!donor : false;

  return (
    <Modal
      title={enb?.dl ? "Change carrier aggregation" : "Set up carrier aggregation"}
      className="ca-wizard-modal"
      onClose={onClose}
      footer={
        <>
          <span className="ca-footer-hint">
            {editable
              ? "Applied as one edit with a snapshot, so Undo puts the file back exactly."
              : "This file is read-only: the change goes into an editable copy in Your uploads."}
          </span>
          {stepIndex > 0 && (
            <button className="btn" onClick={() => setStep(STEPS[stepIndex - 1][0])} disabled={applying}>
              <Icon name="chevron-left" />
              Back
            </button>
          )}
          {step !== "review" ? (
            <button
              className="btn btn-primary"
              disabled={!ready || !canNext}
              onClick={() => (step === "pairs" ? setStep("values") : goReview())}
            >
              {step === "values" ? "Review changes" : "Next"}
              <Icon name="chevron-right" />
            </button>
          ) : (
            <button className="btn btn-primary" disabled={!allConfirmed || nothingToDo || applying} onClick={apply}>
              {applying ? "Applying…" : editable ? "Apply" : "Apply to a copy"}
            </button>
          )}
        </>
      }
    >
      {ready && (
        <div className="required-fields-tabs cw-steps" aria-label="Steps">
          {STEPS.map(([key, label], i) => (
            <button
              key={key}
              className="rf-tab"
              aria-current={step === key ? "step" : undefined}
              disabled={i > stepIndex || applying}
              onClick={() => setStep(key)}
            >
              {label}
            </button>
          ))}
          {step === "review" && plan && !allConfirmed && !nothingToDo && (
            <span className="rf-tab-hint">Tick every check under "Before you load it" to apply.</span>
          )}
        </div>
      )}
      <div className="modal-body ca-wizard-body">{body}</div>
    </Modal>
  );
}

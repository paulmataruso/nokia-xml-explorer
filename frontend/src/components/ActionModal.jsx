import React, { useEffect, useMemo, useRef, useState } from "react";
import { applyAction, applyRun, duplicateToUploads, getActionSetup, previewRun } from "../api.js";
import { ChangeRow, ConfirmList, ManualSteps, PlanProblems, StepsTools, plural, toggleIn } from "./ActionParts.jsx";
import { Findings } from "./CaCheckModal.jsx";
import { Highlight } from "./Highlight.jsx";
import { Icon } from "./Icon.jsx";
import { Modal } from "./Modal.jsx";

const STEPS = [
  ["inputs", "1 · Inputs"],
  ["review", "2 · Review"],
];

const counts = (s) =>
  `${plural(s.errors, "error")}, ${plural(s.warnings, "warning")}` + (s.infos ? `, ${plural(s.infos, "note")}` : "");

/** A field's options: its own, or for a `dependsOn` field the ones keyed by its parent's chosen option (chains too).
 * `excludeField` drops the option another field has chosen ("More neighbours" leaves out the first). */
function resolveOptions(fields, values, field) {
  const own = ownOptions(fields, values, field);
  return field.excludeField ? own.filter((o) => o.value !== values[field.excludeField]) : own;
}

function ownOptions(fields, values, field) {
  // A field with fixed options may still depend on another, for its default only.
  if (!field.dependsOn || !field.optionsByKey) return field.options || [];
  const parent = fields.find((f) => f.id === field.dependsOn);
  const chosen = parent && resolveOptions(fields, values, parent).find((o) => o.value === values[parent.id]);
  if (!chosen?.key) return [];
  // Suggestions are base codes; "474020A.102" hides "474020A".
  const current = (chosen.current || "").split(".")[0];
  return (field.optionsByKey?.[chosen.key] || []).filter((o) => o.value !== current);
}

/** Values that follow a choice: fields depending on `id` whose
 * `defaultByKey` has an entry for the chosen option's key (the current IP of
 * the MME picked, say). */
function dependentDefaults(fields, values, id, value) {
  const parent = fields.find((f) => f.id === id);
  const key = parent && resolveOptions(fields, values, parent).find((o) => o.value === value)?.key;
  const out = {};
  for (const f of fields) if (f.dependsOn === id && key != null && f.defaultByKey?.[key] != null) out[f.id] = f.defaultByKey[key];
  // Down the chain: a default card brings its default ports.
  for (const [k, v] of Object.entries(out)) Object.assign(out, dependentDefaults(fields, { ...values, ...out }, k, v));
  return out;
}

/** The fields that depend on `id`, directly or down a chain. */
function dependents(fields, id) {
  const out = [];
  for (const f of fields) if (f.dependsOn === id) out.push(f.id, ...dependents(fields, f.id));
  return out;
}

function groupBy(options) {
  const out = [];
  for (const o of options) {
    let g = out.find((x) => x.name === (o.group || ""));
    if (!g) out.push((g = { name: o.group || "", items: [] }));
    g.items.push(o);
  }
  return out;
}

function SelectField({ field, value, options, onChange }) {
  const chosen = options.find((o) => o.value === value);
  return (
    <div className="am-field">
      <label className="cw-label" htmlFor={`am-${field.id}`}>
        {field.label}
      </label>
      <select id={`am-${field.id}`} className="am-select" value={value || ""} onChange={(e) => onChange(e.target.value)}>
        <option value="" disabled>
          Pick one
        </option>
        {groupBy(options).map((g) =>
          g.name ? (
            <optgroup key={g.name} label={g.name}>
              {g.items.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </optgroup>
          ) : (
            g.items.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))
          ),
        )}
      </select>
      {chosen?.details?.length > 0 && (
        <ul className="am-details">
          {chosen.details.map((d, i) => (
            <li key={i}>{d}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Free text with suggestions below it: typing filters them, a click takes one. */
function ComboField({ field, value, options, onChange }) {
  const q = (value || "").trim().toLowerCase();
  const shown = options.filter(
    (o) => !q || o.value.toLowerCase().includes(q) || (o.name || "").toLowerCase().includes(q),
  );
  return (
    <div className="am-field">
      <label className="cw-label" htmlFor={`am-${field.id}`}>
        {field.label}
      </label>
      <input
        id={`am-${field.id}`}
        type="text"
        className="input mono"
        value={value || ""}
        placeholder={field.placeholder}
        spellCheck={false}
        autoComplete="off"
        onChange={(e) => onChange(e.target.value)}
      />
      {options.length > 0 && (
        <div className="am-suggest" role="group" aria-label={`${field.label} suggestions`}>
          {shown.length === 0 ? (
            <p className="cw-hint">No suggestion matches. You can still use what you typed.</p>
          ) : (
            groupBy(shown).map((g) => (
              <section key={g.name}>
                {g.name && <h4 className="am-suggest-group">{g.name}</h4>}
                <ul className="cw-donors">
                  {g.items.map((o) => {
                    const on = (value || "").trim() === o.value;
                    return (
                      <li key={o.value} className={"cw-donor" + (on ? " is-selected" : "")}>
                        <button type="button" className="am-suggest-item" onClick={() => onChange(o.value)}>
                          <span className="cw-donor-name">
                            <span className="mono">
                              <Highlight text={o.label} query={q} />
                            </span>
                            {o.name && (
                              <span>
                                <Highlight text={o.name} query={q} />
                              </span>
                            )}
                          </span>
                          {o.hint && <span className="cw-donor-why">{o.hint}</span>}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function TextField({ field, value, onChange }) {
  return (
    <div className="am-field">
      <label className="cw-label" htmlFor={`am-${field.id}`}>
        {field.label}
        {field.optional && <span className="am-optional">optional</span>}
      </label>
      <input
        id={`am-${field.id}`}
        type="text"
        className="input"
        value={value || ""}
        placeholder={field.placeholder}
        aria-describedby={field.hint ? `am-${field.id}-hint` : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {field.hint && (
        <p id={`am-${field.id}-hint`} className="cw-hint am-hint">
          {field.hint}
        </p>
      )}
    </div>
  );
}

/** A set of checkboxes; `value` is the ticked values, every one when unset. */
function ChecksField({ field, value, options, onChange }) {
  const ticked = new Set(value ?? options.map((o) => o.value));
  const toggle = (v) => {
    const next = new Set(ticked);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    onChange(options.map((o) => o.value).filter((x) => next.has(x)));
  };
  const all = ticked.size === options.length;
  return (
    <fieldset className="am-field am-checks">
      <legend className="cw-label">
        {field.label}{" "}
        <span className="am-checks-count">
          {ticked.size} of {options.length}
        </span>
      </legend>
      {options.length > 1 && (
        <button
          type="button"
          className="btn btn-quiet am-checks-all"
          onClick={() => onChange(all ? [] : options.map((o) => o.value))}
        >
          {all ? "Clear all" : "Select all"}
        </button>
      )}
      <ul className="cw-options">
        {options.map((o) => (
          <li key={o.value}>
            <label>
              <input type="checkbox" checked={ticked.has(o.value)} onChange={() => toggle(o.value)} />
              <span>
                <span className="cw-option-label mono">{o.label}</span>
                {o.hint && <span className="cw-option-help">{o.hint}</span>}
              </span>
            </label>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}

/** Several of a long list, ticked: a filter, the options in their groups, and how many are picked. `value` is
 * the ticked values (none when unset). */
function PicksField({ field, value, options, onChange }) {
  const [query, setQuery] = useState("");
  const ticked = new Set(value || []);
  const q = query.trim().toLowerCase();
  const shown = options.filter(
    (o) => !q || o.label.toLowerCase().includes(q) || (o.hint || "").toLowerCase().includes(q),
  );
  const count = options.filter((o) => ticked.has(o.value)).length;
  const toggle = (v) => {
    const next = new Set(ticked);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    onChange(options.map((o) => o.value).filter((x) => next.has(x)));
  };
  return (
    <fieldset className="am-field am-checks am-picks">
      <legend className="cw-label">
        {field.label}
        {field.optional && <span className="am-optional">optional</span>}
        <span className="am-checks-count">{count ? `${count} picked` : `none of ${options.length}`}</span>
      </legend>
      {field.hint && <p className="cw-hint am-hint">{field.hint}</p>}
      <div className="am-picks-bar">
        <input
          type="search"
          className="input"
          value={query}
          placeholder="Filter by id, name, address or file"
          aria-label={`Filter ${field.label}`}
          spellCheck={false}
          onChange={(e) => setQuery(e.target.value)}
        />
        {count > 0 && (
          <button type="button" className="btn btn-quiet" onClick={() => onChange([])}>
            Clear
          </button>
        )}
      </div>
      <div className="am-picks-list">
        {shown.length === 0 ? (
          <p className="cw-hint">Nothing matches “{query.trim()}”.</p>
        ) : (
          groupBy(shown).map((g) => (
            <section key={g.name}>
              {g.name && <h4 className="am-suggest-group">{g.name}</h4>}
              <ul className="cw-options">
                {g.items.map((o) => (
                  <li key={o.value}>
                    <label>
                      <input type="checkbox" checked={ticked.has(o.value)} onChange={() => toggle(o.value)} />
                      <span>
                        <span className="cw-option-label mono">
                          <Highlight text={o.label} query={q} />
                        </span>
                        {o.hint && <span className="cw-option-help">{o.hint}</span>}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </div>
    </fieldset>
  );
}

function Review({ plan, confirmed, onConfirm, view, onView, filename }) {
  const rootId = plan.changes[0]?.dn.split("/")[0];
  const stepsFile = `${(filename || "plan").replace(/\.xml$/i, "")} - ${plan.label || "steps"}.txt`.replace(/[\\/:*?"<>|]/g, "_");
  const restarts = plan.changes.filter((c) => /restart/i.test(c.modification || "")).length;
  const todo = plan.todo || [];
  return (
    <>
      <div className="ca-summary">
        <span className="ca-fact">
          <strong>{plural(plan.changes.length, "change")}</strong>
          {plan.summary ? `: ${plan.summary}` : ""}
        </span>
        <span className="ca-fact">
          Site check: now {counts(plan.check.before)} · after{" "}
          <strong className={plan.check.after.errors > plan.check.before.errors ? "ca-missing" : undefined}>
            {counts(plan.check.after)}
          </strong>
        </span>
      </div>
      {restarts > 0 && (
        <div className="notice is-note cw-notice">
          <Icon name="info" />
          <span className="notice-text">
            {plural(restarts, "change")} may need a BTS restart (marked below). Plan the load for a maintenance window.
          </span>
        </div>
      )}
      {plan.changes.length === 0 && (
        <div className="notice is-note cw-notice">
          <Icon name="check-circle" />
          <span className="notice-text">
            {todo.length ? "Nothing the tool can write is missing." : "The file already has this. Nothing to change."}
          </span>
        </div>
      )}
      {plan.notes.map((n, i) => (
        <div key={i} className="notice is-note cw-notice">
          <Icon name="info" />
          <span className="notice-text">{n}</span>
        </div>
      ))}
      {plan.changes.length > 0 && (
        <>
          <div className="am-views" role="tablist" aria-label="Show the plan as">
            <button role="tab" className="rf-tab" aria-selected={view !== "steps"} onClick={() => onView("changes")}>
              Changes <span className="rf-tab-count">{plan.changes.length}</span>
            </button>
            <button role="tab" className="rf-tab" aria-selected={view === "steps"} onClick={() => onView("steps")}>
              Manual steps <span className="rf-tab-count">{plan.steps.length}</span>
            </button>
            {view === "steps" && <StepsTools text={plan.stepsText} filename={stepsFile} />}
          </div>
          {view === "steps" ? (
            <>
              <p className="cw-hint am-hint">
                What to create and change, object by object, to make this by hand in the Nokia WebUI instead of
                loading the file.
              </p>
              <ManualSteps steps={plan.steps} />
            </>
          ) : (
            <ul className="cw-changes">
              {plan.changes.map((c, i) => (
                <ChangeRow key={i} c={c} rootId={rootId} donorName={plan.donor?.name} />
              ))}
            </ul>
          )}
        </>
      )}
      {todo.length > 0 && (
        <>
          <div className="ms-todo-head">
            <h3 className="ca-section-title">Also needed, by hand</h3>
            {plan.changes.length === 0 && <StepsTools text={plan.stepsText} filename={stepsFile} />}
          </div>
          <ul className="ms-todo">
            {todo.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </>
      )}
      {plan.check.new.length > 0 && (
        <>
          <h3 className="ca-section-title">What the site check would find</h3>
          <Findings enbs={[{ label: rootId, findings: plan.check.new }]} />
        </>
      )}
      {plan.confirm.length > 0 && (
        <>
          <h3 className="ca-section-title">Before you load it</h3>
          <ConfirmList items={plan.confirm} confirmed={confirmed} onToggle={onConfirm} />
        </>
      )}
    </>
  );
}

/** The ticked confirms of one file of a run (keys "file:item"), as the item numbers. */
const confirmsOf = (confirmed, fi) =>
  new Set([...confirmed].filter((k) => k.startsWith(`${fi}:`)).map((k) => Number(k.split(":")[1])));

/** A run's review: each file it writes, with what it does there and its own plan, site check and confirms. */
function RunReview({ run, confirmed, onConfirm, view, onView }) {
  const total = run.reduce((n, f) => n + (f.plan?.changes.length || 0), 0);
  return (
    <>
      <div className="ca-summary">
        <span className="ca-fact">
          <strong>{plural(run.length, "file")}</strong>, {plural(total, "change")} in all
        </span>
        <span className="ca-fact">Written together, each with its own snapshot; a read-only file goes into a copy.</span>
      </div>
      {run.map((f, fi) => (
        <section key={f.key} className="am-run-file" aria-labelledby={`am-run-${fi}`}>
          <h3 id={`am-run-${fi}`} className="am-run-title">
            <span className="am-run-name">{f.name}</span>
            <span className="tag">{f.this ? "This file" : "Other site"}</span>
            {!f.editable && <span className="tag">Read-only: goes into a copy</span>}
          </h3>
          {f.what.length > 0 && (
            <ul className="am-details">
              {f.what.map((w, i) => (
                <li key={i}>{w}.</li>
              ))}
            </ul>
          )}
          {f.problems ? (
            <PlanProblems
              error={{ problems: f.problems }}
              lead="This file's part can't be planned. Untick what asks for it to write the rest:"
            />
          ) : (
            <Review
              plan={f.plan}
              confirmed={confirmsOf(confirmed, fi)}
              onConfirm={(i) => onConfirm(`${fi}:${i}`)}
              view={view}
              onView={onView}
              filename={f.name}
            />
          )}
        </section>
      ))}
    </>
  );
}

/**
 * A site action with a form (backend actions/, UI "form"): its fields,
 * then a review of every change with its reason, the site check before and
 * after, and what to confirm; applied as one undoable edit. A read-only
 * file gets an editable copy first. `onApplied(result)` gets the apply
 * response plus `file`, `copied` and `changeIds`, like the CA wizard's.
 * `initial` seeds field values when the form opens (the object a
 * right-click picked), over the backend's defaults.
 */
export function ActionModal({ filename, actionId, initial, editable, onClose, onApplied, onCopyLeft }) {
  const [setup, setSetup] = useState(null);
  const [values, setValues] = useState({});
  const [step, setStep] = useState("inputs");
  // The run's files (actions/run.py): this file's plan first, then the other sites' files it changes.
  const [run, setRun] = useState(null);
  const [error, setError] = useState(null);
  const [confirmed, setConfirmed] = useState(() => new Set());
  const [applying, setApplying] = useState(false);
  const [view, setView] = useState(null);
  const headingRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    getActionSetup(filename, actionId)
      .then((s) => {
        if (cancelled) return;
        setSetup(s);
        const start = {
          ...Object.fromEntries((s.fields || []).filter((f) => f.default != null).map((f) => [f.id, f.default])),
          ...initial,
        };
        for (const id of Object.keys(start)) Object.assign(start, dependentDefaults(s.fields, start, id, start[id]));
        setValues(start);
      })
      .catch((e) => !cancelled && setSetup({ error: String(e.message || e) }));
    return () => {
      cancelled = true;
    };
  }, [filename, actionId]);

  useEffect(() => {
    headingRef.current?.focus();
  }, [step, setup]);

  const fields = setup?.fields || [];
  const optionsFor = useMemo(() => (field) => resolveOptions(fields, values, field), [fields, values]);
  const setValue = (id, v) =>
    setValues((prev) => {
      const next = { ...prev, [id]: v };
      for (const d of dependents(fields, id)) delete next[d];
      return { ...next, ...dependentDefaults(fields, next, id, v) };
    });
  // A select or checkbox set whose list is empty for this choice isn't shown or asked for, nor is a field
  // whose `showIf` ({field, equals} or {field, in: [...]}) doesn't hold.
  const shown = (f) =>
    !(f.dependsOn && (f.type === "select" || f.type === "checks") && optionsFor(f).length === 0) &&
    (!f.showIf ||
      (f.showIf.in ? f.showIf.in.includes(values[f.showIf.field]) : values[f.showIf.field] === f.showIf.equals));
  // What the backend gets: an untouched checkbox set means all of it, untouched picks none; picks the options
  // no longer offer (another target, the first neighbour) are left out.
  const sent = (f) => {
    if (f.type === "checks") return values[f.id] ?? optionsFor(f).map((o) => o.value);
    if (f.type === "picks") {
      const offered = new Set(optionsFor(f).map((o) => o.value));
      return (values[f.id] ?? f.default ?? []).filter((v) => offered.has(v));
    }
    return values[f.id];
  };
  const inputs = Object.fromEntries(fields.filter(shown).map((f) => [f.id, sent(f)]));
  const complete = fields
    .filter((f) => shown(f) && !f.optional)
    .every((f) =>
      f.type === "checks" || f.type === "picks" ? inputs[f.id].length > 0 : (inputs[f.id] || "").toString().trim() !== "",
    );

  const goReview = () => {
    setStep("review");
    setRun(null);
    setError(null);
    setConfirmed(new Set());
    previewRun(filename, actionId, inputs)
      .then((r) => setRun(r.files))
      .catch((e) => setError({ message: String(e.message || e), problems: e.problems || null }));
  };
  const plan = run?.[0]?.plan;
  const several = run && run.length > 1;

  const apply = async () => {
    setApplying(true);
    setError(null);
    let target = filename;
    let copied = false;
    try {
      if (several) {
        // The server writes every file, copies included, or none.
        const [mine, ...others] = (await applyRun(filename, actionId, inputs)).files;
        onApplied({ ...mine, others });
        return;
      }
      if (!editable) {
        target = (await duplicateToUploads(filename)).name;
        copied = true;
      }
      const res = await applyAction(target, actionId, inputs);
      const changeIds = plan.changes.filter((c) => c.op !== "delete").map((c) => c.id);
      onApplied({ ...res, file: target, copied, changeIds });
    } catch (e) {
      const message = String(e.message || e);
      setError({
        message: copied ? `Made the copy ${target}, but couldn't apply the change to it: ${message}` : message,
        problems: e.problems || null,
      });
      if (copied) onCopyLeft?.(target);
    } finally {
      setApplying(false);
    }
  };

  const breaks = run && run.some((f) => f.plan?.check.new.some((x) => x.severity === "error"));
  const stuck = run && run.some((f) => f.problems);
  const allConfirmed =
    run && run.every((f, fi) => !f.plan || f.plan.confirm.every((_, i) => confirmed.has(`${fi}:${i}`)));
  const confirms = run ? run.reduce((n, f) => n + (f.plan?.confirm.length || 0), 0) : 0;
  const nothingToDo = run && run.every((f) => !f.plan || f.plan.changes.length === 0);

  let body;
  if (!setup) body = <div className="placeholder">Reading the file…</div>;
  else if (setup.error) body = <div className="notice is-error">{setup.error}</div>;
  else if (!setup.available) body = <div className="placeholder">{setup.reason}</div>;
  else if (step === "inputs")
    body = (
      <>
        <h3 className="cw-step-title" ref={headingRef} tabIndex={-1}>
          {setup.summary}
        </h3>
        {setup.intro && <p className="cw-hint">{setup.intro}</p>}
        {fields.filter(shown).map((f) =>
          f.type === "select" ? (
            <SelectField
              key={f.id}
              field={f}
              value={values[f.id]}
              options={optionsFor(f)}
              onChange={(v) => setValue(f.id, v)}
            />
          ) : f.type === "checks" ? (
            optionsFor(f).length > 0 && (
              <ChecksField
                key={f.id}
                field={f}
                value={values[f.id]}
                options={optionsFor(f)}
                onChange={(v) => setValue(f.id, v)}
              />
            )
          ) : f.type === "picks" ? (
            optionsFor(f).length > 0 && (
              <PicksField
                key={f.id}
                field={f}
                value={values[f.id]}
                options={optionsFor(f)}
                onChange={(v) => setValue(f.id, v)}
              />
            )
          ) : f.type === "combo" ? (
            <ComboField
              key={f.id}
              field={f}
              value={values[f.id]}
              options={optionsFor(f)}
              onChange={(v) => setValue(f.id, v)}
            />
          ) : (
            <TextField key={f.id} field={f} value={values[f.id]} onChange={(v) => setValue(f.id, v)} />
          ),
        )}
      </>
    );
  else
    body = (
      <>
        <h3 className="cw-step-title" ref={headingRef} tabIndex={-1}>
          Review the changes
        </h3>
        {error ? (
          <PlanProblems error={error} />
        ) : !run ? (
          <div className="placeholder">Planning the changes…</div>
        ) : several ? (
          <RunReview
            run={run}
            confirmed={confirmed}
            onConfirm={(k) => setConfirmed((prev) => toggleIn(prev, k))}
            view={view || setup.view || "changes"}
            onView={setView}
          />
        ) : (
          <Review
            plan={plan}
            confirmed={confirmsOf(confirmed, 0)}
            onConfirm={(i) => setConfirmed((prev) => toggleIn(prev, `0:${i}`))}
            view={view || setup.view || "changes"}
            onView={setView}
            filename={filename}
          />
        )}
      </>
    );

  const stepIndex = STEPS.findIndex(([k]) => k === step);
  const ready = setup && !setup.error && setup.available;

  return (
    <Modal
      title={setup?.title || "Action"}
      className="action-modal"
      onClose={onClose}
      footer={
        <>
          <span className="ca-footer-hint">
            {breaks
              ? several
                ? "A file of the run would break its links, so none can be written."
                : "This change would break the file's links, so it can't be applied."
              : stuck
                ? "A file's part can't be planned, so none can be written."
                : several
                  ? `Writes the ${run.length} files together, each with its own snapshot; read-only ones go into copies.`
                  : editable
                    ? "Applied as one edit with a snapshot, so Undo puts the file back exactly."
                    : "This file is read-only: the change goes into an editable copy in Your uploads."}
          </span>
          {stepIndex > 0 && (
            <button className="btn" onClick={() => setStep(STEPS[stepIndex - 1][0])} disabled={applying}>
              <Icon name="chevron-left" />
              Back
            </button>
          )}
          {step === "inputs" ? (
            <button className="btn btn-primary" disabled={!ready || !complete} onClick={goReview}>
              Review changes
              <Icon name="chevron-right" />
            </button>
          ) : (
            <button
              className="btn btn-primary"
              disabled={!run || !allConfirmed || nothingToDo || breaks || stuck || applying}
              onClick={apply}
            >
              {applying
                ? "Applying…"
                : several && !nothingToDo
                  ? `Apply to ${plural(run.filter((f) => f.plan?.changes.length).length, "file")}`
                  : editable
                    ? "Apply"
                    : "Apply to a copy"}
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
          {step === "review" && run && !allConfirmed && !nothingToDo && confirms > 0 && (
            <span className="rf-tab-hint">Tick every check under "Before you load it" to apply.</span>
          )}
        </div>
      )}
      <div className="modal-body ca-wizard-body">{body}</div>
    </Modal>
  );
}

import React from "react";
import { Icon } from "./Icon.jsx";

/**
 * The review step's parts, shared by the CA wizard and the generic action
 * modal: one row per planned change (backend actions/doc.py change
 * records), the problems a refused plan lists, and the "before you load
 * it" checklist.
 */

export const OP_LABELS = {
  set: "Set",
  unset: "Remove",
  create: "Add",
  delete: "Delete",
  "add-row": "Add row",
  "remove-row": "Remove row",
  renumber: "Renumber",
};

export const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

const last = (dn) => (dn ? dn.split("/").pop() : "");
// "MRBTS-1/LNBTS-478/LNCEL-0/CAREL-1" under "MRBTS-1/LNBTS-478" -> "LNCEL-0/CAREL-1"
export const underRoot = (dn, rootId) => (rootId && dn.startsWith(rootId + "/") ? dn.slice(rootId.length + 1) : last(dn));

export function BasisTag({ change, donorName }) {
  if (change.basis === "official") {
    const r = change.rule;
    return (
      <span className="badge badge-official" title="Nokia's official parameter dictionary (LTE18 / SBTS18A).">
        Nokia rule{r ? ` · ${r.param}${r.number ? ` ${r.number}` : ""}` : ""}
      </span>
    );
  }
  if (change.basis === "files")
    return (
      <span className="badge badge-unverified" title="A pattern from the working files in your corpus.">
        Seen in your files
      </span>
    );
  if (change.basis === "donor")
    return (
      <span className="badge badge-mid" title={donorName}>
        From the donor
      </span>
    );
  return <span className="badge badge-quiet">Your choice</span>;
}

export function Value({ v }) {
  return v == null ? <span className="ca-unset">not set</span> : <span className="cw-value mono">{v}</span>;
}

function Params({ params, label }) {
  const keys = Object.keys(params || {});
  if (!keys.length) return null;
  return (
    <details className="cw-details">
      <summary>{label || plural(keys.length, "parameter")}</summary>
      <dl className="cw-params mono">
        {keys.map((k) => (
          <React.Fragment key={k}>
            <dt>{k}</dt>
            <dd>{params[k]}</dd>
          </React.Fragment>
        ))}
      </dl>
    </details>
  );
}

export function ChangeRow({ c, rootId, donorName }) {
  const restart = c.modification && c.modification !== "On-line" ? c.modification : null;
  return (
    <li className="cw-change">
      <span className={"tag cw-op is-" + c.op}>{OP_LABELS[c.op] || c.op}</span>
      <div className="cw-change-main">
        <div className="cw-change-head">
          <span className="mono cw-target">
            {underRoot(c.dn, rootId)}
            {c.param ? <span className="cw-param"> · {c.param}</span> : null}
          </span>
          {(c.op === "set" || c.op === "unset") && (
            <span className="cw-delta">
              <Value v={c.old} />
              <Icon name="chevron-right" size={12} />
              <Value v={c.new} />
            </span>
          )}
          {c.op === "delete" && c.count > 1 && (
            <span className="cw-delta">and {plural(c.count - 1, "object")} under it</span>
          )}
          {c.op === "renumber" && (
            <span className="cw-delta">
              <Value v={last(c.old)} />
              <Icon name="chevron-right" size={12} />
              <Value v={last(c.new)} />
              {c.count > 1 && <span>with {plural(c.count - 1, "object")} under it</span>}
            </span>
          )}
          {restart && <span className="tag cw-restart">{restart}</span>}
          <BasisTag change={c} donorName={donorName} />
        </div>
        <p className="cw-reason">
          {c.reason}
          {c.clonedFrom && (
            <>
              {" "}
              Copied from <span className="mono">{underRoot(c.clonedFrom, rootId)}</span>.
            </>
          )}
        </p>
        {c.op === "create" && <Params params={c.params} />}
        {(c.op === "add-row" || c.op === "remove-row") && <Params params={c.row} label="Row" />}
      </div>
    </li>
  );
}

/** A refused plan: `error` is {message, problems} from api.js's errorFrom. */
export function PlanProblems({ error, lead = "This can't be planned:" }) {
  return (
    <div className="notice is-error">
      <Icon name="alert" />
      <div className="notice-text">
        {error.problems ? (
          <>
            {lead}
            <ul className="cw-problems">
              {error.problems.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </>
        ) : (
          error.message
        )}
      </div>
    </div>
  );
}

/** What the XML can't show; every box must be ticked to apply. */
export function ConfirmList({ items, confirmed, onToggle }) {
  return (
    <ul className="cw-confirm">
      {items.map((text, i) => (
        <li key={i}>
          <label>
            <input type="checkbox" checked={confirmed.has(i)} onChange={() => onToggle(i)} />
            <span>{text}</span>
          </label>
        </li>
      ))}
    </ul>
  );
}

export function toggleIn(set, i) {
  const next = new Set(set);
  if (next.has(i)) next.delete(i);
  else next.add(i);
  return next;
}

const STEP_OPS = { create: "Create", modify: "Change", delete: "Delete" };

function StepName({ name, param }) {
  return name && name.toLowerCase() !== param.toLowerCase() ? <span className="ms-name">{name}</span> : null;
}

const rowText = (row) =>
  Object.entries(row || {})
    .map(([k, v]) => `${k} ${v}`)
    .join(", ") || "(empty)";

/**
 * The plan as steps to make by hand (backend actions/steps.py): one per
 * object, parents first, with each parameter's full name, for entering the
 * change in the Nokia WebUI instead of loading the file.
 */
export function ManualSteps({ steps }) {
  return (
    <ol className="ms-steps">
      {steps.map((s) => (
        <li key={s.key || s.dn} className="ms-step">
          <div className="ms-head">
            <span className={"tag cw-op is-" + (s.kind === "modify" ? "set" : s.kind)}>{STEP_OPS[s.kind]}</span>
            <span className="mono cw-target">{s.kind === "create" ? s.label : s.dn}</span>
            {s.kind === "create" && (
              <span className="ms-where">
                under {s.parent}
                {s.copyOf && `, a copy of ${last(s.copyOf)}`}
                {s.copyOf && s.count > 1 && ` with the ${plural(s.count - 1, "object")} under it`}
              </span>
            )}
            {s.kind === "delete" && s.count > 1 && (
              <span className="ms-where">and {plural(s.count - 1, "object")} under it</span>
            )}
          </div>
          {(s.params.length > 0 || s.lists.length > 0 || s.items.length > 0) && (
            <dl className="ms-params">
              {s.params.map((p) => (
                <React.Fragment key={p.param}>
                  <dt className="mono">{p.param}</dt>
                  <dd>
                    <Value v={p.value} />
                    <StepName name={p.name} param={p.param} />
                  </dd>
                </React.Fragment>
              ))}
              {s.lists.map((l) =>
                l.rows ? (
                  l.rows.map((r, i) => (
                    <React.Fragment key={`${l.name}-${i}`}>
                      <dt className="mono">
                        {l.name} row {i + 1}
                      </dt>
                      <dd className="mono cw-value">{rowText(r)}</dd>
                    </React.Fragment>
                  ))
                ) : (
                  <React.Fragment key={l.name}>
                    <dt className="mono">{l.name}</dt>
                    <dd className="mono cw-value">{l.values.join(", ")}</dd>
                  </React.Fragment>
                ),
              )}
              {s.items.map((it, i) => (
                <React.Fragment key={`${it.param}-${i}`}>
                  <dt className="mono">{it.param}</dt>
                  <dd>
                    {it.op === "set" || it.op === "unset" ? (
                      <span className="cw-delta">
                        <Value v={it.old} />
                        <Icon name="chevron-right" size={12} />
                        <Value v={it.new} />
                      </span>
                    ) : (
                      <span>
                        {it.op === "add-row" ? "Add a row: " : "Remove the row: "}
                        <span className="mono cw-value">{rowText(it.row)}</span>
                      </span>
                    )}
                    <StepName name={it.name} param={it.param} />
                  </dd>
                </React.Fragment>
              ))}
            </dl>
          )}
          {s.reasons.length > 0 && (
            <details className="cw-details">
              <summary>Why</summary>
              {s.reasons.map((r, i) => (
                <p key={i} className="cw-reason">
                  {r}
                </p>
              ))}
            </details>
          )}
        </li>
      ))}
    </ol>
  );
}

/** Copy and download buttons for the steps as text. */
export function StepsTools({ text, filename }) {
  const [copied, setCopied] = React.useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Not a secure context (plain http on the LAN): the old way still works.
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([text + "\n"], { type: "text/plain" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: filename });
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <span className="ms-tools">
      <button type="button" className="btn btn-quiet" onClick={copy}>
        <Icon name={copied ? "check" : "copy"} />
        {copied ? "Copied" : "Copy steps"}
      </button>
      <button type="button" className="btn btn-quiet" onClick={download}>
        <Icon name="download" />
        Download .txt
      </button>
    </span>
  );
}

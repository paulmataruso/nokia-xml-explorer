import React from "react";

/**
 * Shared parameter-form building blocks used by both AddObjectModal (create
 * a new object) and AddParamModal (add a parameter to an existing one) --
 * both work off the same class_catalog.json parameter metadata.
 */

export function sortParamNames(paramsDict) {
  return Object.entries(paramsDict).sort((a, b) => {
    // trulyRequired = Mandatory AND no system default -- Nokia's own field
    // description says only these actually must be supplied; a merely
    // "Mandatory" parameter with a default is fine left unset. These always
    // come first so they're never accidentally missed.
    const aTruly = a[1].trulyRequired ? 1 : 0;
    const bTruly = b[1].trulyRequired ? 1 : 0;
    if (aTruly !== bTruly) return bTruly - aTruly;
    const aReq = a[1].requiredOnCreation === "Mandatory" ? 1 : 0;
    const bReq = b[1].requiredOnCreation === "Mandatory" ? 1 : 0;
    if (aReq !== bReq) return bReq - aReq;
    // Prefer parameters actually seen in your own files as safer defaults;
    // official-only ones (valid per Nokia's dictionary but never exercised
    // by a sample file) are still fully usable, just further down the list.
    const aObs = a[1].observed ? 1 : 0;
    const bObs = b[1].observed ? 1 : 0;
    if (aObs !== bObs) return bObs - aObs;
    return (b[1].occurrences || 0) - (a[1].occurrences || 0);
  });
}

export function FieldLabel({ name, observed, trulyRequired }) {
  return (
    <span className="field-label mono">
      {trulyRequired && (
        <span className="required-marker" title="Mandatory with no system default -- must be supplied for a valid object">
          *{" "}
        </span>
      )}
      {name}
      {observed === false && (
        <span className="official-only-badge" title="Valid per Nokia's official dictionary, but not seen in any of your sample files">
          {" "}
          ⚑
        </span>
      )}
    </span>
  );
}

/** Just the input widget (checkbox/select/text) for a parameter, with no
 * label -- used for compact contexts like a table cell. fieldForParam wraps
 * this with a FieldLabel for the full form-row layout. */
export function fieldInputForParam(meta, value, onChange) {
  if (meta.dataType === "boolean") {
    const opts = meta.exampleValues && meta.exampleValues.length >= 2 ? meta.exampleValues : ["true", "false"];
    const checked = value === opts[0];
    return (
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked ? opts[0] : opts[1])} />
    );
  }

  if (meta.dataType === "enum" && meta.exampleValues && meta.exampleValues.length > 0) {
    return (
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        <option value="">(unset)</option>
        {meta.exampleValues.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </select>
    );
  }

  return (
    <input
      type="text"
      value={value ?? ""}
      placeholder={meta.officialRange || meta.exampleValues?.[0] || ""}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

export function fieldForParam(name, meta, value, onChange) {
  const help = [meta.description, meta.officialRange && `Range: ${meta.officialRange}`, meta.unit && `Unit: ${meta.unit}`]
    .filter(Boolean)
    .join("\n");

  return (
    <label className="field-row" title={help}>
      <FieldLabel name={name} observed={meta.observed} trulyRequired={meta.trulyRequired} />
      {fieldInputForParam(meta, value, onChange)}
    </label>
  );
}

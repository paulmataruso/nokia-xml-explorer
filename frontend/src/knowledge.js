/**
 * Combines a tree node with the loaded knowledge base (classes.json,
 * parameters.json, structural glossary) to produce the content shown in the
 * explanation panel. Pure client-side lookup -- fast, no network round trip
 * for the common case where the knowledge base already has an entry.
 */
export function explainNode(node, kb) {
  const { classesKB, paramsKB, structural } = kb;

  switch (node.kind) {
    case "mo":
    case "mo-placeholder": {
      const cls = classesKB[node.class] || null;
      const isPlaceholder = node.kind === "mo-placeholder";
      return {
        title: node.label,
        subtitle: node.fullClass || node.class,
        kindLabel: isPlaceholder ? "Managed object (implied by path)" : "Managed object",
        description:
          (isPlaceholder
            ? "This object is implied by another object's distName path but is not itself " +
              "explicitly defined (with its own <managedObject> element) in this particular file. "
            : "") +
          (cls?.description ||
            `No curated description is available for managed object class "${node.class}". ` +
              "It fell outside the researched sample set. Based on Nokia RAN naming " +
              "conventions, this is a managed object class in the SBTS/AirScale or Flexi Zone " +
              "data model."),
        confidence: cls?.confidence || "heuristic",
        category: cls?.category,
        officialFullName: cls?.officialFullName,
        officialHierarchy: cls?.officialHierarchy,
        attributes: [
          node.distName && {
            key: "distName",
            value: node.distName,
            help: structural.attributes.distName?.description,
          },
          node.fullClass && {
            key: "class",
            value: node.fullClass,
            help: structural.attributes.class?.description,
          },
          node.operation && {
            key: "operation",
            value: node.operation,
            help: structural.attributes.operation?.description,
          },
          node.version && {
            key: "version",
            value: node.version,
            help: structural.attributes.version?.description,
          },
        ].filter(Boolean),
      };
    }

    case "param": {
      const entry = paramsKB[node.label] || null;
      return {
        title: node.label,
        subtitle: node.class ? `Parameter on ${node.class}` : "Parameter",
        kindLabel: "Parameter",
        value: node.value,
        description: entry?.description || null,
        confidence: entry?.confidence || null,
        dataType: entry?.dataType,
        unit: entry?.unit,
        notes: entry?.notes,
        needsFallback: !entry,
        // Present only when sourced from the official Nokia parameter
        // dictionary (see scripts/merge_official_reference.py) -- undefined
        // for curated/heuristic entries, so the panel just skips these rows.
        fullName: entry?.fullName,
        range: entry?.range,
        defaultValue: entry?.defaultValue,
        modification: entry?.modification,
        requiredOnCreation: entry?.requiredOnCreation,
        relatedFeatures: entry?.relatedFeatures,
        threeGppName: entry?.threeGppName,
        threeGppRef: entry?.threeGppRef,
        officialMoClass: entry?.moClass,
      };
    }

    case "list": {
      const entry = paramsKB[node.label] || null;
      const rowCount = node.rowCount ?? (node.children ? node.children.length : 0);
      return {
        title: node.label,
        subtitle: `Table (list) parameter — ${rowCount} row${rowCount === 1 ? "" : "s"}`,
        kindLabel: "Table parameter",
        description:
          (entry?.description ? entry.description + " " : "") +
          structural.elements.list.description,
        confidence: entry?.confidence || "high",
      };
    }

    case "item":
      return {
        title: node.label,
        subtitle: "Row of a table parameter",
        kindLabel: "Table row",
        description: structural.elements.item.description,
        confidence: "high",
      };

    case "fileinfo":
      return {
        title: "File Info",
        subtitle: "raml / cmData / header",
        kindLabel: "File metadata",
        description: `${structural.elements.raml.description} ${structural.elements.cmData.description}`,
        confidence: "high",
        attributes: Object.entries(node.attrs || {}).map(([k, v]) => {
          const shortKey = k.split(".").pop();
          return { key: k, value: v, help: structural.attributes[shortKey]?.description };
        }),
      };

    case "log":
      return {
        title: node.label,
        subtitle: "Audit log entry",
        kindLabel: "Log entry",
        description: structural.elements.log.description,
        confidence: "high",
        attributes: Object.entries(node.attrs || {}).map(([k, v]) => ({
          key: k,
          value: v,
          help: structural.attributes[k]?.description,
        })),
      };

    default:
      return {
        title: node.label,
        kindLabel: node.kind,
        description: "No information available for this node type.",
      };
  }
}

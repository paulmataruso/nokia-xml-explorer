const API_BASE = "/api";

async function getJSON(path) {
  // no-store: several GET endpoints here (notably /sitemgmt/tree) are
  // re-fetched immediately after a write to show its result -- without
  // this, a browser's default HTTP cache heuristics can serve a stale
  // response for the identical URL instead of hitting the server again.
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

export function listFiles() {
  return getJSON("/files");
}

export function getFileTree(filename) {
  return getJSON(`/files/${encodeURIComponent(filename)}/tree`);
}

export function getFileRawTree(filename) {
  return getJSON(`/files/${encodeURIComponent(filename)}/raw`);
}

export function getClassesKB() {
  return getJSON("/knowledge/classes");
}

export function getParamsKB() {
  return getJSON("/knowledge/parameters");
}

export function getStructuralKB() {
  return getJSON("/knowledge/structural");
}

export function explainParamFallback(name, moClass, value) {
  const q = new URLSearchParams({ name });
  if (moClass) q.set("moClass", moClass);
  if (value != null) q.set("value", value);
  return getJSON(`/explain/param?${q.toString()}`);
}

export function explainClassFallback(name) {
  const q = new URLSearchParams({ name });
  return getJSON(`/explain/class?${q.toString()}`);
}

export async function uploadFiles(fileList) {
  const form = new FormData();
  for (const file of fileList) form.append("files", file);
  const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

export async function deleteFile(filename) {
  const res = await fetch(`${API_BASE}/files/${encodeURIComponent(filename)}`, { method: "DELETE" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

async function jsonRequest(path, method, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: body != null ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let detail = text;
    try {
      detail = JSON.parse(text).detail || text;
    } catch {
      // not JSON, use raw text
    }
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export function updateParam(filename, nodeId, value) {
  return jsonRequest(`/files/${encodeURIComponent(filename)}/param`, "PUT", { nodeId, value });
}

export function duplicateToUploads(filename) {
  return jsonRequest(`/files/${encodeURIComponent(filename)}/duplicate-to-uploads`, "POST");
}

export function listSnapshots(filename) {
  return getJSON(`/files/${encodeURIComponent(filename)}/snapshots`);
}

export function restoreSnapshot(filename, snapshotId) {
  return jsonRequest(
    `/files/${encodeURIComponent(filename)}/snapshots/${encodeURIComponent(snapshotId)}/restore`,
    "POST"
  );
}

export function createNewFile(filename) {
  return jsonRequest("/files/new", "POST", { filename });
}

export function getCatalogClasses() {
  return getJSON("/catalog/classes");
}

export function getCatalogClassDetail(className) {
  return getJSON(`/catalog/classes/${encodeURIComponent(className)}`);
}

export function addObject(filename, { parentDistName, className, instanceId, params }) {
  return jsonRequest(`/files/${encodeURIComponent(filename)}/objects`, "POST", {
    parentDistName: parentDistName || null,
    className,
    instanceId: instanceId || null,
    params,
  });
}

export function getMissingRequired(filename) {
  return getJSON(`/files/${encodeURIComponent(filename)}/missing-required`);
}

export function setObjectParam(filename, distName, paramName, value) {
  return jsonRequest(`/files/${encodeURIComponent(filename)}/objects/param`, "PUT", {
    distName,
    paramName,
    value,
  });
}

export function deleteObject(filename, distName) {
  return jsonRequest(`/files/${encodeURIComponent(filename)}/objects`, "DELETE", { distName });
}

export function renameObject(filename, distName, newInstanceId) {
  return jsonRequest(`/files/${encodeURIComponent(filename)}/objects/rename`, "PUT", {
    distName,
    newInstanceId,
  });
}

export function deleteObjectParam(filename, distName, paramName) {
  return jsonRequest(`/files/${encodeURIComponent(filename)}/objects/param`, "DELETE", { distName, paramName });
}

export function getSiteManagementTree() {
  return getJSON("/sitemgmt/tree");
}

export function createFolder(name, parentId) {
  return jsonRequest("/sitemgmt/folders", "POST", { name, parentId: parentId ?? null });
}

export function updateFolder(folderId, patch) {
  return jsonRequest(`/sitemgmt/folders/${encodeURIComponent(folderId)}`, "PUT", patch);
}

export function deleteFolder(folderId) {
  return jsonRequest(`/sitemgmt/folders/${encodeURIComponent(folderId)}`, "DELETE");
}

export function updateFileMeta(filename, patch) {
  return jsonRequest(`/sitemgmt/files/${encodeURIComponent(filename)}`, "PUT", patch);
}

export function searchSiteManagement({ q, tag, site, family, sortBy, sortDir } = {}) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (tag) params.set("tag", tag);
  if (site) params.set("site", site);
  if (family) params.set("family", family);
  if (sortBy) params.set("sortBy", sortBy);
  if (sortDir) params.set("sortDir", sortDir);
  const qs = params.toString();
  return getJSON(`/sitemgmt/search${qs ? `?${qs}` : ""}`);
}

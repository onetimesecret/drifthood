// ── API wrapper functions ──

function assertOk(resp) {
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
  }
}

export async function apiConfig() {
  const resp = await fetch('/api/config');
  assertOk(resp);
  return resp.json();
}

export async function apiTestHost(host, auth) {
  const resp = await fetch('/api/test-host', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ host, auth }),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiCompare(params) {
  // params: { label, method, path, body, content_type, group, host_a, host_b, auth_a, auth_b, ignore_paths }
  const resp = await fetch('/api/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiBatch(params) {
  const resp = await fetch('/api/batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiSave(state, documentId, sessionType, sessionNumber) {
  const resp = await fetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state, documentId, sessionType, sessionNumber }),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiListDocuments() {
  const resp = await fetch('/api/documents');
  assertOk(resp);
  return resp.json();
}

export async function apiGetDocument(docId) {
  const resp = await fetch(`/api/documents/${docId}`);
  assertOk(resp);
  return resp.json();
}

export async function apiUpdateDocumentTitle(docId, title) {
  const resp = await fetch(`/api/documents/${docId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiGetSessions(docId) {
  const resp = await fetch(`/api/documents/${docId}/sessions`);
  assertOk(resp);
  return resp.json();
}

export async function apiGetSession(docId, sessionNumber) {
  const resp = await fetch(`/api/documents/${docId}/sessions/${sessionNumber}`);
  assertOk(resp);
  return resp.json();
}

export async function apiDeleteSession(docId, sessionNumber) {
  const resp = await fetch(`/api/documents/${docId}/sessions/${sessionNumber}`, { method: 'DELETE' });
  assertOk(resp);
  return resp.json();
}

export async function apiParseOpenapi(formData) {
  const resp = await fetch('/api/parse-openapi', { method: 'POST', body: formData });
  assertOk(resp);
  return resp.json();
}

export async function apiDiffSchemas(formData) {
  const resp = await fetch('/api/diff-schemas', { method: 'POST', body: formData });
  assertOk(resp);
  return resp.json();
}

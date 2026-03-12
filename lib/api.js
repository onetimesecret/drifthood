// ── API wrapper functions ──

export async function apiConfig() {
  const resp = await fetch('/api/config');
  return resp.json();
}

export async function apiTestHost(host, auth) {
  const resp = await fetch('/api/test-host', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ host, auth }),
  });
  return resp.json();
}

export async function apiCompare(params) {
  // params: { label, method, path, body, content_type, group, host_a, host_b, auth_a, auth_b, ignore_paths }
  const resp = await fetch('/api/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  return resp.json();
}

export async function apiBatch(params) {
  const resp = await fetch('/api/batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  return resp.json();
}

export async function apiSave(state, documentId, sessionType, sessionNumber) {
  const resp = await fetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state, documentId, sessionType, sessionNumber }),
  });
  return resp.json();
}

export async function apiListDocuments() {
  const resp = await fetch('/api/documents');
  return resp.json();
}

export async function apiGetDocument(docId) {
  const resp = await fetch(`/api/documents/${docId}`);
  return resp.json();
}

export async function apiUpdateDocumentTitle(docId, title) {
  const resp = await fetch(`/api/documents/${docId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  return resp.json();
}

export async function apiGetSessions(docId) {
  const resp = await fetch(`/api/documents/${docId}/sessions`);
  return resp.json();
}

export async function apiGetSession(docId, sessionNumber) {
  const resp = await fetch(`/api/documents/${docId}/sessions/${sessionNumber}`);
  return resp.json();
}

export async function apiDeleteSession(docId, sessionNumber) {
  const resp = await fetch(`/api/documents/${docId}/sessions/${sessionNumber}`, { method: 'DELETE' });
  return resp.json();
}

export async function apiParseOpenapi(formData) {
  const resp = await fetch('/api/parse-openapi', { method: 'POST', body: formData });
  return resp.json();
}

export async function apiDiffSchemas(formData) {
  const resp = await fetch('/api/diff-schemas', { method: 'POST', body: formData });
  return resp.json();
}

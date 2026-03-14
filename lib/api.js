// ── API wrapper functions ──
//
// All entity references use UUIDv7 extids. Integer primary keys
// and raw tokens never cross this boundary.

import { getAuthKey } from '../src/stores/auth.svelte.js';

function assertOk(resp) {
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
  }
}

function apiFetch(url, options = {}) {
  const authKey = getAuthKey();
  if (authKey) {
    options.headers = {
      ...options.headers,
      'Authorization': `Bearer ${authKey}`,
    };
  }
  return fetch(url, options);
}

export async function apiConfig() {
  const resp = await apiFetch('/api/config');
  assertOk(resp);
  return resp.json();
}

export async function apiTestHost(host, auth) {
  const resp = await apiFetch('/api/test-host', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ host, auth }),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiCompare(params) {
  // params: { label, method, path, body, content_type, group, host_a, host_b, auth_a, auth_b, ignore_paths }
  const resp = await apiFetch('/api/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiBatch(params) {
  const resp = await apiFetch('/api/batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiSave(state, documentExtid, testrunType, testrunExtid, blobFields = null) {
  const payload = { state, documentExtid, testrunType, testrunExtid };
  if (blobFields) {
    payload.blobHash = blobFields.blobHash;
    payload.encryptedBlob = blobFields.encryptedBlob;
    payload.blobIv = blobFields.blobIv;
    payload.endpointCount = blobFields.endpointCount;
    payload.driftCount = blobFields.driftCount;
    payload.okCount = blobFields.okCount;
  }
  const resp = await apiFetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiListDocuments() {
  const resp = await apiFetch('/api/documents');
  assertOk(resp);
  return resp.json();
}

export async function apiGetDocument(docExtid) {
  const resp = await apiFetch(`/api/documents/${docExtid}`);
  assertOk(resp);
  return resp.json();
}

export async function apiUpdateDocumentTitle(docExtid, title) {
  const resp = await apiFetch(`/api/documents/${docExtid}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiGetTestruns(docExtid) {
  const resp = await apiFetch(`/api/documents/${docExtid}/testruns`);
  assertOk(resp);
  return resp.json();
}

export async function apiGetTestrun(docExtid, testrunExtid) {
  const resp = await apiFetch(`/api/documents/${docExtid}/testruns/${testrunExtid}`);
  assertOk(resp);
  return resp.json();
}

export async function apiDeleteTestrun(docExtid, testrunExtid) {
  const resp = await apiFetch(`/api/documents/${docExtid}/testruns/${testrunExtid}`, { method: 'DELETE' });
  assertOk(resp);
  return resp.json();
}

export async function apiParseOpenapi(formData) {
  const resp = await apiFetch('/api/parse-openapi', { method: 'POST', body: formData });
  assertOk(resp);
  return resp.json();
}

export async function apiDiffSchemas(formData) {
  const resp = await apiFetch('/api/diff-schemas', { method: 'POST', body: formData });
  assertOk(resp);
  return resp.json();
}

export async function apiGenerateToken() {
  const resp = await apiFetch('/api/auth/token', { method: 'POST' });
  assertOk(resp);
  return resp.json();
}

export async function apiValidateToken() {
  const resp = await apiFetch('/api/auth/validate');
  assertOk(resp);
  return resp.json();
}

// ── Environments ──

export async function apiListEnvironments() {
  const resp = await apiFetch('/api/environments');
  assertOk(resp);
  return resp.json();
}

export async function apiCreateEnvironment(data) {
  const resp = await apiFetch('/api/environments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiUpdateEnvironment(extid, data) {
  const resp = await apiFetch(`/api/environments/${extid}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiDeleteEnvironment(extid) {
  const resp = await apiFetch(`/api/environments/${extid}`, { method: 'DELETE' });
  assertOk(resp);
  return resp.json();
}

// ── Endpoints ──

export async function apiListEndpoints() {
  const resp = await apiFetch('/api/endpoints');
  assertOk(resp);
  return resp.json();
}

export async function apiCreateEndpoint(data) {
  const resp = await apiFetch('/api/endpoints', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiUpdateEndpoint(extid, data) {
  const resp = await apiFetch(`/api/endpoints/${extid}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  assertOk(resp);
  return resp.json();
}

export async function apiDeleteEndpoint(extid) {
  const resp = await apiFetch(`/api/endpoints/${extid}`, { method: 'DELETE' });
  assertOk(resp);
  return resp.json();
}

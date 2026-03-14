// ── API wrapper functions ──
//
// All entity references use UUIDv7 extids. Integer primary keys
// and raw tokens never cross this boundary.

import { getToken } from '../src/stores/auth.svelte.js';

function assertOk(resp) {
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
  }
}

function apiFetch(url, options = {}) {
  const token = getToken();
  if (token) {
    options.headers = {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
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

export async function apiSave(state, documentExtid, testrunType, testrunExtid) {
  const resp = await apiFetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state, documentExtid, testrunType, testrunExtid }),
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

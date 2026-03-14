// Svelte 5 runes — reactive state for endpoint list
// Server-synced with client-side encryption (Phase 4B)

import { encryptBlob, decryptBlob } from '../lib/crypto.js';
import { getEncKey } from './auth.svelte.js';
import { apiListEndpoints, apiCreateEndpoint, apiUpdateEndpoint, apiDeleteEndpoint } from '../../lib/api.js';

// Each endpoint object:
// { extid, _localId, method, label, path, body, contentType, group, fieldsMode,
//   cardFields: {fields, query_fields, path_fields} | null,
//   fieldValues: {} | null,
//   state: 'idle' | 'running' | 'done-ok' | 'done-drift',
//   result: null | compareResult }
//
// _localId: a client-side UUID assigned at creation. Used for all local lookups
// and keying so endpoints are uniquely addressable even before the server assigns
// an extid. Never sent to the server or persisted in snapshots.
export const endpoints = $state([]);

// Fields that get encrypted in the blob (sensitive endpoint config)
const EP_SENSITIVE_FIELDS = ['method', 'path', 'body', 'contentType', 'fieldsMode', 'cardFields', 'fieldValues'];

// Track in-flight saves to deduplicate concurrent saveEndpoint calls
const _savesInFlight = new Map();

async function encryptEpBlob(ep) {
  const encKey = getEncKey();
  if (!encKey) throw new Error('No encryption key available');
  const sensitive = {};
  for (const f of EP_SENSITIVE_FIELDS) {
    if (ep[f] !== undefined) sensitive[f] = ep[f];
  }
  const plaintext = JSON.stringify(sensitive);
  return encryptBlob(encKey, plaintext, ep.extid);
}

async function decryptEpBlob(serverEp) {
  const encKey = getEncKey();
  if (!encKey) throw new Error('No encryption key available');
  if (!serverEp.encrypted_blob || !serverEp.blob_iv) {
    return {
      extid: serverEp.extid,
      _localId: crypto.randomUUID(),
      label: serverEp.label,
      group: serverEp.group,
      method: 'GET', path: '', body: '', contentType: '',
      fieldsMode: 'off', cardFields: null, fieldValues: null,
      state: 'idle',
      result: null,
    };
  }
  const plaintext = await decryptBlob(encKey, serverEp.encrypted_blob, serverEp.blob_iv, serverEp.extid);
  const sensitive = JSON.parse(plaintext);
  return {
    extid: serverEp.extid,
    _localId: crypto.randomUUID(),
    label: serverEp.label,
    group: serverEp.group,
    ...sensitive,
    state: 'idle',   // ephemeral — not persisted
    result: null,     // ephemeral — not persisted
  };
}

/**
 * Load endpoints from server, decrypt each, populate the endpoints array.
 */
export async function loadEndpoints() {
  const encKey = getEncKey();
  if (!encKey) return;
  try {
    const serverEps = await apiListEndpoints();
    const decrypted = await Promise.all(serverEps.map(decryptEpBlob));
    endpoints.splice(0, endpoints.length, ...decrypted);
  } catch (err) {
    console.error('Failed to load endpoints:', err);
  }
}

/**
 * Add a new endpoint. Creates on server first (label/group only, no blob),
 * then encrypts with the server-assigned extid and PUTs the blob.
 */
export async function addEndpoint(opts = {}) {
  const {
    method = 'GET',
    label = '',
    path = '',
    body = '',
    contentType = 'query',
    group = '',
    fieldsMode = 'off',
    cardFields = null,
    fieldValues = null,
  } = opts;

  const ep = {
    extid: null,
    _localId: crypto.randomUUID(),
    method,
    label,
    path,
    body,
    contentType,
    group,
    fieldsMode,
    cardFields,
    fieldValues,
    state: 'idle',
    result: null,
  };

  // Add to local array immediately for UI responsiveness
  endpoints.push(ep);

  const encKey = getEncKey();
  if (!encKey) return;

  try {
    // POST with cleartext metadata only — no blob yet (need extid for AAD)
    const created = await apiCreateEndpoint({ label, group });
    ep.extid = created.extid;

    // Now encrypt sensitive fields using server-assigned extid as AAD
    const { ciphertext, iv, hash } = await encryptEpBlob(ep);
    await apiUpdateEndpoint(ep.extid, {
      label,
      group,
      encrypted_blob: ciphertext,
      blob_iv: iv,
      blob_hash: hash,
    });
  } catch (err) {
    console.error('Failed to create endpoint on server:', err);
  }
}

/**
 * Encrypt and save an endpoint's current state to the server.
 * Deduplicates concurrent calls for the same extid.
 */
export async function saveEndpoint(ep) {
  if (!ep.extid) return;
  const encKey = getEncKey();
  if (!encKey) return;

  // Deduplicate: if a save is already in flight for this extid, wait for it
  // then start a new one (the in-flight save may have stale data)
  if (_savesInFlight.has(ep.extid)) {
    try { await _savesInFlight.get(ep.extid); } catch { /* ignore */ }
  }

  const doSave = async () => {
    const { ciphertext, iv, hash } = await encryptEpBlob(ep);
    await apiUpdateEndpoint(ep.extid, {
      label: ep.label,
      group: ep.group,
      encrypted_blob: ciphertext,
      blob_iv: iv,
      blob_hash: hash,
    });
  };

  const promise = doSave();
  _savesInFlight.set(ep.extid, promise);
  try {
    await promise;
  } finally {
    // Only clear if this is still the latest promise for this extid
    if (_savesInFlight.get(ep.extid) === promise) {
      _savesInFlight.delete(ep.extid);
    }
  }
}

/**
 * Update an endpoint locally and persist to server.
 */
export function updateEndpoint(id, updates) {
  const ep = endpoints.find(e => e._localId === id || (id != null && e.extid === id));
  if (!ep) return;
  Object.assign(ep, updates);

  // Only persist to server if non-ephemeral fields changed
  const persistableKeys = ['method', 'label', 'path', 'body', 'contentType',
    'group', 'fieldsMode', 'cardFields', 'fieldValues'];
  const hasPersistable = Object.keys(updates).some(k => persistableKeys.includes(k));
  if (hasPersistable && ep.extid) {
    saveEndpoint(ep).catch(err => {
      console.error('Failed to save endpoint update:', err);
    });
  }
}

/**
 * Remove an endpoint locally and from the server.
 */
export async function removeEndpoint(id) {
  const idx = endpoints.findIndex(e => e._localId === id || (id != null && e.extid === id));
  if (idx === -1) return;
  const ep = endpoints[idx];
  endpoints.splice(idx, 1);

  if (ep.extid) {
    try {
      await apiDeleteEndpoint(ep.extid);
    } catch (err) {
      console.error('Failed to delete endpoint on server:', err);
    }
  }
}

/**
 * Find an endpoint by extid.
 */
export function getEndpoint(id) {
  return endpoints.find(e => e._localId === id || (id != null && e.extid === id));
}

/**
 * Clear all endpoints locally and from the server.
 */
export async function clearEndpoints() {
  const encKey = getEncKey();
  const toDelete = [...endpoints];
  endpoints.splice(0, endpoints.length);

  if (encKey) {
    // Delete each from server (fire and forget on individual failures)
    await Promise.allSettled(
      toDelete
        .filter(ep => ep.extid)
        .map(ep => apiDeleteEndpoint(ep.extid))
    );
  }
}

/**
 * Clear ephemeral results on all endpoints (local-only, not persisted).
 */
export function clearResults() {
  for (const ep of endpoints) {
    ep.state = 'idle';
    ep.result = null;
  }
}

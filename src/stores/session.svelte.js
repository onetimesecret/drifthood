// src/stores/session.svelte.js

import { apiConfig, apiListEnvironments, apiCreateEnvironment, apiUpdateEnvironment, apiDeleteEnvironment } from '../../lib/api.js';
import { encryptBlob, decryptBlob } from '../lib/crypto.js';
import { getEncKey } from './auth.svelte.js';

// Svelte 5 runes — reactive state for session config
//
// Environments are server-synced with client-side encryption.
// Each environment is { extid, name, baseUrl, auth, memo, metadata }.
// Sensitive fields (baseUrl, auth, memo, metadata) are encrypted before
// leaving the client; the server only sees name + opaque blob.
// selectedA/selectedB hold environment extids for the two comparison roles.
export const session = $state({
  title: '',
  memo: '',
  environments: [],    // array of environment objects
  selectedA: '',       // environment extid
  selectedB: '',       // environment extid
  ignorePaths: [],     // array of raw dot-notation strings (not DeepDiff format)
  specSource: null,    // breadcrumb source text
});

export function resetSession() {
  session.title = '';
  session.memo = '';
  session.environments = [];
  session.selectedA = '';
  session.selectedB = '';
  session.ignorePaths = [];
  session.specSource = null;
}

// ── Encryption helpers ──

const ENV_SENSITIVE_FIELDS = ['baseUrl', 'auth', 'memo', 'metadata'];

async function encryptEnvBlob(env) {
  const encKey = getEncKey();
  if (!encKey) return { encrypted_blob: null, blob_iv: null, blob_hash: null };
  const sensitive = {};
  for (const f of ENV_SENSITIVE_FIELDS) {
    if (env[f] !== undefined) sensitive[f] = env[f];
  }
  const plaintext = JSON.stringify(sensitive);
  const { ciphertext, iv, hash } = await encryptBlob(encKey, plaintext, env.extid);
  return { encrypted_blob: ciphertext, blob_iv: iv, blob_hash: hash };
}

async function decryptEnvBlob(serverEnv) {
  const encKey = getEncKey();
  if (!encKey || !serverEnv.encrypted_blob || !serverEnv.blob_iv) {
    // Return what we have — no sensitive fields available
    return {
      extid: serverEnv.extid,
      name: serverEnv.name || '',
      baseUrl: '',
      auth: '',
      memo: '',
      metadata: {},
      created_at: serverEnv.created_at,
      updated_at: serverEnv.updated_at,
    };
  }
  const plaintext = await decryptBlob(encKey, serverEnv.encrypted_blob, serverEnv.blob_iv, serverEnv.extid);
  const sensitive = JSON.parse(plaintext);
  return {
    extid: serverEnv.extid,
    name: serverEnv.name || '',
    ...sensitive,
    created_at: serverEnv.created_at,
    updated_at: serverEnv.updated_at,
  };
}

// ── Environment helpers (server-synced) ──

/**
 * Load all environments from the server, decrypt each blob, and populate
 * session.environments. Replaces the local array entirely.
 */
export async function loadEnvironments() {
  try {
    const serverEnvs = await apiListEnvironments();
    const decrypted = await Promise.all(serverEnvs.map(decryptEnvBlob));
    session.environments = decrypted;
  } catch (err) {
    console.error('Failed to load environments:', err);
  }
}

/**
 * Create a new environment: encrypt sensitive fields, POST to server,
 * add the server-assigned result to local state.
 * Returns the decrypted environment object with server-assigned extid.
 */
export async function createEnvironment(fields = {}) {
  // Build a temporary env object with a placeholder extid for encryption.
  // The server will assign the real extid, so we'll re-encrypt after creation.
  const env = {
    extid: 'pending',
    name: fields.name || '',
    baseUrl: fields.baseUrl || '',
    auth: fields.auth || '',
    memo: fields.memo || '',
    metadata: fields.metadata || {},
  };

  // Create on server first (without blob — we need the real extid for AAD)
  const serverEnv = await apiCreateEnvironment({ name: env.name });

  // Now encrypt with the real extid and update server
  env.extid = serverEnv.extid;
  const { encrypted_blob, blob_iv, blob_hash } = await encryptEnvBlob(env);
  if (encrypted_blob) {
    await apiUpdateEnvironment(serverEnv.extid, {
      encrypted_blob,
      blob_iv,
      blob_hash,
    });
  }

  // Build the local flat object
  const localEnv = {
    extid: serverEnv.extid,
    name: env.name,
    baseUrl: env.baseUrl,
    auth: env.auth,
    memo: env.memo,
    metadata: env.metadata,
    created_at: serverEnv.created_at,
    updated_at: serverEnv.updated_at,
  };
  const existingIdx = session.environments.findIndex(e => e.extid === localEnv.extid);
  if (existingIdx >= 0) {
    session.environments[existingIdx] = localEnv; // update in place (backend returned existing)
  } else {
    session.environments.push(localEnv);
  }
  return localEnv;
}

/**
 * Save an environment: encrypt sensitive fields, PUT to server.
 * Uses blob_hash for dedup — server skips the write if hash is unchanged.
 * The `extid` parameter identifies which environment to update.
 */
export async function saveEnvironment(extid, fields) {
  const env = session.environments.find(e => e.extid === extid);
  if (!env) return;

  // Merge fields into local state first
  for (const [k, v] of Object.entries(fields)) {
    env[k] = v;
  }

  // Encrypt and push to server
  const { encrypted_blob, blob_iv, blob_hash } = await encryptEnvBlob(env);
  const payload = { name: env.name };
  if (encrypted_blob) {
    payload.encrypted_blob = encrypted_blob;
    payload.blob_iv = blob_iv;
    payload.blob_hash = blob_hash;
  }
  try {
    await apiUpdateEnvironment(extid, payload);
  } catch (err) {
    console.error('Failed to save environment:', err);
  }
}

/**
 * Remove an environment: DELETE on server, then remove from local state.
 */
export async function removeEnvironment(extid) {
  try {
    await apiDeleteEnvironment(extid);
  } catch (err) {
    console.error('Failed to delete environment:', err);
  }
  const idx = session.environments.findIndex(e => e.extid === extid);
  if (idx !== -1) {
    session.environments.splice(idx, 1);
  }
  if (session.selectedA === extid) session.selectedA = '';
  if (session.selectedB === extid) session.selectedB = '';
}

export function getEnvironment(extid) {
  return session.environments.find(e => e.extid === extid) || null;
}

export function getEnvA() {
  return getEnvironment(session.selectedA);
}

export function getEnvB() {
  return getEnvironment(session.selectedB);
}

// Fetch default environments from server config (HOST_A/HOST_B) and seed them
// into the session via server-synced createEnvironment(). Called on fresh start
// and when creating a new document.
export async function seedDefaultEnvironments() {
  try {
    // Load existing environments from server first — local state is empty on
    // every page refresh, so we must check the server to avoid creating dupes.
    await loadEnvironments();

    if (session.environments.length > 0) {
      // Server already has environments; restore selections if possible
      if (!session.selectedA && session.environments.length >= 1) {
        session.selectedA = session.environments[0].extid;
      }
      if (!session.selectedB && session.environments.length >= 2) {
        session.selectedB = session.environments[1].extid;
      }
      return;
    }

    const cfg = await apiConfig();
    if (cfg.default_environments) {
      for (const envDef of cfg.default_environments) {
        await createEnvironment(envDef);
      }
      if (session.environments.length >= 2) {
        session.selectedA = session.environments[0].extid;
        session.selectedB = session.environments[1].extid;
      }
    }
  } catch { /* config fetch failed, continue without defaults */ }
}

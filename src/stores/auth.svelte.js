// src/stores/auth.svelte.js

//
// The raw token is the root secret, stored in browser storage.
// The extid is the public-facing session identifier (used in URLs, HKDF salt).
// Derived keys (authKey, encKey) live in memory only — never persisted.
//
// Key derivation:
//   HKDF(token, salt=extid, info="auth") → authKey  (sent in Bearer header)
//   HKDF(token, salt=extid, info="enc")  → encKey   (AES-GCM CryptoKey)
//
// On page reload, keys re-derive from the stored token + extid.

import { deriveKeys } from '../lib/crypto.js';

const TOKEN_KEY = 'dd_token';
const EXTID_KEY = 'dd_extid';

export const auth = $state({
  token: null,
  extid: null,
  rememberMe: false,
  authKey: null,   // derived, in-memory only
  encKey: null,    // derived, in-memory only
});

/** Initialize auth from browser storage. Call once on app startup.
 *  Async because key derivation uses SubtleCrypto. */
export async function initAuth() {
  const fromSession = sessionStorage.getItem(TOKEN_KEY);
  const fromLocal = localStorage.getItem(TOKEN_KEY);
  const extidSession = sessionStorage.getItem(EXTID_KEY);
  const extidLocal = localStorage.getItem(EXTID_KEY);
  if (fromSession) {
    auth.token = fromSession;
    auth.extid = extidSession;
  } else if (fromLocal) {
    auth.token = fromLocal;
    auth.extid = extidLocal;
    auth.rememberMe = true;
  }

  // Derive keys if we have both token and extid
  if (auth.token && auth.extid) {
    try {
      const { authKey, encKey } = await deriveKeys(auth.token, auth.extid);
      auth.authKey = authKey;
      auth.encKey = encKey;
    } catch (err) {
      console.error('Key derivation failed during init:', err);
      // Clear auth state — stored credentials are unusable
      auth.token = null;
      auth.extid = null;
      auth.authKey = null;
      auth.encKey = null;
    }
  }
}

/** Store a token and its extid, then derive auth/enc keys.
 *  sessionStorage always; localStorage if rememberMe. */
export async function setTokenWithKeys(token, extid, remember = false) {
  auth.token = token;
  auth.extid = extid;
  auth.rememberMe = remember;
  sessionStorage.setItem(TOKEN_KEY, token);
  if (extid) {
    sessionStorage.setItem(EXTID_KEY, extid);
  }
  if (remember) {
    localStorage.setItem(TOKEN_KEY, token);
    if (extid) {
      localStorage.setItem(EXTID_KEY, extid);
    }
  } else {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(EXTID_KEY);
  }

  // Derive keys from the raw token + extid
  if (token && extid) {
    const { authKey, encKey } = await deriveKeys(token, extid);
    auth.authKey = authKey;
    auth.encKey = encKey;
  } else {
    auth.authKey = null;
    auth.encKey = null;
  }
}

/** Update just the extid and re-derive keys.
 *  Used when the extid comes from a URL or server response after the token is already stored. */
export async function setExtid(extid) {
  auth.extid = extid;
  sessionStorage.setItem(EXTID_KEY, extid);
  if (auth.rememberMe) {
    localStorage.setItem(EXTID_KEY, extid);
  }

  // Re-derive keys with the new extid (it's the HKDF salt)
  if (auth.token && extid) {
    const { authKey, encKey } = await deriveKeys(auth.token, extid);
    auth.authKey = authKey;
    auth.encKey = encKey;
  }
}

/** Clear token, extid, and derived keys from all storage and memory. */
export function clearToken() {
  auth.token = null;
  auth.extid = null;
  auth.rememberMe = false;
  auth.authKey = null;
  auth.encKey = null;
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(EXTID_KEY);
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EXTID_KEY);
}

/** Get the current raw token (for display / re-entry, NOT for network use). */
export function getToken() {
  return auth.token;
}

/** Get the derived auth key (for Authorization: Bearer header). */
export function getAuthKey() {
  return auth.authKey;
}

/** Get the derived encryption key (AES-GCM CryptoKey for encrypt/decrypt). */
export function getEncKey() {
  return auth.encKey;
}

/** Get the current session extid (convenience). */
export function getExtid() {
  return auth.extid;
}

// Svelte 5 runes — reactive state for token-based session identity.
//
// The token is the auth credential (used in Authorization header).
// The extid is the public-facing session identifier (used in URLs).
// These are stored separately so the token never appears in the URL.

const TOKEN_KEY = 'dd_token';
const EXTID_KEY = 'dd_extid';

export const auth = $state({
  token: null,
  extid: null,
  rememberMe: false,
});

/** Initialize auth from browser storage. Call once on app startup. */
export function initAuth() {
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
}

/** Store a token and its extid. sessionStorage always; localStorage if rememberMe. */
export function setToken(token, extid, remember = false) {
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
}

/** Update just the extid (e.g. after validating an existing token). */
export function setExtid(extid) {
  auth.extid = extid;
  sessionStorage.setItem(EXTID_KEY, extid);
  if (auth.rememberMe) {
    localStorage.setItem(EXTID_KEY, extid);
  }
}

/** Clear token and extid from all storage. */
export function clearToken() {
  auth.token = null;
  auth.extid = null;
  auth.rememberMe = false;
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(EXTID_KEY);
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EXTID_KEY);
}

/** Get the current token (convenience). */
export function getToken() {
  return auth.token;
}

/** Get the current session extid (convenience). */
export function getExtid() {
  return auth.extid;
}

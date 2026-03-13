// Svelte 5 runes — reactive state for token-based session identity
const STORAGE_KEY = 'dd_token';

export const auth = $state({
  token: null,
  rememberMe: false,
});

/** Initialize auth from browser storage. Call once on app startup. */
export function initAuth() {
  const fromSession = sessionStorage.getItem(STORAGE_KEY);
  const fromLocal = localStorage.getItem(STORAGE_KEY);
  if (fromSession) {
    auth.token = fromSession;
  } else if (fromLocal) {
    auth.token = fromLocal;
    auth.rememberMe = true;
  }
}

/** Store a token. sessionStorage always; localStorage if rememberMe. */
export function setToken(token, remember = false) {
  auth.token = token;
  auth.rememberMe = remember;
  sessionStorage.setItem(STORAGE_KEY, token);
  if (remember) {
    localStorage.setItem(STORAGE_KEY, token);
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

/** Clear token from all storage. */
export function clearToken() {
  auth.token = null;
  auth.rememberMe = false;
  sessionStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(STORAGE_KEY);
}

/** Get the current token (convenience). */
export function getToken() {
  return auth.token;
}

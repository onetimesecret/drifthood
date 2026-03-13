// Svelte 5 runes — reactive state for session config
//
// Environments replace the old flat hostA/hostB/authA/authB/memoA/memoB fields.
// Each environment is { id, name, baseUrl, auth, memo, metadata }.
// selectedA/selectedB hold environment IDs for the two comparison roles.
export const session = $state({
  title: '',
  memo: '',
  environments: [],    // array of environment objects
  selectedA: '',       // environment ID
  selectedB: '',       // environment ID
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

// ── Environment helpers ──

export function createEnvironment(fields = {}) {
  return {
    id: crypto.randomUUID(),
    name: fields.name || '',
    baseUrl: fields.baseUrl || '',
    auth: fields.auth || '',
    memo: fields.memo || '',
    metadata: fields.metadata || {},
  };
}

export function addEnvironment(fields = {}) {
  const env = createEnvironment(fields);
  session.environments.push(env);
  return env;
}

export function updateEnvironment(id, fields) {
  const env = session.environments.find(e => e.id === id);
  if (!env) return;
  for (const [k, v] of Object.entries(fields)) {
    env[k] = v;
  }
}

export function removeEnvironment(id) {
  const idx = session.environments.findIndex(e => e.id === id);
  if (idx === -1) return;
  session.environments.splice(idx, 1);
  if (session.selectedA === id) session.selectedA = '';
  if (session.selectedB === id) session.selectedB = '';
}

export function getEnvironment(id) {
  return session.environments.find(e => e.id === id) || null;
}

export function getEnvA() {
  return getEnvironment(session.selectedA);
}

export function getEnvB() {
  return getEnvironment(session.selectedB);
}

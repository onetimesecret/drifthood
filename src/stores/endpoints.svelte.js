// Svelte 5 runes — reactive state for endpoint list
let nextId = $state(0);

// Each endpoint object:
// { id, method, label, path, body, contentType, group, fieldsMode,
//   cardFields: {fields, query_fields, path_fields} | null,
//   fieldValues: {} | null,
//   state: 'idle' | 'running' | 'done-ok' | 'done-drift',
//   result: null | compareResult }
export const endpoints = $state([]);

export function addEndpoint(opts = {}) {
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

  const id = nextId++;
  const ep = {
    id,
    method,
    label,
    path,
    body,
    contentType,
    group,
    fieldsMode,
    cardFields,   // {fields: [], query_fields: [], path_fields: []} or null
    fieldValues,  // {fieldPath: value} or null
    state: 'idle',
    result: null,
  };
  endpoints.push(ep);
  return id;
}

export function removeEndpoint(id) {
  const idx = endpoints.findIndex(ep => ep.id === id);
  if (idx !== -1) endpoints.splice(idx, 1);
}

export function updateEndpoint(id, updates) {
  const ep = endpoints.find(ep => ep.id === id);
  if (ep) Object.assign(ep, updates);
}

export function getEndpoint(id) {
  return endpoints.find(ep => ep.id === id);
}

export function clearEndpoints() {
  endpoints.length = 0;
  nextId = 0;
}

export function clearResults() {
  for (const ep of endpoints) {
    ep.state = 'idle';
    ep.result = null;
  }
}

export function resetIdCounter() {
  nextId = 0;
}

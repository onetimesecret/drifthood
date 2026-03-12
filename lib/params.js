// ── Parameter manipulation utilities ──

export function setNestedValue(obj, path, val) {
  const parts = path.split('.');
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (!(parts[i] in cur)) cur[parts[i]] = {};
    cur = cur[parts[i]];
  }
  // Try to parse typed values
  if (val === 'true') val = true;
  else if (val === 'false') val = false;
  else if (!isNaN(val) && val !== '') val = Number(val);
  cur[parts[parts.length - 1]] = val;
}

export function flattenObj(obj, prefix = '') {
  const result = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      Object.assign(result, flattenObj(v, key));
    } else {
      result[key] = v;
    }
  }
  return result;
}

export function parseKvString(str) {
  if (!str || !str.trim()) return [];
  return str.split('&').map(pair => {
    const eq = pair.indexOf('=');
    if (eq === -1) return { key: pair, val: '' };
    return { key: decodeURIComponent(pair.slice(0, eq)), val: decodeURIComponent(pair.slice(eq + 1)) };
  }).filter(p => p.key !== '');
}

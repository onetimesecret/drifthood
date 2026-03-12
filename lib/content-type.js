// ── Content type definitions ──

export const CT = {
  query: { value: 'query', label: 'QUERY', cls: 'query', placeholder: 'key=val&key2=val2 (query params)' },
  form:  { value: 'application/x-www-form-urlencoded', label: 'FORM', cls: 'form', placeholder: 'key=val&key2=val2 (form body)' },
  json:  { value: 'application/json', label: 'JSON', cls: 'json', placeholder: '{"key":"val"} (JSON body)' },
};

export const CT_CYCLE = ['query', 'form', 'json'];

export function ctInfo(v) { return v === 'application/json' ? CT.json : v === 'application/x-www-form-urlencoded' ? CT.form : CT.query; }

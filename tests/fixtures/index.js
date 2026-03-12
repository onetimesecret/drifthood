export function makeCompareResult(overrides = {}) {
  return {
    method: 'GET', path: '/api/v1/status', label: 'status',
    has_drift: false, diff: {},
    response_a: { status: 200, headers: {}, body: { status: 'ok' }, elapsed_ms: 42 },
    response_b: { status: 200, headers: {}, body: { status: 'ok' }, elapsed_ms: 38 },
    ignored_paths: [],
    ...overrides,
  };
}

export function makeDiff(overrides = {}) {
  return {
    values_changed: { "root['body']['version']": { old_value: '1.0', new_value: '2.0' } },
    ...overrides,
  };
}

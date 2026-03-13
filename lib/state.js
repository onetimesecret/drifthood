// ── State fingerprinting for dirty detection ──

export function stateFingerprint(state) {
  // Strip volatile fields that change every save but don't represent user changes
  const {savedAt, sessionNumber, testrunNumber, version, ...rest} = state;
  const raw = JSON.stringify(rest, Object.keys(rest).sort());
  // Simple djb2 hash to string - fast, good enough for change detection
  let hash = 5381;
  for (let i = 0; i < raw.length; i++) {
    hash = ((hash << 5) + hash + raw.charCodeAt(i)) & 0xffffffff;
  }
  return hash.toString(36);
}

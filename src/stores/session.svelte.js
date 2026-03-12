// Svelte 5 runes — reactive state for session config
//
// Saving semantics: explicit saves update the current session in-place.
// New sessions are only created on first save (no existing session) or
// via autosave when state has changed. This gives users the expected
// "save persists in-place" behavior while autosave still creates snapshots.
export const session = $state({
  title: '',
  memo: '',
  hostA: '',
  hostB: '',
  authA: '',
  authB: '',
  memoA: '',
  memoB: '',
  ignorePaths: [],       // array of raw dot-notation strings (not DeepDiff format)
  specSource: null,       // breadcrumb source text
});

export function resetSession() {
  session.title = '';
  session.memo = '';
  session.hostA = '';
  session.hostB = '';
  session.authA = '';
  session.authB = '';
  session.memoA = '';
  session.memoB = '';
  session.ignorePaths = [];
  session.specSource = null;
}

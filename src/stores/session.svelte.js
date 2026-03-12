// Svelte 5 runes — reactive state for session config
//
// Saving semantics: each save creates a new numbered session snapshot within
// the current document (append-only versioning). The session counter is
// expected to grow on every save — this is intentional, not a bug.
// Autosave skips if the state hash hasn't changed, but explicit saves
// always create a new snapshot so users can revisit prior states.
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

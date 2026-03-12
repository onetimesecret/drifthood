// Svelte 5 runes — reactive state for session config
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

// Svelte 5 runes — reactive state for UI view
export const ui = $state({
  filter: 'all',           // 'all' | 'drift' | 'ok'
  sidebarCollapsed: false,
  ignoreOpen: false,
  expandedDocs: new Set(),  // Set of doc IDs expanded in sidebar
  activeModal: null,        // null | 'openapi' | 'schema-diff'
});

export function resetUi() {
  ui.filter = 'all';
  ui.sidebarCollapsed = false;
  ui.ignoreOpen = false;
  ui.expandedDocs = new Set();
  ui.activeModal = null;
}

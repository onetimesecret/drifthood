// Svelte 5 runes — reactive state for UI view
export const ui = $state({
  filter: 'all',           // 'all' | 'drift' | 'ok'
  collapseGen: 0,          // bumped to collapse all ResultDisplay panels
  sidebarCollapsed: false,
  ignoreOpen: false,
  expandedDocs: new Set(),  // Set of doc IDs expanded in sidebar
  activeModal: null,        // null | 'openapi' | 'schema-diff'
});

export function resetUi() {
  ui.filter = 'all';
  ui.collapseGen = 0;
  ui.sidebarCollapsed = false;
  ui.ignoreOpen = false;
  ui.expandedDocs = new Set();
  ui.activeModal = null;
}

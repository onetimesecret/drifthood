// Svelte 5 runes — reactive state for document/session tracking
export const documents = $state({
  currentDocumentId: null,
  currentSessionNumber: 0,
  lastSavedStateHash: null,
  list: [],                 // cached document list from API
  refreshVersion: 0,        // bump to trigger sidebar re-fetch
});

/** Signal that the sidebar document list should re-fetch from the API. */
export function notifyDocumentsChanged() {
  documents.refreshVersion++;
}

export function resetDocuments() {
  documents.currentDocumentId = null;
  documents.currentSessionNumber = 0;
  documents.lastSavedStateHash = null;
  documents.list = [];
  // Note: don't reset refreshVersion — keep the counter monotonic
}

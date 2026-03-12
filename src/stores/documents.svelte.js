// Svelte 5 runes — reactive state for document/session tracking
export const documents = $state({
  currentDocumentId: null,
  currentSessionNumber: 0,
  lastSavedStateHash: null,
  list: [],                 // cached document list from API
});

export function resetDocuments() {
  documents.currentDocumentId = null;
  documents.currentSessionNumber = 0;
  documents.lastSavedStateHash = null;
  documents.list = [];
}

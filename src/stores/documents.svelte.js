// Svelte 5 runes — reactive state for document/testrun tracking.
//
// All references use UUIDv7 extids. Integer IDs never appear here.
export const documents = $state({
  currentDocumentExtid: null,
  currentTestrunExtid: null,
  currentTestrunNumber: 0,
  lastSavedStateHash: null,
  list: [],                 // cached document list from API
  refreshVersion: 0,        // bump to trigger sidebar re-fetch
});

/** Signal that the sidebar document list should re-fetch from the API. */
export function notifyDocumentsChanged() {
  documents.refreshVersion++;
}

const LAST_DOC_KEY = 'dd:lastDocument';

/** Persist the current doc/testrun so it survives page refresh. */
export function rememberLastDocument(docExtid, testrunExtid, testrunNumber) {
  try {
    localStorage.setItem(LAST_DOC_KEY, JSON.stringify({ docExtid, testrunExtid, testrunNumber }));
  } catch { /* quota / private browsing */ }
}

/** Retrieve the last-viewed doc/testrun, or null. */
export function recallLastDocument() {
  try {
    const raw = localStorage.getItem(LAST_DOC_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed?.docExtid) return parsed;
  } catch { /* corrupted */ }
  return null;
}

export function resetDocuments() {
  documents.currentDocumentExtid = null;
  documents.currentTestrunExtid = null;
  documents.currentTestrunNumber = 0;
  documents.lastSavedStateHash = null;
  documents.list = [];
  // Note: don't reset refreshVersion — keep the counter monotonic
}

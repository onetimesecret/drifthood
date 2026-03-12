import { session, resetSession } from './session.svelte.js';
import { endpoints, addEndpoint, clearEndpoints, resetIdCounter } from './endpoints.svelte.js';
import { ui, resetUi } from './ui.svelte.js';
import { documents, resetDocuments } from './documents.svelte.js';

const DD_VERSION = '0.4.0';

/**
 * Serialize current state to a plain object suitable for JSON.stringify.
 * Replaces the old collectState() that scraped DOM elements.
 */
export function snapshot() {
  return {
    version: DD_VERSION,
    savedAt: new Date().toISOString(),
    documentId: documents.currentDocumentId,
    sessionNumber: documents.currentSessionNumber,
    title: session.title,
    memo: session.memo,
    hostA: session.hostA,
    hostB: session.hostB,
    memoA: session.memoA,
    memoB: session.memoB,
    authA: session.authA,
    authB: session.authB,
    specSource: session.specSource,
    ignorePaths: [...session.ignorePaths],
    endpoints: endpoints.map(ep => ({
      method: ep.method,
      label: ep.label,
      path: ep.path,
      body: ep.body,
      contentType: ep.contentType,
      group: ep.group,
      fieldsMode: ep.fieldsMode,
      state: ep.state,
      cardFields: ep.cardFields,
      fieldValues: ep.fieldValues,
      // Note: result data is NOT serialized (old resultHtml was fragile).
      // Users re-run comparisons after restore.
    })),
    filter: ui.filter,
    ignoreOpen: ui.ignoreOpen,
  };
}

/**
 * Restore state from a snapshot object.
 * Replaces the old restoreState() that rebuilt DOM.
 */
export function restore(snap) {
  // Reset everything first
  resetSession();
  clearEndpoints();
  resetIdCounter();

  // Restore session config
  session.title = snap.title || '';
  session.memo = snap.memo || '';
  session.hostA = snap.hostA || '';
  session.hostB = snap.hostB || '';
  session.authA = snap.authA || '';
  session.authB = snap.authB || '';
  session.memoA = snap.memoA || '';
  session.memoB = snap.memoB || '';
  session.specSource = snap.specSource || null;
  if (snap.ignorePaths && snap.ignorePaths.length) {
    session.ignorePaths = [...snap.ignorePaths];
  }

  // Restore document tracking
  if (snap.documentId) documents.currentDocumentId = snap.documentId;
  if (snap.sessionNumber) documents.currentSessionNumber = snap.sessionNumber;

  // Restore endpoints
  for (const ep of (snap.endpoints || [])) {
    addEndpoint({
      method: ep.method,
      label: ep.label,
      path: ep.path,
      body: ep.body,
      contentType: ep.contentType,
      group: ep.group,
      fieldsMode: ep.fieldsMode || 'off',
      cardFields: ep.cardFields || null,
      fieldValues: ep.fieldValues || null,
    });
    // Old sessions with resultHtml: result stays null, state shows as idle.
    // This is intentional — no migration code.
  }

  // Restore UI state
  ui.filter = snap.filter || 'all';
  ui.ignoreOpen = !!snap.ignoreOpen;
}

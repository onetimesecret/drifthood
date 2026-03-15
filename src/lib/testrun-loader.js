// ── Shared testrun loading logic ──
//
// Fetches a testrun from the API, decrypts the encrypted blob if present,
// restores state into reactive stores, loads manifest-style entities,
// and updates document tracking. Callers handle UI-specific side effects
// (toasts, breadcrumbs, autosave) with the returned data.

import { apiGetTestrun } from '../../lib/api.js';
import { stateFingerprint } from '../../lib/state.js';
import { getEncKey } from '../stores/auth.svelte.js';
import { decryptBlob } from './crypto.js';
import { restore } from '../stores/snapshot.js';
import { loadEnvironments } from '../stores/session.svelte.js';
import { loadEndpoints } from '../stores/endpoints.svelte.js';
import { documents, rememberLastDocument } from '../stores/documents.svelte.js';

/**
 * Load a testrun: fetch, decrypt, restore state, update tracking.
 *
 * Throws on network error, missing testrun, or missing state so callers
 * can handle failures in their own way (toast, silent catch, etc.).
 *
 * @param {string} docExtid       - Document extid
 * @param {string} testrunExtid   - Testrun extid
 * @param {number} testrunNumber  - Testrun number for display
 * @returns {{ state: object, sensitive: object|null, testrunNumber: number }}
 */
export async function loadTestrun(docExtid, testrunExtid, testrunNumber) {
  const data = await apiGetTestrun(docExtid, testrunExtid);
  if (data.error || !data.testrun) {
    throw new Error(data.error || 'no testrun data');
  }

  const tr = data.testrun;
  const state = tr.state;
  if (!state) {
    throw new Error('Testrun has no state data');
  }

  // Decrypt encrypted blob if present (manifest-style testruns)
  let sensitive = null;
  if (tr.encrypted_blob && tr.blob_iv) {
    try {
      const encKey = getEncKey();
      if (encKey) {
        const aad = docExtid || 'doc';
        const plaintext = await decryptBlob(encKey, tr.encrypted_blob, tr.blob_iv, aad);
        sensitive = JSON.parse(plaintext);
      }
    } catch (err) {
      console.warn('Blob decryption failed, falling back to legacy state:', err.message);
      // Fall through — restore will use legacy mode from state_json
    }
  }

  await restore(state, sensitive);

  // For manifest-style testruns, load entities from server
  if (state.environment_extids || state.endpoint_extids) {
    await loadEnvironments();
    await loadEndpoints();
  }

  // Set document tracking AFTER restore() so stale snapshot
  // values don't overwrite the actual navigation target.
  documents.currentDocumentExtid = docExtid;
  documents.currentTestrunExtid = testrunExtid;
  documents.currentTestrunNumber = testrunNumber;
  documents.lastSavedStateHash = sensitive
    ? stateFingerprint({ ...state, ...sensitive })
    : stateFingerprint(state);
  rememberLastDocument(docExtid, testrunExtid, testrunNumber);

  return { state, sensitive, testrunNumber };
}

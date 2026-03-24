// src/stores/snapshot.js

import { session, resetSession } from './session.svelte.js';
import { endpoints, addEndpoint, clearEndpointsLocal } from './endpoints.svelte.js';
import { ui } from './ui.svelte.js';
import { documents } from './documents.svelte.js';

import { DD_VERSION } from '../../lib/examples.js';

/**
 * Serialize current state into manifest (cleartext) + sensitive (encrypted).
 *
 * The manifest contains only entity references and non-sensitive metadata.
 * It is stored in state_json on the server and is queryable.
 *
 * The sensitive object contains credentials, results, UI config, and
 * anything that should be encrypted client-side before storage.
 */
export function snapshot() {
  const manifest = {
    version: DD_VERSION,
    savedAt: new Date().toISOString(),
    documentExtid: documents.currentDocumentExtid,
    testrunExtid: documents.currentTestrunExtid,
    testrunNumber: documents.currentTestrunNumber,
    // Title lives in manifest for document naming (non-sensitive metadata)
    title: session.title,
    // References (clear, in manifest)
    environment_extids: session.environments.map(e => e.extid),
    endpoint_extids: endpoints.map(e => e.extid),
    selectedA: session.selectedA,
    selectedB: session.selectedB,
  };

  const sensitive = {
    title: session.title,
    memo: session.memo,
    specSource: session.specSource,
    ignorePaths: [...session.ignorePaths],
    filter: ui.filter,
    ignoreOpen: ui.ignoreOpen,
    endpoint_results: endpoints.map(e => ({
      extid: e.extid,
      state: e.state,
      result: e.result ?? null,
    })),
  };

  return { manifest, sensitive };
}

/**
 * Produce a legacy-format snapshot (flat object with everything inline).
 * Used for drag-and-drop JSON export and HTML snapshot embedding where
 * the full state needs to be self-contained in a single object.
 */
export function snapshotLegacy() {
  return {
    version: DD_VERSION,
    savedAt: new Date().toISOString(),
    documentExtid: documents.currentDocumentExtid,
    testrunExtid: documents.currentTestrunExtid,
    testrunNumber: documents.currentTestrunNumber,
    title: session.title,
    memo: session.memo,
    environments: session.environments.map(env => ({
      extid: env.extid,
      name: env.name,
      baseUrl: env.baseUrl,
      auth: env.auth,
      memo: env.memo,
      metadata: { ...(env.metadata || {}) },
    })),
    selectedA: session.selectedA,
    selectedB: session.selectedB,
    specSource: session.specSource,
    ignorePaths: [...session.ignorePaths],
    endpoints: endpoints.map(ep => ({
      extid: ep.extid,
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
      result: ep.result ?? null,
    })),
    filter: ui.filter,
    ignoreOpen: ui.ignoreOpen,
  };
}

/**
 * Restore state from a manifest + optional decrypted sensitive data.
 *
 * Three modes:
 * 1. manifest-style with sensitive blob: snap has environment_extids/endpoint_extids,
 *    sensitive has title/memo/results. Entities loaded separately via server.
 * 2. Legacy full snapshot: snap has environments/endpoints arrays inline.
 *    Used for drag-and-drop imports, HTML snapshots, and old testruns without
 *    encrypted blobs.
 * 3. Legacy full snapshot without separate sensitive: backward compat for old
 *    testruns where everything was in state_json.
 */
export async function restore(snap, sensitive = null) {
  // Reset everything first
  resetSession();
  clearEndpointsLocal();

  // If we have sensitive data (from decrypted blob), use it
  if (sensitive) {
    session.title = sensitive.title || '';
    session.memo = sensitive.memo || '';
    session.specSource = sensitive.specSource || null;
    if (sensitive.ignorePaths?.length) {
      session.ignorePaths = [...sensitive.ignorePaths];
    }
    ui.filter = sensitive.filter || 'all';
    ui.ignoreOpen = !!sensitive.ignoreOpen;
  }

  // Restore environments from snap (backward compat) or load from server
  if (snap.environments?.length) {
    // Old-style snapshot with inline environments
    session.environments = snap.environments.map(env => ({
      extid: env.extid || env.id || '',  // backward compat: old snapshots used "id"
      name: env.name || '',
      baseUrl: env.baseUrl || '',
      auth: env.auth || '',
      memo: env.memo || '',
      metadata: env.metadata ? { ...env.metadata } : {},
    }));
  }
  // If manifest-style (environment_extids), environments are loaded separately via loadEnvironments()

  session.selectedA = snap.selectedA || '';
  session.selectedB = snap.selectedB || '';

  // NOTE: Document tracking (currentDocumentExtid, currentTestrunExtid) is NOT
  // restored here — callers set it after restore() to avoid stale snapshot
  // values overwriting the actual navigation target.

  // Restore endpoints from snap (backward compat with inline endpoints)
  if (snap.endpoints?.length) {
    for (const ep of snap.endpoints) {
      await addEndpoint({
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
      // Restore run state and result if present in the snapshot
      if (ep.state && ep.state !== 'idle') {
        // addEndpoint pushes to the end; find the last endpoint added
        const restored = endpoints[endpoints.length - 1];
        if (restored) {
          restored.state = ep.state;
          restored.result = ep.result || null;
        }
      }
    }
  }
  // If manifest-style (endpoint_extids), endpoints are loaded separately via loadEndpoints()

  // Apply endpoint results from sensitive blob
  if (sensitive?.endpoint_results?.length) {
    for (const er of sensitive.endpoint_results) {
      const ep = endpoints.find(e => e.extid === er.extid);
      if (ep) {
        ep.state = er.state || 'idle';
        ep.result = er.result || null;
      }
    }
  }

  // Backward compat: old snapshots had title/memo at top level
  if (!sensitive && snap.title !== undefined) {
    session.title = snap.title || '';
    session.memo = snap.memo || '';
    session.specSource = snap.specSource || null;
    if (snap.ignorePaths?.length) session.ignorePaths = [...snap.ignorePaths];
    ui.filter = snap.filter || 'all';
    ui.ignoreOpen = !!snap.ignoreOpen;
  }
}

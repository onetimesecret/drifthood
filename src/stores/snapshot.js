import { session, resetSession, createEnvironment } from './session.svelte.js';
import { endpoints, addEndpoint, clearEndpoints, resetIdCounter } from './endpoints.svelte.js';
import { ui } from './ui.svelte.js';
import { documents } from './documents.svelte.js';

import { DD_VERSION } from '../../lib/examples.js';

/**
 * Serialize current state to a plain object suitable for JSON.stringify.
 */
export function snapshot() {
  return {
    version: DD_VERSION,
    savedAt: new Date().toISOString(),
    documentExtid: documents.currentDocumentExtid,
    testrunExtid: documents.currentTestrunExtid,
    testrunNumber: documents.currentTestrunNumber,
    title: session.title,
    memo: session.memo,
    environments: session.environments.map(env => ({
      id: env.id,
      name: env.name,
      baseUrl: env.baseUrl,
      auth: env.auth,
      memo: env.memo,
      metadata: { ...env.metadata },
    })),
    selectedA: session.selectedA,
    selectedB: session.selectedB,
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
      result: ep.result ?? null,
    })),
    filter: ui.filter,
    ignoreOpen: ui.ignoreOpen,
  };
}

/**
 * Restore state from a snapshot object.
 */
export function restore(snap) {
  // Reset everything first
  resetSession();
  clearEndpoints();
  resetIdCounter();

  // Restore session config
  session.title = snap.title || '';
  session.memo = snap.memo || '';
  session.specSource = snap.specSource || null;
  if (snap.ignorePaths && snap.ignorePaths.length) {
    session.ignorePaths = [...snap.ignorePaths];
  }

  // Restore environments
  if (snap.environments && snap.environments.length) {
    session.environments = snap.environments.map(env => createEnvironment({
      ...env,
      metadata: env.metadata ? { ...env.metadata } : {},
    }));
    // Preserve original IDs from snapshot
    for (let i = 0; i < snap.environments.length; i++) {
      session.environments[i].id = snap.environments[i].id;
    }
  }
  session.selectedA = snap.selectedA || '';
  session.selectedB = snap.selectedB || '';

  // NOTE: Document tracking (currentDocumentExtid, currentTestrunExtid) is NOT
  // restored here — callers set it after restore() to avoid stale snapshot
  // values overwriting the actual navigation target.

  // Restore endpoints (config only — results start clean to avoid stale data)
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
  }

  // Restore UI state
  ui.filter = snap.filter || 'all';
  ui.ignoreOpen = !!snap.ignoreOpen;
}

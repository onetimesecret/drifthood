// src/lib/testrun-loader.test.js

import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mocks ──
// All external dependencies are mocked so the test exercises only
// the orchestration logic inside loadTestrun().

vi.mock('../../lib/api.js', () => ({
  apiGetTestrun: vi.fn(),
}));

vi.mock('../../lib/state.js', () => ({
  stateFingerprint: vi.fn(() => 'fp-abc'),
}));

vi.mock('../stores/auth.svelte.js', () => ({
  getEncKey: vi.fn(() => null),
}));

vi.mock('./crypto.js', () => ({
  decryptBlob: vi.fn(),
}));

vi.mock('../stores/snapshot.js', () => ({
  restore: vi.fn(),
}));

vi.mock('../stores/session.svelte.js', () => ({
  loadEnvironments: vi.fn(),
}));

vi.mock('../stores/endpoints.svelte.js', () => ({
  loadEndpoints: vi.fn(),
}));

vi.mock('../stores/documents.svelte.js', () => ({
  documents: {
    currentDocumentExtid: null,
    currentTestrunExtid: null,
    currentTestrunNumber: 0,
    lastSavedStateHash: null,
  },
  rememberLastDocument: vi.fn(),
}));

// ── Import subjects after mocks are registered ──
import { loadTestrun } from './testrun-loader.js';
import { apiGetTestrun } from '../../lib/api.js';
import { stateFingerprint } from '../../lib/state.js';
import { getEncKey } from '../stores/auth.svelte.js';
import { decryptBlob } from './crypto.js';
import { restore } from '../stores/snapshot.js';
import { loadEnvironments } from '../stores/session.svelte.js';
import { loadEndpoints } from '../stores/endpoints.svelte.js';
import { documents, rememberLastDocument } from '../stores/documents.svelte.js';

beforeEach(() => {
  vi.clearAllMocks();
  documents.currentDocumentExtid = null;
  documents.currentTestrunExtid = null;
  documents.currentTestrunNumber = 0;
  documents.lastSavedStateHash = null;
});

// ── Helpers ──
function makeTestrunResponse(overrides = {}) {
  return {
    testrun: {
      state: { selectedA: 'a', selectedB: 'b' },
      ...overrides,
    },
  };
}

describe('loadTestrun', () => {
  // ── Error paths ──

  describe('error paths', () => {
    it('throws when API returns an error', async () => {
      apiGetTestrun.mockResolvedValue({ error: 'not found' });

      await expect(loadTestrun('doc-1', 'tr-1', 1))
        .rejects.toThrow('not found');
    });

    it('throws when API returns no testrun', async () => {
      apiGetTestrun.mockResolvedValue({});

      await expect(loadTestrun('doc-1', 'tr-1', 1))
        .rejects.toThrow('no testrun data');
    });

    it('throws when testrun has no state', async () => {
      apiGetTestrun.mockResolvedValue({ testrun: { state: null } });

      await expect(loadTestrun('doc-1', 'tr-1', 1))
        .rejects.toThrow('Testrun has no state data');
    });

    it('does not call restore when API fails', async () => {
      apiGetTestrun.mockResolvedValue({ error: 'gone' });

      await expect(loadTestrun('doc-1', 'tr-1', 1)).rejects.toThrow();
      expect(restore).not.toHaveBeenCalled();
    });
  });

  // ── Legacy path (no encrypted blob) ──

  describe('legacy path (no encrypted blob)', () => {
    it('calls restore with state and null sensitive', async () => {
      const state = { selectedA: 'a', selectedB: 'b' };
      apiGetTestrun.mockResolvedValue(makeTestrunResponse());

      await loadTestrun('doc-1', 'tr-1', 5);

      expect(restore).toHaveBeenCalledWith(state, null);
    });

    it('sets document tracking fields', async () => {
      apiGetTestrun.mockResolvedValue(makeTestrunResponse());

      await loadTestrun('doc-1', 'tr-1', 5);

      expect(documents.currentDocumentExtid).toBe('doc-1');
      expect(documents.currentTestrunExtid).toBe('tr-1');
      expect(documents.currentTestrunNumber).toBe(5);
    });

    it('calls rememberLastDocument with correct args', async () => {
      apiGetTestrun.mockResolvedValue(makeTestrunResponse());

      await loadTestrun('doc-1', 'tr-1', 5);

      expect(rememberLastDocument).toHaveBeenCalledWith('doc-1', 'tr-1', 5);
    });

    it('computes fingerprint from state alone when no sensitive data', async () => {
      const state = { selectedA: 'a', selectedB: 'b' };
      stateFingerprint.mockReturnValue('hash-legacy');
      apiGetTestrun.mockResolvedValue(makeTestrunResponse());

      await loadTestrun('doc-1', 'tr-1', 5);

      expect(stateFingerprint).toHaveBeenCalledWith(state);
      expect(documents.lastSavedStateHash).toBe('hash-legacy');
    });

    it('returns state, sensitive=null, and testrunNumber', async () => {
      apiGetTestrun.mockResolvedValue(makeTestrunResponse());

      const result = await loadTestrun('doc-1', 'tr-1', 5);

      expect(result).toEqual({
        state: { selectedA: 'a', selectedB: 'b' },
        sensitive: null,
        testrunNumber: 5,
      });
    });

    it('does not call loadEnvironments or loadEndpoints', async () => {
      apiGetTestrun.mockResolvedValue(makeTestrunResponse());

      await loadTestrun('doc-1', 'tr-1', 5);

      expect(loadEnvironments).not.toHaveBeenCalled();
      expect(loadEndpoints).not.toHaveBeenCalled();
    });
  });

  // ── Decrypt path (encrypted blob present) ──

  describe('decrypt path', () => {
    const encryptedTestrun = {
      state: { environment_extids: ['env-1'], endpoint_extids: ['ep-1'] },
      encrypted_blob: 'cipher-abc',
      blob_iv: 'iv-abc',
    };

    it('decrypts blob and passes sensitive to restore', async () => {
      const sensitive = { title: 'My Test', memo: 'notes' };
      apiGetTestrun.mockResolvedValue(makeTestrunResponse(encryptedTestrun));
      getEncKey.mockReturnValue('enc-key-123');
      decryptBlob.mockResolvedValue(JSON.stringify(sensitive));

      await loadTestrun('doc-1', 'tr-1', 3);

      expect(decryptBlob).toHaveBeenCalledWith('enc-key-123', 'cipher-abc', 'iv-abc', 'doc-1');
      expect(restore).toHaveBeenCalledWith(encryptedTestrun.state, sensitive);
    });

    it('uses "doc" as AAD fallback when docExtid is falsy', async () => {
      apiGetTestrun.mockResolvedValue(makeTestrunResponse(encryptedTestrun));
      getEncKey.mockReturnValue('enc-key-123');
      decryptBlob.mockResolvedValue(JSON.stringify({ title: 'x' }));

      await loadTestrun('', 'tr-1', 3);

      expect(decryptBlob).toHaveBeenCalledWith('enc-key-123', 'cipher-abc', 'iv-abc', 'doc');
    });

    it('computes fingerprint from merged state+sensitive when decrypted', async () => {
      const state = encryptedTestrun.state;
      const sensitive = { title: 'x', memo: 'y' };
      apiGetTestrun.mockResolvedValue(makeTestrunResponse(encryptedTestrun));
      getEncKey.mockReturnValue('enc-key-123');
      decryptBlob.mockResolvedValue(JSON.stringify(sensitive));
      stateFingerprint.mockReturnValue('hash-merged');

      await loadTestrun('doc-1', 'tr-1', 3);

      expect(stateFingerprint).toHaveBeenCalledWith({ ...state, ...sensitive });
      expect(documents.lastSavedStateHash).toBe('hash-merged');
    });

    it('falls back to legacy mode when decryption fails', async () => {
      apiGetTestrun.mockResolvedValue(makeTestrunResponse(encryptedTestrun));
      getEncKey.mockReturnValue('enc-key-123');
      decryptBlob.mockRejectedValue(new Error('bad key'));

      await loadTestrun('doc-1', 'tr-1', 3);

      // Should still call restore with null sensitive (fallback)
      expect(restore).toHaveBeenCalledWith(encryptedTestrun.state, null);
    });

    it('skips decryption when no encKey is available', async () => {
      apiGetTestrun.mockResolvedValue(makeTestrunResponse(encryptedTestrun));
      getEncKey.mockReturnValue(null);

      await loadTestrun('doc-1', 'tr-1', 3);

      expect(decryptBlob).not.toHaveBeenCalled();
      expect(restore).toHaveBeenCalledWith(encryptedTestrun.state, null);
    });
  });

  // ── Manifest entity loading ──

  describe('manifest entity loading', () => {
    it('loads environments and endpoints when environment_extids present', async () => {
      apiGetTestrun.mockResolvedValue(makeTestrunResponse({
        state: { environment_extids: ['env-1'] },
      }));

      await loadTestrun('doc-1', 'tr-1', 1);

      expect(loadEnvironments).toHaveBeenCalled();
      expect(loadEndpoints).toHaveBeenCalled();
    });

    it('loads environments and endpoints when endpoint_extids present', async () => {
      apiGetTestrun.mockResolvedValue(makeTestrunResponse({
        state: { endpoint_extids: ['ep-1'] },
      }));

      await loadTestrun('doc-1', 'tr-1', 1);

      expect(loadEnvironments).toHaveBeenCalled();
      expect(loadEndpoints).toHaveBeenCalled();
    });

    it('skips entity loading when neither extid list is present', async () => {
      apiGetTestrun.mockResolvedValue(makeTestrunResponse({
        state: { title: 'plain' },
      }));

      await loadTestrun('doc-1', 'tr-1', 1);

      expect(loadEnvironments).not.toHaveBeenCalled();
      expect(loadEndpoints).not.toHaveBeenCalled();
    });
  });

  // ── Document tracking ──

  describe('document tracking updates', () => {
    it('sets all tracking fields after restore completes', async () => {
      apiGetTestrun.mockResolvedValue(makeTestrunResponse());

      await loadTestrun('doc-42', 'tr-77', 12);

      expect(documents.currentDocumentExtid).toBe('doc-42');
      expect(documents.currentTestrunExtid).toBe('tr-77');
      expect(documents.currentTestrunNumber).toBe(12);
      expect(documents.lastSavedStateHash).toBeDefined();
      expect(rememberLastDocument).toHaveBeenCalledWith('doc-42', 'tr-77', 12);
    });

    it('does not update tracking on error', async () => {
      apiGetTestrun.mockResolvedValue({ error: 'boom' });

      await expect(loadTestrun('doc-1', 'tr-1', 1)).rejects.toThrow();

      expect(documents.currentDocumentExtid).toBeNull();
      expect(rememberLastDocument).not.toHaveBeenCalled();
    });
  });
});

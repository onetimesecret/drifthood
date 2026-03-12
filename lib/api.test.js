import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  apiConfig, apiTestHost, apiCompare, apiBatch, apiSave,
  apiListDocuments, apiGetDocument, apiUpdateDocumentTitle,
  apiGetSessions, apiGetSession, apiDeleteSession,
  apiParseOpenapi, apiDiffSchemas,
} from './api.js';

// Mock fetch globally
const mockJson = vi.fn();
const mockFetch = vi.fn(() => Promise.resolve({ json: mockJson }));

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch);
  mockJson.mockResolvedValue({ ok: true });
  mockFetch.mockClear();
  mockJson.mockClear();
});

describe('apiConfig', () => {
  it('fetches /api/config', async () => {
    await apiConfig();
    expect(mockFetch).toHaveBeenCalledWith('/api/config');
  });
});

describe('apiTestHost', () => {
  it('POSTs host and auth', async () => {
    await apiTestHost('http://localhost:3000', 'token123');
    expect(mockFetch).toHaveBeenCalledWith('/api/test-host', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ host: 'http://localhost:3000', auth: 'token123' }),
    });
  });
});

describe('apiCompare', () => {
  it('POSTs comparison params', async () => {
    const params = { label: 'test', method: 'GET', path: '/status' };
    await apiCompare(params);
    expect(mockFetch).toHaveBeenCalledWith('/api/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
  });
});

describe('apiBatch', () => {
  it('POSTs batch params', async () => {
    const params = { endpoints: [] };
    await apiBatch(params);
    expect(mockFetch).toHaveBeenCalledWith('/api/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
  });
});

describe('apiSave', () => {
  it('POSTs state with documentId and sessionType', async () => {
    await apiSave({ data: 1 }, 'doc-123', 'manual');
    expect(mockFetch).toHaveBeenCalledWith('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: { data: 1 }, documentId: 'doc-123', sessionType: 'manual' }),
    });
  });
});

describe('apiListDocuments', () => {
  it('fetches /api/documents', async () => {
    await apiListDocuments();
    expect(mockFetch).toHaveBeenCalledWith('/api/documents');
  });
});

describe('apiGetDocument', () => {
  it('fetches specific document', async () => {
    await apiGetDocument('abc');
    expect(mockFetch).toHaveBeenCalledWith('/api/documents/abc');
  });
});

describe('apiUpdateDocumentTitle', () => {
  it('PATCHes document title', async () => {
    await apiUpdateDocumentTitle('abc', 'New Title');
    expect(mockFetch).toHaveBeenCalledWith('/api/documents/abc', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'New Title' }),
    });
  });
});

describe('apiGetSessions', () => {
  it('fetches sessions for a document', async () => {
    await apiGetSessions('abc');
    expect(mockFetch).toHaveBeenCalledWith('/api/documents/abc/sessions');
  });
});

describe('apiGetSession', () => {
  it('fetches specific session', async () => {
    await apiGetSession('abc', 3);
    expect(mockFetch).toHaveBeenCalledWith('/api/documents/abc/sessions/3');
  });
});

describe('apiDeleteSession', () => {
  it('DELETEs specific session', async () => {
    await apiDeleteSession('abc', 2);
    expect(mockFetch).toHaveBeenCalledWith('/api/documents/abc/sessions/2', { method: 'DELETE' });
  });
});

describe('apiParseOpenapi', () => {
  it('POSTs FormData', async () => {
    const fd = new FormData();
    await apiParseOpenapi(fd);
    expect(mockFetch).toHaveBeenCalledWith('/api/parse-openapi', { method: 'POST', body: fd });
  });
});

describe('apiDiffSchemas', () => {
  it('POSTs FormData', async () => {
    const fd = new FormData();
    await apiDiffSchemas(fd);
    expect(mockFetch).toHaveBeenCalledWith('/api/diff-schemas', { method: 'POST', body: fd });
  });
});

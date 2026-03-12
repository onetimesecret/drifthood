import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  apiConfig, apiTestHost, apiCompare, apiBatch, apiSave,
  apiListDocuments, apiGetDocument, apiUpdateDocumentTitle,
  apiGetSessions, apiGetSession, apiDeleteSession,
  apiParseOpenapi, apiDiffSchemas,
} from './api.js';

// Mock fetch globally
const mockJson = vi.fn();
const mockFetch = vi.fn(() => Promise.resolve({ ok: true, json: mockJson }));

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch);
  mockJson.mockResolvedValue({ status: 'ok' });
  mockFetch.mockClear();
  mockJson.mockClear();
  // Reset to successful response by default
  mockFetch.mockImplementation(() => Promise.resolve({ ok: true, json: mockJson }));
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

  it('includes sessionNumber in request body when provided', async () => {
    await apiSave({ data: 2 }, 'doc-456', 'save', 7);
    expect(mockFetch).toHaveBeenCalledWith('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: { data: 2 }, documentId: 'doc-456', sessionType: 'save', sessionNumber: 7 }),
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

describe('HTTP error handling', () => {
  beforeEach(() => {
    mockFetch.mockImplementation(() =>
      Promise.resolve({ ok: false, status: 500, statusText: 'Internal Server Error', json: mockJson })
    );
  });

  it('apiConfig throws on server error', async () => {
    await expect(apiConfig()).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiTestHost throws on server error', async () => {
    await expect(apiTestHost('http://localhost', 'tok')).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiCompare throws on server error', async () => {
    await expect(apiCompare({ label: 'x' })).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiBatch throws on server error', async () => {
    await expect(apiBatch({})).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiSave throws on server error', async () => {
    await expect(apiSave({}, 'doc1', 'save')).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiListDocuments throws on server error', async () => {
    await expect(apiListDocuments()).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiGetDocument throws on server error', async () => {
    await expect(apiGetDocument('abc')).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiUpdateDocumentTitle throws on server error', async () => {
    await expect(apiUpdateDocumentTitle('abc', 'Title')).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiGetSessions throws on server error', async () => {
    await expect(apiGetSessions('abc')).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiGetSession throws on server error', async () => {
    await expect(apiGetSession('abc', 1)).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiDeleteSession throws on server error', async () => {
    await expect(apiDeleteSession('abc', 1)).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiParseOpenapi throws on server error', async () => {
    await expect(apiParseOpenapi(new FormData())).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiDiffSchemas throws on server error', async () => {
    await expect(apiDiffSchemas(new FormData())).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('includes status code in error for 502 Bad Gateway', async () => {
    mockFetch.mockImplementation(() =>
      Promise.resolve({ ok: false, status: 502, statusText: 'Bad Gateway', json: mockJson })
    );
    await expect(apiConfig()).rejects.toThrow('HTTP 502: Bad Gateway');
  });
});

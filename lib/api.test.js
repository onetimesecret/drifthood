import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the auth store before importing api.js
vi.mock('../src/stores/auth.svelte.js', () => ({
  getToken: vi.fn(() => null),
}));

import { getToken } from '../src/stores/auth.svelte.js';

import {
  apiConfig, apiTestHost, apiCompare, apiBatch, apiSave,
  apiListDocuments, apiGetDocument, apiUpdateDocumentTitle,
  apiGetTestruns, apiGetTestrun, apiDeleteTestrun,
  apiParseOpenapi, apiDiffSchemas,
  apiGenerateToken, apiValidateToken,
} from './api.js';

// Mock fetch globally
const mockJson = vi.fn();
const mockFetch = vi.fn(() => Promise.resolve({ ok: true, json: mockJson }));

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch);
  mockJson.mockResolvedValue({ status: 'ok' });
  mockFetch.mockClear();
  mockJson.mockClear();
  getToken.mockReturnValue(null);
  // Reset to successful response by default
  mockFetch.mockImplementation(() => Promise.resolve({ ok: true, json: mockJson }));
});

describe('apiConfig', () => {
  it('fetches /api/config', async () => {
    await apiConfig();
    expect(mockFetch).toHaveBeenCalledWith('/api/config', {});
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
  it('POSTs state with documentId and testrunType', async () => {
    await apiSave({ data: 1 }, 'doc-123', 'manual');
    expect(mockFetch).toHaveBeenCalledWith('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: { data: 1 }, documentId: 'doc-123', testrunType: 'manual' }),
    });
  });

  it('includes testrunNumber in request body when provided', async () => {
    await apiSave({ data: 2 }, 'doc-456', 'save', 7);
    expect(mockFetch).toHaveBeenCalledWith('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: { data: 2 }, documentId: 'doc-456', testrunType: 'save', testrunNumber: 7 }),
    });
  });
});

describe('apiListDocuments', () => {
  it('fetches /api/documents', async () => {
    await apiListDocuments();
    expect(mockFetch).toHaveBeenCalledWith('/api/documents', {});
  });
});

describe('apiGetDocument', () => {
  it('fetches specific document', async () => {
    await apiGetDocument('abc');
    expect(mockFetch).toHaveBeenCalledWith('/api/documents/abc', {});
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

describe('apiGetTestruns', () => {
  it('fetches testruns for a document', async () => {
    await apiGetTestruns('abc');
    expect(mockFetch).toHaveBeenCalledWith('/api/documents/abc/testruns', {});
  });
});

describe('apiGetTestrun', () => {
  it('fetches specific testrun', async () => {
    await apiGetTestrun('abc', 3);
    expect(mockFetch).toHaveBeenCalledWith('/api/documents/abc/testruns/3', {});
  });
});

describe('apiDeleteTestrun', () => {
  it('DELETEs specific testrun', async () => {
    await apiDeleteTestrun('abc', 2);
    expect(mockFetch).toHaveBeenCalledWith('/api/documents/abc/testruns/2', { method: 'DELETE' });
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

describe('apiGenerateToken', () => {
  it('POSTs to /api/auth/token', async () => {
    await apiGenerateToken();
    expect(mockFetch).toHaveBeenCalledWith('/api/auth/token', { method: 'POST' });
  });
});

describe('apiValidateToken', () => {
  it('fetches /api/auth/validate', async () => {
    await apiValidateToken();
    expect(mockFetch).toHaveBeenCalledWith('/api/auth/validate', {});
  });
});

describe('apiFetch token injection', () => {
  it('adds Authorization header when token is present', async () => {
    getToken.mockReturnValue('my-secret-token');
    await apiConfig();
    expect(mockFetch).toHaveBeenCalledWith('/api/config', {
      headers: { 'Authorization': 'Bearer my-secret-token' },
    });
  });

  it('merges Authorization with existing headers', async () => {
    getToken.mockReturnValue('tok-42');
    await apiTestHost('http://example.com', 'auth');
    expect(mockFetch).toHaveBeenCalledWith('/api/test-host', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer tok-42',
      },
      body: JSON.stringify({ host: 'http://example.com', auth: 'auth' }),
    });
  });

  it('does not add Authorization header when token is null', async () => {
    getToken.mockReturnValue(null);
    await apiConfig();
    expect(mockFetch).toHaveBeenCalledWith('/api/config', {});
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

  it('apiGetTestruns throws on server error', async () => {
    await expect(apiGetTestruns('abc')).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiGetTestrun throws on server error', async () => {
    await expect(apiGetTestrun('abc', 1)).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiDeleteTestrun throws on server error', async () => {
    await expect(apiDeleteTestrun('abc', 1)).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiParseOpenapi throws on server error', async () => {
    await expect(apiParseOpenapi(new FormData())).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiDiffSchemas throws on server error', async () => {
    await expect(apiDiffSchemas(new FormData())).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiGenerateToken throws on server error', async () => {
    await expect(apiGenerateToken()).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('apiValidateToken throws on server error', async () => {
    await expect(apiValidateToken()).rejects.toThrow('HTTP 500: Internal Server Error');
  });

  it('includes status code in error for 502 Bad Gateway', async () => {
    mockFetch.mockImplementation(() =>
      Promise.resolve({ ok: false, status: 502, statusText: 'Bad Gateway', json: mockJson })
    );
    await expect(apiConfig()).rejects.toThrow('HTTP 502: Bad Gateway');
  });
});

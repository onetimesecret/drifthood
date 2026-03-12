import { describe, it, expect } from 'vitest';
import { statusLabel, contentLength, fmtHeaders, fmtBody, buildContextLines, buildDriftSummary, buildSideMd, buildFullMd } from './export.js';

describe('statusLabel', () => {
  it('returns status when present', () => {
    expect(statusLabel({ status: 200 })).toBe(200);
  });
  it('returns "ERR" when status is null', () => {
    expect(statusLabel({ status: null })).toBe('ERR');
  });
  it('returns "ERR" when status is undefined', () => {
    expect(statusLabel({})).toBe('ERR');
  });
});

describe('contentLength', () => {
  it('returns content-length header', () => {
    expect(contentLength({ headers: { 'content-length': '1234' } })).toBe('1234');
  });
  it('returns Content-Length header (capitalized)', () => {
    expect(contentLength({ headers: { 'Content-Length': '5678' } })).toBe('5678');
  });
  it('estimates from string body', () => {
    expect(contentLength({ headers: {}, body: 'hello' })).toBe('~5');
  });
  it('estimates from object body', () => {
    const result = contentLength({ headers: {}, body: { a: 1 } });
    expect(result).toMatch(/^~/);
  });
  it('returns "?" for missing resp', () => {
    expect(contentLength(null)).toBe('?');
  });
  it('returns "?" for missing headers', () => {
    expect(contentLength({})).toBe('?');
  });
});

describe('fmtHeaders', () => {
  it('formats header entries', () => {
    expect(fmtHeaders({ 'Content-Type': 'application/json', 'X-Custom': 'val' }))
      .toBe('Content-Type: application/json\nX-Custom: val');
  });
  it('returns "(none)" for empty/null headers', () => {
    expect(fmtHeaders(null)).toBe('(none)');
    expect(fmtHeaders({})).toBe('(none)');
  });
});

describe('fmtBody', () => {
  it('returns string body as-is', () => {
    expect(fmtBody('raw text')).toBe('raw text');
  });
  it('JSON-stringifies object body', () => {
    expect(fmtBody({ a: 1 })).toBe('{\n  "a": 1\n}');
  });
  it('returns "(empty)" for null', () => {
    expect(fmtBody(null)).toBe('(empty)');
  });
});

const baseContext = {
  title: 'Test Session',
  memo: 'some notes',
  hostA: 'http://localhost:3000',
  hostB: 'http://localhost:4000',
  memoA: 'v1',
  memoB: 'v2',
};

describe('buildContextLines', () => {
  it('builds markdown context lines', () => {
    const lines = buildContextLines('md', baseContext);
    expect(lines[0]).toBe('# Test Session');
    expect(lines[1]).toBe('some notes');
    expect(lines[2]).toContain('**Hosts:**');
    expect(lines[2]).toContain('(v1)');
    expect(lines[2]).toContain('(v2)');
  });

  it('builds text context lines', () => {
    const lines = buildContextLines('text', baseContext);
    expect(lines[0]).toBe('Test Session');
    expect(lines[2]).toContain('Hosts:');
  });

  it('omits title/memo when empty', () => {
    const lines = buildContextLines('md', { ...baseContext, title: '', memo: '' });
    expect(lines[0]).toContain('**Hosts:**');
  });

  it('omits memos from host labels when empty', () => {
    const lines = buildContextLines('text', { ...baseContext, memoA: '', memoB: '' });
    const hostLine = lines.find(l => l.includes('Hosts:'));
    expect(hostLine).not.toContain('()');
  });
});

describe('buildDriftSummary', () => {
  const result = {
    method: 'GET',
    path: '/api/status',
    response_a: { status: 200, headers: { 'x-ver': '1' }, elapsed_ms: 50, body: '{}' },
    response_b: { status: 200, headers: { 'x-ver': '2' }, elapsed_ms: 55, body: '{}' },
    diff: {
      values_changed: {
        "root['version']": { old_value: '1.0', new_value: '2.0' },
      },
    },
    ignored_paths: ["root['timestamp']"],
  };

  it('includes DRIFT header', () => {
    const summary = buildDriftSummary(result, baseContext);
    expect(summary).toContain('DRIFT: GET /api/status');
  });

  it('includes status and size', () => {
    const summary = buildDriftSummary(result, baseContext);
    expect(summary).toContain('Status: 200/200');
  });

  it('includes header diffs', () => {
    const summary = buildDriftSummary(result, baseContext);
    expect(summary).toContain('Headers diff:');
    expect(summary).toContain('x-ver');
  });

  it('includes body diffs', () => {
    const summary = buildDriftSummary(result, baseContext);
    expect(summary).toContain('Body diff:');
    expect(summary).toContain('version');
  });

  it('includes ignored paths', () => {
    const summary = buildDriftSummary(result, baseContext);
    expect(summary).toContain('Ignored (1)');
    expect(summary).toContain('timestamp');
  });
});

describe('buildSideMd', () => {
  const result = {
    method: 'GET',
    path: '/api/status',
    response_a: { status: 200, request_url: 'http://a/api/status', request_headers: {}, headers: {}, body: '{}', elapsed_ms: 10 },
    response_b: { status: 201, request_url: 'http://b/api/status', request_headers: {}, headers: {}, body: '{}', elapsed_ms: 20 },
  };

  it('renders side A markdown', () => {
    const md = buildSideMd(result, 'a', { memoA: 'staging', memoB: 'prod' });
    expect(md).toContain('### Host A (staging)');
    expect(md).toContain('**Status:** 200');
  });

  it('renders side B markdown', () => {
    const md = buildSideMd(result, 'b', { memoA: '', memoB: 'prod' });
    expect(md).toContain('### Host B (prod)');
    expect(md).toContain('**Status:** 201');
  });

  it('omits memo when empty', () => {
    const md = buildSideMd(result, 'a', { memoA: '', memoB: '' });
    expect(md).toContain('### Host A\n');
  });
});

describe('buildFullMd', () => {
  const result = {
    method: 'POST',
    path: '/api/share',
    has_drift: true,
    response_a: { status: 200, request_url: 'http://a/api/share', request_headers: {}, headers: {}, body: {}, elapsed_ms: 10 },
    response_b: { status: 200, request_url: 'http://b/api/share', request_headers: {}, headers: {}, body: {}, elapsed_ms: 20 },
    diff: {
      dictionary_item_added: { "root['new_field']": 'value' },
    },
    ignored_paths: [],
  };

  it('includes method and path', () => {
    const md = buildFullMd(result, baseContext);
    expect(md).toContain('## POST /api/share');
  });

  it('includes drift result', () => {
    const md = buildFullMd(result, baseContext);
    expect(md).toContain('**Result:** DRIFT');
  });

  it('includes differences section', () => {
    const md = buildFullMd(result, baseContext);
    expect(md).toContain('## Differences');
    expect(md).toContain('Added in B');
  });

  it('includes both sides', () => {
    const md = buildFullMd(result, baseContext);
    expect(md).toContain('### Host A');
    expect(md).toContain('### Host B');
  });

  it('shows OK for non-drift result', () => {
    const okResult = { ...result, has_drift: false, diff: {} };
    const md = buildFullMd(okResult, baseContext);
    expect(md).toContain('**Result:** OK');
  });
});

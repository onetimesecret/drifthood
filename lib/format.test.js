import { describe, it, expect } from 'vitest';
import { esc, escHtml, toDiffPath, prettifyPath, relativeTime, driftIndicator, stripOpIdPrefix } from './format.js';

describe('esc', () => {
  it('escapes double quotes', () => {
    expect(esc('a"b')).toBe('a&quot;b');
  });
  it('leaves strings without quotes unchanged', () => {
    expect(esc('hello')).toBe('hello');
  });
  it('escapes multiple quotes', () => {
    expect(esc('"a""b"')).toBe('&quot;a&quot;&quot;b&quot;');
  });
});

describe('escHtml', () => {
  it('escapes all HTML entities', () => {
    expect(escHtml('<div class="x">&')).toBe('&lt;div class=&quot;x&quot;&gt;&amp;');
  });
  it('returns "null" for null input', () => {
    expect(escHtml(null)).toBe('null');
  });
  it('converts numbers to string', () => {
    expect(escHtml(42)).toBe('42');
  });
});

describe('toDiffPath', () => {
  it('converts dot notation to DeepDiff path', () => {
    expect(toDiffPath('body.created')).toBe("root['body']['created']");
  });
  it('passes through existing DeepDiff paths', () => {
    expect(toDiffPath("root['status']")).toBe("root['status']");
  });
  it('handles single segment', () => {
    expect(toDiffPath('status')).toBe("root['status']");
  });
  it('returns falsy input unchanged', () => {
    expect(toDiffPath('')).toBe('');
    expect(toDiffPath(null)).toBe(null);
  });
});

describe('prettifyPath', () => {
  it('converts DeepDiff path to dot notation', () => {
    expect(prettifyPath("root['body']['metadata']['created']")).toBe('body.metadata.created');
  });
  it('handles single key', () => {
    expect(prettifyPath("root['status']")).toBe('status');
  });
  it('returns falsy input unchanged', () => {
    expect(prettifyPath('')).toBe('');
    expect(prettifyPath(null)).toBe(null);
  });
});

describe('relativeTime', () => {
  it('returns "just now" for recent timestamps', () => {
    const now = new Date().toISOString();
    expect(relativeTime(now)).toBe('just now');
  });
  it('returns minutes ago', () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(relativeTime(fiveMinAgo)).toBe('5m ago');
  });
  it('returns hours ago', () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    expect(relativeTime(twoHoursAgo)).toBe('2h ago');
  });
  it('returns date for older timestamps', () => {
    const old = '2024-01-15T09:30:00Z';
    expect(relativeTime(old)).toBe('01-15 09:30');
  });
});

describe('driftIndicator', () => {
  it('returns empty circle when nothing has run', () => {
    const result = driftIndicator({ endpoint_count: 5, ok_count: 0, drift_count: 0 });
    expect(result.title).toBe('not run');
    expect(result.color).toBe('var(--text-dim)');
  });
  it('returns green when all OK', () => {
    const result = driftIndicator({ endpoint_count: 3, ok_count: 3, drift_count: 0 });
    expect(result.title).toBe('all OK');
    expect(result.color).toBe('var(--green)');
  });
  it('returns yellow when mostly OK', () => {
    const result = driftIndicator({ endpoint_count: 10, ok_count: 9, drift_count: 1 });
    expect(result.title).toBe('1 drift');
    expect(result.color).toBe('var(--yellow)');
  });
  it('returns red when many drifts', () => {
    const result = driftIndicator({ endpoint_count: 5, ok_count: 1, drift_count: 4 });
    expect(result.title).toBe('4 drifts');
    expect(result.color).toBe('var(--red)');
  });
});

describe('stripOpIdPrefix', () => {
  it('strips version prefix', () => {
    expect(stripOpIdPrefix('v2_concealSecret')).toBe('concealSecret');
  });
  it('strips colonel prefix', () => {
    expect(stripOpIdPrefix('colonel_getStatus')).toBe('getStatus');
  });
  it('strips account prefix', () => {
    expect(stripOpIdPrefix('account_getInfo')).toBe('getInfo');
  });
  it('strips guest prefix', () => {
    expect(stripOpIdPrefix('guest_createSecret')).toBe('createSecret');
  });
  it('returns empty string for falsy input', () => {
    expect(stripOpIdPrefix('')).toBe('');
    expect(stripOpIdPrefix(null)).toBe('');
  });
  it('leaves labels without known prefix unchanged', () => {
    expect(stripOpIdPrefix('someFunction')).toBe('someFunction');
  });
});

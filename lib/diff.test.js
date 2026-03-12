import { describe, it, expect } from 'vitest';
import { DIFF_CATEGORIES, DIFF_CAT_KEYS, parseDiff, SUMMARIZE_DEFAULTS, summarize, jsonSummary } from './diff.js';

describe('DIFF_CATEGORIES', () => {
  it('has 6 categories', () => {
    expect(DIFF_CATEGORIES).toHaveLength(6);
  });
  it('each category has required fields', () => {
    for (const cat of DIFF_CATEGORIES) {
      expect(cat).toHaveProperty('key');
      expect(cat).toHaveProperty('label');
      expect(cat).toHaveProperty('textLabel');
      expect(cat).toHaveProperty('kind');
    }
  });
});

describe('DIFF_CAT_KEYS', () => {
  it('is a Set of category keys', () => {
    expect(DIFF_CAT_KEYS).toBeInstanceOf(Set);
    expect(DIFF_CAT_KEYS.has('values_changed')).toBe(true);
    expect(DIFF_CAT_KEYS.has('dictionary_item_added')).toBe(true);
    expect(DIFF_CAT_KEYS.has('nonexistent')).toBe(false);
  });
});

describe('parseDiff', () => {
  it('returns empty array for null/undefined', () => {
    expect(parseDiff(null)).toEqual([]);
    expect(parseDiff(undefined)).toEqual([]);
  });

  it('parses values_changed with old/new values', () => {
    const diff = {
      values_changed: {
        "root['status']": { old_value: 200, new_value: 201 },
      },
    };
    const sections = parseDiff(diff);
    expect(sections).toHaveLength(1);
    expect(sections[0].key).toBe('values_changed');
    expect(sections[0].entries).toHaveLength(1);
    expect(sections[0].entries[0].oldVal).toBe(200);
    expect(sections[0].entries[0].newVal).toBe(201);
  });

  it('parses dictionary_item_added with raw values', () => {
    const diff = {
      dictionary_item_added: {
        "root['newField']": 'hello',
      },
    };
    const sections = parseDiff(diff);
    expect(sections).toHaveLength(1);
    expect(sections[0].key).toBe('dictionary_item_added');
    expect(sections[0].entries[0].raw).toBe('hello');
  });

  it('catches unknown categories', () => {
    const diff = {
      some_weird_category: { foo: 'bar' },
    };
    const sections = parseDiff(diff);
    expect(sections).toHaveLength(1);
    expect(sections[0].key).toBe('some_weird_category');
    expect(sections[0].kind).toBe('other');
  });

  it('handles multiple categories', () => {
    const diff = {
      values_changed: { "root['a']": { old_value: 1, new_value: 2 } },
      dictionary_item_added: { "root['b']": 'new' },
    };
    const sections = parseDiff(diff);
    expect(sections).toHaveLength(2);
  });
});

describe('summarize', () => {
  it('returns null/undefined as-is', () => {
    expect(summarize(null)).toBe(null);
    expect(summarize(undefined)).toBe(undefined);
  });

  it('returns short strings unchanged', () => {
    expect(summarize('hello')).toBe('hello');
  });

  it('truncates long strings', () => {
    const long = 'x'.repeat(2000);
    const result = summarize(long);
    expect(result).toContain('... (2000 chars total)');
    expect(result.length).toBeLessThan(2000);
  });

  it('truncates large arrays', () => {
    const arr = Array.from({ length: 20 }, (_, i) => i);
    const result = summarize(arr);
    expect(result).toHaveLength(6); // 5 items + "... (15 more, 20 total)"
    expect(result[5]).toContain('15 more');
  });

  it('truncates large objects', () => {
    const obj = {};
    for (let i = 0; i < 20; i++) obj[`key${i}`] = i;
    const result = summarize(obj);
    const keys = Object.keys(result);
    expect(keys).toHaveLength(11); // 10 shown + 1 "more" key
  });

  it('returns primitives as-is', () => {
    expect(summarize(42)).toBe(42);
    expect(summarize(true)).toBe(true);
  });
});

describe('jsonSummary', () => {
  it('returns JSON string of summarized value', () => {
    expect(jsonSummary({ a: 1 })).toBe('{"a":1}');
  });
  it('respects indent parameter', () => {
    expect(jsonSummary({ a: 1 }, 2)).toBe('{\n  "a": 1\n}');
  });
});

describe('SUMMARIZE_DEFAULTS', () => {
  it('has expected default values', () => {
    expect(SUMMARIZE_DEFAULTS.maxStr).toBe(1024);
    expect(SUMMARIZE_DEFAULTS.maxArr).toBe(5);
    expect(SUMMARIZE_DEFAULTS.maxKeys).toBe(10);
    expect(SUMMARIZE_DEFAULTS.depth).toBe(0);
    expect(SUMMARIZE_DEFAULTS.maxDepth).toBe(2);
  });
});

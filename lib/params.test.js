import { describe, it, expect } from 'vitest';
import { setNestedValue, flattenObj, parseKvString } from './params.js';

describe('setNestedValue', () => {
  it('sets a top-level value', () => {
    const obj = {};
    setNestedValue(obj, 'key', 'val');
    expect(obj.key).toBe('val');
  });

  it('sets a nested value', () => {
    const obj = {};
    setNestedValue(obj, 'a.b.c', 'deep');
    expect(obj.a.b.c).toBe('deep');
  });

  it('creates intermediate objects', () => {
    const obj = {};
    setNestedValue(obj, 'x.y', 'z');
    expect(typeof obj.x).toBe('object');
    expect(obj.x.y).toBe('z');
  });

  it('coerces "true" to boolean', () => {
    const obj = {};
    setNestedValue(obj, 'flag', 'true');
    expect(obj.flag).toBe(true);
  });

  it('coerces "false" to boolean', () => {
    const obj = {};
    setNestedValue(obj, 'flag', 'false');
    expect(obj.flag).toBe(false);
  });

  it('coerces numeric strings to numbers', () => {
    const obj = {};
    setNestedValue(obj, 'count', '42');
    expect(obj.count).toBe(42);
  });

  it('preserves non-numeric strings', () => {
    const obj = {};
    setNestedValue(obj, 'name', 'alice');
    expect(obj.name).toBe('alice');
  });
});

describe('flattenObj', () => {
  it('flattens a nested object', () => {
    const result = flattenObj({ a: { b: 1, c: 2 } });
    expect(result).toEqual({ 'a.b': 1, 'a.c': 2 });
  });

  it('handles flat objects', () => {
    const result = flattenObj({ x: 1, y: 2 });
    expect(result).toEqual({ x: 1, y: 2 });
  });

  it('handles deeply nested objects', () => {
    const result = flattenObj({ a: { b: { c: 3 } } });
    expect(result).toEqual({ 'a.b.c': 3 });
  });

  it('preserves arrays as values', () => {
    const result = flattenObj({ a: [1, 2] });
    expect(result).toEqual({ a: [1, 2] });
  });

  it('uses prefix parameter', () => {
    const result = flattenObj({ b: 1 }, 'a');
    expect(result).toEqual({ 'a.b': 1 });
  });
});

describe('parseKvString', () => {
  it('parses key=val pairs', () => {
    const result = parseKvString('key=val&key2=val2');
    expect(result).toEqual([
      { key: 'key', val: 'val' },
      { key: 'key2', val: 'val2' },
    ]);
  });

  it('handles keys without values', () => {
    const result = parseKvString('keyonly');
    expect(result).toEqual([{ key: 'keyonly', val: '' }]);
  });

  it('decodes URI components', () => {
    const result = parseKvString('name=hello%20world');
    expect(result).toEqual([{ key: 'name', val: 'hello world' }]);
  });

  it('returns empty array for empty/null input', () => {
    expect(parseKvString('')).toEqual([]);
    expect(parseKvString(null)).toEqual([]);
    expect(parseKvString(undefined)).toEqual([]);
  });

  it('filters out empty keys', () => {
    const result = parseKvString('&a=1&');
    expect(result).toEqual([{ key: 'a', val: '1' }]);
  });

  it('handles values containing equals signs', () => {
    const result = parseKvString('expr=a=b');
    expect(result).toEqual([{ key: 'expr', val: 'a=b' }]);
  });
});

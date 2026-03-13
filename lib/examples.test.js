import { describe, it, expect } from 'vitest';
import { DD_VERSION, EXAMPLES } from './examples.js';

describe('DD_VERSION', () => {
  it('is 0.5.0', () => {
    expect(DD_VERSION).toBe('0.5.0');
  });
});

describe('EXAMPLES', () => {
  it('has four example sets', () => {
    expect(Object.keys(EXAMPLES)).toEqual(['mixed', 'query-only', 'form-only', 'json-only']);
  });

  it('each example has required fields', () => {
    for (const [name, endpoints] of Object.entries(EXAMPLES)) {
      expect(Array.isArray(endpoints)).toBe(true);
      for (const ep of endpoints) {
        expect(ep).toHaveProperty('m');
        expect(ep).toHaveProperty('l');
        expect(ep).toHaveProperty('p');
        expect(ep).toHaveProperty('ct');
        expect(typeof ep.b).toBe('string');
      }
    }
  });

  it('query-only examples all use query content type', () => {
    for (const ep of EXAMPLES['query-only']) {
      expect(ep.ct).toBe('query');
    }
  });

  it('json-only examples all use application/json', () => {
    for (const ep of EXAMPLES['json-only']) {
      expect(ep.ct).toBe('application/json');
    }
  });

  it('form-only examples all use form-urlencoded', () => {
    for (const ep of EXAMPLES['form-only']) {
      expect(ep.ct).toBe('application/x-www-form-urlencoded');
    }
  });
});

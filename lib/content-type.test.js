import { describe, it, expect } from 'vitest';
import { CT, CT_CYCLE, ctInfo } from './content-type.js';

describe('CT', () => {
  it('has query, form, json entries', () => {
    expect(CT.query.value).toBe('query');
    expect(CT.form.value).toBe('application/x-www-form-urlencoded');
    expect(CT.json.value).toBe('application/json');
  });
  it('each entry has label, cls, placeholder', () => {
    for (const key of ['query', 'form', 'json']) {
      expect(CT[key]).toHaveProperty('label');
      expect(CT[key]).toHaveProperty('cls');
      expect(CT[key]).toHaveProperty('placeholder');
    }
  });
});

describe('CT_CYCLE', () => {
  it('has the three content types in order', () => {
    expect(CT_CYCLE).toEqual(['query', 'form', 'json']);
  });
});

describe('ctInfo', () => {
  it('returns CT.json for application/json', () => {
    expect(ctInfo('application/json')).toBe(CT.json);
  });
  it('returns CT.form for application/x-www-form-urlencoded', () => {
    expect(ctInfo('application/x-www-form-urlencoded')).toBe(CT.form);
  });
  it('returns CT.query for "query"', () => {
    expect(ctInfo('query')).toBe(CT.query);
  });
  it('returns CT.query for unknown values', () => {
    expect(ctInfo('text/plain')).toBe(CT.query);
    expect(ctInfo('')).toBe(CT.query);
  });
});

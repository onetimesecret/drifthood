import { describe, it, expect } from 'vitest';
import { stateFingerprint } from './state.js';

describe('stateFingerprint', () => {
  it('returns a string', () => {
    const result = stateFingerprint({ endpoints: [] });
    expect(typeof result).toBe('string');
  });

  it('produces same hash for same data', () => {
    const state = { endpoints: [{ method: 'GET', path: '/api/status' }] };
    expect(stateFingerprint(state)).toBe(stateFingerprint(state));
  });

  it('produces different hash for different data', () => {
    const a = { hostA: 'http://localhost:3000' };
    const b = { hostA: 'http://localhost:4000' };
    expect(stateFingerprint(a)).not.toBe(stateFingerprint(b));
  });

  it('ignores volatile fields (savedAt, sessionNumber, testrunNumber, version)', () => {
    const base = { endpoints: [{ method: 'GET' }] };
    const withVolatile = { ...base, savedAt: '2026-01-01', sessionNumber: 5, testrunNumber: 3, version: '0.4.0' };
    expect(stateFingerprint(base)).toBe(stateFingerprint(withVolatile));
  });

  it('is order-independent for keys', () => {
    const a = { x: 1, y: 2 };
    const b = { y: 2, x: 1 };
    expect(stateFingerprint(a)).toBe(stateFingerprint(b));
  });
});

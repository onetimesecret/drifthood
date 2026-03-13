import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import DiffView from '../../src/components/DiffView.svelte';

// Mock the session store — DiffView reads session.title, session.memo, etc. for copy
vi.mock('../../src/stores/session.svelte.js', () => {
  const envA = { id: 'env-a', name: 'v1', baseUrl: 'http://localhost:3000', auth: '', memo: '', metadata: {} };
  const envB = { id: 'env-b', name: 'v2', baseUrl: 'http://localhost:4000', auth: '', memo: '', metadata: {} };
  return {
    session: {
      title: 'Test Session',
      memo: '',
      environments: [envA, envB],
      selectedA: 'env-a',
      selectedB: 'env-b',
      ignorePaths: [],
    },
    getEnvA: () => envA,
    getEnvB: () => envB,
  };
});

// Mock clipboard API
beforeEach(() => {
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

function makeResult(overrides = {}) {
  return {
    method: 'GET',
    path: '/api/v1/status',
    has_drift: false,
    diff: {},
    response_a: { status: 200, headers: {}, body: { status: 'ok' }, elapsed_ms: 42 },
    response_b: { status: 200, headers: {}, body: { status: 'ok' }, elapsed_ms: 38 },
    ignored_paths: [],
    ...overrides,
  };
}

describe('DiffView', () => {
  describe('no drift', () => {
    it('renders "No differences detected" for matching responses', () => {
      render(DiffView, {
        props: { result: makeResult(), endpointId: 1 },
      });
      expect(screen.getByText('No differences detected.')).toBeTruthy();
    });

    it('shows ignored fields count when paths are ignored and responses are real', () => {
      const result = makeResult({
        ignored_paths: ["root['created']", "root['updated']"],
      });
      render(DiffView, {
        props: { result, endpointId: 1 },
      });
      expect(screen.getByText('2 fields ignored')).toBeTruthy();
    });

    it('does not show ignored fields count on connection errors', () => {
      const result = makeResult({
        response_a: { status: null, error: 'Connection refused', headers: {}, body: null, elapsed_ms: null },
        response_b: { status: null, error: 'Connection refused', headers: {}, body: null, elapsed_ms: null },
        ignored_paths: ["root['created']", "root['updated']"],
      });
      render(DiffView, {
        props: { result, endpointId: 1 },
      });
      // Should NOT show "2 fields ignored" because both sides are connection errors
      expect(screen.queryByText('2 fields ignored')).toBeNull();
    });
  });

  describe('with drift', () => {
    it('renders diff sections for values_changed', () => {
      const result = makeResult({
        has_drift: true,
        diff: {
          values_changed: {
            "root['version']": { old_value: '1.0', new_value: '2.0' },
          },
        },
      });
      render(DiffView, {
        props: { result, endpointId: 1 },
      });
      expect(screen.getByText('Values Changed')).toBeTruthy();
      expect(screen.getByText('version')).toBeTruthy();
    });

    it('renders diff sections for dictionary_item_added', () => {
      const result = makeResult({
        has_drift: true,
        diff: {
          dictionary_item_added: {
            "root['newField']": 'hello',
          },
        },
      });
      render(DiffView, {
        props: { result, endpointId: 1 },
      });
      expect(screen.getByText('Added in B')).toBeTruthy();
      expect(screen.getByText('newField')).toBeTruthy();
    });

    it('renders diff sections for dictionary_item_removed', () => {
      const result = makeResult({
        has_drift: true,
        diff: {
          dictionary_item_removed: {
            "root['oldField']": 'gone',
          },
        },
      });
      render(DiffView, {
        props: { result, endpointId: 1 },
      });
      expect(screen.getByText('Removed from B')).toBeTruthy();
    });

    it('shows Copy summary button on drift', () => {
      const result = makeResult({
        has_drift: true,
        diff: {
          values_changed: {
            "root['status']": { old_value: 'ok', new_value: 'error' },
          },
        },
      });
      render(DiffView, {
        props: { result, endpointId: 1 },
      });
      expect(screen.getByText('Copy summary')).toBeTruthy();
    });

    it('renders multiple diff categories', () => {
      const result = makeResult({
        has_drift: true,
        diff: {
          values_changed: {
            "root['a']": { old_value: 1, new_value: 2 },
          },
          dictionary_item_added: {
            "root['b']": 'new',
          },
        },
      });
      render(DiffView, {
        props: { result, endpointId: 1 },
      });
      expect(screen.getByText('Values Changed')).toBeTruthy();
      expect(screen.getByText('Added in B')).toBeTruthy();
    });

    it('shows type change entries with old and new types', () => {
      const result = makeResult({
        has_drift: true,
        diff: {
          type_changes: {
            "root['count']": { old_value: '5', new_value: 5, old_type: 'str', new_type: 'int' },
          },
        },
      });
      render(DiffView, {
        props: { result, endpointId: 1 },
      });
      expect(screen.getByText('Type Changes')).toBeTruthy();
      expect(screen.getByText('count')).toBeTruthy();
      // The old_type and new_type should be rendered in parentheses
      expect(screen.getByText('(str)')).toBeTruthy();
      expect(screen.getByText('(int)')).toBeTruthy();
    });
  });

  describe('edge cases', () => {
    it('renders with null result without crashing', () => {
      // When result is null, result?.has_drift is undefined (falsy),
      // so the component falls into the "no drift" branch and shows the OK message.
      render(DiffView, {
        props: { result: null, endpointId: 1 },
      });
      expect(screen.getByText('No differences detected.')).toBeTruthy();
      expect(screen.queryByText('Values Changed')).toBeNull();
    });

    it('renders with empty diff object on drift', () => {
      const result = makeResult({
        has_drift: true,
        diff: {},
      });
      render(DiffView, {
        props: { result, endpointId: 1 },
      });
      // has_drift is true but diff is empty — should still show Copy summary
      expect(screen.getByText('Copy summary')).toBeTruthy();
    });

    it('renders with undefined ignored_paths', () => {
      const result = makeResult({
        ignored_paths: undefined,
      });
      render(DiffView, {
        props: { result, endpointId: 1 },
      });
      expect(screen.getByText('No differences detected.')).toBeTruthy();
      expect(screen.queryByText(/fields ignored/)).toBeNull();
    });
  });
});

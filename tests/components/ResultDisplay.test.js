import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import ResultDisplay from '../../src/components/ResultDisplay.svelte';

// Mock the session store
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

// Mock clipboard
beforeEach(() => {
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

function makeEndpoint(resultOverrides = {}, endpointOverrides = {}) {
  const defaultResult = {
    method: 'GET',
    path: '/api/v1/status',
    has_drift: false,
    diff: {},
    response_a: { status: 200, headers: { 'content-length': '42' }, body: { status: 'ok' }, elapsed_ms: 42 },
    response_b: { status: 200, headers: { 'content-length': '42' }, body: { status: 'ok' }, elapsed_ms: 38 },
    ignored_paths: [],
    request_body: null,
    request_content_type: 'query',
    ...resultOverrides,
  };
  return {
    id: 1,
    method: 'GET',
    path: '/api/v1/status',
    label: 'status',
    body: '',
    contentType: 'query',
    state: 'done-ok',
    result: defaultResult,
    ...endpointOverrides,
  };
}

describe('ResultDisplay', () => {
  describe('basic rendering', () => {
    it('renders without crashing with a valid endpoint', () => {
      const endpoint = makeEndpoint();
      render(ResultDisplay, { props: { endpoint } });
      // The badge and meta info should be visible
      expect(screen.getByText('OK')).toBeTruthy();
    });

    it('shows OK badge for matching responses', () => {
      const endpoint = makeEndpoint();
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText('OK')).toBeTruthy();
    });

    it('shows DRIFT badge when has_drift is true', () => {
      const endpoint = makeEndpoint({
        has_drift: true,
        diff: { values_changed: { "root['v']": { old_value: 1, new_value: 2 } } },
      }, { state: 'done-drift' });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText('DRIFT')).toBeTruthy();
    });

    it('shows MATCH badge when both sides have errors but no drift', () => {
      const endpoint = makeEndpoint({
        has_drift: false,
        response_a: { status: 500, headers: {}, body: { error: 'internal' }, elapsed_ms: 10 },
        response_b: { status: 500, headers: {}, body: { error: 'internal' }, elapsed_ms: 12 },
      });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText('MATCH')).toBeTruthy();
    });

    it('shows MATCH badge when both sides have connection errors', () => {
      const endpoint = makeEndpoint({
        has_drift: false,
        response_a: { status: null, error: 'Connection refused', headers: {}, body: null, elapsed_ms: null },
        response_b: { status: null, error: 'Connection refused', headers: {}, body: null, elapsed_ms: null },
      });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText('MATCH')).toBeTruthy();
    });
  });

  describe('meta information', () => {
    it('displays status codes for both hosts', () => {
      const endpoint = makeEndpoint();
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText(/200\/200/)).toBeTruthy();
    });

    it('displays timing information', () => {
      const endpoint = makeEndpoint();
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText(/42\/38ms/)).toBeTruthy();
    });

    it('shows ERR for null status codes', () => {
      const endpoint = makeEndpoint({
        response_a: { status: null, error: 'timeout', headers: {}, body: null, elapsed_ms: null },
        response_b: { status: 200, headers: {}, body: {}, elapsed_ms: 10 },
      });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText(/ERR\/200/)).toBeTruthy();
    });
  });

  describe('response body panels', () => {
    it('shows environment name labels with status codes', () => {
      // Result display shows bodies in an expandable area. DRIFT results auto-expand.
      const endpoint = makeEndpoint({
        has_drift: true,
        diff: { values_changed: { "root['x']": { old_value: 1, new_value: 2 } } },
      }, { state: 'done-drift' });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText('v1 (200)')).toBeTruthy();
      expect(screen.getByText('v2 (200)')).toBeTruthy();
    });

    it('shows ERR for error responses in panel labels', () => {
      const endpoint = makeEndpoint({
        has_drift: true,
        diff: {},
        response_a: { status: null, error: 'timeout', headers: {}, body: null, elapsed_ms: null },
        response_b: { status: 200, headers: {}, body: {}, elapsed_ms: 10 },
      }, { state: 'done-drift' });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText('v1 (ERR)')).toBeTruthy();
      expect(screen.getByText('v2 (200)')).toBeTruthy();
    });
  });

  describe('toggle buttons', () => {
    it('has "Show raw diff JSON" button in expanded view', () => {
      // DRIFT auto-expands the detail panel
      const endpoint = makeEndpoint({
        has_drift: true,
        diff: { values_changed: { "root['x']": { old_value: 1, new_value: 2 } } },
      }, { state: 'done-drift' });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText('Show raw diff JSON')).toBeTruthy();
    });

    it('has "Show request headers" button', () => {
      const endpoint = makeEndpoint({
        has_drift: true,
        diff: { values_changed: { "root['x']": { old_value: 1, new_value: 2 } } },
      }, { state: 'done-drift' });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText('Show request headers')).toBeTruthy();
    });

    it('has "Show response headers" button', () => {
      const endpoint = makeEndpoint({
        has_drift: true,
        diff: { values_changed: { "root['x']": { old_value: 1, new_value: 2 } } },
      }, { state: 'done-drift' });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText('Show response headers')).toBeTruthy();
    });

    it('shows "Show request body" when request has a body', () => {
      const endpoint = makeEndpoint({
        has_drift: true,
        diff: {},
        request_body: '{"key":"val"}',
        request_content_type: 'application/json',
      }, { state: 'done-drift' });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText('Show request body')).toBeTruthy();
    });

    it('does not show "Show request body" when there is no body', () => {
      const endpoint = makeEndpoint({
        has_drift: true,
        diff: {},
        request_body: null,
        request_content_type: 'query',
      }, { state: 'done-drift' });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.queryByText('Show request body')).toBeNull();
    });
  });

  describe('expand/collapse', () => {
    it('auto-expands when result has drift', () => {
      const endpoint = makeEndpoint({
        has_drift: true,
        diff: { values_changed: { "root['x']": { old_value: 1, new_value: 2 } } },
      }, { state: 'done-drift' });
      render(ResultDisplay, { props: { endpoint } });
      // When auto-expanded, the DiffView content and toggle buttons should be visible
      expect(screen.getByText('Show raw diff JSON')).toBeTruthy();
    });

    it('clicking the result bar toggles the open class on the detail panel', async () => {
      const endpoint = makeEndpoint();
      const { container } = render(ResultDisplay, { props: { endpoint } });
      // OK results start collapsed — the toggle-block element should NOT have the "open" class
      const panel = container.querySelector('.toggle-block');
      expect(panel).toBeTruthy();
      expect(panel.classList.contains('open')).toBe(false);

      // Click the chevron/bar to expand
      const bar = screen.getByRole('button', { name: /OK/ });
      await fireEvent.click(bar);

      // Now the panel should have the "open" class
      expect(panel.classList.contains('open')).toBe(true);
    });
  });

  describe('copy menu', () => {
    it('shows "Copy as..." button in expanded view', () => {
      const endpoint = makeEndpoint({
        has_drift: true,
        diff: {},
      }, { state: 'done-drift' });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText('Copy as...')).toBeTruthy();
    });

    it('clicking "Copy as..." opens the copy menu', async () => {
      const endpoint = makeEndpoint({
        has_drift: true,
        diff: {},
      }, { state: 'done-drift' });
      render(ResultDisplay, { props: { endpoint } });

      const copyBtn = screen.getByText('Copy as...');
      await fireEvent.click(copyBtn);

      expect(screen.getByText('Full result (markdown)')).toBeTruthy();
      expect(screen.getByText('Full result (json)')).toBeTruthy();
    });
  });

  describe('edge cases', () => {
    it('renders nothing when endpoint has no result', () => {
      const endpoint = {
        id: 1,
        method: 'GET',
        path: '/test',
        label: 'test',
        body: '',
        contentType: 'query',
        state: 'idle',
        result: null,
      };
      const { container } = render(ResultDisplay, { props: { endpoint } });
      // The component is wrapped in {#if r} so nothing should render
      expect(container.querySelector('.border-t')).toBeNull();
    });

    it('handles response with N/A elapsed_ms', () => {
      const endpoint = makeEndpoint({
        response_a: { status: 200, headers: {}, body: {}, elapsed_ms: null },
        response_b: { status: 200, headers: {}, body: {}, elapsed_ms: null },
      });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText(/N\/A\/N\/Ams/)).toBeTruthy();
    });

    it('handles mixed error and success responses', () => {
      const endpoint = makeEndpoint({
        has_drift: true,
        diff: {},
        response_a: { status: null, error: 'Connection refused', headers: {}, body: null, elapsed_ms: null },
        response_b: { status: 200, headers: { 'content-length': '100' }, body: { ok: true }, elapsed_ms: 25 },
      }, { state: 'done-drift' });
      render(ResultDisplay, { props: { endpoint } });
      expect(screen.getByText('DRIFT')).toBeTruthy();
      expect(screen.getByText(/ERR\/200/)).toBeTruthy();
    });
  });
});

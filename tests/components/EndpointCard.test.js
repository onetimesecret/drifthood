import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import EndpointCard from '../../src/components/EndpointCard.svelte';

// Track calls to store functions
const mockUpdateEndpoint = vi.fn();
const mockRemoveEndpoint = vi.fn();

vi.mock('../../src/stores/endpoints.svelte.js', () => ({
  endpoints: [],
  updateEndpoint: (...args) => mockUpdateEndpoint(...args),
  removeEndpoint: (...args) => mockRemoveEndpoint(...args),
}));

vi.mock('../../src/stores/session.svelte.js', () => {
  const envA = { id: 'env-a', name: 'Host A', baseUrl: 'http://localhost:3000', auth: '', memo: '', metadata: {} };
  const envB = { id: 'env-b', name: 'Host B', baseUrl: 'http://localhost:4000', auth: '', memo: '', metadata: {} };
  return {
    session: {
      title: '',
      memo: '',
      environments: [envA, envB],
      selectedA: 'env-a',
      selectedB: 'env-b',
      ignorePaths: [],
      specSource: null,
    },
    getEnvA: () => envA,
    getEnvB: () => envB,
  };
});

vi.mock('../../lib/api.js', () => ({
  apiCompare: vi.fn().mockResolvedValue({
    method: 'GET',
    path: '/api/v1/status',
    has_drift: false,
    diff: {},
    response_a: { status: 200, headers: {}, body: { status: 'ok' }, elapsed_ms: 42 },
    response_b: { status: 200, headers: {}, body: { status: 'ok' }, elapsed_ms: 38 },
    ignored_paths: [],
  }),
}));

beforeEach(() => {
  mockUpdateEndpoint.mockClear();
  mockRemoveEndpoint.mockClear();
});

function makeEndpoint(overrides = {}) {
  return {
    id: 1,
    method: 'GET',
    label: 'status',
    path: '/api/v1/status',
    body: '',
    contentType: 'query',
    group: '',
    fieldsMode: 'off',
    cardFields: null,
    fieldValues: null,
    state: 'idle',
    result: null,
    ...overrides,
  };
}

describe('EndpointCard', () => {
  describe('basic rendering', () => {
    it('renders without crashing', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint() },
      });
      expect(screen.getByDisplayValue('/api/v1/status')).toBeTruthy();
    });

    it('displays the method selector with correct value', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ method: 'POST' }) },
      });
      const select = screen.getByDisplayValue('POST');
      expect(select).toBeTruthy();
    });

    it('displays the path input', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ path: '/api/v2/secrets' }) },
      });
      expect(screen.getByDisplayValue('/api/v2/secrets')).toBeTruthy();
    });

    it('shows QUERY content type button by default', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint() },
      });
      expect(screen.getByText('QUERY')).toBeTruthy();
    });

    it('shows JSON content type button for JSON endpoints', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ contentType: 'application/json' }) },
      });
      expect(screen.getByText('JSON')).toBeTruthy();
    });

    it('shows FORM content type button for form endpoints', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ contentType: 'application/x-www-form-urlencoded' }) },
      });
      expect(screen.getByText('FORM')).toBeTruthy();
    });

    it('shows run button', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint() },
      });
      expect(screen.getByTitle('Run this endpoint')).toBeTruthy();
    });

    it('shows remove button', () => {
      const { container } = render(EndpointCard, {
        props: { endpoint: makeEndpoint() },
      });
      // The endpoint-level remove button is a direct child of the top flex row
      const topRow = container.querySelector('.flex.gap-2');
      const removeBtn = topRow.querySelector('[title="Remove"]');
      expect(removeBtn).toBeTruthy();
    });
  });

  describe('method selector', () => {
    it('offers GET, POST, PUT, DELETE options', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint() },
      });
      const options = screen.getAllByRole('option');
      const values = options.map(o => o.textContent);
      expect(values).toEqual(['GET', 'POST', 'PUT', 'DELETE']);
    });

    it('calls updateEndpoint when method changes', async () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint() },
      });
      const select = screen.getByDisplayValue('GET');
      await fireEvent.change(select, { target: { value: 'POST' } });
      expect(mockUpdateEndpoint).toHaveBeenCalledWith(1, { method: 'POST' });
    });
  });

  describe('path input', () => {
    it('calls updateEndpoint when path changes', async () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint() },
      });
      const input = screen.getByDisplayValue('/api/v1/status');
      await fireEvent.input(input, { target: { value: '/api/v2/secrets' } });
      expect(mockUpdateEndpoint).toHaveBeenCalledWith(1, { path: '/api/v2/secrets' });
    });
  });

  describe('content type cycling', () => {
    it('cycles through content types when CT button is clicked', async () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ contentType: 'query' }) },
      });
      const ctBtn = screen.getByTitle('query / form / json');
      await fireEvent.click(ctBtn);
      // query -> form
      expect(mockUpdateEndpoint).toHaveBeenCalledWith(1, { contentType: 'application/x-www-form-urlencoded' });
    });

    it('cycles from json back to query', async () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ contentType: 'application/json' }) },
      });
      const ctBtn = screen.getByTitle('query / form / json');
      await fireEvent.click(ctBtn);
      // json -> query
      expect(mockUpdateEndpoint).toHaveBeenCalledWith(1, { contentType: 'query' });
    });
  });

  describe('label display', () => {
    it('shows label input for simple endpoints', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ label: 'mytest' }) },
      });
      expect(screen.getByDisplayValue('mytest')).toBeTruthy();
    });

    it('shows stripped operationId badge for spec-imported endpoints', () => {
      render(EndpointCard, {
        props: {
          endpoint: makeEndpoint({
            label: 'v2_concealSecret',
            cardFields: { fields: [{ path: 'secret', name: 'secret', type: 'string' }], path_fields: [], query_fields: [] },
          }),
        },
      });
      // stripOpIdPrefix('v2_concealSecret') -> 'concealSecret'
      expect(screen.getByText('concealSecret')).toBeTruthy();
    });
  });

  describe('group badge', () => {
    it('does not show group badge when group is empty', () => {
      const { container } = render(EndpointCard, {
        props: { endpoint: makeEndpoint({ group: '' }) },
      });
      // No badge with group text
      const badges = container.querySelectorAll('span.text-\\[0\\.6em\\]');
      const groupBadges = [...badges].filter(b => !b.hasAttribute('title'));
      expect(groupBadges).toHaveLength(0);
    });

    it('shows group badge when group is set', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ group: 'auth' }) },
      });
      expect(screen.getByText('auth')).toBeTruthy();
    });
  });

  describe('remove button', () => {
    it('calls removeEndpoint when remove is clicked', async () => {
      const { container } = render(EndpointCard, {
        props: { endpoint: makeEndpoint() },
      });
      // Target the endpoint-level remove button (in the top flex row), not the KvPairs row remove
      const topRow = container.querySelector('.flex.gap-2');
      const removeBtn = topRow.querySelector('[title="Remove"]');
      await fireEvent.click(removeBtn);
      expect(mockRemoveEndpoint).toHaveBeenCalledWith(1);
    });
  });

  describe('running state', () => {
    it('shows spinner in run button when state is running', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ state: 'running' }) },
      });
      // The run button should contain a spinner span, not text "run"
      const runBtn = screen.getByTitle('Run this endpoint');
      expect(runBtn.querySelector('.animate-spin')).toBeTruthy();
      expect(runBtn.textContent.trim()).not.toBe('run');
    });

    it('shows "Running..." message when state is running with no result', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ state: 'running', result: null }) },
      });
      expect(screen.getByText('Running...')).toBeTruthy();
    });
  });

  describe('state-based border colors', () => {
    it('has default border for idle state', () => {
      const { container } = render(EndpointCard, {
        props: { endpoint: makeEndpoint({ state: 'idle' }) },
      });
      const card = container.firstChild;
      expect(card.className).toContain('border-edge');
    });

    it('has red-tinted border for drift state', () => {
      const { container } = render(EndpointCard, {
        props: { endpoint: makeEndpoint({ state: 'done-drift' }) },
      });
      const card = container.firstChild;
      expect(card.className).toContain('border-red/40');
    });

    it('has green-tinted border for ok state', () => {
      const { container } = render(EndpointCard, {
        props: { endpoint: makeEndpoint({ state: 'done-ok' }) },
      });
      const card = container.firstChild;
      expect(card.className).toContain('border-green/20');
    });

    it('has accent border for running state', () => {
      const { container } = render(EndpointCard, {
        props: { endpoint: makeEndpoint({ state: 'running' }) },
      });
      const card = container.firstChild;
      expect(card.className).toContain('border-accent/30');
    });
  });

  describe('fields mode', () => {
    it('does not show FIELDS button when endpoint has no card fields', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ cardFields: null }) },
      });
      expect(screen.queryByText('FIELDS')).toBeNull();
    });

    it('shows FIELDS button when endpoint has card fields', () => {
      const endpoint = makeEndpoint({
        cardFields: {
          fields: [{ path: 'secret', name: 'secret', type: 'string' }],
          path_fields: [],
          query_fields: [],
        },
      });
      render(EndpointCard, { props: { endpoint } });
      expect(screen.getByText('FIELDS')).toBeTruthy();
    });

    it('toggles fields mode when FIELDS button is clicked', async () => {
      const endpoint = makeEndpoint({
        fieldsMode: 'off',
        cardFields: {
          fields: [{ path: 'secret', name: 'secret', type: 'string' }],
          path_fields: [],
          query_fields: [],
        },
      });
      render(EndpointCard, { props: { endpoint } });
      const fieldsBtn = screen.getByText('FIELDS');
      await fireEvent.click(fieldsBtn);
      expect(mockUpdateEndpoint).toHaveBeenCalledWith(1, { fieldsMode: 'on' });
    });
  });

  describe('result display', () => {
    it('shows ResultDisplay when endpoint has a result', () => {
      const result = {
        method: 'GET',
        path: '/api/v1/status',
        has_drift: false,
        diff: {},
        response_a: { status: 200, headers: {}, body: { status: 'ok' }, elapsed_ms: 42 },
        response_b: { status: 200, headers: {}, body: { status: 'ok' }, elapsed_ms: 38 },
        ignored_paths: [],
        request_body: null,
        request_content_type: 'query',
      };
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ state: 'done-ok', result }) },
      });
      expect(screen.getByText('OK')).toBeTruthy();
    });

    it('does not show ResultDisplay when no result and idle', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ state: 'idle', result: null }) },
      });
      // No border-t (ResultDisplay wrapper)
      expect(screen.queryByText('OK')).toBeNull();
      expect(screen.queryByText('DRIFT')).toBeNull();
    });
  });

  describe('body input visibility', () => {
    it('does not show body text input for query content type (shows KvPairs instead)', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ contentType: 'query', body: '' }) },
      });
      // KvPairs should be rendered instead of a body text input
      expect(screen.getByText('Query Parameters')).toBeTruthy();
    });

    it('shows body text input for JSON content type', () => {
      render(EndpointCard, {
        props: { endpoint: makeEndpoint({ contentType: 'application/json', body: '{}' }) },
      });
      // For JSON, a text input with the JSON placeholder should appear
      const input = screen.getByPlaceholderText('{"key":"val"} (JSON body)');
      expect(input).toBeTruthy();
    });
  });
});

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import KvPairs from '../../src/components/KvPairs.svelte';

// Mock the updateEndpoint function
const mockUpdateEndpoint = vi.fn();
vi.mock('../../src/stores/endpoints.svelte.js', () => ({
  updateEndpoint: (...args) => mockUpdateEndpoint(...args),
}));

beforeEach(() => {
  mockUpdateEndpoint.mockClear();
});

function makeEndpoint(body = '', _localId = 'test-id-123') {
  // Create a reactive-like object that allows body updates
  return {
    _localId,
    body,
  };
}

// Helper to get input value
function getInputValue(testId) {
  const input = screen.getByTestId(testId);
  return input.value;
}

describe('KvPairs', () => {
  describe('basic rendering', () => {
    it('renders with empty body showing one empty row', () => {
      const endpoint = makeEndpoint('');
      render(KvPairs, { props: { endpoint } });

      const keyInputs = screen.getAllByTestId(/kv-key-/);
      expect(keyInputs).toHaveLength(1);
    });

    it('parses initial body into key-value pairs', async () => {
      const endpoint = makeEndpoint('foo=bar&baz=qux');
      render(KvPairs, { props: { endpoint } });

      await waitFor(() => {
        expect(getInputValue('kv-key-0')).toBe('foo');
        expect(getInputValue('kv-value-0')).toBe('bar');
        expect(getInputValue('kv-key-1')).toBe('baz');
        expect(getInputValue('kv-value-1')).toBe('qux');
      });
    });

    it('shows Query Parameters label by default', () => {
      const endpoint = makeEndpoint('');
      render(KvPairs, { props: { endpoint } });
      expect(screen.getByText('Query Parameters')).toBeTruthy();
    });

    it('shows Form Parameters label when type is form', () => {
      const endpoint = makeEndpoint('');
      render(KvPairs, { props: { endpoint, type: 'form' } });
      expect(screen.getByText('Form Parameters')).toBeTruthy();
    });
  });

  describe('user interactions', () => {
    it('adds a new row when Add button is clicked', async () => {
      const endpoint = makeEndpoint('');
      render(KvPairs, { props: { endpoint } });

      const addButton = screen.getByTestId('kv-add');
      await fireEvent.click(addButton);

      const keyInputs = screen.getAllByTestId(/kv-key-/);
      expect(keyInputs).toHaveLength(2);
    });

    it('removes a row when remove button is clicked', async () => {
      const endpoint = makeEndpoint('a=1&b=2');
      render(KvPairs, { props: { endpoint } });

      await waitFor(() => {
        expect(screen.getAllByTestId(/kv-key-/)).toHaveLength(2);
      });

      const removeButton = screen.getByTestId('kv-remove-0');
      await fireEvent.click(removeButton);

      await waitFor(() => {
        expect(screen.getAllByTestId(/kv-key-/)).toHaveLength(1);
        expect(getInputValue('kv-key-0')).toBe('b');
      });
    });

    it('keeps at least one row when removing the last row', async () => {
      const endpoint = makeEndpoint('a=1');
      render(KvPairs, { props: { endpoint } });

      await waitFor(() => {
        expect(screen.getAllByTestId(/kv-key-/)).toHaveLength(1);
      });

      const removeButton = screen.getByTestId('kv-remove-0');
      await fireEvent.click(removeButton);

      await waitFor(() => {
        const keyInputs = screen.getAllByTestId(/kv-key-/);
        expect(keyInputs).toHaveLength(1);
        expect(keyInputs[0].value).toBe('');
      });
    });

    it('calls updateEndpoint when key is modified', async () => {
      const endpoint = makeEndpoint('');
      render(KvPairs, { props: { endpoint } });

      const keyInput = screen.getByTestId('kv-key-0');
      await fireEvent.input(keyInput, { target: { value: 'newkey' } });

      await waitFor(() => {
        expect(mockUpdateEndpoint).toHaveBeenCalledWith(
          'test-id-123',
          expect.objectContaining({ body: expect.any(String) })
        );
      });
    });

    it('assembles pairs into URL-encoded body', async () => {
      const endpoint = makeEndpoint('');
      render(KvPairs, { props: { endpoint } });

      const keyInput = screen.getByTestId('kv-key-0');
      const valueInput = screen.getByTestId('kv-value-0');

      await fireEvent.input(keyInput, { target: { value: 'foo' } });
      await fireEvent.input(valueInput, { target: { value: 'bar value' } });

      await waitFor(() => {
        const lastCall = mockUpdateEndpoint.mock.calls[mockUpdateEndpoint.mock.calls.length - 1];
        expect(lastCall[1].body).toBe('foo=bar%20value');
      });
    });
  });

  describe('race condition handling (Task 42 fix)', () => {
    it('internal edits do not trigger re-parse loop', async () => {
      // This tests that when we edit a field, the body update we generate
      // does not cause the component to re-parse the body into pairs.
      const endpoint = makeEndpoint('a=1');
      render(KvPairs, { props: { endpoint } });

      await waitFor(() => {
        expect(getInputValue('kv-key-0')).toBe('a');
      });

      // Clear and track calls after initial render
      mockUpdateEndpoint.mockClear();

      const valueInput = screen.getByTestId('kv-value-0');
      await fireEvent.input(valueInput, { target: { value: '2' } });

      // The key should still be 'a', not re-parsed to something else
      await waitFor(() => {
        expect(getInputValue('kv-key-0')).toBe('a');
        expect(getInputValue('kv-value-0')).toBe('2');
      });
    });

    it('empty keys are filtered from assembled body', async () => {
      const endpoint = makeEndpoint('');
      render(KvPairs, { props: { endpoint } });

      // Add a row with empty key
      await fireEvent.click(screen.getByTestId('kv-add'));

      // Fill in only the second row
      const keyInput1 = screen.getByTestId('kv-key-1');
      const valueInput1 = screen.getByTestId('kv-value-1');
      await fireEvent.input(keyInput1, { target: { value: 'valid' } });
      await fireEvent.input(valueInput1, { target: { value: 'value' } });

      await waitFor(() => {
        const lastCall = mockUpdateEndpoint.mock.calls[mockUpdateEndpoint.mock.calls.length - 1];
        // First row with empty key should be filtered out
        expect(lastCall[1].body).toBe('valid=value');
      });
    });
  });
});

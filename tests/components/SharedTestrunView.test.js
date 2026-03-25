import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import SharedTestrunView from '../../src/components/SharedTestrunView.svelte';

// Mock the API module
const mockApiGetSharedTestrun = vi.fn();
vi.mock('../../lib/api.js', () => ({
  apiGetSharedTestrun: (...args) => mockApiGetSharedTestrun(...args),
}));

// Mock the format module
vi.mock('../../lib/format.js', () => ({
  relativeTime: () => '5 minutes ago',
}));

beforeEach(() => {
  mockApiGetSharedTestrun.mockClear();
});

/**
 * Tests for SharedTestrunView isEncrypted check.
 *
 * Task 43 fixed the isEncrypted check to use:
 *   testrun?.encrypted_blob && !testrun?.state?.endpoints?.length
 * instead of the previous:
 *   testrun?.encrypted_blob && !testrun?.state
 *
 * The fix ensures that empty object states {} (which are truthy) are
 * correctly identified as encrypted when encrypted_blob is present.
 */
describe('SharedTestrunView isEncrypted check', () => {
  const makeTestrunResponse = (overrides = {}) => ({
    testrun: {
      extid: 'test-extid',
      testrun_number: 1,
      testrun_type: 'save',
      endpoint_count: 0,
      drift_count: 0,
      ok_count: 0,
      created_at: '2024-01-01T00:00:00Z',
      state: {},
      encrypted_blob: null,
      ...overrides,
    },
    document: {
      extid: 'doc-extid',
      title: 'Test Document',
      created_at: '2024-01-01T00:00:00Z',
    },
  });

  it('shows encrypted notice when state is empty object {} and encrypted_blob is present', async () => {
    mockApiGetSharedTestrun.mockResolvedValue(makeTestrunResponse({
      state: {},  // Empty object - truthy but no endpoints
      encrypted_blob: 'encrypted-data-here',
    }));

    render(SharedTestrunView, { props: { extid: 'test-123' } });

    await waitFor(() => {
      expect(screen.getByText('Encrypted Content')).toBeTruthy();
    });
  });

  it('shows encrypted notice when state has no endpoints and encrypted_blob is present', async () => {
    mockApiGetSharedTestrun.mockResolvedValue(makeTestrunResponse({
      state: { title: 'Some Title', endpoints: [] },  // Has state but empty endpoints
      encrypted_blob: 'encrypted-data-here',
    }));

    render(SharedTestrunView, { props: { extid: 'test-123' } });

    await waitFor(() => {
      expect(screen.getByText('Encrypted Content')).toBeTruthy();
    });
  });

  it('does NOT show encrypted notice when state has endpoints', async () => {
    mockApiGetSharedTestrun.mockResolvedValue(makeTestrunResponse({
      state: {
        endpoints: [
          { method: 'GET', path: '/api/status', state: 'done-ok' },
        ],
      },
      encrypted_blob: 'encrypted-data-here',  // Even with blob, endpoints exist
    }));

    render(SharedTestrunView, { props: { extid: 'test-123' } });

    await waitFor(() => {
      // Should see the endpoint, not the encrypted notice
      expect(screen.queryByText('Encrypted Content')).toBeNull();
      expect(screen.getByText('/api/status')).toBeTruthy();
    });
  });

  it('shows encrypted notice when state is null and encrypted_blob is present', async () => {
    mockApiGetSharedTestrun.mockResolvedValue(makeTestrunResponse({
      state: null,  // Null state
      encrypted_blob: 'encrypted-data-here',
    }));

    render(SharedTestrunView, { props: { extid: 'test-123' } });

    await waitFor(() => {
      expect(screen.getByText('Encrypted Content')).toBeTruthy();
    });
  });

  it('shows "No endpoints" when no encrypted_blob and no endpoints', async () => {
    mockApiGetSharedTestrun.mockResolvedValue(makeTestrunResponse({
      state: { endpoints: [] },
      encrypted_blob: null,  // No blob
    }));

    render(SharedTestrunView, { props: { extid: 'test-123' } });

    await waitFor(() => {
      expect(screen.queryByText('Encrypted Content')).toBeNull();
      expect(screen.getByText('No endpoints in this testrun.')).toBeTruthy();
    });
  });

  it('does NOT show encrypted notice when no encrypted_blob even with empty state', async () => {
    mockApiGetSharedTestrun.mockResolvedValue(makeTestrunResponse({
      state: {},
      encrypted_blob: null,  // No blob means not encrypted
    }));

    render(SharedTestrunView, { props: { extid: 'test-123' } });

    await waitFor(() => {
      expect(screen.queryByText('Encrypted Content')).toBeNull();
    });
  });
});

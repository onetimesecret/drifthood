<script>
  /**
   * SharedTestrunView - Read-only view for shared testrun links.
   *
   * Fetches from /api/share/{extid} (no auth required).
   * Displays:
   * - Document title and testrun metadata
   * - Endpoint summary (manifest portion)
   * - Notice when blob is encrypted (cannot decrypt without key)
   */
  import { relativeTime } from '../../lib/format.js';
  import { SEVERITY_LEVELS } from '../../lib/diff.js';

  let { extid } = $props();

  let loading = $state(true);
  let error = $state(null);
  let testrun = $state(null);
  let document = $state(null);

  $effect(() => {
    if (!extid) {
      error = 'No testrun ID provided';
      loading = false;
      return;
    }

    fetchSharedTestrun(extid);
  });

  async function fetchSharedTestrun(id) {
    loading = true;
    error = null;

    try {
      const response = await fetch(`/api/share/${id}`);
      if (!response.ok) {
        if (response.status === 404) {
          error = 'Testrun not found or has been deleted';
        } else {
          error = `Failed to load testrun: ${response.statusText}`;
        }
        loading = false;
        return;
      }

      const data = await response.json();
      testrun = data.testrun;
      document = data.document;
    } catch (err) {
      error = `Network error: ${err.message}`;
    } finally {
      loading = false;
    }
  }

  // Derived state
  let isEncrypted = $derived(testrun?.encrypted_blob && !testrun?.state);
  let endpoints = $derived(testrun?.state?.endpoints ?? []);
  let endpointCounts = $derived(computeEndpointCounts(endpoints));

  function computeEndpointCounts(eps) {
    const counts = { total: eps.length, drift: 0, ok: 0, idle: 0, error: 0 };
    for (const ep of eps) {
      if (ep.state === 'done-drift') counts.drift++;
      else if (ep.state === 'done-ok') counts.ok++;
      else if (ep.state === 'idle') counts.idle++;
      else if (ep.state === 'error') counts.error++;
    }
    return counts;
  }

  function stateToSeverity(state) {
    if (state === 'done-drift') return 'breaking';
    if (state === 'done-ok') return 'none';
    if (state === 'error') return 'structural';
    return 'none';
  }
</script>

<div class="shared-testrun-view min-h-screen bg-bg-dim p-6">
  {#if loading}
    <div class="flex items-center justify-center h-64">
      <div class="text-text-dim">Loading shared testrun...</div>
    </div>
  {:else if error}
    <div class="max-w-2xl mx-auto">
      <div class="bg-red/10 border border-red/30 rounded-lg p-6 text-center">
        <h2 class="text-xl font-semibold text-red mb-2">Unable to Load</h2>
        <p class="text-text-dim">{error}</p>
      </div>
    </div>
  {:else}
    <div class="max-w-4xl mx-auto">
      <!-- Header -->
      <header class="mb-8">
        <div class="flex items-center gap-2 text-text-dim text-sm mb-2">
          <span>Shared Testrun</span>
          {#if testrun?.created_at}
            <span class="text-text-dim/50">|</span>
            <span title={testrun.created_at}>{relativeTime(testrun.created_at)}</span>
          {/if}
        </div>
        <h1 class="text-2xl font-bold text-text">
          {document?.title || 'Untitled Document'}
        </h1>
        {#if testrun?.testrun_type}
          <span class="inline-block mt-2 text-xs px-2 py-0.5 rounded bg-text-dim/10 border border-edge text-text-dim">
            {testrun.testrun_type}
          </span>
        {/if}
      </header>

      <!-- Encrypted blob notice -->
      {#if isEncrypted}
        <div class="bg-amber/10 border border-amber/30 rounded-lg p-4 mb-6">
          <h3 class="font-semibold text-amber mb-1">Encrypted Content</h3>
          <p class="text-text-dim text-sm">
            This testrun contains encrypted data. The full results require the
            encryption key which is not stored on the server. Only metadata is
            visible without the key.
          </p>
        </div>
      {/if}

      <!-- Summary stats -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <div class="bg-panel rounded-lg p-4 border border-edge">
          <div class="text-2xl font-bold text-text">{endpointCounts.total}</div>
          <div class="text-sm text-text-dim">Endpoints</div>
        </div>
        <div class="bg-panel rounded-lg p-4 border border-edge">
          <div class="text-2xl font-bold text-green">{endpointCounts.ok}</div>
          <div class="text-sm text-text-dim">OK</div>
        </div>
        <div class="bg-panel rounded-lg p-4 border border-edge">
          <div class="text-2xl font-bold text-red">{endpointCounts.drift}</div>
          <div class="text-sm text-text-dim">Drift</div>
        </div>
        <div class="bg-panel rounded-lg p-4 border border-edge">
          <div class="text-2xl font-bold text-text-dim">{endpointCounts.idle + endpointCounts.error}</div>
          <div class="text-sm text-text-dim">Idle/Error</div>
        </div>
      </div>

      <!-- Endpoint list (manifest portion) -->
      {#if endpoints.length > 0}
        <section class="bg-panel rounded-lg border border-edge">
          <h2 class="text-lg font-semibold text-text px-4 py-3 border-b border-edge">
            Endpoints
          </h2>
          <ul class="divide-y divide-edge">
            {#each endpoints as ep, i}
              {@const severity = stateToSeverity(ep.state)}
              {@const severityInfo = SEVERITY_LEVELS[severity] || SEVERITY_LEVELS.none}
              {@const methodClass =
                ep.method === 'GET' ? 'bg-blue/20 text-blue' :
                ep.method === 'POST' ? 'bg-green/20 text-green' :
                ep.method === 'PUT' || ep.method === 'PATCH' ? 'bg-amber/20 text-amber' :
                ep.method === 'DELETE' ? 'bg-red/20 text-red' : ''}
              {@const stateClass =
                ep.state === 'done-ok' ? 'bg-green/20 text-green' :
                ep.state === 'done-drift' ? 'bg-red/20 text-red' :
                ep.state === 'idle' ? 'bg-text-dim/20 text-text-dim' :
                ep.state === 'error' ? 'bg-amber/20 text-amber' : ''}
              <li class="px-4 py-3 flex items-center gap-3">
                <span class="flex-shrink-0 w-16 text-xs font-mono font-medium px-2 py-0.5 rounded text-center {methodClass}">
                  {ep.method}
                </span>
                <span class="flex-grow font-mono text-sm text-text truncate">
                  {ep.path}
                </span>
                <span class="flex-shrink-0 text-xs px-2 py-0.5 rounded {stateClass}">
                  {#if ep.state === 'done-ok'}
                    OK
                  {:else if ep.state === 'done-drift'}
                    Drift
                  {:else if ep.state === 'idle'}
                    Idle
                  {:else if ep.state === 'error'}
                    Error
                  {:else}
                    {ep.state || 'Unknown'}
                  {/if}
                </span>
              </li>
            {/each}
          </ul>
        </section>
      {:else if !isEncrypted}
        <div class="text-center text-text-dim py-8">
          No endpoints in this testrun.
        </div>
      {/if}

      <!-- Footer -->
      <footer class="mt-8 text-center text-text-dim text-sm">
        <p>
          This is a read-only view of a shared testrun.
          <a href="/" class="text-blue hover:underline">Create your own</a>
        </p>
      </footer>
    </div>
  {/if}
</div>

<style>
  /* Use Tailwind classes via @apply or inline */
</style>

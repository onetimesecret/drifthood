<script>
  import { session, getEnvironment } from '../stores/session.svelte.js';
  import { auth } from '../stores/auth.svelte.js';

  let { extid = '' } = $props();

  let env = $derived(getEnvironment(extid));

  function goBack() {
    const sessionExtid = auth.extid;
    if (sessionExtid) {
      history.pushState(null, '', `/s/${encodeURIComponent(sessionExtid)}`);
    } else {
      history.pushState(null, '', '/');
    }
    // Trigger a re-render by dispatching popstate
    window.dispatchEvent(new PopStateEvent('popstate'));
  }

  function maskedAuth(authStr) {
    if (!authStr) return '';
    const parts = authStr.split(':');
    if (parts.length < 2) return '***';
    return parts[0] + ':' + '*'.repeat(Math.min(parts[1].length, 8));
  }
</script>

<div class="max-w-2xl mx-auto py-8 px-4">
  <button
    class="text-[0.8em] text-text-dim hover:text-accent cursor-pointer bg-transparent border-none mb-6 font-mono"
    onclick={goBack}
  >&larr; Back to session</button>

  {#if env}
    <h1 class="text-[1.4em] font-semibold mb-1">{env.name || 'Unnamed environment'}</h1>
    <p class="text-[0.75em] font-mono text-text-dim mb-6 break-all">{extid}</p>

    <div class="space-y-4">
      <!-- Base URL -->
      <div class="bg-surface border border-edge rounded-lg p-4">
        <div class="text-[0.7em] uppercase tracking-widest text-text-dim font-semibold mb-1">Base URL</div>
        <div class="font-mono text-[0.85em] text-text-primary break-all">{env.baseUrl || '(not set)'}</div>
      </div>

      <!-- Auth -->
      <div class="bg-surface border border-edge rounded-lg p-4">
        <div class="text-[0.7em] uppercase tracking-widest text-text-dim font-semibold mb-1">Auth</div>
        <div class="font-mono text-[0.85em] text-text-primary">{env.auth ? maskedAuth(env.auth) : '(none)'}</div>
      </div>

      <!-- Memo -->
      {#if env.memo}
        <div class="bg-surface border border-edge rounded-lg p-4">
          <div class="text-[0.7em] uppercase tracking-widest text-text-dim font-semibold mb-1">Memo</div>
          <div class="text-[0.85em] text-text-primary whitespace-pre-wrap">{env.memo}</div>
        </div>
      {/if}

      <!-- Metadata -->
      {#if env.metadata && Object.keys(env.metadata).length > 0}
        <div class="bg-surface border border-edge rounded-lg p-4">
          <div class="text-[0.7em] uppercase tracking-widest text-text-dim font-semibold mb-2">Metadata</div>
          <div class="space-y-1">
            {#each Object.entries(env.metadata) as [key, value]}
              <div class="flex gap-2 text-[0.8em] font-mono">
                <span class="text-text-dim">{key}:</span>
                <span class="text-text-primary break-all">{value}</span>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  {:else}
    <div class="bg-surface border border-edge rounded-lg p-6 text-center">
      <div class="text-[0.9em] text-text-dim mb-2">Environment not found</div>
      <div class="text-[0.75em] text-text-dim font-mono break-all">{extid}</div>
      <p class="text-[0.8em] text-text-dim mt-4">This environment may not exist in the current session, or the session data has not been loaded yet.</p>
    </div>
  {/if}
</div>

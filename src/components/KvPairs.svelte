<script>
  import { parseKvString } from '../../lib/params.js';
  import { updateEndpoint } from '../stores/endpoints.svelte.js';

  let { endpoint, type = 'query' } = $props();

  let pairs = $state([{ key: '', val: '' }]);
  let syncing = false;

  // Parse endpoint.body into pairs on mount and when body changes externally
  $effect(() => {
    const body = endpoint.body;
    if (syncing) return;
    const parsed = parseKvString(body);
    pairs = parsed.length > 0 ? parsed : [{ key: '', val: '' }];
  });

  // Sync pairs back to endpoint.body on change
  $effect(() => {
    // Read all pairs to track reactivity
    const assembled = pairs
      .filter(p => p.key.trim())
      .map(p => encodeURIComponent(p.key) + '=' + encodeURIComponent(p.val))
      .join('&');

    syncing = true;
    updateEndpoint(endpoint._localId, { body: assembled });
    // Use queueMicrotask to reset flag after the reactive update propagates
    queueMicrotask(() => { syncing = false; });
  });

  function addRow() {
    pairs.push({ key: '', val: '' });
  }

  function removeRow(index) {
    pairs.splice(index, 1);
    if (pairs.length === 0) {
      pairs.push({ key: '', val: '' });
    }
  }

  let headerLabel = $derived(type === 'query' ? 'Query Parameters' : 'Form Parameters');
</script>

<div class="px-3 py-1.5 pb-2.5 border-t border-edge">
  <div class="text-[0.65em] uppercase tracking-wider text-text-dim my-0.5 mb-1">{headerLabel}</div>

  {#each pairs as pair, i}
    <div class="flex items-center gap-1.5 mb-1 text-[0.8em] font-mono">
      <input
        type="text"
        class="flex-1 max-w-[200px] bg-bg border border-edge text-text-primary px-1.5 py-0.5 rounded font-mono text-[0.9em] min-w-[80px]"
        placeholder="key"
        bind:value={pair.key}
      />
      <span class="text-text-dim text-[0.85em] shrink-0 select-none">=</span>
      <input
        type="text"
        class="flex-2 bg-bg border border-edge text-text-primary px-1.5 py-0.5 rounded font-mono text-[0.9em] min-w-[80px]"
        placeholder="value"
        bind:value={pair.val}
      />
      <button
        class="bg-transparent border-none text-text-dim cursor-pointer text-[1.1em] px-1.5 py-0.5 rounded shrink-0 hover:text-red hover:bg-red/10"
        title="Remove"
        onclick={() => removeRow(i)}
      >&times;</button>
    </div>
  {/each}

  <button class="text-[0.75em] font-mono px-2.5 py-0.5 rounded cursor-pointer border border-dashed border-edge bg-transparent text-text-dim mt-0.5 hover:border-accent hover:text-accent" onclick={addRow}>+ Add</button>
</div>

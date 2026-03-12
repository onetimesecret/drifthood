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
    updateEndpoint(endpoint.id, { body: assembled });
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

<div class="kv-pairs">
  <div class="kv-header">{headerLabel}</div>

  {#each pairs as pair, i}
    <div class="kv-row">
      <input
        type="text"
        class="kv-key"
        placeholder="key"
        bind:value={pair.key}
      />
      <span class="kv-sep">=</span>
      <input
        type="text"
        class="kv-val"
        placeholder="value"
        bind:value={pair.val}
      />
      <button
        class="kv-remove"
        title="Remove"
        onclick={() => removeRow(i)}
      >&times;</button>
    </div>
  {/each}

  <button class="kv-add-btn" onclick={addRow}>+ Add</button>
</div>

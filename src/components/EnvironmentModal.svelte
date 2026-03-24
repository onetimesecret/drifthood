<!-- src/components/EnvironmentModal.svelte -->

<script>
  import Modal from './Modal.svelte';
  import { session, createEnvironment, saveEnvironment, removeEnvironment } from '../stores/session.svelte.js';

  let { open, onclose } = $props();

  let editingExtid = $state(null);

  let editingEnv = $derived(
    editingExtid ? session.environments.find(e => e.extid === editingExtid) : null
  );

  // Convert metadata object to editable rows whenever the selected env changes
  let metaRows = $state([]);
  let lastMetaSyncExtid = null;

  $effect(() => {
    const env = editingEnv;
    if (!env) {
      metaRows = [];
      lastMetaSyncExtid = null;
      return;
    }
    if (env.extid !== lastMetaSyncExtid) {
      lastMetaSyncExtid = env.extid;
      const entries = Object.entries(env.metadata || {});
      metaRows = entries.length > 0
        ? entries.map(([key, val]) => ({ key, val: String(val) }))
        : [{ key: '', val: '' }];
    }
  });

  function syncMetaToStore() {
    if (!editingEnv) return;
    const obj = {};
    for (const row of metaRows) {
      const k = row.key.trim();
      if (k) obj[k] = row.val;
    }
    saveEnvironment(editingEnv.extid, { metadata: obj });
  }

  function addMetaRow() {
    metaRows.push({ key: '', val: '' });
  }

  function removeMetaRow(index) {
    metaRows.splice(index, 1);
    if (metaRows.length === 0) {
      metaRows.push({ key: '', val: '' });
    }
    syncMetaToStore();
  }

  function handleMetaChange() {
    syncMetaToStore();
  }

  async function handleAdd() {
    const env = await createEnvironment({ name: 'New Environment' });
    editingExtid = env.extid;
  }

  function handleSelect(extid) {
    editingExtid = extid;
  }

  function handleRemove(extid) {
    if (extid === editingExtid) editingExtid = null;
    removeEnvironment(extid);
  }

  function isInUse(extid) {
    if (session.selectedA === extid && session.selectedB === extid) return 'In use as Environment A & B';
    if (session.selectedA === extid) return 'In use as Environment A';
    if (session.selectedB === extid) return 'In use as Environment B';
    return null;
  }

  function handleFieldChange(field, value) {
    if (!editingEnv) return;
    saveEnvironment(editingEnv.extid, { [field]: value });
  }
</script>

<Modal {open} {onclose} maxWidth="900px">
  <!-- Header -->
  <div class="flex items-center justify-between px-5 py-3.5 border-b border-edge shrink-0">
    <div class="flex items-center gap-3">
      <h2 class="text-[0.85em] font-semibold text-text-primary">Manage Environments</h2>
      <span class="text-[0.7em] text-text-dim italic">changes auto-saved</span>
    </div>
    <button
      class="text-[0.8em] px-3 py-1 rounded cursor-pointer bg-transparent border border-edge text-text-primary font-mono hover:border-accent hover:text-accent"
      onclick={onclose}
    >Done</button>
  </div>

  <!-- Body: list + form -->
  <div class="flex flex-1 overflow-hidden min-h-0">
    <!-- Environment list -->
    <div class="w-[260px] min-w-[260px] border-r border-edge flex flex-col overflow-y-auto">
      <div class="p-3">
        <button
          class="block w-full px-2.5 py-1.5 text-[0.8em] bg-transparent border border-dashed border-edge text-text-dim rounded-md cursor-pointer text-left hover:border-accent hover:text-accent"
          onclick={handleAdd}
        >+ Add Environment</button>
      </div>

      <div class="flex-1 overflow-y-auto">
        {#each session.environments as env (env.extid)}
          {@const inUse = isInUse(env.extid)}
          {@const selected = editingExtid === env.extid}
          <div
            role="button"
            tabindex="0"
            class="group/env flex items-center gap-2 px-3.5 py-2.5 cursor-pointer border-b border-edge text-[0.8em] hover:bg-white/[0.03] {selected ? 'bg-accent/[0.08]' : ''}"
            onclick={() => handleSelect(env.extid)}
            onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleSelect(env.extid); } }}
          >
            <div class="flex-1 min-w-0">
              <div class="text-text-primary font-medium truncate">{env.name || 'Untitled'}</div>
              <div class="text-[0.85em] text-text-dim font-mono truncate">{env.baseUrl || 'no url'}</div>
            </div>
            {#if session.selectedA === env.extid && session.selectedB === env.extid}
              <span class="text-[0.65em] font-mono font-semibold text-accent shrink-0" title={inUse}>A B</span>
            {:else if session.selectedA === env.extid}
              <span class="text-[0.65em] font-mono font-semibold text-accent shrink-0" title={inUse}>A</span>
            {:else if session.selectedB === env.extid}
              <span class="text-[0.65em] font-mono font-semibold text-accent shrink-0" title={inUse}>B</span>
            {/if}
            {#if inUse}
              <button
                class="opacity-30 cursor-not-allowed bg-transparent border-none text-text-dim text-[1em] px-1 rounded-sm shrink-0"
                title={inUse}
                disabled
              >&times;</button>
            {:else}
              <button
                class="opacity-0 group-hover/env:opacity-60 bg-transparent border-none text-text-dim cursor-pointer text-[1em] px-1 rounded-sm shrink-0 hover:opacity-100 hover:text-red"
                title="Remove environment"
                onclick={(e) => { e.stopPropagation(); handleRemove(env.extid); }}
              >&times;</button>
            {/if}
          </div>
        {/each}

        {#if session.environments.length === 0}
          <div class="px-3.5 py-4 text-[0.8em] text-text-dim">No environments yet.</div>
        {/if}
      </div>
    </div>

    <!-- Edit form -->
    <div class="flex-1 overflow-y-auto p-5">
      {#if editingEnv}
        <div class="flex flex-col gap-3">
          <!-- Name -->
          <div class="flex flex-col gap-0.5">
            <label class="text-[0.7em] text-text-dim uppercase tracking-wider" for="env-name">Name</label>
            <input
              class="bg-surface border border-edge text-text-primary px-2.5 py-1.5 rounded-md font-mono text-[0.85em] w-full"
              id="env-name"
              type="text"
              value={editingEnv.name}
              oninput={(e) => handleFieldChange('name', e.target.value)}
              placeholder="e.g. Production v3"
            />
          </div>

          <!-- Base URL -->
          <div class="flex flex-col gap-0.5">
            <label class="text-[0.7em] text-text-dim uppercase tracking-wider" for="env-url">Base URL</label>
            <input
              class="bg-surface border border-edge text-text-primary px-2.5 py-1.5 rounded-md font-mono text-[0.85em] w-full"
              id="env-url"
              type="text"
              value={editingEnv.baseUrl}
              oninput={(e) => handleFieldChange('baseUrl', e.target.value)}
              placeholder="http://localhost:10235"
            />
          </div>

          <!-- Auth -->
          <div class="flex flex-col gap-0.5">
            <label class="text-[0.7em] text-text-dim uppercase tracking-wider" for="env-auth">Auth (user:token)</label>
            <input
              class="bg-surface border border-edge text-text-primary px-2.5 py-1.5 rounded-md font-mono text-[0.85em] w-full"
              id="env-auth"
              type="text"
              value={editingEnv.auth}
              oninput={(e) => handleFieldChange('auth', e.target.value)}
              placeholder="user@example.com:TOKEN"
            />
          </div>

          <!-- Memo -->
          <div class="flex flex-col gap-0.5">
            <label class="text-[0.7em] text-text-dim uppercase tracking-wider" for="env-memo">Memo</label>
            <input
              class="bg-surface border border-edge text-text-dim px-2.5 py-1.5 rounded-md font-mono text-[0.85em] w-full italic placeholder:italic"
              id="env-memo"
              type="text"
              value={editingEnv.memo}
              oninput={(e) => handleFieldChange('memo', e.target.value)}
              placeholder="e.g. v3 stable branch"
            />
          </div>

          <!-- Metadata -->
          <div class="flex flex-col gap-1 mt-1">
            <div class="text-[0.7em] text-text-dim uppercase tracking-wider">Metadata</div>

            {#each metaRows as row, i}
              <div class="flex items-center gap-1.5 text-[0.8em] font-mono">
                <input
                  type="text"
                  class="flex-1 max-w-[200px] bg-bg border border-edge text-text-primary px-1.5 py-0.5 rounded font-mono text-[0.9em] min-w-[80px]"
                  placeholder="key"
                  bind:value={row.key}
                  oninput={handleMetaChange}
                />
                <span class="text-text-dim text-[0.85em] shrink-0 select-none">=</span>
                <input
                  type="text"
                  class="flex-2 bg-bg border border-edge text-text-primary px-1.5 py-0.5 rounded font-mono text-[0.9em] min-w-[80px]"
                  placeholder="value"
                  bind:value={row.val}
                  oninput={handleMetaChange}
                />
                <button
                  class="bg-transparent border-none text-text-dim cursor-pointer text-[1.1em] px-1.5 py-0.5 rounded shrink-0 hover:text-red hover:bg-red/10"
                  title="Remove"
                  onclick={() => removeMetaRow(i)}
                >&times;</button>
              </div>
            {/each}

            <button
              class="text-[0.75em] font-mono px-2.5 py-0.5 rounded cursor-pointer border border-dashed border-edge bg-transparent text-text-dim mt-0.5 hover:border-accent hover:text-accent self-start"
              onclick={addMetaRow}
            >+ Add</button>
          </div>
        </div>
      {:else}
        <div class="flex items-center justify-center h-full text-[0.85em] text-text-dim">
          {#if session.environments.length > 0}
            Select an environment to edit
          {:else}
            Add an environment to get started
          {/if}
        </div>
      {/if}
    </div>
  </div>
</Modal>

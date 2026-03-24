<!-- src/components/OpenApiLoader.svelte -->

<script>
  import Modal from './Modal.svelte';
  import { apiParseOpenapi } from '../../lib/api.js';
  import { addEndpoint, clearEndpointsLocal } from '../stores/endpoints.svelte.js';
  import { session } from '../stores/session.svelte.js';

  let { open, onclose } = $props();

  let parsedSpec = $state(null);
  let specUrl = $state('');
  let loading = $state(false);
  let infoText = $state('');
  let groupChecked = $state([]);
  let opChecked = $state([]);
  let groupsOpen = $state([]);

  function resetState() {
    parsedSpec = null;
    specUrl = '';
    loading = false;
    infoText = '';
    groupChecked = [];
    opChecked = [];
    groupsOpen = [];
  }

  async function loadSpecFromUrl() {
    if (!specUrl.trim()) return;
    const fd = new FormData();
    fd.append('url', specUrl.trim());
    await loadSpec(fd, specUrl.trim());
  }

  function loadSpecFromFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    loadSpec(fd, file.name);
  }

  async function loadSpec(fd, sourceName) {
    loading = true;
    infoText = 'Loading...';
    parsedSpec = null;
    try {
      const data = await apiParseOpenapi(fd);
      if (data.error) {
        infoText = 'Error: ' + data.error;
        loading = false;
        return;
      }
      parsedSpec = data;
      parsedSpec._src = sourceName;
      infoText = '';
      // Initialize checkbox state: all checked by default
      groupChecked = data.groups.map(() => true);
      groupsOpen = data.groups.map(() => false);
      opChecked = data.groups.map(g => g.operations.map(() => true));
    } catch (err) {
      infoText = 'Error: ' + err.message;
    }
    loading = false;
  }

  function toggleGroup(gi) {
    groupsOpen[gi] = !groupsOpen[gi];
  }

  function toggleGroupCheck(gi, checked) {
    groupChecked[gi] = checked;
    opChecked[gi] = opChecked[gi].map(() => checked);
  }

  function selectAll(checked) {
    groupChecked = groupChecked.map(() => checked);
    opChecked = opChecked.map(ops => ops.map(() => checked));
  }

  async function loadSelectedToEndpoints() {
    if (!parsedSpec) return;
    const sel = [];
    parsedSpec.groups.forEach((g, gi) => {
      g.operations.forEach((op, oi) => {
        if (opChecked[gi]?.[oi]) {
          sel.push({ ...op, _group: g.name });
        }
      });
    });
    if (!sel.length) return;
    clearEndpointsLocal();
    for (const op of sel) {
      let body = op.body || '';
      if (op.content_type === 'application/json' && body && body.includes('=')) {
        try {
          const obj = {};
          body.split('&').forEach(pair => {
            const [k, v] = pair.split('=');
            if (v === 'true' || v === 'false') obj[k] = v === 'true';
            else if (!isNaN(v) && v !== '') obj[k] = Number(v);
            else obj[k] = decodeURIComponent(v);
          });
          body = JSON.stringify(obj);
        } catch {
          // keep original body
        }
      }
      await addEndpoint({
        method: op.method,
        label: op.label,
        path: op.path,
        body,
        contentType: op.content_type,
        group: op._group,
        cardFields: (op.fields || op.query_fields || op.path_fields)
          ? { fields: op.fields || [], query_fields: op.query_fields || [], path_fields: op.path_fields || [], response_fields: op.response_fields || {} }
          : null,
        fieldsMode: (op.fields || op.query_fields || op.path_fields) ? 'on' : 'off',
      });
    }
    session.specSource = parsedSpec._src || 'OpenAPI spec';
    resetState();
    onclose();
  }

  function handleClose() {
    resetState();
    onclose();
  }
</script>

<Modal open={open} onclose={handleClose}>
  <div class="flex items-center justify-between px-[18px] py-3.5 border-b border-edge">
    <h3 class="text-[0.95em] font-semibold">Import from OpenAPI Spec</h3>
    <button data-testid="btn-close-openapi" class="bg-transparent border-none text-text-dim cursor-pointer text-[1.3em] px-1 rounded hover:text-red" onclick={handleClose}>&times;</button>
  </div>

  <div class="p-[18px] overflow-y-auto flex-1">
    <div class="flex gap-2 items-center mb-3 flex-wrap">
      <input type="text" bind:value={specUrl} placeholder="https://example.com/openapi.yaml" class="bg-bg border border-edge text-text-primary px-2.5 py-1.5 rounded-md font-mono text-[0.85em] flex-1 min-w-[200px]" data-testid="openapi-url-input" />
      <button class="btn-secondary" data-testid="btn-openapi-fetch" onclick={loadSpecFromUrl} disabled={loading}>Fetch</button>
      <span class="text-text-dim text-[0.8em] px-1">or</span>
      <input type="file" accept=".json,.yaml,.yml" onchange={loadSpecFromFile} class="text-[0.8em] text-text-dim" data-testid="openapi-file-input" />
    </div>

    {#if infoText}
      <div class="text-[0.8em] text-text-dim mb-2.5 font-mono">{infoText}</div>
    {/if}

    {#if parsedSpec}
      <div class="text-[0.8em] text-text-dim mb-2.5 font-mono">
        <strong>{parsedSpec.title}</strong> {parsedSpec.version} &mdash; {parsedSpec.total_operations} ops in {parsedSpec.groups.length} groups
      </div>

      <div class="flex gap-2 mb-2">
        <button class="btn-ghost" data-testid="btn-openapi-select-all" onclick={() => selectAll(true)}>Select All</button>
        <button class="btn-ghost" data-testid="btn-openapi-deselect-all" onclick={() => selectAll(false)}>Deselect All</button>
      </div>

      <div class="max-h-[400px] overflow-y-auto">
        {#each parsedSpec.groups as g, gi}
          <div class="mb-2 border border-edge rounded-md overflow-hidden">
            <div class="flex items-center gap-2 px-3 py-2 cursor-pointer select-none bg-white/[0.02] hover:bg-white/[0.04]" role="button" tabindex="0" data-testid="openapi-group-{gi}" onclick={() => toggleGroup(gi)} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleGroup(gi); } }}>
              <input
                type="checkbox"
                checked={groupChecked[gi]}
                class="m-0 accent-accent"
                data-testid="openapi-group-check-{gi}"
                onclick={(e) => { e.stopPropagation(); toggleGroupCheck(gi, e.target.checked); }}
              />
              <span class="chevron" class:open={groupsOpen[gi]}>&#9654;</span>
              <span class="font-semibold font-mono text-[0.85em]">{g.name}</span>
              <span class="text-text-dim text-[0.75em]">{g.count} ops</span>
            </div>
            <div class="toggle-block px-3 py-1 pb-2" class:open={groupsOpen[gi]}>
              {#each g.operations as op, oi}
                <div class="flex items-center gap-2 py-1 text-[0.8em] font-mono">
                  <input
                    type="checkbox"
                    checked={opChecked[gi]?.[oi] ?? true}
                    class="m-0 accent-accent"
                    data-testid="openapi-op-check-{gi}-{oi}"
                    onchange={(e) => { opChecked[gi][oi] = e.target.checked; }}
                  />
                  <span class="font-semibold w-[52px] text-right {op.method.toLowerCase() === 'get' ? 'text-green' : op.method.toLowerCase() === 'post' ? 'text-accent' : op.method.toLowerCase() === 'put' ? 'text-yellow' : op.method.toLowerCase() === 'delete' ? 'text-red' : op.method.toLowerCase() === 'patch' ? 'text-purple' : ''}">{op.method}</span>
                  <span class="text-text-primary">{op.path}</span>
                  {#if op.summary}
                    <span class="text-text-dim ml-2 italic">{op.summary}</span>
                  {/if}
                </div>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  {#if parsedSpec}
    <div class="flex gap-2 px-[18px] py-3 border-t border-edge">
      <button class="btn-primary" data-testid="btn-openapi-load" onclick={loadSelectedToEndpoints}>Load Selected</button>
    </div>
  {/if}
</Modal>

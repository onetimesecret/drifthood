<script>
  import Modal from './Modal.svelte';
  import { apiParseOpenapi } from '../../lib/api.js';
  import { addEndpoint, clearEndpoints } from '../stores/endpoints.svelte.js';
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

  function loadSelectedToEndpoints() {
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
    clearEndpoints();
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
      addEndpoint({
        method: op.method,
        label: op.label,
        path: op.path,
        body,
        contentType: op.content_type,
        group: op._group,
        cardFields: op.fields || op.query_fields || op.path_fields
          ? { fields: op.fields || [], query_fields: op.query_fields || [], path_fields: op.path_fields || [] }
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
  <div class="modal-header">
    <h3>Import from OpenAPI Spec</h3>
    <button class="modal-close" onclick={handleClose}>&times;</button>
  </div>

  <div class="modal-body">
    <div class="openapi-input-row">
      <input type="text" bind:value={specUrl} placeholder="https://example.com/openapi.yaml" style="flex:1" />
      <button class="btn-secondary" onclick={loadSpecFromUrl} disabled={loading}>Fetch</button>
      <span class="openapi-or">or</span>
      <input type="file" accept=".json,.yaml,.yml" onchange={loadSpecFromFile} />
    </div>

    {#if infoText}
      <div class="openapi-info">{infoText}</div>
    {/if}

    {#if parsedSpec}
      <div class="openapi-info">
        <strong>{parsedSpec.title}</strong> {parsedSpec.version} &mdash; {parsedSpec.total_operations} ops in {parsedSpec.groups.length} groups
      </div>

      <div style="display:flex;gap:8px;margin-bottom:8px">
        <button class="btn-ghost" onclick={() => selectAll(true)}>Select All</button>
        <button class="btn-ghost" onclick={() => selectAll(false)}>Deselect All</button>
      </div>

      <div class="openapi-groups">
        {#each parsedSpec.groups as g, gi}
          <div class="openapi-group">
            <div class="openapi-group-header" role="button" tabindex="0" onclick={() => toggleGroup(gi)} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleGroup(gi); } }}>
              <input
                type="checkbox"
                checked={groupChecked[gi]}
                onclick={(e) => { e.stopPropagation(); toggleGroupCheck(gi, e.target.checked); }}
              />
              <span class="chevron" class:open={groupsOpen[gi]}>&#9654;</span>
              <span class="openapi-group-name">{g.name}</span>
              <span class="openapi-group-count">{g.count} ops</span>
            </div>
            <div class="openapi-group-body" class:open={groupsOpen[gi]}>
              {#each g.operations as op, oi}
                <div class="openapi-op">
                  <input
                    type="checkbox"
                    checked={opChecked[gi]?.[oi] ?? true}
                    onchange={(e) => { opChecked[gi][oi] = e.target.checked; }}
                  />
                  <span class="op-method {op.method.toLowerCase()}">{op.method}</span>
                  <span class="op-path">{op.path}</span>
                  {#if op.summary}
                    <span class="op-summary">{op.summary}</span>
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
    <div class="modal-footer has-spec">
      <button class="btn-primary" onclick={loadSelectedToEndpoints}>Load Selected</button>
    </div>
  {/if}
</Modal>

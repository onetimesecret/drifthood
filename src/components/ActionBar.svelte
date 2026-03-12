<script>
  import { EXAMPLES } from '../../lib/examples.js';
  import { apiCompare } from '../../lib/api.js';
  import { toDiffPath } from '../../lib/format.js';
  import { setNestedValue, flattenObj } from '../../lib/params.js';
  import { endpoints, addEndpoint, clearEndpoints, clearResults } from '../stores/endpoints.svelte.js';
  import { session } from '../stores/session.svelte.js';
  import { ui } from '../stores/ui.svelte.js';
  import { snapshot, restore } from '../stores/snapshot.js';

  // Local dropdown state
  let openMenu = $state(null); // 'examples' | 'import' | 'export' | null
  let running = $state(false);

  // Tally (derived from endpoints)
  let total = $derived(endpoints.length);
  let driftCount = $derived(endpoints.filter(ep => ep.state === 'done-drift').length);
  let okCount = $derived(endpoints.filter(ep => ep.state === 'done-ok').length);
  let runningCount = $derived(endpoints.filter(ep => ep.state === 'running').length);
  let ran = $derived(driftCount + okCount + runningCount);
  let hasResults = $derived(ran > 0);

  function toggleMenu(name) {
    openMenu = openMenu === name ? null : name;
  }

  function closeMenus() {
    openMenu = null;
  }

  // Click-outside to close menus
  $effect(() => {
    function handleClick(e) {
      if (openMenu && !e.target.closest('.action-menu')) {
        openMenu = null;
      }
    }
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  });

  function addEndpointDefault() {
    addEndpoint({});
  }

  function loadExampleSet(name) {
    clearEndpoints();
    for (const r of (EXAMPLES[name] || [])) {
      addEndpoint({ method: r.m, label: r.l, path: r.p, body: r.b, contentType: r.ct });
    }
    closeMenus();
  }

  function setFilter(filter) {
    ui.filter = filter;
  }

  function handleClearRuns() {
    clearResults();
    ui.filter = 'all';
  }

  // Run all visible endpoints sequentially
  async function runAll() {
    running = true;
    const ignorePaths = session.ignorePaths.length
      ? session.ignorePaths.map(toDiffPath)
      : null;

    for (const ep of endpoints) {
      // Skip filtered-out endpoints
      if (ui.filter === 'drift' && ep.state !== 'done-drift') continue;
      if (ui.filter === 'ok' && ep.state !== 'done-ok') continue;
      // For 'all' filter, run everything

      // We need to gather endpoint config and run apiCompare
      const epConfig = readEndpointConfig(ep);

      // Set running state
      ep.state = 'running';
      ep.result = null;

      try {
        const r = await apiCompare({
          label: epConfig.label,
          method: epConfig.method,
          path: epConfig.path,
          body: epConfig.body,
          content_type: epConfig.content_type,
          group: epConfig.group,
          host_a: session.hostA,
          host_b: session.hostB,
          auth_a: session.authA || null,
          auth_b: session.authB || null,
          ignore_paths: ignorePaths,
        });

        r.request_body = epConfig.body;
        r.request_content_type = epConfig.content_type;

        ep.state = r.has_drift ? 'done-drift' : 'done-ok';
        ep.result = r;
      } catch (err) {
        ep.state = 'done-drift';
        ep.result = {
          has_drift: true,
          error: err.message,
          diff: {},
          response_a: { status: null, headers: {}, body: null, elapsed_ms: null },
          response_b: { status: null, headers: {}, body: null, elapsed_ms: null },
        };
      }
    }

    running = false;
  }

  // Gather endpoint config for API call (mirrors EndpointCard.readEndpoint)
  function readEndpointConfig(ep) {
    let body = ep.body || null;
    const hasBodyFields = ep.cardFields?.fields?.length > 0;

    if (ep.fieldsMode === 'on' && hasBodyFields) {
      const info = ep.cardFields;
      const fv = ep.fieldValues || {};
      const obj = {};
      for (const f of info.fields) {
        if (f.nested) continue;
        const val = fv[f.path];
        if (val === undefined || val === '') continue;
        setNestedValue(obj, f.path, val);
      }
      if (ep.contentType === 'application/json') {
        body = JSON.stringify(obj, null, 2) || null;
      } else {
        const flat = flattenObj(obj);
        body = Object.entries(flat).map(([k, v]) => `${k}=${v}`).join('&') || null;
      }
    }

    let path = ep.path;
    const info = ep.cardFields;
    if (info && info.path_fields?.length) {
      const fv = ep.fieldValues || {};
      for (const pf of info.path_fields) {
        const val = fv[pf.path] || '';
        path = path.replace(`{${pf.name}}`, encodeURIComponent(val));
      }
    }

    return {
      method: ep.method,
      label: ep.label || ep.path,
      path,
      body,
      content_type: ep.contentType || 'query',
      group: ep.group || null,
    };
  }

  // Export JSON
  function exportJson() {
    const state = snapshot();
    const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    a.href = url;
    a.download = `drift-session-${ts}.json`;
    a.click();
    URL.revokeObjectURL(url);
    closeMenus();
  }

  // Export HTML (simplified — embeds snapshot as DD_SNAPSHOT)
  function exportHtml() {
    const state = snapshot();
    const src = state.title || state.specSource || 'manual';
    const ts = new Date().toISOString().slice(0, 10);
    const html = `<!DOCTYPE html>
<html><head><title>Drift Detector - ${src} - ${ts}</title>
<script>var DD_SNAPSHOT = ${JSON.stringify(state)};<\/script>
</head><body><p>This snapshot can be imported into Drift Detector.</p></body></html>`;
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const tsFile = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    a.href = url;
    a.download = `drift-snapshot-${tsFile}.html`;
    a.click();
    URL.revokeObjectURL(url);
    closeMenus();
  }

  // Import from file
  let fileInput;

  function triggerImport() {
    closeMenus();
    fileInput?.click();
  }

  function handleFileImport(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const name = file.name.toLowerCase();

    const reader = new FileReader();
    reader.onload = (evt) => {
      const text = evt.target.result;
      if (name.endsWith('.html') || name.endsWith('.htm')) {
        importHtml(text);
      } else if (name.endsWith('.json')) {
        importJson(text, file.name);
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  }

  function importJson(text, filename) {
    try {
      const data = JSON.parse(text);
      if (data.endpoints && Array.isArray(data.endpoints)) {
        restore(data);
      } else if (data.openapi || data.swagger || data.paths) {
        // OpenAPI spec — open the modal
        ui.activeModal = 'openapi';
        return;
      }
    } catch (err) {
      console.error('Failed to parse JSON:', err);
    }
  }

  function importHtml(text) {
    const match = text.match(/var\s+DD_SNAPSHOT\s*=\s*(\{[\s\S]*?\});\s*<\/script>/);
    if (!match) return;
    try {
      const snap = JSON.parse(match[1]);
      if (snap.endpoints && Array.isArray(snap.endpoints)) {
        restore(snap);
      }
    } catch (err) {
      console.error('Failed to parse HTML snapshot:', err);
    }
  }

  function openOpenapiModal() {
    ui.activeModal = 'openapi';
    closeMenus();
  }

  function openSchemaDiffModal() {
    ui.activeModal = 'schema-diff';
  }
</script>

<div class="action-bar">
  <button class="btn-ghost" onclick={addEndpointDefault}>+ Add Endpoint</button>

  <!-- Examples menu -->
  <div class="action-menu">
    <button class="btn-ghost" onclick={() => toggleMenu('examples')}>Examples</button>
    <div class="action-dropdown" class:open={openMenu === 'examples'}>
      <div class="menu-desc">Load example endpoint sets</div>
      <button onclick={() => loadExampleSet('mixed')}>Mixed (GET + form + json)</button>
      <button onclick={() => loadExampleSet('query-only')}>Query-only (GET)</button>
      <button onclick={() => loadExampleSet('form-only')}>Form-only (POST)</button>
      <button onclick={() => loadExampleSet('json-only')}>JSON-only (POST)</button>
    </div>
  </div>

  <!-- Import menu -->
  <div class="action-menu">
    <button class="btn-ghost" onclick={() => toggleMenu('import')}>Import</button>
    <div class="action-dropdown" class:open={openMenu === 'import'}>
      <button onclick={openOpenapiModal}>From OpenAPI spec...</button>
      <button onclick={triggerImport}>From file (.json/.html)...</button>
      <div class="menu-hint">Or drag &amp; drop a file onto the page</div>
    </div>
  </div>

  <!-- Export menu -->
  <div class="action-menu">
    <button class="btn-ghost" onclick={() => toggleMenu('export')}>Export</button>
    <div class="action-dropdown" class:open={openMenu === 'export'}>
      <button onclick={exportJson}>Current state as JSON</button>
      <button onclick={exportHtml}>Snapshot as HTML</button>
    </div>
  </div>

  <button class="btn-ghost" onclick={openSchemaDiffModal}>Diff Schemas</button>

  <button class="btn-primary" onclick={runAll} disabled={running || total === 0}>
    {#if running}
      <span class="spinner"></span> Running...
    {:else}
      Run All
    {/if}
  </button>

  <button class="btn-ghost" onclick={handleClearRuns} disabled={!hasResults}>Clear Runs</button>

  {#if hasResults}
    <div class="filter-pills">
      <button class:active={ui.filter === 'all'} onclick={() => setFilter('all')}>All</button>
      <button class:active={ui.filter === 'drift'} onclick={() => setFilter('drift')}>Drifts</button>
      <button class:active={ui.filter === 'ok'} onclick={() => setFilter('ok')}>OK</button>
    </div>
  {/if}

  <div class="tally">
    {#if ran === 0}
      <span class="t-dim">{total} endpoint{total !== 1 ? 's' : ''}</span>
    {:else}
      <span class="t-drift">{driftCount} drift</span>
      {' '}<span class="t-ok">{okCount} ok</span>
      {' '}<span class="t-dim">({ran}/{total})</span>
    {/if}
  </div>
</div>

<!-- Hidden file input for imports -->
<input
  type="file"
  accept=".json,.html,.htm"
  style="display:none"
  bind:this={fileInput}
  onchange={handleFileImport}
/>

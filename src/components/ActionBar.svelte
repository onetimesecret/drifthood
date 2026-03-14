<script>
  import { EXAMPLES } from '../../lib/examples.js';
  import { apiCompare } from '../../lib/api.js';
  import { toDiffPath } from '../../lib/format.js';
  import { setNestedValue, flattenObj } from '../../lib/params.js';
  import { runConcurrent } from '../../lib/concurrent.js';
  import { endpoints, addEndpoint, clearEndpoints, clearResults } from '../stores/endpoints.svelte.js';
  import { session, getEnvA, getEnvB } from '../stores/session.svelte.js';
  import { ui } from '../stores/ui.svelte.js';
  import { snapshotLegacy, restore } from '../stores/snapshot.js';

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

  async function loadExampleSet(name) {
    await clearEndpoints();
    for (const r of (EXAMPLES[name] || [])) {
      await addEndpoint({ method: r.m, label: r.l, path: r.p, body: r.b, contentType: r.ct });
    }
    closeMenus();
  }

  function setFilter(filter) {
    ui.filter = filter;
    ui.collapseGen++;
  }

  function handleClearRuns() {
    clearResults();
    ui.filter = 'all';
  }

  async function runAll() {
    running = true;
    const ignorePaths = session.ignorePaths.length
      ? session.ignorePaths.map(toDiffPath)
      : null;
    const envA = getEnvA();
    const envB = getEnvB();

    const tasks = [];
    for (const ep of endpoints) {
      const epConfig = readEndpointConfig(ep);
      ep.state = 'running';
      ep.result = null;

      tasks.push(async () => {
        try {
          const r = await apiCompare({
            label: epConfig.label,
            method: epConfig.method,
            path: epConfig.path,
            body: epConfig.body,
            content_type: epConfig.content_type,
            group: epConfig.group,
            host_a: envA?.baseUrl || '',
            host_b: envB?.baseUrl || '',
            auth_a: envA?.auth || null,
            auth_b: envB?.auth || null,
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
      });
    }

    await runConcurrent(tasks);
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
    const state = snapshotLegacy();
    const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    a.href = url;
    a.download = `drift-testrun-${ts}.json`;
    a.click();
    URL.revokeObjectURL(url);
    closeMenus();
  }

  // Export HTML (simplified — embeds snapshot as DD_SNAPSHOT)
  function exportHtml() {
    const state = snapshotLegacy();
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

  async function importJson(text, filename) {
    try {
      const data = JSON.parse(text);
      if (data.endpoints && Array.isArray(data.endpoints)) {
        await restore(data);
      } else if (data.openapi || data.swagger || data.paths) {
        // OpenAPI spec — open the modal
        ui.activeModal = 'openapi';
        return;
      }
    } catch (err) {
      console.error('Failed to parse JSON:', err);
    }
  }

  async function importHtml(text) {
    const match = text.match(/var\s+DD_SNAPSHOT\s*=\s*(\{[\s\S]*?\});\s*<\/script>/);
    if (!match) return;
    try {
      const snap = JSON.parse(match[1]);
      if (snap.endpoints && Array.isArray(snap.endpoints)) {
        await restore(snap);
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

<div class="sticky top-0 z-15 bg-bg py-2 pb-2.5 flex gap-2.5 items-center flex-wrap border-b border-edge mb-2.5">
  <button class="btn-ghost" onclick={addEndpointDefault}>+ Add Endpoint</button>

  <!-- Examples menu -->
  <div class="action-menu relative inline-block">
    <button class="btn-ghost" onclick={() => toggleMenu('examples')}>Examples</button>
    <div class="toggle-block absolute top-full left-0 bg-surface border border-edge rounded-lg p-1 z-10 min-w-[260px] mt-1 shadow-[0_8px_24px_rgba(0,0,0,0.4)]" class:open={openMenu === 'examples'}>
      <div class="text-[0.75em] text-text-dim px-3 py-1">Load example endpoint sets</div>
      <button class="block w-full text-left bg-transparent border-none text-text-primary px-3 py-2 rounded text-[0.85em] cursor-pointer hover:bg-white/5" onclick={() => loadExampleSet('mixed')}>Mixed (GET + form + json)</button>
      <button class="block w-full text-left bg-transparent border-none text-text-primary px-3 py-2 rounded text-[0.85em] cursor-pointer hover:bg-white/5" onclick={() => loadExampleSet('query-only')}>Query-only (GET)</button>
      <button class="block w-full text-left bg-transparent border-none text-text-primary px-3 py-2 rounded text-[0.85em] cursor-pointer hover:bg-white/5" onclick={() => loadExampleSet('form-only')}>Form-only (POST)</button>
      <button class="block w-full text-left bg-transparent border-none text-text-primary px-3 py-2 rounded text-[0.85em] cursor-pointer hover:bg-white/5" onclick={() => loadExampleSet('json-only')}>JSON-only (POST)</button>
    </div>
  </div>

  <!-- Import menu -->
  <div class="action-menu relative inline-block">
    <button class="btn-ghost" onclick={() => toggleMenu('import')}>Import</button>
    <div class="toggle-block absolute top-full left-0 bg-surface border border-edge rounded-lg p-1 z-10 min-w-[260px] mt-1 shadow-[0_8px_24px_rgba(0,0,0,0.4)]" class:open={openMenu === 'import'}>
      <button class="block w-full text-left bg-transparent border-none text-text-primary px-3 py-2 rounded text-[0.85em] cursor-pointer hover:bg-white/5" onclick={openOpenapiModal}>From OpenAPI spec...</button>
      <button class="block w-full text-left bg-transparent border-none text-text-primary px-3 py-2 rounded text-[0.85em] cursor-pointer hover:bg-white/5" onclick={triggerImport}>From file (.json/.html)...</button>
      <div class="text-[0.7em] text-text-dim px-3 py-1.5 border-t border-edge mt-1">Or drag &amp; drop a file onto the page</div>
    </div>
  </div>

  <!-- Export menu -->
  <div class="action-menu relative inline-block">
    <button class="btn-ghost" onclick={() => toggleMenu('export')}>Export</button>
    <div class="toggle-block absolute top-full left-0 bg-surface border border-edge rounded-lg p-1 z-10 min-w-[260px] mt-1 shadow-[0_8px_24px_rgba(0,0,0,0.4)]" class:open={openMenu === 'export'}>
      <button class="block w-full text-left bg-transparent border-none text-text-primary px-3 py-2 rounded text-[0.85em] cursor-pointer hover:bg-white/5" onclick={exportJson}>Current state as JSON</button>
      <button class="block w-full text-left bg-transparent border-none text-text-primary px-3 py-2 rounded text-[0.85em] cursor-pointer hover:bg-white/5" onclick={exportHtml}>Snapshot as HTML</button>
    </div>
  </div>

  <button class="btn-ghost" onclick={openSchemaDiffModal}>Diff Schemas</button>

  <button class="btn-primary" onclick={runAll} disabled={running || total === 0}>
    {#if running}
      <span class="inline-block w-3 h-3 border-2 border-edge border-t-accent rounded-full animate-spin"></span> Running...
    {:else}
      Run All
    {/if}
  </button>

  <button class="btn-ghost" onclick={handleClearRuns} disabled={!hasResults}>Clear Runs</button>

  {#if hasResults}
    <div class="flex gap-1">
      <button class="text-[0.7em] px-2 py-0.5 rounded-full cursor-pointer border bg-bg {ui.filter === 'all' ? 'border-accent text-accent bg-accent/10' : 'border-edge text-text-dim'}" onclick={() => setFilter('all')}>All</button>
      <button class="text-[0.7em] px-2 py-0.5 rounded-full cursor-pointer border bg-bg {ui.filter === 'drift' ? 'border-accent text-accent bg-accent/10' : 'border-edge text-text-dim'}" onclick={() => setFilter('drift')}>Drifts</button>
      <button class="text-[0.7em] px-2 py-0.5 rounded-full cursor-pointer border bg-bg {ui.filter === 'ok' ? 'border-accent text-accent bg-accent/10' : 'border-edge text-text-dim'}" onclick={() => setFilter('ok')}>OK</button>
    </div>
  {/if}

  <div class="text-[0.8em] font-mono ml-auto">
    {#if ran === 0}
      <span class="text-text-dim">{total} endpoint{total !== 1 ? 's' : ''}</span>
    {:else}
      <span class="text-red font-semibold">{driftCount} drift</span>
      {' '}<span class="text-green font-semibold">{okCount} ok</span>
      {' '}<span class="text-text-dim">({ran}/{total})</span>
    {/if}
  </div>
</div>

<!-- Hidden file input for imports -->
<input
  type="file"
  accept=".json,.html,.htm"
  class="hidden"
  bind:this={fileInput}
  onchange={handleFileImport}
/>

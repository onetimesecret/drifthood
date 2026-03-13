<script>
  import TokenGate from './components/TokenGate.svelte';
  import Sidebar from './components/Sidebar.svelte';
  import HostConfig from './components/HostConfig.svelte';
  import IgnoreConfig from './components/IgnoreConfig.svelte';
  import ActionBar from './components/ActionBar.svelte';
  import EndpointCard from './components/EndpointCard.svelte';
  import OpenApiLoader from './components/OpenApiLoader.svelte';
  import SchemaDiff from './components/SchemaDiff.svelte';

  import { DD_VERSION } from '../lib/examples.js';
  import { stateFingerprint } from '../lib/state.js';
  import { apiConfig, apiSave, apiCompare, apiListDocuments, apiGetDocument, apiGetTestrun, apiUpdateDocumentTitle } from '../lib/api.js';
  import { toDiffPath } from '../lib/format.js';
  import { setNestedValue, flattenObj } from '../lib/params.js';
  import { session } from './stores/session.svelte.js';
  import { endpoints, addEndpoint } from './stores/endpoints.svelte.js';
  import { ui } from './stores/ui.svelte.js';
  import { documents, notifyDocumentsChanged } from './stores/documents.svelte.js';
  import { snapshot, restore } from './stores/snapshot.js';

  // ── Save button state ──
  let saveStatus = $state({ text: 'Save', color: '', disabled: false });

  // ── Drop overlay and toast ──
  let dropActive = $state(false);
  let dropDepth = 0;
  let toast = $state({ text: '', cls: '', visible: false });
  let toastTimer;

  // ── Back-to-top ──
  let showBackToTop = $state(false);

  // ── Breadcrumb ──
  let breadcrumbText = $state('');

  // ── Derived: endpoint groups and filtering ──
  let visibleEndpoints = $derived.by(() => {
    return endpoints.map((ep, idx) => {
      const visible = ui.filter === 'all'
        || (ui.filter === 'drift' && ep.state === 'done-drift')
        || (ui.filter === 'ok' && ep.state === 'done-ok');
      return { ep, idx, visible };
    });
  });

  // Group dividers: detect group boundaries
  let groupedEntries = $derived.by(() => {
    const entries = [];
    let lastGroup = null;

    for (const item of visibleEndpoints) {
      if (!item.visible) continue;
      const g = item.ep.group;
      if (g && g !== lastGroup) {
        // Compute group stats
        const groupEps = endpoints.filter(ep => ep.group === g);
        const groupVisible = visibleEndpoints.filter(v => v.ep.group === g && v.visible);
        const driftCount = groupEps.filter(ep => ep.state === 'done-drift').length;
        const okCount = groupEps.filter(ep => ep.state === 'done-ok').length;
        entries.push({
          type: 'divider',
          group: g,
          count: groupEps.length,
          visibleCount: groupVisible.length,
          driftCount,
          okCount,
        });
      }
      lastGroup = g;
      entries.push({ type: 'card', ep: item.ep });
    }
    return entries;
  });

  // ── Doc indicator ──
  let docIndicator = $derived(
    documents.currentDocumentId
      ? `doc #${documents.currentDocumentId} / testrun #${documents.currentTestrunNumber}`
      : ''
  );

  // ── Init on mount ──
  $effect(() => {
    init();
    // Scroll listener for back-to-top
    const onScroll = () => { showBackToTop = window.scrollY > 400; };
    window.addEventListener('scroll', onScroll);
    return () => window.removeEventListener('scroll', onScroll);
  });

  async function init() {
    // Check for embedded snapshot (HTML export)
    if (typeof globalThis.DD_SNAPSHOT !== 'undefined' && globalThis.DD_SNAPSHOT?.endpoints) {
      restore(globalThis.DD_SNAPSHOT);
      const snap = globalThis.DD_SNAPSHOT;
      const src = snap.specSource || 'snapshot';
      const when = snap.savedAt ? ' (' + snap.savedAt.slice(0, 19).replace('T', ' ') + ')' : '';
      breadcrumbText = 'snapshot: ' + src + when;
      startAutosave();
      return;
    }

    // Try loading most recent document from DB
    try {
      const data = await apiListDocuments();
      if (data.documents?.length) {
        const mostRecent = data.documents[0];
        try {
          const docData = await apiGetDocument(mostRecent.id);
          if (docData.testruns?.length) {
            const latest = docData.testruns[docData.testruns.length - 1];
            await loadSavedTestrun(mostRecent.id, latest.testrun_number);
            return;
          }
        } catch { /* fall through */ }
      }
    } catch { /* server not running */ }

    // Fresh start
    addEndpoint();
  }

  async function loadSavedTestrun(docId, testrunNumber) {
    try {
      const data = await apiGetTestrun(docId, testrunNumber);
      if (data.error || !data.testrun) {
        showDropToast('Testrun not found: ' + (data.error || 'no testrun data'), true);
        return;
      }
      const state = data.testrun.state;
      if (!state) {
        showDropToast('Testrun has no state data', true);
        return;
      }
      restore(state);
      // Set document tracking AFTER restore() so the stale testrunNumber
      // stored inside the snapshot doesn't overwrite the actual values.
      documents.currentDocumentId = docId;
      documents.currentTestrunNumber = testrunNumber;
      documents.lastSavedStateHash = stateFingerprint(state);
      breadcrumbText = `doc #${docId} testrun #${testrunNumber}`;
      showDropToast(`Loaded testrun #${testrunNumber}`, false);
      startAutosave();
    } catch (err) {
      showDropToast('Load failed: ' + err.message, true);
    }
  }

  // ── Save ──
  async function saveTestrun() {
    saveStatus = { text: 'Saving...', color: '', disabled: true };
    try {
      const state = snapshot();
      const data = await apiSave(state, documents.currentDocumentId, 'save', documents.currentTestrunNumber || null);
      if (data.ok) {
        documents.currentDocumentId = data.document.id;
        if (data.testrun) {
          documents.currentTestrunNumber = data.testrun.testrun_number;
        }
        documents.lastSavedStateHash = stateFingerprint(state);
        breadcrumbText = `doc #${documents.currentDocumentId} testrun #${documents.currentTestrunNumber}`;
        startAutosave();
        saveStatus = { text: 'Saved', color: 'var(--green)', disabled: true };
        notifyDocumentsChanged();
        showDropToast(`Saved testrun #${documents.currentTestrunNumber}`, false);
      } else {
        saveStatus = { text: 'Error', color: 'var(--red)', disabled: true };
        showDropToast('Save failed', true);
      }
    } catch {
      saveStatus = { text: 'Error', color: 'var(--red)', disabled: true };
      showDropToast('Save failed', true);
    }
    setTimeout(() => {
      saveStatus = { text: 'Save', color: '', disabled: false };
    }, 1500);
  }

  // ── Title blur → update doc title ──
  let lastSyncedTitle = '';
  function onTitleFocus() {
    lastSyncedTitle = session.title;
  }
  async function onTitleBlur() {
    const newTitle = session.title.trim();
    if (!documents.currentDocumentId || newTitle === lastSyncedTitle) return;
    lastSyncedTitle = newTitle;
    try {
      await apiUpdateDocumentTitle(documents.currentDocumentId, newTitle || 'Untitled');
    } catch { /* silent */ }
  }

  // ── Autosave ──
  const AUTOSAVE_INTERVAL_MS = 60000;
  let autosaveTimer = null;

  function startAutosave() {
    stopAutosave();
    autosaveTimer = setInterval(doAutosave, AUTOSAVE_INTERVAL_MS);
  }

  function stopAutosave() {
    if (autosaveTimer) {
      clearInterval(autosaveTimer);
      autosaveTimer = null;
    }
  }

  async function doAutosave() {
    if (!documents.currentDocumentId) return;
    if (!endpoints.length) return;
    try {
      const state = snapshot();
      const fp = stateFingerprint(state);
      if (fp === documents.lastSavedStateHash) return;
      const saveData = await apiSave(state, documents.currentDocumentId, 'autosave');
      if (saveData.skipped) {
        documents.lastSavedStateHash = fp;
        return;
      }
      documents.lastSavedStateHash = fp;
      if (saveData.testrun) {
        documents.currentTestrunNumber = saveData.testrun.testrun_number;
        breadcrumbText = `doc #${documents.currentDocumentId} testrun #${documents.currentTestrunNumber}`;
      }
      notifyDocumentsChanged();
      showAutoSaveToast();
    } catch {
      // Silent failure for autosave
    }
  }

  // Pause autosave when page hidden, resume when visible
  $effect(() => {
    function onVisibility() {
      if (document.hidden) {
        stopAutosave();
      } else if (documents.currentDocumentId) {
        startAutosave();
      }
    }
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      stopAutosave();
    };
  });

  // ── Drag and drop ──
  $effect(() => {
    function onDragEnter(e) {
      e.preventDefault();
      dropDepth++;
      if (dropDepth === 1) dropActive = true;
    }
    function onDragLeave(e) {
      e.preventDefault();
      dropDepth--;
      if (dropDepth <= 0) { dropDepth = 0; dropActive = false; }
    }
    function onDragOver(e) { e.preventDefault(); }
    function onDrop(e) {
      e.preventDefault();
      dropDepth = 0;
      dropActive = false;
      const file = e.dataTransfer?.files?.[0];
      if (!file) return;
      handleDroppedFile(file);
    }

    document.addEventListener('dragenter', onDragEnter);
    document.addEventListener('dragleave', onDragLeave);
    document.addEventListener('dragover', onDragOver);
    document.addEventListener('drop', onDrop);
    return () => {
      document.removeEventListener('dragenter', onDragEnter);
      document.removeEventListener('dragleave', onDragLeave);
      document.removeEventListener('dragover', onDragOver);
      document.removeEventListener('drop', onDrop);
    };
  });

  function handleDroppedFile(file) {
    const name = file.name.toLowerCase();
    const reader = new FileReader();
    reader.onload = (evt) => {
      const text = evt.target.result;
      if (name.endsWith('.html') || name.endsWith('.htm')) {
        handleDropHtml(text, file.name);
      } else if (name.endsWith('.json')) {
        handleDropJson(text, file.name);
      } else {
        showDropToast('Unsupported file type. Expected .json or .html', true);
      }
    };
    reader.readAsText(file);
  }

  function handleDropJson(text, filename) {
    let data;
    try {
      data = JSON.parse(text);
    } catch (err) {
      showDropToast('Invalid JSON: ' + err.message, true);
      return;
    }
    if (data.endpoints && Array.isArray(data.endpoints)) {
      stopAutosave();
      restore(data);
      breadcrumbText = data.specSource || filename;
      showDropToast('Loaded testrun: ' + filename, false);
      startAutosave();
      return;
    }
    if (data.openapi || data.swagger || data.paths) {
      ui.activeModal = 'openapi';
      showDropToast('Loading OpenAPI spec: ' + filename, false);
      return;
    }
    showDropToast('Unrecognized JSON. Expected a testrun export or OpenAPI spec.', true);
  }

  function handleDropHtml(text, filename) {
    const match = text.match(/var\s+DD_SNAPSHOT\s*=\s*(\{[\s\S]*?\});\s*<\/script>/);
    if (!match) {
      showDropToast('No snapshot data found in HTML file', true);
      return;
    }
    try {
      const snap = JSON.parse(match[1]);
      if (!snap.endpoints || !Array.isArray(snap.endpoints)) {
        showDropToast('HTML snapshot has no endpoints', true);
        return;
      }
      stopAutosave();
      restore(snap);
      const src = snap.specSource || filename;
      const when = snap.savedAt ? ' (' + snap.savedAt.slice(0, 19).replace('T', ' ') + ')' : '';
      breadcrumbText = 'snapshot: ' + src + when;
      showDropToast('Loaded snapshot: ' + filename, false);
      startAutosave();
    } catch (err) {
      showDropToast('Failed to parse snapshot: ' + err.message, true);
    }
  }

  // ── Toast ──
  function showDropToast(msg, isError) {
    toast = { text: msg, cls: isError ? 'error' : 'ok', visible: true };
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast = { ...toast, visible: false };
    }, 3500);
  }

  function showAutoSaveToast() {
    toast = { text: 'Autosaved', cls: 'autosave', visible: true };
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast = { ...toast, visible: false };
    }, 2000);
  }

  function dismissBreadcrumb() {
    breadcrumbText = '';
  }

  function scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // ── Run group ──
  // Exposed for group divider "run group" buttons — delegates to ActionBar's run logic
  // But since ActionBar has runAll, we do a lightweight version here that runs
  // only endpoints in a specific group.
  async function runGroup(groupName) {
    const ignorePaths = session.ignorePaths.length
      ? session.ignorePaths.map(toDiffPath)
      : null;

    for (const ep of endpoints) {
      if (ep.group !== groupName) continue;

      ep.state = 'running';
      ep.result = null;

      // Build config (same as ActionBar.readEndpointConfig)
      let body = ep.body || null;
      if (ep.fieldsMode === 'on' && ep.cardFields?.fields?.length > 0) {
        const fv = ep.fieldValues || {};
        const obj = {};
        for (const f of ep.cardFields.fields) {
          if (f.nested) continue;
          const val = fv[f.path];
          if (val === undefined || val === '') continue;
          setNestedValue(obj, f.path, val);
        }
        body = ep.contentType === 'application/json'
          ? JSON.stringify(obj, null, 2) || null
          : Object.entries(flattenObj(obj)).map(([k, v]) => `${k}=${v}`).join('&') || null;
      }

      let path = ep.path;
      if (ep.cardFields?.path_fields?.length) {
        const fv = ep.fieldValues || {};
        for (const pf of ep.cardFields.path_fields) {
          path = path.replace(`{${pf.name}}`, encodeURIComponent(fv[pf.path] || ''));
        }
      }

      try {
        const r = await apiCompare({
          label: ep.label || ep.path,
          method: ep.method,
          path,
          body,
          content_type: ep.contentType || 'query',
          group: ep.group || null,
          host_a: session.hostA,
          host_b: session.hostB,
          auth_a: session.authA || null,
          auth_b: session.authB || null,
          ignore_paths: ignorePaths,
        });
        r.request_body = body;
        r.request_content_type = ep.contentType || 'query';
        ep.state = r.has_drift ? 'done-drift' : 'done-ok';
        ep.result = r;
      } catch (err) {
        ep.state = 'done-drift';
        ep.result = {
          has_drift: true, error: err.message, diff: {},
          response_a: { status: null, headers: {}, body: null, elapsed_ms: null },
          response_b: { status: null, headers: {}, body: null, elapsed_ms: null },
        };
      }
    }
  }
</script>

<TokenGate>
<div class="flex min-h-screen -m-5">
  <Sidebar onBreadcrumb={(text) => breadcrumbText = text} />

  <div class="flex-1 p-5 overflow-x-hidden min-w-0">
    <!-- Header -->
    <div class="flex items-center gap-3 mb-1">
      <h1 class="text-[1.4em] font-semibold mb-1">Drift Detector <span class="text-[0.5em] font-normal opacity-50">v{DD_VERSION}</span></h1>
      <button
        class="btn-ghost ml-auto"
        style={saveStatus.color ? `color:${saveStatus.color}` : ''}
        onclick={saveTestrun}
        disabled={saveStatus.disabled}
      >{saveStatus.text}</button>
      {#if docIndicator}
        <span class="text-[0.7em] text-text-dim font-mono" title="Save updates the current testrun. Autosave creates new snapshots when state changes.">{docIndicator}</span>
      {/if}
    </div>

    <!-- Session header -->
    <div class="mb-4">
      <input
        class="bg-transparent border-none text-text-primary text-[1.1em] font-semibold font-[inherit] w-full px-0 py-1 outline-none border-b border-b-transparent focus:border-b-accent placeholder:text-text-dim placeholder:font-normal"
        type="text"
        placeholder="Testrun title (optional)"
        bind:value={session.title}
        onfocus={onTitleFocus}
        onblur={onTitleBlur}
      />
      <textarea
        class="bg-transparent border-none text-text-dim text-[0.8em] font-[inherit] w-full px-0 py-0.5 outline-none resize-none border-b border-b-transparent focus:border-b-edge focus:text-text-primary leading-snug placeholder:text-text-dim"
        placeholder="Notes / context for this comparison testrun"
        rows="1"
        bind:value={session.memo}
      ></textarea>
    </div>

    <!-- Host config -->
    <div class="flex gap-3 items-start mb-5 flex-wrap">
      <HostConfig side="A" />
      <HostConfig side="B" />
    </div>

    <!-- Ignore config -->
    <IgnoreConfig />

    <!-- Endpoints section label -->
    <div class="text-[0.7em] uppercase tracking-widest text-text-dim mb-2 font-semibold">Endpoints</div>

    <!-- Action bar -->
    <ActionBar />

    <!-- Breadcrumb -->
    {#if breadcrumbText}
      <div class="flex items-center gap-2 text-[0.75em] font-mono text-text-dim px-2.5 py-1 bg-surface border border-edge rounded mb-2.5">
        <span class="text-accent">{breadcrumbText}</span>
        <button class="cursor-pointer text-text-dim bg-transparent border-none text-[1em] px-1 hover:text-red" onclick={dismissBreadcrumb}>&times;</button>
      </div>
    {/if}

    <!-- Endpoint cards with group dividers -->
    <div class="mb-5">
      {#each groupedEntries as entry (entry.type === 'card' ? `card-${entry.ep.id}` : `div-${entry.group}`)}
        {#if entry.type === 'divider'}
          <div class="text-[0.75em] font-mono text-text-dim pt-2.5 pb-1 border-b border-edge mb-2 flex items-center gap-2">
            <span class="font-semibold text-text-primary">{entry.group}</span>
            <span class="text-text-dim">{entry.count}</span>
            <span class="text-[0.9em]">
              {#if entry.driftCount + entry.okCount > 0}
                {#if entry.driftCount}
                  <span class="text-red">{entry.driftCount} drift</span>
                {:else}
                  <span class="text-green">all ok</span>
                {/if}
              {/if}
            </span>
            <button class="bg-transparent border border-edge text-text-dim cursor-pointer text-[0.85em] px-2 py-0.5 rounded ml-auto hover:text-accent hover:border-accent" onclick={() => runGroup(entry.group)}>run group</button>
          </div>
        {:else}
          <EndpointCard endpoint={entry.ep} />
        {/if}
      {/each}
    </div>

    <!-- Back to top -->
    {#if showBackToTop}
      <button
        class="fixed bottom-6 right-6 bg-surface border border-edge text-accent w-10 h-10 rounded-full cursor-pointer text-[1.2em] flex items-center justify-center z-30 shadow-[0_4px_12px_rgba(0,0,0,0.4)] hover:bg-accent/15"
        onclick={scrollToTop}
      >&#8593;</button>
    {/if}
  </div>
</div>

<!-- Modals -->
<OpenApiLoader open={ui.activeModal === 'openapi'} onclose={() => { ui.activeModal = null; }} />
<SchemaDiff open={ui.activeModal === 'schema-diff'} onclose={() => { ui.activeModal = null; }} />

<!-- Drop overlay -->
{#if dropActive}
  <div class="fixed inset-0 z-100 bg-[rgba(13,17,23,0.85)] flex items-center justify-center pointer-events-none">
    <div class="border-2 border-dashed border-accent rounded-2xl px-16 py-12 text-center text-accent font-mono">
      <div class="text-[2.5em] mb-3">&#128230;</div>
      <div class="text-[1em] font-semibold">Drop to import</div>
      <div class="text-[0.75em] text-text-dim mt-2">.json (testrun) or .html (snapshot)</div>
    </div>
  </div>
{/if}

<!-- Drop toast -->
{#if toast.visible}
  <div class="fixed bottom-6 left-1/2 -translate-x-1/2 z-[110] bg-surface border rounded-lg px-5 py-2.5 text-[0.85em] font-mono shadow-[0_8px_24px_rgba(0,0,0,0.4)] {toast.cls === 'error' ? 'border-red text-red' : toast.cls === 'ok' ? 'border-green text-green' : 'border-text-dim text-text-dim opacity-80 text-[0.78em]'}">{toast.text}</div>
{/if}
</TokenGate>

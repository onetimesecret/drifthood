<script>
  import TokenGate from './components/TokenGate.svelte';
  import Sidebar from './components/Sidebar.svelte';
  import EnvironmentSelector from './components/EnvironmentSelector.svelte';
  import EnvironmentModal from './components/EnvironmentModal.svelte';
  import EnvironmentDetail from './components/EnvironmentDetail.svelte';
  import IgnoreConfig from './components/IgnoreConfig.svelte';
  import ActionBar from './components/ActionBar.svelte';
  import EndpointCard from './components/EndpointCard.svelte';
  import OpenApiLoader from './components/OpenApiLoader.svelte';
  import SchemaDiff from './components/SchemaDiff.svelte';

  import { DD_VERSION } from '../lib/examples.js';
  import { stateFingerprint } from '../lib/state.js';
  import { apiSave, apiCompare, apiListDocuments, apiGetDocument, apiGetTestrun, apiUpdateDocumentTitle } from '../lib/api.js';
  import { toDiffPath } from '../lib/format.js';
  import { setNestedValue, flattenObj } from '../lib/params.js';
  import { session, addEnvironment, getEnvA, getEnvB, seedDefaultEnvironments } from './stores/session.svelte.js';
  import { endpoints, addEndpoint, clearResults } from './stores/endpoints.svelte.js';
  import { ui } from './stores/ui.svelte.js';
  import { documents, notifyDocumentsChanged, rememberLastDocument, recallLastDocument } from './stores/documents.svelte.js';
  import { snapshot, restore } from './stores/snapshot.js';
  import { runConcurrent } from '../lib/concurrent.js';

  // ── Route state ──
  let currentView = $state('session');  // 'session' | 'environment'
  let envDetailExtid = $state(null);

  // Parse route from URL
  function parseRoute() {
    const path = window.location.pathname;
    const envMatch = path.match(/^\/e\/(.+)/);
    if (envMatch) {
      currentView = 'environment';
      envDetailExtid = decodeURIComponent(envMatch[1]);
    } else {
      currentView = 'session';
      envDetailExtid = null;
    }
  }

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
    documents.currentDocumentExtid
      ? `testrun #${documents.currentTestrunNumber}`
      : ''
  );

  // ── Init on mount ──
  $effect(() => {
    parseRoute();
    init();
    // Scroll listener for back-to-top
    const onScroll = () => { showBackToTop = window.scrollY > 400; };
    window.addEventListener('scroll', onScroll);
    // Listen for popstate (back/forward navigation)
    const onPopState = () => { parseRoute(); };
    window.addEventListener('popstate', onPopState);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('popstate', onPopState);
    };
  });

  // ── Invalidate results when environment config changes ──
  let lastEnvFingerprint = '';
  $effect(() => {
    const envA = getEnvA();
    const envB = getEnvB();
    const fp = JSON.stringify([
      session.selectedA, session.selectedB,
      envA?.baseUrl, envA?.auth,
      envB?.baseUrl, envB?.auth,
    ]);
    if (lastEnvFingerprint && fp !== lastEnvFingerprint) {
      const hasResults = endpoints.some(ep => ep.result !== null);
      if (hasResults) {
        clearResults();
        showDropToast('Results cleared — environment changed', false);
      }
    }
    lastEnvFingerprint = fp;
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

    // Try loading last-viewed document, falling back to most recent
    try {
      const data = await apiListDocuments();
      if (data.documents?.length) {
        const last = recallLastDocument();
        const docExtids = new Set(data.documents.map(d => d.extid));

        // Prefer the remembered doc if it still exists
        if (last?.docExtid && docExtids.has(last.docExtid)) {
          try {
            await loadSavedTestrun(last.docExtid, last.testrunExtid, last.testrunNumber);
            return;
          } catch { /* fall through to most recent */ }
        }

        // Fall back to most recent document
        const mostRecent = data.documents[0];
        try {
          const docData = await apiGetDocument(mostRecent.extid);
          if (docData.testruns?.length) {
            const latest = docData.testruns[docData.testruns.length - 1];
            await loadSavedTestrun(mostRecent.extid, latest.extid, latest.testrun_number);
            return;
          }
        } catch { /* fall through */ }
      }
    } catch { /* server not running */ }

    // Fresh start — seed default environments from server config (HOST_A/HOST_B)
    await seedDefaultEnvironments();
    addEndpoint();
  }

  async function loadSavedTestrun(docExtid, testrunExtid, testrunNumber) {
    try {
      const data = await apiGetTestrun(docExtid, testrunExtid);
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
      // Set document tracking AFTER restore() so the stale values
      // stored inside the snapshot don't overwrite the actual values.
      documents.currentDocumentExtid = docExtid;
      documents.currentTestrunExtid = testrunExtid;
      documents.currentTestrunNumber = testrunNumber;
      documents.lastSavedStateHash = stateFingerprint(state);
      rememberLastDocument(docExtid, testrunExtid, testrunNumber);
      breadcrumbText = `testrun #${testrunNumber}`;
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
      const data = await apiSave(state, documents.currentDocumentExtid, 'save', documents.currentTestrunExtid || null);
      if (data.ok) {
        documents.currentDocumentExtid = data.document.extid;
        if (data.testrun) {
          documents.currentTestrunExtid = data.testrun.extid;
          documents.currentTestrunNumber = data.testrun.testrun_number;
        }
        documents.lastSavedStateHash = stateFingerprint(state);
        rememberLastDocument(documents.currentDocumentExtid, documents.currentTestrunExtid, documents.currentTestrunNumber);
        breadcrumbText = `testrun #${documents.currentTestrunNumber}`;
        startAutosave();
        saveStatus = { text: '\u2713 Saved', color: 'var(--green)', disabled: true };
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
    }, 3000);
  }

  // ── Title blur → update doc title ──
  let lastSyncedTitle = '';
  function onTitleFocus() {
    lastSyncedTitle = session.title;
  }
  async function onTitleBlur() {
    const newTitle = session.title.trim();
    if (!documents.currentDocumentExtid || newTitle === lastSyncedTitle) return;
    lastSyncedTitle = newTitle;
    try {
      await apiUpdateDocumentTitle(documents.currentDocumentExtid, newTitle || 'Untitled');
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
    if (!documents.currentDocumentExtid) return;
    if (!endpoints.length) return;
    try {
      const state = snapshot();
      const fp = stateFingerprint(state);
      if (fp === documents.lastSavedStateHash) return;
      const saveData = await apiSave(state, documents.currentDocumentExtid, 'autosave');
      if (saveData.skipped) {
        documents.lastSavedStateHash = fp;
        return;
      }
      documents.lastSavedStateHash = fp;
      if (saveData.testrun) {
        documents.currentTestrunExtid = saveData.testrun.extid;
        documents.currentTestrunNumber = saveData.testrun.testrun_number;
        breadcrumbText = `testrun #${documents.currentTestrunNumber}`;
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
      } else if (documents.currentDocumentExtid) {
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
      documents.currentDocumentExtid = null;
      documents.currentTestrunExtid = null;
      documents.currentTestrunNumber = 0;
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
      documents.currentDocumentExtid = null;
      documents.currentTestrunExtid = null;
      documents.currentTestrunNumber = 0;
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
  async function runGroup(groupName) {
    const ignorePaths = session.ignorePaths.length
      ? session.ignorePaths.map(toDiffPath)
      : null;
    const envA = getEnvA();
    const envB = getEnvB();

    const tasks = [];
    for (const ep of endpoints) {
      if (ep.group !== groupName) continue;

      ep.state = 'running';
      ep.result = null;

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

      const capturedBody = body;
      const capturedPath = path;
      const capturedContentType = ep.contentType || 'query';

      tasks.push(async () => {
        try {
          const r = await apiCompare({
            label: ep.label || ep.path,
            method: ep.method,
            path: capturedPath,
            body: capturedBody,
            content_type: capturedContentType,
            group: ep.group || null,
            host_a: envA?.baseUrl || '',
            host_b: envB?.baseUrl || '',
            auth_a: envA?.auth || null,
            auth_b: envB?.auth || null,
            ignore_paths: ignorePaths,
          });
          r.request_body = capturedBody;
          r.request_content_type = capturedContentType;
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
      });
    }

    await runConcurrent(tasks);
  }
</script>

<TokenGate>
{#if currentView === 'environment' && envDetailExtid}
  <EnvironmentDetail extid={envDetailExtid} />
{:else}
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
    <div class="flex items-center gap-2 mb-2">
      <span class="text-[0.7em] uppercase tracking-widest text-text-dim font-semibold">Environments</span>
      <button
        class="text-[0.7em] text-text-dim hover:text-accent cursor-pointer bg-transparent border border-edge px-2 py-0.5 rounded font-mono hover:border-accent"
        onclick={() => { ui.activeModal = 'environments'; }}
      >Manage</button>
    </div>
    <div class="flex gap-3 items-start mb-5 flex-wrap">
      <EnvironmentSelector side="A" />
      <EnvironmentSelector side="B" />
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

    <!-- Spacer so the fixed back-to-top button never overlaps the last card -->
    <div class="h-16"></div>

    <!-- Back to top -->
    {#if showBackToTop}
      <button
        class="fixed bottom-6 right-6 bg-surface border border-edge text-accent w-10 h-10 rounded-full cursor-pointer text-[1.2em] flex items-center justify-center z-30 shadow-[0_4px_12px_rgba(0,0,0,0.4)] hover:bg-accent/15"
        onclick={scrollToTop}
        title="Scroll to top"
      >&#8593;</button>
    {/if}
  </div>
</div>

<!-- Modals -->
<OpenApiLoader open={ui.activeModal === 'openapi'} onclose={() => { ui.activeModal = null; }} />
<SchemaDiff open={ui.activeModal === 'schema-diff'} onclose={() => { ui.activeModal = null; }} />
<EnvironmentModal open={ui.activeModal === 'environments'} onclose={() => { ui.activeModal = null; }} />
{/if}

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

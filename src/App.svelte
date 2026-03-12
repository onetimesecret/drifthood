<script>
  import Sidebar from './components/Sidebar.svelte';
  import HostConfig from './components/HostConfig.svelte';
  import IgnoreConfig from './components/IgnoreConfig.svelte';
  import ActionBar from './components/ActionBar.svelte';
  import EndpointCard from './components/EndpointCard.svelte';
  import OpenApiLoader from './components/OpenApiLoader.svelte';
  import SchemaDiff from './components/SchemaDiff.svelte';

  import { DD_VERSION } from '../lib/examples.js';
  import { stateFingerprint } from '../lib/state.js';
  import { apiConfig, apiSave, apiCompare, apiListDocuments, apiGetDocument, apiGetSession, apiUpdateDocumentTitle } from '../lib/api.js';
  import { toDiffPath } from '../lib/format.js';
  import { setNestedValue, flattenObj } from '../lib/params.js';
  import { session } from './stores/session.svelte.js';
  import { endpoints, addEndpoint } from './stores/endpoints.svelte.js';
  import { ui } from './stores/ui.svelte.js';
  import { documents } from './stores/documents.svelte.js';
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
      ? `doc #${documents.currentDocumentId} / session #${documents.currentSessionNumber}`
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
          if (docData.sessions?.length) {
            const latest = docData.sessions[docData.sessions.length - 1];
            await loadSavedSession(mostRecent.id, latest.session_number);
            return;
          }
        } catch { /* fall through */ }
      }
    } catch { /* server not running */ }

    // Fresh start
    addEndpoint();
  }

  async function loadSavedSession(docId, sessionNumber) {
    try {
      const data = await apiGetSession(docId, sessionNumber);
      if (data.error || !data.session) {
        showDropToast('Session not found: ' + (data.error || 'no session data'), true);
        return;
      }
      const state = data.session.state;
      if (!state) {
        showDropToast('Session has no state data', true);
        return;
      }
      documents.currentDocumentId = docId;
      documents.currentSessionNumber = sessionNumber;
      restore(state);
      documents.lastSavedStateHash = stateFingerprint(state);
      breadcrumbText = `doc #${docId} session #${sessionNumber}`;
      showDropToast(`Loaded session #${sessionNumber}`, false);
      startAutosave();
    } catch (err) {
      showDropToast('Load failed: ' + err.message, true);
    }
  }

  // ── Save ──
  async function saveSession() {
    saveStatus = { text: 'Saving...', color: '', disabled: true };
    try {
      const state = snapshot();
      const data = await apiSave(state, documents.currentDocumentId);
      if (data.ok) {
        documents.currentDocumentId = data.document.id;
        if (data.session) {
          documents.currentSessionNumber = data.session.session_number;
        }
        documents.lastSavedStateHash = stateFingerprint(state);
        startAutosave();
        saveStatus = { text: 'Saved', color: 'var(--green)', disabled: true };
      } else {
        saveStatus = { text: 'Error', color: 'var(--red)', disabled: true };
      }
    } catch {
      saveStatus = { text: 'Error', color: 'var(--red)', disabled: true };
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
      if (saveData.session) {
        documents.currentSessionNumber = saveData.session.session_number;
      }
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
      showDropToast('Loaded session: ' + filename, false);
      startAutosave();
      return;
    }
    if (data.openapi || data.swagger || data.paths) {
      ui.activeModal = 'openapi';
      showDropToast('Loading OpenAPI spec: ' + filename, false);
      return;
    }
    showDropToast('Unrecognized JSON. Expected a session export or OpenAPI spec.', true);
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

<div class="app-layout">
  <Sidebar />

  <div class="main-panel">
    <!-- Header -->
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
      <h1>Drift Detector <span style="font-size:0.5em;font-weight:400;opacity:0.5">v{DD_VERSION}</span></h1>
      <button
        class="btn-ghost"
        style="margin-left:auto;{saveStatus.color ? `color:${saveStatus.color}` : ''}"
        onclick={saveSession}
        disabled={saveStatus.disabled}
      >{saveStatus.text}</button>
      {#if docIndicator}
        <span style="font-size:0.7em;color:var(--text-dim);font-family:var(--mono)" title="Each save creates a new session snapshot. The counter grows intentionally so you can revisit prior states.">{docIndicator}</span>
      {/if}
    </div>

    <!-- Session header -->
    <div class="session-header">
      <input
        class="session-title"
        type="text"
        placeholder="Session title (optional)"
        bind:value={session.title}
        onfocus={onTitleFocus}
        onblur={onTitleBlur}
      />
      <textarea
        class="session-memo"
        placeholder="Notes / context for this comparison session"
        rows="1"
        bind:value={session.memo}
      ></textarea>
    </div>

    <!-- Host config -->
    <div class="config">
      <HostConfig side="A" />
      <HostConfig side="B" />
    </div>

    <!-- Ignore config -->
    <IgnoreConfig />

    <!-- Endpoints section label -->
    <div class="section-label">Endpoints</div>

    <!-- Action bar -->
    <ActionBar />

    <!-- Breadcrumb -->
    {#if breadcrumbText}
      <div class="loader-breadcrumb" style="display:flex">
        <span class="breadcrumb-source">{breadcrumbText}</span>
        <button class="breadcrumb-dismiss" onclick={dismissBreadcrumb}>&times;</button>
      </div>
    {/if}

    <!-- Endpoint cards with group dividers -->
    <div class="endpoints-area">
      {#each groupedEntries as entry (entry.type === 'card' ? `card-${entry.ep.id}` : `div-${entry.group}`)}
        {#if entry.type === 'divider'}
          <div class="group-divider">
            <span class="group-name">{entry.group}</span>
            <span class="group-count">{entry.count}</span>
            <span class="group-tally">
              {#if entry.driftCount + entry.okCount > 0}
                {#if entry.driftCount}
                  <span style="color:var(--red)">{entry.driftCount} drift</span>
                {:else}
                  <span style="color:var(--green)">all ok</span>
                {/if}
              {/if}
            </span>
            <button class="group-run-btn" onclick={() => runGroup(entry.group)}>run group</button>
          </div>
        {:else}
          <EndpointCard endpoint={entry.ep} />
        {/if}
      {/each}
    </div>

    <!-- Back to top -->
    <button
      class="back-to-top"
      style="display:{showBackToTop ? 'flex' : 'none'}"
      onclick={scrollToTop}
    >&#8593;</button>
  </div>
</div>

<!-- Modals -->
<OpenApiLoader open={ui.activeModal === 'openapi'} onclose={() => { ui.activeModal = null; }} />
<SchemaDiff open={ui.activeModal === 'schema-diff'} onclose={() => { ui.activeModal = null; }} />

<!-- Drop overlay -->
<div class="drop-overlay" class:active={dropActive}>
  <div class="drop-overlay-inner">
    <div class="drop-icon">&#128230;</div>
    <div class="drop-label">Drop to import</div>
    <div class="drop-hint">.json (session) or .html (snapshot)</div>
  </div>
</div>

<!-- Drop toast -->
{#if toast.visible}
  <div class="drop-toast {toast.cls}" style="display:block">{toast.text}</div>
{/if}

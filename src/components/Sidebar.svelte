<script>
  import { apiListDocuments, apiGetSessions, apiGetSession, apiDeleteSession } from '../../lib/api.js';
  import { relativeTime, driftIndicator } from '../../lib/format.js';
  import { documents, resetDocuments } from '../stores/documents.svelte.js';
  import { endpoints, addEndpoint, clearEndpoints, resetIdCounter } from '../stores/endpoints.svelte.js';
  import { session, resetSession } from '../stores/session.svelte.js';
  import { ui, resetUi } from '../stores/ui.svelte.js';
  import { restore } from '../stores/snapshot.js';
  import { stateFingerprint } from '../../lib/state.js';

  let { onBreadcrumb } = $props();
  let sessionsByDoc = $state({});

  // Fetch documents on mount and whenever refreshVersion changes (e.g. after save)
  $effect(() => {
    // Read refreshVersion to establish reactive dependency
    const _v = documents.refreshVersion;
    refreshSidebar();
  });

  async function refreshSidebar() {
    try {
      const data = await apiListDocuments();
      documents.list = data.documents || [];
    } catch {
      documents.list = [];
    }
  }

  function toggleSidebar() {
    ui.sidebarCollapsed = !ui.sidebarCollapsed;
  }

  function toggleDoc(docId) {
    const expanded = ui.expandedDocs;
    if (expanded.has(docId)) {
      expanded.delete(docId);
      // Force reactivity on Set mutation
      ui.expandedDocs = new Set(expanded);
    } else {
      expanded.add(docId);
      ui.expandedDocs = new Set(expanded);
      loadSessionsForDoc(docId);
    }
  }

  function isDocExpanded(docId) {
    return docId === documents.currentDocumentId || ui.expandedDocs.has(docId);
  }

  async function loadSessionsForDoc(docId) {
    try {
      const data = await apiGetSessions(docId);
      const sessions = data.sessions || [];
      // Reverse chronological
      sessionsByDoc[docId] = [...sessions].reverse();
    } catch {
      sessionsByDoc[docId] = null;
    }
  }

  // Auto-load sessions for expanded docs when document list or refreshVersion changes
  $effect(() => {
    const _v = documents.refreshVersion;
    for (const d of documents.list) {
      if (isDocExpanded(d.id)) {
        // Re-fetch sessions whenever refresh is triggered (not just when missing)
        loadSessionsForDoc(d.id);
      }
    }
  });

  async function loadSession(docId, sessionNumber) {
    try {
      const data = await apiGetSession(docId, sessionNumber);
      if (data.error || !data.session) return;
      const state = data.session.state;
      if (!state) return;
      restore(state);
      documents.currentDocumentId = docId;
      documents.currentSessionNumber = sessionNumber;
      documents.lastSavedStateHash = stateFingerprint(state);
      onBreadcrumb?.(`doc #${docId} session #${sessionNumber}`);
    } catch {
      // Silent failure
    }
  }

  async function deleteSessionClick(docId, sessionNumber, event) {
    event.stopPropagation();
    try {
      const data = await apiDeleteSession(docId, sessionNumber);
      if (data.ok) {
        if (docId === documents.currentDocumentId && sessionNumber === documents.currentSessionNumber) {
          documents.currentSessionNumber = 0;
        }
        await loadSessionsForDoc(docId);
        await refreshSidebar();
      }
    } catch {
      // Silent failure
    }
  }

  function newDocument() {
    resetSession();
    clearEndpoints();
    resetIdCounter();
    resetDocuments();
    resetUi();
    addEndpoint();
    refreshSidebar();
  }
</script>

<div class="w-[250px] min-w-[250px] bg-surface border-r border-edge flex flex-col overflow-hidden transition-all duration-150 {ui.sidebarCollapsed ? 'w-0 min-w-0 border-r-0' : ''}">
  <div class="flex items-center justify-between px-3.5 py-3 border-b border-edge shrink-0">
    <h2 class="text-[0.75em] uppercase tracking-widest text-text-dim font-semibold whitespace-nowrap">Documents</h2>
    <button class="bg-transparent border-none text-text-dim cursor-pointer text-[1em] px-1.5 py-0.5 rounded hover:text-text-primary hover:bg-white/5" onclick={toggleSidebar} title="Collapse sidebar">&#9666;</button>
  </div>

  <button class="block w-[calc(100%-24px)] mx-3 my-2 px-2.5 py-1.5 text-[0.8em] bg-transparent border border-dashed border-edge text-text-dim rounded-md cursor-pointer text-left hover:border-accent hover:text-accent" onclick={newDocument}>+ New document</button>

  <div class="flex-1 overflow-y-auto py-1">
    {#if documents.list.length === 0}
      <div class="px-3.5 py-3 text-[0.8em] text-text-dim">No documents yet.</div>
    {:else}
      {#each documents.list as doc}
        {@const expanded = isDocExpanded(doc.id)}
        {@const isCurrent = doc.id === documents.currentDocumentId}
        <div class="border-b border-edge">
          <button
            type="button"
            class="w-full bg-transparent border-none text-left text-inherit flex items-center gap-1.5 px-3.5 py-2 cursor-pointer select-none text-[0.8em] hover:bg-white/[0.03] {isCurrent ? 'bg-accent/[0.08]' : ''}"
            onclick={() => toggleDoc(doc.id)}
          >
            <span class="chevron text-[0.7em]" class:open={expanded}>&#9654;</span>
            <span class="flex-1 whitespace-nowrap overflow-hidden text-ellipsis font-medium">{doc.title || 'Untitled'}</span>
            <span class="text-[0.8em] text-text-dim font-mono">{doc.session_count}</span>
          </button>

          <div class="toggle-block pb-1" class:open={expanded}>
            {#if sessionsByDoc[doc.id] === null}
              <div class="px-7 py-1 text-[0.75em] text-red">Error</div>
            {:else if sessionsByDoc[doc.id]?.length === 0}
              <div class="px-7 py-1 text-[0.75em] text-text-dim">No sessions</div>
            {:else if sessionsByDoc[doc.id]}
              {#each sessionsByDoc[doc.id] as s}
                {@const isActive = doc.id === documents.currentDocumentId && s.session_number === documents.currentSessionNumber}
                {@const di = driftIndicator(s)}
                <div
                  role="button"
                  tabindex="0"
                  class="group/session flex items-center gap-1.5 py-1 pl-7 pr-3.5 cursor-pointer text-[0.75em] font-mono text-text-dim hover:bg-white/[0.03] hover:text-text-primary {isActive ? 'text-accent' : ''}"
                  onclick={() => loadSession(doc.id, s.session_number)}
                  onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); loadSession(doc.id, s.session_number); } }}
                >
                  <span class="min-w-[20px]">#{s.session_number}</span>
                  <span class="text-[0.9em]" style="color:{di.color}" title={di.title}>{@html di.symbol}</span>
                  {#if s.session_type === 'autosave'}
                    <span title="autosave" class="opacity-50">&#8635;</span>
                  {:else}
                    <span title="saved" class="text-accent">&#9646;</span>
                  {/if}
                  {#if s.endpoint_count}
                    <span class="opacity-60">{s.endpoint_count}ep</span>
                  {/if}
                  <span class="flex-1 text-right">{relativeTime(s.created_at)}</span>
                  <button
                    class="opacity-0 group-hover/session:opacity-60 bg-transparent border-none text-text-dim cursor-pointer text-[0.9em] px-0.5 rounded-sm shrink-0 hover:opacity-100 hover:text-red"
                    onclick={(e) => deleteSessionClick(doc.id, s.session_number, e)}
                    title="Delete session"
                  >&times;</button>
                </div>
              {/each}
            {/if}
          </div>
        </div>
      {/each}
    {/if}
  </div>
</div>

<button
  class="fixed top-2.5 left-2.5 z-20 bg-surface border border-edge text-text-dim cursor-pointer px-2 py-1 rounded text-[0.8em] hover:text-text-primary hover:border-text-dim {ui.sidebarCollapsed ? 'block' : 'hidden'}"
  onclick={toggleSidebar}
  title="Expand sidebar"
>&#9656;</button>

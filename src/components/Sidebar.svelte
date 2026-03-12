<script>
  import { apiListDocuments, apiGetSessions, apiGetSession, apiDeleteSession } from '../../lib/api.js';
  import { relativeTime, driftIndicator } from '../../lib/format.js';
  import { documents, resetDocuments } from '../stores/documents.svelte.js';
  import { endpoints, addEndpoint, clearEndpoints, resetIdCounter } from '../stores/endpoints.svelte.js';
  import { session, resetSession } from '../stores/session.svelte.js';
  import { ui, resetUi } from '../stores/ui.svelte.js';
  import { restore } from '../stores/snapshot.js';

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

<div class="sidebar" class:collapsed={ui.sidebarCollapsed}>
  <div class="sidebar-header">
    <h2>Documents</h2>
    <button class="sidebar-toggle" onclick={toggleSidebar} title="Collapse sidebar">&#9666;</button>
  </div>

  <button class="sidebar-new-btn" onclick={newDocument}>+ New document</button>

  <div class="sidebar-list">
    {#if documents.list.length === 0}
      <div style="padding:12px 14px;font-size:0.8em;color:var(--text-dim)">No documents yet.</div>
    {:else}
      {#each documents.list as doc}
        {@const expanded = isDocExpanded(doc.id)}
        {@const isCurrent = doc.id === documents.currentDocumentId}
        <div class="sidebar-doc">
          <div
            class="sidebar-doc-header"
            class:active={isCurrent}
            onclick={() => toggleDoc(doc.id)}
          >
            <span class="chevron" class:open={expanded} style="font-size:0.7em">&#9654;</span>
            <span class="sidebar-doc-title">{doc.title || 'Untitled'}</span>
            <span class="sidebar-doc-count">{doc.session_count}</span>
          </div>

          <div class="sidebar-sessions" class:open={expanded}>
            {#if sessionsByDoc[doc.id] === null}
              <div style="padding:4px 28px;font-size:0.75em;color:var(--red)">Error</div>
            {:else if sessionsByDoc[doc.id]?.length === 0}
              <div style="padding:4px 28px;font-size:0.75em;color:var(--text-dim)">No sessions</div>
            {:else if sessionsByDoc[doc.id]}
              {#each sessionsByDoc[doc.id] as s}
                {@const isActive = doc.id === documents.currentDocumentId && s.session_number === documents.currentSessionNumber}
                {@const di = driftIndicator(s)}
                <div
                  class="sidebar-session"
                  class:active={isActive}
                  onclick={() => loadSession(doc.id, s.session_number)}
                >
                  <span class="ss-num">#{s.session_number}</span>
                  <span style="color:{di.color};font-size:0.9em" title={di.title}>{@html di.symbol}</span>
                  {#if s.session_type === 'autosave'}
                    <span title="autosave" style="opacity:0.5">&#8635;</span>
                  {:else}
                    <span title="saved" style="color:var(--accent)">&#9646;</span>
                  {/if}
                  {#if s.endpoint_count}
                    <span style="opacity:0.6">{s.endpoint_count}ep</span>
                  {/if}
                  <span class="ss-time">{relativeTime(s.created_at)}</span>
                  <button
                    class="ss-delete"
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
  class="sidebar-expand-btn"
  class:visible={ui.sidebarCollapsed}
  onclick={toggleSidebar}
  title="Expand sidebar"
>&#9656;</button>

<!-- src/components/Sidebar.svelte -->

<script>
  import { apiListDocuments, apiGetTestruns, apiDeleteTestrun } from '../../lib/api.js';
  import { loadTestrun as fetchAndRestoreTestrun } from '../lib/testrun-loader.js';
  import { relativeTime, driftIndicator } from '../../lib/format.js';
  import { documents, resetDocuments } from '../stores/documents.svelte.js';
  import { endpoints, addEndpoint, clearEndpointsLocal } from '../stores/endpoints.svelte.js';
  import { session, resetSession, seedDefaultEnvironments } from '../stores/session.svelte.js';
  import { ui, resetUi } from '../stores/ui.svelte.js';
  import { getAuthKey } from '../stores/auth.svelte.js';

  let { onBreadcrumb } = $props();
  let testrunsByDoc = $state({});

  // Fetch documents on mount and whenever refreshVersion changes (e.g. after save)
  $effect(() => {
    // Read refreshVersion to establish reactive dependency
    const _v = documents.refreshVersion;
    refreshSidebar();
  });

  async function refreshSidebar() {
    if (!getAuthKey()) return;  // not authenticated yet
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

  async function toggleDoc(docExtid) {
    const expanded = ui.expandedDocs;
    if (expanded.has(docExtid)) {
      expanded.delete(docExtid);
      ui.expandedDocs = new Set(expanded);
    } else {
      expanded.add(docExtid);
      ui.expandedDocs = new Set(expanded);
      await loadTestrunsForDoc(docExtid);
      const testruns = testrunsByDoc[docExtid];
      if (testruns?.length) {
        loadTestrun(docExtid, testruns[0].extid, testruns[0].testrun_number);
      }
    }
  }

  function isDocExpanded(docExtid) {
    return docExtid === documents.currentDocumentExtid || ui.expandedDocs.has(docExtid);
  }

  async function loadTestrunsForDoc(docExtid) {
    try {
      const data = await apiGetTestruns(docExtid);
      const testruns = data.testruns || [];
      // Reverse chronological
      testrunsByDoc[docExtid] = [...testruns].reverse();
    } catch {
      testrunsByDoc[docExtid] = null;
    }
  }

  // Auto-load sessions for expanded docs when document list or refreshVersion changes
  $effect(() => {
    const _v = documents.refreshVersion;
    for (const d of documents.list) {
      if (isDocExpanded(d.extid)) {
        // Re-fetch testruns whenever refresh is triggered (not just when missing)
        loadTestrunsForDoc(d.extid);
      }
    }
  });

  async function loadTestrun(docExtid, testrunExtid, testrunNumber) {
    try {
      await fetchAndRestoreTestrun(docExtid, testrunExtid, testrunNumber);
      onBreadcrumb?.(`testrun #${testrunNumber}`);
    } catch {
      // Silent failure
    }
  }

  async function deleteTestrunClick(docExtid, testrunExtid, testrunNumber, event) {
    event.stopPropagation();
    try {
      const data = await apiDeleteTestrun(docExtid, testrunExtid);
      if (data.ok) {
        if (docExtid === documents.currentDocumentExtid && testrunExtid === documents.currentTestrunExtid) {
          documents.currentTestrunExtid = null;
          documents.currentTestrunNumber = 0;
        }
        await loadTestrunsForDoc(docExtid);
        await refreshSidebar();
      }
    } catch {
      // Silent failure
    }
  }

  async function newDocument() {
    clearEndpointsLocal();
    resetSession();
    resetDocuments();
    resetUi();
    // Restore server-side environments (including user-created ones) into
    // local state, seeding defaults only if the server has none.
    await seedDefaultEnvironments();
    await addEndpoint();
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
    {#if !documents.currentDocumentExtid && endpoints.length > 0}
      <div class="border-b border-edge">
        <div class="flex items-center gap-1.5 px-3.5 py-2 text-[0.8em] bg-accent/[0.08]">
          <span class="flex-1 whitespace-nowrap overflow-hidden text-ellipsis font-medium italic text-text-dim">{session.title || 'Untitled'} <span class="text-[0.85em] opacity-60">(unsaved)</span></span>
        </div>
      </div>
    {/if}
    {#if documents.list.length === 0 && (documents.currentDocumentExtid || endpoints.length === 0)}
      <div class="px-3.5 py-3 text-[0.8em] text-text-dim">No documents yet.</div>
    {:else}
      {#each documents.list as doc}
        {@const expanded = isDocExpanded(doc.extid)}
        {@const isCurrent = doc.extid === documents.currentDocumentExtid}
        <div class="border-b border-edge">
          <button
            type="button"
            class="w-full bg-transparent border-none text-left text-inherit flex items-center gap-1.5 px-3.5 py-2 cursor-pointer select-none text-[0.8em] hover:bg-white/[0.03] {isCurrent ? 'bg-accent/[0.08]' : ''}"
            onclick={() => toggleDoc(doc.extid)}
          >
            <span class="chevron text-[0.7em]" class:open={expanded}>&#9654;</span>
            <span class="flex-1 whitespace-nowrap overflow-hidden text-ellipsis font-medium">{doc.title || 'Untitled'}</span>
            <span class="text-[0.8em] text-text-dim font-mono">{doc.testrun_count}</span>
          </button>

          <div class="toggle-block pb-1" class:open={expanded}>
            {#if testrunsByDoc[doc.extid] === null}
              <div class="px-7 py-1 text-[0.75em] text-red">Error</div>
            {:else if testrunsByDoc[doc.extid]?.length === 0}
              <div class="px-7 py-1 text-[0.75em] text-text-dim">No testruns</div>
            {:else if testrunsByDoc[doc.extid]}
              {#each testrunsByDoc[doc.extid] as s}
                {@const isActive = doc.extid === documents.currentDocumentExtid && s.extid === documents.currentTestrunExtid}
                {@const di = driftIndicator(s)}
                <div
                  role="button"
                  tabindex="0"
                  class="group/testrun flex items-center gap-1.5 py-1 pl-7 pr-3.5 cursor-pointer text-[0.75em] font-mono text-text-dim hover:bg-white/[0.03] hover:text-text-primary {isActive ? 'text-accent' : ''}"
                  onclick={() => loadTestrun(doc.extid, s.extid, s.testrun_number)}
                  onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); loadTestrun(doc.extid, s.extid, s.testrun_number); } }}
                >
                  <span class="min-w-[20px]">#{s.testrun_number}</span>
                  <span class="text-[0.9em]" style="color:{di.color}" title={di.title}>{@html di.symbol}</span>
                  {#if s.testrun_type === 'autosave'}
                    <span title="autosave" class="opacity-50">&#8635;</span>
                  {:else}
                    <span title="saved" class="text-accent">&#9646;</span>
                  {/if}
                  {#if s.endpoint_count}
                    <span class="opacity-60">{s.endpoint_count}ep</span>
                  {/if}
                  <span class="flex-1 text-right">{relativeTime(s.created_at)}</span>
                  <button
                    class="opacity-0 group-hover/testrun:opacity-60 bg-transparent border-none text-text-dim cursor-pointer text-[0.9em] px-0.5 rounded-sm shrink-0 hover:opacity-100 hover:text-red"
                    onclick={(e) => deleteTestrunClick(doc.extid, s.extid, s.testrun_number, e)}
                    title="Delete testrun"
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

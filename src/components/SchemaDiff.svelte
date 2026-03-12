<script>
  import Modal from './Modal.svelte';
  import { apiDiffSchemas } from '../../lib/api.js';

  let { open, onclose } = $props();

  let urlA = $state('');
  let urlB = $state('');
  let fileA = $state(null);
  let fileB = $state(null);
  let status = $state('');
  let results = $state(null);
  let expandedEndpoints = $state(new Set());

  function resetState() {
    urlA = '';
    urlB = '';
    fileA = null;
    fileB = null;
    status = '';
    results = null;
    expandedEndpoints = new Set();
  }

  async function runSchemaDiff() {
    status = 'Comparing schemas...';
    results = null;

    const fd = new FormData();

    if (fileA) fd.append('file_a', fileA);
    else if (urlA.trim()) fd.append('url_a', urlA.trim());
    else { status = 'Provide spec A (file or URL)'; return; }

    if (fileB) fd.append('file_b', fileB);
    else if (urlB.trim()) fd.append('url_b', urlB.trim());
    else { status = 'Provide spec B (file or URL)'; return; }

    try {
      const data = await apiDiffSchemas(fd);
      if (data.error) {
        status = 'Error: ' + data.error;
        return;
      }
      results = data;
      status = '';
      // Auto-expand changed endpoints
      const expanded = new Set();
      for (const r of (data.results || [])) {
        if (r.status === 'changed') {
          expanded.add(endpointKey(r));
        }
      }
      expandedEndpoints = expanded;
    } catch (err) {
      status = 'Error: ' + err.message;
    }
  }

  function endpointKey(r) {
    return `${r.method}-${r.path.replace(/\W/g, '_')}`;
  }

  function toggleEndpoint(r) {
    const key = endpointKey(r);
    const next = new Set(expandedEndpoints);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    expandedEndpoints = next;
  }

  function handleClose() {
    resetState();
    onclose();
  }

  let interesting = $derived(
    results ? results.results.filter(r => r.status !== 'identical') : []
  );
</script>

<Modal open={open} onclose={handleClose} maxWidth="900px">
  <div class="modal-header">
    <h3>Diff Request Schemas</h3>
    <button class="modal-close" onclick={handleClose}>&times;</button>
  </div>

  <div class="modal-body">
    <p style="font-size:0.8em;color:var(--text-dim);margin-bottom:12px">
      Compare request schemas between two OpenAPI specs to detect field-level changes.
    </p>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:12px">
      <div>
        <div style="font-size:0.7em;text-transform:uppercase;color:var(--text-dim);margin-bottom:4px">Spec A</div>
        <input type="text" bind:value={urlA} placeholder="URL to spec A" style="width:100%;margin-bottom:6px" />
        <input type="file" accept=".json,.yaml,.yml" onchange={(e) => { fileA = e.target.files[0] || null; }} />
      </div>
      <div>
        <div style="font-size:0.7em;text-transform:uppercase;color:var(--text-dim);margin-bottom:4px">Spec B</div>
        <input type="text" bind:value={urlB} placeholder="URL to spec B" style="width:100%;margin-bottom:6px" />
        <input type="file" accept=".json,.yaml,.yml" onchange={(e) => { fileB = e.target.files[0] || null; }} />
      </div>
    </div>

    <button class="btn-primary" onclick={runSchemaDiff}>Compare</button>

    {#if status}
      <div style="margin-top:8px;font-size:0.85em;color:var(--text-dim)">
        {#if status === 'Comparing schemas...'}
          <span class="spinner"></span>
        {/if}
        {status}
      </div>
    {/if}

    {#if results}
      <div class="schema-diff-results">
        <div class="sd-summary">
          <span style="color:var(--text)">{results.summary.spec_a} vs {results.summary.spec_b}</span>
          <span class="sd-stat" style="color:var(--yellow)">{results.summary.changed} changed</span>
          <span class="sd-stat" style="color:var(--green)">{results.summary.added} added</span>
          <span class="sd-stat" style="color:var(--red)">{results.summary.removed} removed</span>
          <span class="sd-stat" style="color:var(--text-dim)">{results.summary.identical} identical</span>
        </div>

        {#if interesting.length === 0}
          <div style="color:var(--green);font-size:0.85em;padding:8px 0">All request schemas are identical.</div>
        {:else}
          {#each interesting as r}
            {@const key = endpointKey(r)}
            {@const isOpen = expandedEndpoints.has(key)}
            <div class="sd-endpoint">
              <div class="sd-endpoint-header" role="button" tabindex="0" onclick={() => toggleEndpoint(r)} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleEndpoint(r); } }}>
                <span class="chevron" class:open={isOpen}>&#9654;</span>
                <span class="sd-badge {r.status}">{r.status.replace('_', ' ')}</span>
                <span class="op-method {r.method.toLowerCase()}" style="font-weight:600;width:52px;text-align:right">{r.method}</span>
                <span>{r.path}</span>
              </div>
              <div class="sd-body" class:open={isOpen}>
                {#if r.status === 'added_in_b'}
                  <div class="sd-section">
                    <h5>New endpoint in Spec B</h5>
                    {#each r.fields_b || [] as f}
                      <div class="sd-item" style="color:var(--green)">&plus; {f.path} <span style="color:var(--text-dim)">({f.type}{f.required ? ' req' : ''})</span></div>
                    {/each}
                  </div>
                {:else if r.status === 'removed_from_b'}
                  <div class="sd-section">
                    <h5>Removed from Spec B</h5>
                    {#each r.fields_a || [] as f}
                      <div class="sd-item" style="color:var(--red)">&minus; {f.path} <span style="color:var(--text-dim)">({f.type}{f.required ? ' req' : ''})</span></div>
                    {/each}
                  </div>
                {:else if r.diff}
                  {#if r.diff.possible_renames?.length}
                    <div class="sd-section">
                      <h5>Possible Renames</h5>
                      {#each r.diff.possible_renames as rn}
                        <div class="sd-item sd-rename">
                          <span style="color:var(--red)">{rn.old_path}</span> &rarr;
                          <span style="color:var(--green)">{rn.new_path}</span>
                          <span style="color:var(--text-dim)">({rn.type})</span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                  {#if r.diff.added?.length}
                    <div class="sd-section">
                      <h5>Fields Added in B</h5>
                      {#each r.diff.added as f}
                        <div class="sd-item" style="color:var(--green)">&plus; {f.path} <span style="color:var(--text-dim)">({f.type}{f.required ? ' req' : ''})</span></div>
                      {/each}
                    </div>
                  {/if}
                  {#if r.diff.removed?.length}
                    <div class="sd-section">
                      <h5>Fields Removed from B</h5>
                      {#each r.diff.removed as f}
                        <div class="sd-item" style="color:var(--red)">&minus; {f.path} <span style="color:var(--text-dim)">({f.type}{f.required ? ' req' : ''})</span></div>
                      {/each}
                    </div>
                  {/if}
                  {#if r.diff.type_changed?.length}
                    <div class="sd-section">
                      <h5>Type Changes</h5>
                      {#each r.diff.type_changed as tc}
                        <div class="sd-item">
                          <span style="color:var(--yellow)">{tc.path}</span>:
                          <span style="color:var(--red)">{tc.type_a}</span> &rarr;
                          <span style="color:var(--green)">{tc.type_b}</span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                  {#if r.diff.const_changed?.length}
                    <div class="sd-section">
                      <h5>Const Changes</h5>
                      {#each r.diff.const_changed as cc}
                        <div class="sd-item">
                          <span style="color:var(--yellow)">{cc.path}</span>:
                          <span style="color:var(--red)">{String(cc.const_a)}</span> &rarr;
                          <span style="color:var(--green)">{String(cc.const_b)}</span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                  {#if !r.diff.possible_renames?.length && !r.diff.added?.length && !r.diff.removed?.length && !r.diff.type_changed?.length && !r.diff.const_changed?.length}
                    <div style="color:var(--text-dim)">No field-level differences.</div>
                  {/if}
                {/if}
              </div>
            </div>
          {/each}
        {/if}
      </div>
    {/if}
  </div>
</Modal>

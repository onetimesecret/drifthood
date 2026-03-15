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

  function hasResponseDiff(r) {
    return r.response_diff && r.response_diff.has_changes;
  }

  let interesting = $derived(
    results ? results.results.filter(r => r.status !== 'identical') : []
  );
</script>

<Modal open={open} onclose={handleClose} maxWidth="900px">
  <div class="flex items-center justify-between px-[18px] py-3.5 border-b border-edge">
    <h3 class="text-[0.95em] font-semibold">Diff Request &amp; Response Schemas</h3>
    <button class="bg-transparent border-none text-text-dim cursor-pointer text-[1.3em] px-1 rounded hover:text-red" onclick={handleClose}>&times;</button>
  </div>

  <div class="p-[18px] overflow-y-auto flex-1">
    <p class="text-[0.8em] text-text-dim mb-3">
      Compare request and response schemas between two OpenAPI specs to detect field-level changes.
    </p>

    <div class="grid grid-cols-2 gap-4 mb-3">
      <div>
        <div class="text-[0.7em] uppercase text-text-dim mb-1">Spec A</div>
        <input type="text" bind:value={urlA} placeholder="URL to spec A" class="bg-bg border border-edge text-text-primary px-2.5 py-1.5 rounded-md font-mono text-[0.85em] w-full mb-1.5" />
        <input type="file" accept=".json,.yaml,.yml" onchange={(e) => { fileA = e.target.files[0] || null; }} class="text-[0.8em] text-text-dim" />
      </div>
      <div>
        <div class="text-[0.7em] uppercase text-text-dim mb-1">Spec B</div>
        <input type="text" bind:value={urlB} placeholder="URL to spec B" class="bg-bg border border-edge text-text-primary px-2.5 py-1.5 rounded-md font-mono text-[0.85em] w-full mb-1.5" />
        <input type="file" accept=".json,.yaml,.yml" onchange={(e) => { fileB = e.target.files[0] || null; }} class="text-[0.8em] text-text-dim" />
      </div>
    </div>

    <button class="btn-primary" onclick={runSchemaDiff}>Compare</button>

    {#if status}
      <div class="mt-2 text-[0.85em] text-text-dim">
        {#if status === 'Comparing schemas...'}
          <span class="inline-block w-3 h-3 border-2 border-edge border-t-accent rounded-full animate-spin"></span>
        {/if}
        {status}
      </div>
    {/if}

    {#if results}
      <div class="mt-3">
        <div class="flex gap-3 py-2 font-mono text-[0.85em] flex-wrap">
          <span class="text-text-primary">{results.summary.spec_a} vs {results.summary.spec_b}</span>
          <span class="px-2 py-0.5 rounded text-yellow">{results.summary.changed} changed</span>
          <span class="px-2 py-0.5 rounded text-green">{results.summary.added} added</span>
          <span class="px-2 py-0.5 rounded text-red">{results.summary.removed} removed</span>
          <span class="px-2 py-0.5 rounded text-text-dim">{results.summary.identical} identical</span>
        </div>

        {#if interesting.length === 0}
          <div class="text-green text-[0.85em] py-2">All request schemas are identical.</div>
        {:else}
          {#each interesting as r}
            {@const key = endpointKey(r)}
            {@const isOpen = expandedEndpoints.has(key)}
            <div class="mb-2.5 border border-edge rounded-md overflow-hidden">
              <div class="flex items-center gap-2 px-2.5 py-1.5 cursor-pointer font-mono text-[0.8em] bg-white/[0.02] hover:bg-white/[0.04]" role="button" tabindex="0" onclick={() => toggleEndpoint(r)} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleEndpoint(r); } }}>
                <span class="chevron" class:open={isOpen}>&#9654;</span>
                <span class="text-[0.7em] font-semibold px-1.5 py-px rounded-lg uppercase {r.status === 'changed' ? 'bg-yellow/20 text-yellow' : r.status === 'added' || r.status === 'added_in_b' ? 'bg-green/15 text-green' : r.status === 'removed' || r.status === 'removed_from_b' ? 'bg-red/15 text-red' : 'bg-text-dim/15 text-text-dim'}">{r.status.replace('_', ' ')}</span>
                <span class="font-semibold w-[52px] text-right {r.method.toLowerCase() === 'get' ? 'text-green' : r.method.toLowerCase() === 'post' ? 'text-accent' : r.method.toLowerCase() === 'put' ? 'text-yellow' : r.method.toLowerCase() === 'delete' ? 'text-red' : r.method.toLowerCase() === 'patch' ? 'text-purple' : ''}">{r.method}</span>
                <span>{r.path}</span>
              </div>
              <div class="toggle-block px-2.5 py-2 border-t border-edge text-[0.8em] font-mono" class:open={isOpen}>
                {#if r.status === 'added_in_b'}
                  <div class="mb-2">
                    <h5 class="text-[0.85em] text-text-dim uppercase tracking-wider mb-1">New endpoint in Spec B</h5>
                    {#each r.fields_b || [] as f}
                      <div class="px-1.5 py-0.5 mb-0.5 rounded-sm bg-bg text-green">&plus; {f.path} <span class="text-text-dim">({f.type}{f.required ? ' req' : ''})</span></div>
                    {/each}
                  </div>
                {:else if r.status === 'removed_from_b'}
                  <div class="mb-2">
                    <h5 class="text-[0.85em] text-text-dim uppercase tracking-wider mb-1">Removed from Spec B</h5>
                    {#each r.fields_a || [] as f}
                      <div class="px-1.5 py-0.5 mb-0.5 rounded-sm bg-bg text-red">&minus; {f.path} <span class="text-text-dim">({f.type}{f.required ? ' req' : ''})</span></div>
                    {/each}
                  </div>
                {:else if r.diff}
                  {#if r.diff.possible_renames?.length}
                    <div class="mb-2">
                      <h5 class="text-[0.85em] text-text-dim uppercase tracking-wider mb-1">Possible Renames</h5>
                      {#each r.diff.possible_renames as rn}
                        <div class="px-1.5 py-0.5 mb-0.5 rounded-sm bg-yellow/10 border-l-2 border-yellow pl-2">
                          <span class="text-red">{rn.old_path}</span> &rarr;
                          <span class="text-green">{rn.new_path}</span>
                          <span class="text-text-dim">({rn.type})</span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                  {#if r.diff.added?.length}
                    <div class="mb-2">
                      <h5 class="text-[0.85em] text-text-dim uppercase tracking-wider mb-1">Fields Added in B</h5>
                      {#each r.diff.added as f}
                        <div class="px-1.5 py-0.5 mb-0.5 rounded-sm bg-bg text-green">&plus; {f.path} <span class="text-text-dim">({f.type}{f.required ? ' req' : ''})</span></div>
                      {/each}
                    </div>
                  {/if}
                  {#if r.diff.removed?.length}
                    <div class="mb-2">
                      <h5 class="text-[0.85em] text-text-dim uppercase tracking-wider mb-1">Fields Removed from B</h5>
                      {#each r.diff.removed as f}
                        <div class="px-1.5 py-0.5 mb-0.5 rounded-sm bg-bg text-red">&minus; {f.path} <span class="text-text-dim">({f.type}{f.required ? ' req' : ''})</span></div>
                      {/each}
                    </div>
                  {/if}
                  {#if r.diff.type_changed?.length}
                    <div class="mb-2">
                      <h5 class="text-[0.85em] text-text-dim uppercase tracking-wider mb-1">Type Changes</h5>
                      {#each r.diff.type_changed as tc}
                        <div class="px-1.5 py-0.5 mb-0.5 rounded-sm bg-bg">
                          <span class="text-yellow">{tc.path}</span>:
                          <span class="text-red">{tc.type_a}</span> &rarr;
                          <span class="text-green">{tc.type_b}</span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                  {#if r.diff.const_changed?.length}
                    <div class="mb-2">
                      <h5 class="text-[0.85em] text-text-dim uppercase tracking-wider mb-1">Const Changes</h5>
                      {#each r.diff.const_changed as cc}
                        <div class="px-1.5 py-0.5 mb-0.5 rounded-sm bg-bg">
                          <span class="text-yellow">{cc.path}</span>:
                          <span class="text-red">{String(cc.const_a)}</span> &rarr;
                          <span class="text-green">{String(cc.const_b)}</span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                  {#if !r.diff.possible_renames?.length && !r.diff.added?.length && !r.diff.removed?.length && !r.diff.type_changed?.length && !r.diff.const_changed?.length && !hasResponseDiff(r)}
                    <div class="text-text-dim">No field-level differences.</div>
                  {/if}

                  {#if hasResponseDiff(r)}
                    <div class="mt-3 pt-2 border-t border-edge">
                      <h5 class="text-[0.85em] text-text-dim uppercase tracking-wider mb-1">Response Schema Changes</h5>
                      {#each Object.entries(r.response_diff.per_code || {}) as [code, codeDiff]}
                        {#if codeDiff.status !== 'identical'}
                          <div class="mb-2 ml-2">
                            <div class="text-[0.85em] font-mono mb-0.5">
                              <span class="font-semibold">{code}</span>
                              <span class="text-text-dim ml-1 text-[0.85em] uppercase">{codeDiff.status.replace('_', ' ')}</span>
                            </div>
                            {#if codeDiff.status === 'added_in_b' && codeDiff.fields}
                              {#each codeDiff.fields as f}
                                <div class="px-1.5 py-0.5 mb-0.5 rounded-sm bg-bg text-green ml-2">&plus; {f.path} <span class="text-text-dim">({f.type}{f.required ? ' req' : ''})</span></div>
                              {/each}
                            {:else if codeDiff.status === 'removed_from_b' && codeDiff.fields}
                              {#each codeDiff.fields as f}
                                <div class="px-1.5 py-0.5 mb-0.5 rounded-sm bg-bg text-red ml-2">&minus; {f.path} <span class="text-text-dim">({f.type}{f.required ? ' req' : ''})</span></div>
                              {/each}
                            {:else if codeDiff.diff}
                              {#if codeDiff.diff.added?.length}
                                {#each codeDiff.diff.added as f}
                                  <div class="px-1.5 py-0.5 mb-0.5 rounded-sm bg-bg text-green ml-2">&plus; {f.path} <span class="text-text-dim">({f.type}{f.required ? ' req' : ''})</span></div>
                                {/each}
                              {/if}
                              {#if codeDiff.diff.removed?.length}
                                {#each codeDiff.diff.removed as f}
                                  <div class="px-1.5 py-0.5 mb-0.5 rounded-sm bg-bg text-red ml-2">&minus; {f.path} <span class="text-text-dim">({f.type}{f.required ? ' req' : ''})</span></div>
                                {/each}
                              {/if}
                              {#if codeDiff.diff.type_changed?.length}
                                {#each codeDiff.diff.type_changed as tc}
                                  <div class="px-1.5 py-0.5 mb-0.5 rounded-sm bg-bg ml-2">
                                    <span class="text-yellow">{tc.path}</span>:
                                    <span class="text-red">{tc.type_a}</span> &rarr;
                                    <span class="text-green">{tc.type_b}</span>
                                  </div>
                                {/each}
                              {/if}
                              {#if codeDiff.diff.const_changed?.length}
                                {#each codeDiff.diff.const_changed as cc}
                                  <div class="px-1.5 py-0.5 mb-0.5 rounded-sm bg-bg ml-2">
                                    <span class="text-yellow">{cc.path}</span>:
                                    <span class="text-red">{String(cc.const_a)}</span> &rarr;
                                    <span class="text-green">{String(cc.const_b)}</span>
                                  </div>
                                {/each}
                              {/if}
                            {/if}
                          </div>
                        {/if}
                      {/each}
                    </div>
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

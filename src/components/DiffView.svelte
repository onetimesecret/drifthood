<script>
  import { parseDiff, jsonSummary } from '../../lib/diff.js';
  import { prettifyPath } from '../../lib/format.js';
  import { buildDriftSummary, buildCurlCommand } from '../../lib/export.js';
  import { session, getEnvA, getEnvB } from '../stores/session.svelte.js';

  let { result, endpointId } = $props();

  let sections = $derived(result?.has_drift ? parseDiff(result.diff) : []);

  // Only show ignored-fields badge when both sides returned real responses
  // (not connection errors). Showing "6 fields ignored" on a connection
  // error is misleading — there was nothing to ignore.
  let isRealComparison = $derived(
    result?.response_a?.status != null && result?.response_b?.status != null
  );
  let ignoredCount = $derived(isRealComparison ? (result?.ignored_paths?.length ?? 0) : 0);
  let ignoredTooltip = $derived(
    ignoredCount > 0 && result?.ignored_paths
      ? result.ignored_paths.map(prettifyPath).join('\n')
      : ''
  );

  let copyLabel = $state('Copy summary');
  let copyClass = $state('');
  let curlLabelA = $state('Copy curl A');
  let curlClassA = $state('');
  let curlLabelB = $state('Copy curl B');
  let curlClassB = $state('');

  function copyCurl(side) {
    if (!result) return;
    const cmd = buildCurlCommand(result, side);
    if (!cmd) return;
    navigator.clipboard.writeText(cmd).then(() => {
      if (side === 'a') {
        curlLabelA = 'Copied';
        curlClassA = 'copied';
        setTimeout(() => { curlLabelA = 'Copy curl A'; curlClassA = ''; }, 1500);
      } else {
        curlLabelB = 'Copied';
        curlClassB = 'copied';
        setTimeout(() => { curlLabelB = 'Copy curl B'; curlClassB = ''; }, 1500);
      }
    });
  }

  function copySummary() {
    if (!result?.has_drift) return;
    const envA = getEnvA();
    const envB = getEnvB();
    const text = buildDriftSummary(result, {
      title: session.title,
      memo: session.memo,
      hostA: envA?.baseUrl || '',
      hostB: envB?.baseUrl || '',
      memoA: envA?.name || '',
      memoB: envB?.name || '',
    });
    navigator.clipboard.writeText(text).then(() => {
      copyLabel = 'Copied';
      copyClass = 'copied';
      setTimeout(() => { copyLabel = 'Copy summary'; copyClass = ''; }, 1500);
    });
  }
</script>

{#if !result?.has_drift}
  <div class="text-green text-[0.85em] py-1">
    No differences detected.{#if ignoredCount > 0}
      {' '}<span class="text-[0.7em] text-text-dim font-mono px-1.5 py-0.5 rounded bg-text-dim/10 border border-edge ml-2 cursor-help" title={ignoredTooltip}>{ignoredCount} fields ignored</span>
    {/if}
  </div>
{:else}
  {#each sections as sec, secIdx}
    <div class="mb-3">
      <h4 class="text-[0.8em] text-text-dim uppercase tracking-wider mb-1.5">
        {sec.label}
        {#if secIdx === 0}
          {' '}<button class="text-[0.75em] text-yellow cursor-pointer bg-transparent border border-yellow px-2 py-0.5 rounded ml-2 align-middle font-normal normal-case tracking-normal hover:bg-yellow/15 {copyClass === 'copied' ? 'text-green border-green' : ''}" onclick={(e) => { e.stopPropagation(); copySummary(); }}>{copyLabel}</button>
          {' '}<button class="text-[0.75em] text-cyan cursor-pointer bg-transparent border border-cyan px-2 py-0.5 rounded ml-1 align-middle font-normal normal-case tracking-normal hover:bg-cyan/15 {curlClassA === 'copied' ? 'text-green border-green' : ''}" onclick={(e) => { e.stopPropagation(); copyCurl('a'); }}>{curlLabelA}</button>
          {' '}<button class="text-[0.75em] text-cyan cursor-pointer bg-transparent border border-cyan px-2 py-0.5 rounded ml-1 align-middle font-normal normal-case tracking-normal hover:bg-cyan/15 {curlClassB === 'copied' ? 'text-green border-green' : ''}" onclick={(e) => { e.stopPropagation(); copyCurl('b'); }}>{curlLabelB}</button>
          {#if ignoredCount > 0}
            {' '}<span class="text-[0.7em] text-text-dim font-mono px-1.5 py-0.5 rounded bg-text-dim/10 border border-edge ml-2 cursor-help" title={ignoredTooltip}>{ignoredCount} fields ignored</span>
          {/if}
        {/if}
      </h4>

      {#each sec.entries as e}
        <div class="font-mono text-[0.8em] px-2 py-1 mb-0.5 rounded bg-bg">
          {#if e.oldVal !== undefined && e.oldType}
            <span class="text-yellow" title={e.path}>{prettifyPath(e.path)}</span><br>
            <span class="text-red">&minus; {jsonSummary(e.oldVal)} <span class="opacity-60">({e.oldType})</span></span><br>
            <span class="text-green">&plus; {jsonSummary(e.newVal)} <span class="opacity-60">({e.newType})</span></span>
          {:else if e.oldVal !== undefined}
            <span class="text-yellow" title={e.path}>{prettifyPath(e.path)}</span><br>
            <span class="text-red">&minus; {jsonSummary(e.oldVal)}</span><br>
            <span class="text-green">&plus; {jsonSummary(e.newVal)}</span>
          {:else if e.kind === 'added'}
            <span class="text-yellow" title={e.path}>{prettifyPath(e.path)}</span>
            {' '}<span class="text-green">&plus; {jsonSummary(e.raw)}</span>
          {:else if e.kind === 'removed'}
            <span class="text-yellow" title={e.path}>{prettifyPath(e.path)}</span>
            {' '}<span class="text-red">&minus; {jsonSummary(e.raw)}</span>
          {:else}
            {jsonSummary(e.raw, 2)}
          {/if}
        </div>
      {/each}
    </div>
  {/each}

  {#if sections.length === 0}
    <button class="text-[0.75em] text-yellow cursor-pointer bg-transparent border border-yellow px-2 py-0.5 rounded ml-2 align-middle font-normal normal-case tracking-normal hover:bg-yellow/15 {copyClass === 'copied' ? 'text-green border-green' : ''}" onclick={(e) => { e.stopPropagation(); copySummary(); }}>{copyLabel}</button>
    {' '}<button class="text-[0.75em] text-cyan cursor-pointer bg-transparent border border-cyan px-2 py-0.5 rounded ml-1 align-middle font-normal normal-case tracking-normal hover:bg-cyan/15 {curlClassA === 'copied' ? 'text-green border-green' : ''}" onclick={(e) => { e.stopPropagation(); copyCurl('a'); }}>{curlLabelA}</button>
    {' '}<button class="text-[0.75em] text-cyan cursor-pointer bg-transparent border border-cyan px-2 py-0.5 rounded ml-1 align-middle font-normal normal-case tracking-normal hover:bg-cyan/15 {curlClassB === 'copied' ? 'text-green border-green' : ''}" onclick={(e) => { e.stopPropagation(); copyCurl('b'); }}>{curlLabelB}</button>
    {#if ignoredCount > 0}
      {' '}<span class="text-[0.7em] text-text-dim font-mono px-1.5 py-0.5 rounded bg-text-dim/10 border border-edge ml-2 cursor-help" title={ignoredTooltip}>{ignoredCount} fields ignored</span>
    {/if}
  {/if}
{/if}

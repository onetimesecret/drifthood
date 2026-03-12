<script>
  import { parseDiff, jsonSummary } from '../../lib/diff.js';
  import { prettifyPath, escHtml } from '../../lib/format.js';
  import { buildDriftSummary } from '../../lib/export.js';
  import { session } from '../stores/session.svelte.js';

  let { result, endpointId } = $props();

  let sections = $derived(result?.has_drift ? parseDiff(result.diff) : []);
  let ignoredCount = $derived(result?.ignored_paths?.length ?? 0);
  let ignoredTooltip = $derived(
    result?.ignored_paths ? result.ignored_paths.map(prettifyPath).join('\n') : ''
  );

  let copyLabel = $state('Copy summary');
  let copyClass = $state('');

  function copySummary() {
    if (!result?.has_drift) return;
    const text = buildDriftSummary(result, {
      title: session.title,
      memo: session.memo,
      hostA: session.hostA,
      hostB: session.hostB,
      memoA: session.memoA,
      memoB: session.memoB,
    });
    navigator.clipboard.writeText(text).then(() => {
      copyLabel = 'Copied';
      copyClass = 'copied';
      setTimeout(() => { copyLabel = 'Copy summary'; copyClass = ''; }, 1500);
    });
  }
</script>

{#if !result?.has_drift}
  <div style="color:var(--green);font-size:0.85em;padding:4px 0">
    No differences detected.{#if ignoredCount > 0}
      {' '}<span class="ignored-badge" title={ignoredTooltip}>{ignoredCount} fields ignored</span>
    {/if}
  </div>
{:else}
  {#each sections as sec, secIdx}
    <div class="diff-section">
      <h4>
        {escHtml(sec.label)}
        {#if secIdx === 0}
          {' '}<button class="copy-drift-btn {copyClass}" onclick={(e) => { e.stopPropagation(); copySummary(); }}>{copyLabel}</button>
          {#if ignoredCount > 0}
            {' '}<span class="ignored-badge" title={ignoredTooltip}>{ignoredCount} fields ignored</span>
          {/if}
        {/if}
      </h4>

      {#each sec.entries as e}
        <div class="diff-entry">
          {#if e.oldVal !== undefined && e.oldType}
            <span class="diff-path" title={e.path}>{prettifyPath(e.path)}</span><br>
            <span class="diff-old">&minus; {escHtml(jsonSummary(e.oldVal))} <span style="opacity:0.6">({e.oldType})</span></span><br>
            <span class="diff-new">&plus; {escHtml(jsonSummary(e.newVal))} <span style="opacity:0.6">({e.newType})</span></span>
          {:else if e.oldVal !== undefined}
            <span class="diff-path" title={e.path}>{prettifyPath(e.path)}</span><br>
            <span class="diff-old">&minus; {escHtml(jsonSummary(e.oldVal))}</span><br>
            <span class="diff-new">&plus; {escHtml(jsonSummary(e.newVal))}</span>
          {:else if e.kind === 'added'}
            <span class="diff-path" title={e.path}>{prettifyPath(e.path)}</span>
            {' '}<span class="diff-new">&plus; {escHtml(jsonSummary(e.raw))}</span>
          {:else if e.kind === 'removed'}
            <span class="diff-path" title={e.path}>{prettifyPath(e.path)}</span>
            {' '}<span class="diff-old">&minus; {escHtml(jsonSummary(e.raw))}</span>
          {:else}
            {escHtml(jsonSummary(e.raw, 2))}
          {/if}
        </div>
      {/each}
    </div>
  {/each}

  {#if sections.length === 0}
    <button class="copy-drift-btn {copyClass}" onclick={(e) => { e.stopPropagation(); copySummary(); }}>{copyLabel}</button>
    {#if ignoredCount > 0}
      {' '}<span class="ignored-badge" title={ignoredTooltip}>{ignoredCount} fields ignored</span>
    {/if}
  {/if}
{/if}

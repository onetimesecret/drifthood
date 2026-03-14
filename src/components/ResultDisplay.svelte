<script>
  import DiffView from './DiffView.svelte';
  import { statusLabel, contentLength, buildFullMd } from '../../lib/export.js';
  import { jsonSummary } from '../../lib/diff.js';
  import { escHtml, relativeTime } from '../../lib/format.js';
  import { session, getEnvA, getEnvB } from '../stores/session.svelte.js';
  import { ui } from '../stores/ui.svelte.js';

  let { endpoint } = $props();

  let r = $derived(endpoint.result);

  // Local toggle state
  let expanded = $state(false);
  let rawDiffVisible = $state(false);
  let reqBodyVisible = $state(false);
  let reqHeadersVisible = $state(false);
  let respHeadersVisible = $state(false);
  let copyMenuOpen = $state(false);

  // Auto-expand when a run completes (any result, not just drift)
  let lastResultRef = null;
  $effect(() => {
    if (r && r !== lastResultRef) {
      lastResultRef = r;
      expanded = true;
    }
  });

  // Collapse when filter pills are clicked
  let lastCollapseGen = 0;
  $effect(() => {
    const gen = ui.collapseGen;
    if (gen > lastCollapseGen) {
      expanded = false;
      lastCollapseGen = gen;
    }
  });

  const STALE_THRESHOLD_MS = 5 * 60 * 1000;

  // Computed meta strings
  let metaStatus = $derived(r ? `${statusLabel(r.response_a)}/${statusLabel(r.response_b)}` : '');
  let metaSize = $derived(r ? `${isErrorResponse(r.response_a) ? 'N/A' : contentLength(r.response_a)}/${isErrorResponse(r.response_b) ? 'N/A' : contentLength(r.response_b)} bytes` : '');
  let metaTiming = $derived(r ? `${r.response_a.elapsed_ms ?? 'N/A'}/${r.response_b.elapsed_ms ?? 'N/A'}ms` : '');
  let capturedAge = $derived(r?.captured_at ? relativeTime(r.captured_at) : '');
  let isStale = $derived(r?.captured_at ? (Date.now() - new Date(r.captured_at).getTime()) > STALE_THRESHOLD_MS : false);

  // Request body formatting
  let reqBodyFmt = $derived(r ? formatRequestBody(r.request_body, r.request_content_type) : null);

  function toggleBody() {
    expanded = !expanded;
  }

  function clipCopy(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
      if (!btn) return;
      const orig = btn.textContent;
      btn.textContent = 'copied';
      btn.classList.add('copied');
      setTimeout(() => { btn.textContent = orig; btn.classList.remove('copied'); }, 1200);
    });
  }

  function sessionContext() {
    const envA = getEnvA();
    const envB = getEnvB();
    return {
      title: session.title,
      memo: session.memo,
      hostA: envA?.baseUrl || '',
      hostB: envB?.baseUrl || '',
      memoA: envA?.name || '',
      memoB: envB?.name || '',
    };
  }

  function copyFullMd(btn) {
    if (!r) return;
    clipCopyWithMenuClose(buildFullMd(r, sessionContext()), btn);
  }

  function copyFullJson(btn) {
    if (!r) return;
    clipCopyWithMenuClose(JSON.stringify(r, null, 2), btn);
  }

  function clipCopyWithMenuClose(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
      if (btn) {
        const orig = btn.textContent;
        btn.textContent = 'Copied';
        btn.classList.add('copied');
        setTimeout(() => { btn.textContent = orig; btn.classList.remove('copied'); copyMenuOpen = false; }, 1200);
      } else {
        copyMenuOpen = false;
      }
    });
  }

  function isErrorResponse(resp) {
    return resp.status == null && resp.error;
  }

  function isHttpError(resp) {
    return resp.status != null && resp.status >= 400;
  }

  // Determine badge text and class:
  // - DRIFT when responses differ
  // - MATCH when responses agree but both are errors (connection or HTTP 4xx/5xx)
  // - OK when responses agree and at least one is a success
  let badgeText = $derived.by(() => {
    if (!r) return '';
    if (r.has_drift) return 'DRIFT';
    const bothError = (isErrorResponse(r.response_a) || isHttpError(r.response_a))
                   && (isErrorResponse(r.response_b) || isHttpError(r.response_b));
    return bothError ? 'MATCH' : 'OK';
  });

  let badgeClasses = $derived.by(() => {
    if (!r) return '';
    if (r.has_drift) return 'bg-red/15 text-red';
    const bothError = (isErrorResponse(r.response_a) || isHttpError(r.response_a))
                   && (isErrorResponse(r.response_b) || isHttpError(r.response_b));
    return bothError ? 'bg-yellow/15 text-yellow' : 'bg-green/15 text-green';
  });

  function formatReqHeaders(result, side) {
    const resp = side === 'a' ? result.response_a : result.response_b;
    if (isErrorResponse(resp)) {
      return `Error: ${resp.error}`;
    }
    let lines = [];
    if (resp.request_url) lines.push(`URL: ${resp.request_url}`);
    lines.push(`Method: ${result.method}`);
    if (resp.request_headers && Object.keys(resp.request_headers).length) {
      for (const [k, v] of Object.entries(resp.request_headers)) {
        lines.push(`${k}: ${v}`);
      }
    }
    return lines.join('\n');
  }

  function formatRequestBody(body, contentType) {
    if (body == null || body === '') return null;

    const ct = contentType || 'query';

    if (ct === 'application/json') {
      try {
        const parsed = JSON.parse(body);
        const pretty = JSON.stringify(parsed, null, 2);
        return { html: escHtml(pretty), text: pretty, type: 'json' };
      } catch (_) {
        return { html: escHtml(body), text: body, type: 'raw' };
      }
    }

    if (ct === 'application/x-www-form-urlencoded' || ct === 'query') {
      const label = ct === 'query' ? 'Query' : 'Form';
      try {
        const params = new URLSearchParams(body);
        const entries = [...params.entries()];
        if (entries.length === 0) return { html: escHtml(body), text: body, type: 'raw' };

        let html = `<table style="border-collapse:collapse;width:100%;font-family:var(--mono);font-size:0.85em;">`;
        html += `<tr style="border-bottom:1px solid var(--border);color:var(--text-dim);"><td style="padding:3px 8px;font-size:0.85em;text-transform:uppercase;letter-spacing:0.06em;">${label} Key</td><td style="padding:3px 8px;font-size:0.85em;text-transform:uppercase;letter-spacing:0.06em;">Value</td></tr>`;
        for (const [k, v] of entries) {
          html += `<tr style="border-bottom:1px solid var(--border);"><td style="padding:3px 8px;color:var(--accent);">${escHtml(k)}</td><td style="padding:3px 8px;color:var(--text);">${escHtml(v)}</td></tr>`;
        }
        html += `</table>`;
        html += `<div style="margin-top:6px;font-size:0.8em;color:var(--text-dim);">Raw: <code>${escHtml(body)}</code></div>`;

        return { html, text: body, type: label.toLowerCase() };
      } catch (_) {
        return { html: escHtml(body), text: body, type: 'raw' };
      }
    }

    return { html: escHtml(body), text: body, type: 'raw' };
  }

  function fmtBody(body, resp) {
    if (body == null) {
      if (resp && isErrorResponse(resp)) return `No response (${resp.error})`;
      return '(empty)';
    }
    return typeof body === 'string' ? body : JSON.stringify(body, null, 2);
  }

  function fmtRespHeaders(resp) {
    if (isErrorResponse(resp)) return `No response (${resp.error})`;
    return JSON.stringify(resp.headers, null, 2);
  }

  // Close copy menu on outside click
  $effect(() => {
    function handleClick(e) {
      if (copyMenuOpen && !e.target.closest('.copy-menu')) {
        copyMenuOpen = false;
      }
    }
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  });
</script>

{#if r}
  <div class="border-t border-edge {isStale ? 'opacity-75' : ''}">
    <div class="flex items-center gap-2.5 px-3 py-2 cursor-pointer select-none text-[0.85em] hover:bg-white/[0.02]" role="button" tabindex="0" onclick={toggleBody} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleBody(); } }}>
      <span class="chevron text-text-dim text-[0.8em] transition-transform duration-150" class:open={expanded}>&#9654;</span>
      <span class="text-[0.75em] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider {badgeClasses}">{badgeText}</span>
      <span class="font-mono text-[0.75em] text-text-dim">{metaStatus} {metaSize}</span>
      <span class="ml-auto font-mono text-[0.75em] text-text-dim">{metaTiming}</span>
      {#if capturedAge}
        <span class="font-mono text-[0.65em] {isStale ? 'text-yellow' : 'text-text-dim'}" title={r.captured_at}>{isStale ? 'stale: ' : ''}{capturedAge}</span>
      {/if}
    </div>

    <div class="toggle-block px-3.5 py-3 border-t border-edge" class:open={expanded}>
      <DiffView result={r} endpointId={endpoint.extid} />

      <div class="grid grid-cols-2 gap-3 mt-2.5">
        <div class="relative group bg-bg p-2 rounded-md">
          <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(fmtBody(r.response_a.body, r.response_a), e.currentTarget)}>copy</button>
          <div class="text-[0.7em] text-text-dim uppercase tracking-wider mb-1">{getEnvA()?.name || 'Environment A'} ({r.response_a.status || 'ERR'})</div>
          <div class="font-mono text-[0.75em] whitespace-pre-wrap max-h-[300px] overflow-y-auto text-text-dim">{isErrorResponse(r.response_a) ? fmtBody(null, r.response_a) : jsonSummary(r.response_a.body, 2)}</div>
        </div>
        <div class="relative group bg-bg p-2 rounded-md">
          <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(fmtBody(r.response_b.body, r.response_b), e.currentTarget)}>copy</button>
          <div class="text-[0.7em] text-text-dim uppercase tracking-wider mb-1">{getEnvB()?.name || 'Environment B'} ({r.response_b.status || 'ERR'})</div>
          <div class="font-mono text-[0.75em] whitespace-pre-wrap max-h-[300px] overflow-y-auto text-text-dim">{isErrorResponse(r.response_b) ? fmtBody(null, r.response_b) : jsonSummary(r.response_b.body, 2)}</div>
        </div>
      </div>

      <div class="flex gap-1 flex-wrap items-center mt-2">
        <button class="text-[0.75em] text-accent cursor-pointer bg-transparent border-none p-0 mt-2" onclick={() => rawDiffVisible = !rawDiffVisible}>
          {rawDiffVisible ? 'Hide' : 'Show'} raw diff JSON
        </button>
        {#if reqBodyFmt}
          <button class="text-[0.75em] text-accent cursor-pointer bg-transparent border-none p-0 mt-2 ml-3" onclick={() => reqBodyVisible = !reqBodyVisible}>
            {reqBodyVisible ? 'Hide' : 'Show'} request body
          </button>
        {/if}
        <button class="text-[0.75em] text-accent cursor-pointer bg-transparent border-none p-0 mt-2 ml-3" onclick={() => reqHeadersVisible = !reqHeadersVisible}>
          {reqHeadersVisible ? 'Hide' : 'Show'} request headers
        </button>
        <button class="text-[0.75em] text-accent cursor-pointer bg-transparent border-none p-0 mt-2 ml-3" onclick={() => respHeadersVisible = !respHeadersVisible}>
          {respHeadersVisible ? 'Hide' : 'Show'} response headers
        </button>
        <div class="copy-menu relative inline-block">
          <button class="text-[0.75em] text-accent cursor-pointer bg-transparent border-none p-0 mt-2 ml-3" onclick={() => copyMenuOpen = !copyMenuOpen}>Copy as...</button>
          {#if copyMenuOpen}
            <div class="absolute bottom-full left-0 bg-surface border border-edge rounded-md p-1 z-20 min-w-[180px] mb-1 shadow-[0_8px_24px_rgba(0,0,0,0.4)]">
              <button class="block w-full text-left bg-transparent border-none text-text-primary px-2.5 py-1.5 rounded text-[0.8em] font-mono cursor-pointer whitespace-nowrap hover:bg-white/5" onclick={(e) => copyFullMd(e.currentTarget)}>Full result (markdown)</button>
              <button class="block w-full text-left bg-transparent border-none text-text-primary px-2.5 py-1.5 rounded text-[0.8em] font-mono cursor-pointer whitespace-nowrap hover:bg-white/5" onclick={(e) => copyFullJson(e.currentTarget)}>Full result (json)</button>
            </div>
          {/if}
        </div>
      </div>

      {#if rawDiffVisible}
        <div class="relative group font-mono text-[0.75em] bg-bg p-2.5 rounded-md overflow-x-auto whitespace-pre-wrap mt-1.5 max-h-[400px] overflow-y-auto text-text-dim">
          <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(JSON.stringify(r.diff, null, 2), e.currentTarget)}>copy</button>
          {JSON.stringify(r.diff, null, 2)}
        </div>
      {/if}

      {#if reqBodyFmt && reqBodyVisible}
        <div class="relative group font-mono text-[0.75em] bg-bg p-2.5 rounded-md overflow-x-auto whitespace-pre-wrap mt-1.5 max-h-[400px] overflow-y-auto text-text-dim">
          <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(reqBodyFmt.text, e.currentTarget)}>copy</button>
          <div class="text-[0.7em] text-text-dim uppercase tracking-wider mb-1">Request Body <span class="text-[0.85em] text-text-dim normal-case tracking-normal">({r.request_content_type || 'query'})</span></div>
          <div class="font-mono text-[0.75em] whitespace-pre-wrap max-h-[300px] overflow-y-auto text-text-dim">{@html reqBodyFmt.html}</div>
        </div>
      {/if}

      {#if reqHeadersVisible}
        <div class="font-mono text-[0.75em] bg-bg p-2.5 rounded-md overflow-x-auto whitespace-pre-wrap mt-1.5 max-h-[400px] overflow-y-auto text-text-dim">
          <div class="grid grid-cols-2 gap-3">
            <div class="relative group">
              <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(formatReqHeaders(r, 'a'), e.currentTarget)}>copy</button>
              <div class="text-[0.7em] text-text-dim uppercase tracking-wider mb-1">Request to {getEnvA()?.name || 'A'}</div>
              {formatReqHeaders(r, 'a')}
            </div>
            <div class="relative group">
              <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(formatReqHeaders(r, 'b'), e.currentTarget)}>copy</button>
              <div class="text-[0.7em] text-text-dim uppercase tracking-wider mb-1">Request to {getEnvB()?.name || 'B'}</div>
              {formatReqHeaders(r, 'b')}
            </div>
          </div>
        </div>
      {/if}

      {#if respHeadersVisible}
        <div class="font-mono text-[0.75em] bg-bg p-2.5 rounded-md overflow-x-auto whitespace-pre-wrap mt-1.5 max-h-[400px] overflow-y-auto text-text-dim">
          <div class="grid grid-cols-2 gap-3">
            <div class="relative group">
              <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(fmtRespHeaders(r.response_a), e.currentTarget)}>copy</button>
              <div class="text-[0.7em] text-text-dim uppercase tracking-wider mb-1">Response A</div>
              {fmtRespHeaders(r.response_a)}
            </div>
            <div class="relative group">
              <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(fmtRespHeaders(r.response_b), e.currentTarget)}>copy</button>
              <div class="text-[0.7em] text-text-dim uppercase tracking-wider mb-1">Response B</div>
              {fmtRespHeaders(r.response_b)}
            </div>
          </div>
        </div>
      {/if}
    </div>
  </div>
{/if}

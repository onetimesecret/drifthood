<script>
  import DiffView from './DiffView.svelte';
  import { statusLabel, contentLength, buildFullMd } from '../../lib/export.js';
  import { escHtml, relativeTime } from '../../lib/format.js';
  import { session, getEnvA, getEnvB } from '../stores/session.svelte.js';
  import { ui } from '../stores/ui.svelte.js';

  let { endpoint } = $props();

  let r = $derived(endpoint.result);

  // ── Section tab state (Task 3: tab/accordion restructure) ──
  // Available tabs: 'diff' | 'bodies' | 'request' | 'response' | 'raw'
  let expanded = $state(false);
  let activeTab = $state('diff');
  let copyMenuOpen = $state(false);

  // Task 2: request headers collapsed by default, expand on click
  let reqHeadersExpanded = $state(false);

  // Task 6: response headers show only deltas by default
  let showAllRespHeaders = $state(false);

  // Auto-expand when a run completes (any result, not just drift)
  let lastResultRef = null;
  $effect(() => {
    if (r && r !== lastResultRef) {
      lastResultRef = r;
      expanded = true;
      activeTab = 'diff';
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

  // ── Tab definitions ──
  const TABS = [
    { id: 'diff', label: 'Diff' },
    { id: 'bodies', label: 'Bodies' },
    { id: 'request', label: 'Request' },
    { id: 'response', label: 'Response' },
    { id: 'raw', label: 'Raw' },
  ];

  // Only show request body tab indicator when there is a request body
  let visibleTabs = $derived(TABS);

  function toggleBody() {
    expanded = !expanded;
  }

  function setTab(tabId) {
    activeTab = tabId;
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

  // ── Request header helpers ──
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

  // Task 2: Build a compact summary of request headers for the collapsed view
  function reqHeaderSummary(result) {
    const resp = result.response_a;
    if (isErrorResponse(resp)) return result.method;
    const headers = resp.request_headers || {};
    const parts = [result.method];
    const ua = headers['User-Agent'] || headers['user-agent'] || '';
    if (ua) {
      // Extract just the library name, e.g. "python-requests/2.32.3" -> "python-requests/2.32.3"
      const short = ua.split(' ')[0];
      if (short) parts.push(short);
    }
    const conn = headers['Connection'] || headers['connection'] || '';
    if (conn) parts.push(conn);
    const accept = headers['Accept'] || headers['accept'] || '';
    if (accept && accept !== '*/*') parts.push(`accept: ${accept}`);
    return parts.join(', ');
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

  // ── Task 5: JSON syntax highlighting ──
  // Tokenize raw JSON, escape each token individually, then wrap in spans.
  // This avoids HTML entities (&quot; etc.) breaking regex boundaries.
  function highlightJson(jsonStr) {
    if (!jsonStr || typeof jsonStr !== 'string') return escHtml(String(jsonStr ?? ''));

    // Tokenize the raw (unescaped) JSON string.
    // Group 1+2: key string + colon, 3: plain string, 4: number,
    // 5: boolean/null, 6: punctuation, 7: whitespace
    const TOKEN_RE = /("(?:[^"\\]|\\.)*")\s*(:)|("(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b|(true|false|null)\b|([{}\[\]:,])|(\s+)/g;
    const parts = [];
    let lastIndex = 0;
    let m;

    while ((m = TOKEN_RE.exec(jsonStr)) !== null) {
      if (m.index > lastIndex) {
        parts.push(escHtml(jsonStr.slice(lastIndex, m.index)));
      }
      lastIndex = TOKEN_RE.lastIndex;

      if (m[1] !== undefined) {
        // JSON key (quoted string followed by colon)
        parts.push('<span class="json-key">' + escHtml(m[1]) + '</span>' + escHtml(m[2]));
      } else if (m[3] !== undefined) {
        // String value
        parts.push('<span class="json-str">' + escHtml(m[3]) + '</span>');
      } else if (m[4] !== undefined) {
        // Number
        parts.push('<span class="json-num">' + escHtml(m[4]) + '</span>');
      } else if (m[5] !== undefined) {
        // Boolean or null
        parts.push('<span class="json-bool">' + escHtml(m[5]) + '</span>');
      } else if (m[6] !== undefined) {
        // Punctuation
        parts.push(escHtml(m[6]));
      } else if (m[7] !== undefined) {
        // Whitespace
        parts.push(m[7]);
      }
    }

    if (lastIndex < jsonStr.length) {
      parts.push(escHtml(jsonStr.slice(lastIndex)));
    }

    return parts.join('');
  }

  // Highlighted body output
  function highlightedBody(body, resp) {
    const text = fmtBody(body, resp);
    if (resp && isErrorResponse(resp)) return escHtml(text);
    return highlightJson(text);
  }

  // ── Tasks 1+6: Response header tabular diff ──
  // Computes a unified key-value table comparing headers from both sides.
  // Each row: { key, valA, valB, status: 'same'|'changed'|'only-a'|'only-b' }
  let respHeaderRows = $derived.by(() => {
    if (!r) return { changed: [], same: [] };
    const hA = (isErrorResponse(r.response_a)) ? {} : (r.response_a.headers || {});
    const hB = (isErrorResponse(r.response_b)) ? {} : (r.response_b.headers || {});
    const allKeys = [...new Set([...Object.keys(hA), ...Object.keys(hB)])];

    // Sort: case-insensitive alphabetical
    allKeys.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));

    const changed = [];
    const same = [];

    for (const key of allKeys) {
      const valA = hA[key];
      const valB = hB[key];
      const strA = valA !== undefined ? String(valA) : undefined;
      const strB = valB !== undefined ? String(valB) : undefined;

      if (strA === undefined) {
        changed.push({ key, valA: null, valB: strB, status: 'only-b' });
      } else if (strB === undefined) {
        changed.push({ key, valA: strA, valB: null, status: 'only-a' });
      } else if (strA !== strB) {
        changed.push({ key, valA: strA, valB: strB, status: 'changed' });
      } else {
        same.push({ key, valA: strA, valB: strB, status: 'same' });
      }
    }

    return { changed, same };
  });

  let respHeaderDeltaCount = $derived(respHeaderRows.changed.length);
  let respHeaderSameCount = $derived(respHeaderRows.same.length);

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
    <!-- Collapsed summary row -->
    <div class="flex items-center gap-2.5 px-3 py-2 cursor-pointer select-none text-[0.85em] hover:bg-white/[0.02]" role="button" tabindex="0" onclick={toggleBody} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleBody(); } }}>
      <span class="chevron text-text-dim text-[0.8em] transition-transform duration-150" class:open={expanded}>&#9654;</span>
      <span class="text-[0.75em] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider {badgeClasses}">{badgeText}</span>
      <span class="font-mono text-[0.75em] text-text-dim">{metaStatus} {metaSize}</span>
      <span class="ml-auto font-mono text-[0.75em] text-text-dim">{metaTiming}</span>
      {#if capturedAge}
        <span class="font-mono text-[0.65em] {isStale ? 'text-yellow' : 'text-text-dim'}" title={r.captured_at}>{isStale ? 'stale: ' : ''}{capturedAge}</span>
      {/if}
    </div>

    <!-- Expanded content -->
    <div class="toggle-block border-t border-edge" class:open={expanded}>

      <!-- Task 3: Tab bar replacing inline Show/Hide toggles -->
      <div class="flex items-center gap-0 px-3.5 pt-2 pb-0 border-b border-edge bg-surface/30">
        {#each visibleTabs as tab}
          <button
            class="px-3 py-1.5 text-[0.75em] font-medium border-b-2 cursor-pointer bg-transparent transition-colors duration-100
              {activeTab === tab.id
                ? 'text-accent border-accent'
                : 'text-text-dim border-transparent hover:text-text-primary hover:border-edge'}"
            onclick={() => setTab(tab.id)}
          >
            {tab.label}
            {#if tab.id === 'response' && respHeaderDeltaCount > 0}
              <span class="ml-1 text-[0.8em] text-yellow">({respHeaderDeltaCount})</span>
            {/if}
          </button>
        {/each}

        <!-- Copy menu stays in the tab bar for easy access -->
        <div class="copy-menu relative inline-block ml-auto">
          <button class="text-[0.7em] text-text-dim cursor-pointer bg-transparent border border-edge px-2 py-1 rounded hover:text-text-primary hover:border-text-dim" onclick={() => copyMenuOpen = !copyMenuOpen}>Copy as...</button>
          {#if copyMenuOpen}
            <div class="absolute bottom-full right-0 bg-surface border border-edge rounded-md p-1 z-20 min-w-[180px] mb-1 shadow-[0_8px_24px_rgba(0,0,0,0.4)]">
              <button class="block w-full text-left bg-transparent border-none text-text-primary px-2.5 py-1.5 rounded text-[0.8em] font-mono cursor-pointer whitespace-nowrap hover:bg-white/5" onclick={(e) => copyFullMd(e.currentTarget)}>Full result (markdown)</button>
              <button class="block w-full text-left bg-transparent border-none text-text-primary px-2.5 py-1.5 rounded text-[0.8em] font-mono cursor-pointer whitespace-nowrap hover:bg-white/5" onclick={(e) => copyFullJson(e.currentTarget)}>Full result (json)</button>
            </div>
          {/if}
        </div>
      </div>

      <div class="px-3.5 py-3">

        <!-- ════════ DIFF TAB ════════ -->
        {#if activeTab === 'diff'}
          <DiffView result={r} endpointId={endpoint.extid} />
        {/if}

        <!-- ════════ BODIES TAB (Task 5: syntax highlighting) ════════ -->
        {#if activeTab === 'bodies'}
          <div class="grid grid-cols-2 gap-3">
            <div class="relative group bg-bg p-2 rounded-md">
              <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(fmtBody(r.response_a.body, r.response_a), e.currentTarget)}>copy</button>
              <div class="text-[0.7em] text-text-dim uppercase tracking-wider mb-1">{getEnvA()?.name || 'Environment A'} ({r.response_a.status || 'ERR'})</div>
              <div class="font-mono text-[0.75em] whitespace-pre-wrap max-h-[300px] overflow-y-auto">{@html highlightedBody(r.response_a.body, r.response_a)}</div>
            </div>
            <div class="relative group bg-bg p-2 rounded-md">
              <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(fmtBody(r.response_b.body, r.response_b), e.currentTarget)}>copy</button>
              <div class="text-[0.7em] text-text-dim uppercase tracking-wider mb-1">{getEnvB()?.name || 'Environment B'} ({r.response_b.status || 'ERR'})</div>
              <div class="font-mono text-[0.75em] whitespace-pre-wrap max-h-[300px] overflow-y-auto">{@html highlightedBody(r.response_b.body, r.response_b)}</div>
            </div>
          </div>

          <!-- Request body (if present) -->
          {#if reqBodyFmt}
            <div class="relative group font-mono text-[0.75em] bg-bg p-2.5 rounded-md overflow-x-auto whitespace-pre-wrap mt-3 max-h-[400px] overflow-y-auto border-l-2 border-accent/30">
              <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(reqBodyFmt.text, e.currentTarget)}>copy</button>
              <div class="text-[0.7em] text-text-dim uppercase tracking-wider mb-1">Request Body <span class="text-[0.85em] text-text-dim normal-case tracking-normal">({r.request_content_type || 'query'})</span></div>
              <div class="font-mono text-[0.75em] whitespace-pre-wrap max-h-[300px] overflow-y-auto text-text-dim">{@html reqBodyFmt.html}</div>
            </div>
          {/if}
        {/if}

        <!-- ════════ REQUEST TAB (Task 2: collapsed by default, Task 4: visual differentiation) ════════ -->
        {#if activeTab === 'request'}
          <div class="border-l-2 border-accent/30 rounded-md overflow-hidden">
            <!-- Task 2: Compact summary line, click to expand -->
            <button
              class="w-full flex items-center gap-2 px-3 py-2 bg-accent/[0.04] text-left cursor-pointer border-none hover:bg-accent/[0.07] transition-colors duration-100"
              onclick={() => reqHeadersExpanded = !reqHeadersExpanded}
            >
              <span class="chevron text-text-dim text-[0.7em] transition-transform duration-150" class:open={reqHeadersExpanded}>&#9654;</span>
              <span class="text-[0.75em] text-text-dim uppercase tracking-wider font-medium">Request Headers</span>
              <span class="font-mono text-[0.7em] text-accent/70 ml-1">{reqHeaderSummary(r)}</span>
            </button>

            {#if reqHeadersExpanded}
              <div class="font-mono text-[0.75em] bg-accent/[0.02] p-2.5 overflow-x-auto whitespace-pre-wrap max-h-[400px] overflow-y-auto">
                <div class="grid grid-cols-2 gap-3">
                  <div class="relative group">
                    <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(formatReqHeaders(r, 'a'), e.currentTarget)}>copy</button>
                    <div class="text-[0.7em] text-text-dim uppercase tracking-wider mb-1">Request to {getEnvA()?.name || 'A'}</div>
                    <div class="text-text-dim">{formatReqHeaders(r, 'a')}</div>
                  </div>
                  <div class="relative group">
                    <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(formatReqHeaders(r, 'b'), e.currentTarget)}>copy</button>
                    <div class="text-[0.7em] text-text-dim uppercase tracking-wider mb-1">Request to {getEnvB()?.name || 'B'}</div>
                    <div class="text-text-dim">{formatReqHeaders(r, 'b')}</div>
                  </div>
                </div>
              </div>
            {/if}
          </div>
        {/if}

        <!-- ════════ RESPONSE TAB (Task 1: tabular diff, Task 4: visual zone, Task 6: deltas-only) ════════ -->
        {#if activeTab === 'response'}
          <div class="border-l-2 border-purple/30 rounded-md overflow-hidden">

            {#if isErrorResponse(r.response_a) && isErrorResponse(r.response_b)}
              <div class="p-3 text-[0.8em] text-red">
                No response headers available (both requests failed).
                <div class="text-text-dim mt-1 text-[0.9em]">A: {r.response_a.error}</div>
                <div class="text-text-dim mt-0.5 text-[0.9em]">B: {r.response_b.error}</div>
              </div>
            {:else}
              <!-- Header delta count and Show All toggle -->
              <div class="flex items-center gap-2 px-3 py-2 bg-purple/[0.04]">
                <span class="text-[0.75em] text-text-dim uppercase tracking-wider font-medium">Response Headers</span>
                {#if respHeaderDeltaCount > 0}
                  <span class="text-[0.7em] font-mono px-1.5 py-0.5 rounded-full bg-yellow/15 text-yellow">{respHeaderDeltaCount} differ</span>
                {/if}
                {#if respHeaderSameCount > 0}
                  <span class="text-[0.7em] font-mono text-text-dim">{respHeaderSameCount} identical</span>
                {/if}
                <button
                  class="ml-auto text-[0.7em] text-accent cursor-pointer bg-transparent border border-edge px-2 py-0.5 rounded hover:border-text-dim hover:text-text-primary transition-colors duration-100"
                  onclick={() => showAllRespHeaders = !showAllRespHeaders}
                >
                  {showAllRespHeaders ? 'Show deltas only' : 'Show all'}
                </button>
                <button class="text-[0.65em] font-mono text-text-dim cursor-pointer bg-transparent border border-edge px-1.5 py-0.5 rounded hover:text-text-primary hover:border-text-dim leading-snug" onclick={(e) => {
                  const text = fmtRespHeaders(r.response_a) + '\n---\n' + fmtRespHeaders(r.response_b);
                  clipCopy(text, e.currentTarget);
                }}>copy</button>
              </div>

              <!-- Tabular diff view -->
              <div class="overflow-x-auto bg-purple/[0.02]">
                <table class="w-full border-collapse font-mono text-[0.75em]">
                  <thead>
                    <tr class="border-b border-edge">
                      <th class="text-left px-3 py-1.5 text-[0.85em] text-text-dim uppercase tracking-wider font-medium w-[28%]">Header</th>
                      <th class="text-left px-3 py-1.5 text-[0.85em] text-text-dim uppercase tracking-wider font-medium w-[36%]">{getEnvA()?.name || 'A'}</th>
                      <th class="text-left px-3 py-1.5 text-[0.85em] text-text-dim uppercase tracking-wider font-medium w-[36%]">{getEnvB()?.name || 'B'}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <!-- Changed/added/removed rows always visible -->
                    {#each respHeaderRows.changed as row}
                      <tr class="border-b border-edge/50
                        {row.status === 'changed' ? 'bg-yellow/[0.06]' : ''}
                        {row.status === 'only-a' ? 'bg-red/[0.06]' : ''}
                        {row.status === 'only-b' ? 'bg-green/[0.06]' : ''}">
                        <td class="px-3 py-1 text-accent font-medium break-all">{row.key}</td>
                        <td class="px-3 py-1 break-all {row.status === 'only-b' ? 'text-text-dim/40 italic' : row.status === 'changed' ? 'text-red' : 'text-text-dim'}">
                          {#if row.valA != null}{row.valA}{:else}<span class="text-text-dim/40">(absent)</span>{/if}
                        </td>
                        <td class="px-3 py-1 break-all {row.status === 'only-a' ? 'text-text-dim/40 italic' : row.status === 'changed' ? 'text-green' : 'text-text-dim'}">
                          {#if row.valB != null}{row.valB}{:else}<span class="text-text-dim/40">(absent)</span>{/if}
                        </td>
                      </tr>
                    {/each}

                    {#if respHeaderDeltaCount === 0}
                      <tr class="border-b border-edge/50">
                        <td colspan="3" class="px-3 py-2 text-green text-[0.9em]">All headers identical between A and B.</td>
                      </tr>
                    {/if}

                    <!-- Identical rows: collapsed behind disclosure (Task 6) -->
                    {#if showAllRespHeaders && respHeaderSameCount > 0}
                      <tr class="border-b border-edge/30">
                        <td colspan="3" class="px-3 py-1 text-[0.85em] text-text-dim/60 uppercase tracking-wider">Identical headers</td>
                      </tr>
                      {#each respHeaderRows.same as row}
                        <tr class="border-b border-edge/20 opacity-50 hover:opacity-80 transition-opacity duration-100">
                          <td class="px-3 py-1 text-text-dim">{row.key}</td>
                          <td class="px-3 py-1 text-text-dim" colspan="2">{row.valA}</td>
                        </tr>
                      {/each}
                    {/if}
                  </tbody>
                </table>
              </div>
            {/if}
          </div>
        {/if}

        <!-- ════════ RAW TAB ════════ -->
        {#if activeTab === 'raw'}
          <div class="relative group font-mono text-[0.75em] bg-bg p-2.5 rounded-md overflow-x-auto whitespace-pre-wrap max-h-[400px] overflow-y-auto text-text-dim">
            <button class="absolute top-1 right-1 bg-surface border border-edge text-text-dim text-[0.65em] font-mono px-1.5 py-0.5 rounded cursor-pointer opacity-0 group-hover:opacity-70 hover:opacity-100 hover:text-text-primary hover:border-text-dim z-5 leading-snug" onclick={(e) => clipCopy(JSON.stringify(r.diff, null, 2), e.currentTarget)}>copy</button>
            <div class="text-[0.7em] text-text-dim uppercase tracking-wider mb-2">Raw Diff JSON</div>
            <div>{@html highlightJson(JSON.stringify(r.diff, null, 2))}</div>
          </div>
        {/if}

      </div>
    </div>
  </div>
{/if}

<style>
  /* Task 5: JSON syntax highlighting colors */
  :global(.json-key) { color: var(--color-accent); }
  :global(.json-str) { color: var(--color-green); }
  :global(.json-num) { color: var(--color-purple); }
  :global(.json-bool) { color: var(--color-yellow); }
</style>

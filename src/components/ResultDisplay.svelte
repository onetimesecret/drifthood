<script>
  import DiffView from './DiffView.svelte';
  import { statusLabel, contentLength, buildFullMd } from '../../lib/export.js';
  import { jsonSummary } from '../../lib/diff.js';
  import { escHtml } from '../../lib/format.js';
  import { session } from '../stores/session.svelte.js';

  let { endpoint } = $props();

  let r = $derived(endpoint.result);

  // Local toggle state
  let expanded = $state(false);
  let rawDiffVisible = $state(false);
  let reqBodyVisible = $state(false);
  let reqHeadersVisible = $state(false);
  let respHeadersVisible = $state(false);
  let copyMenuOpen = $state(false);

  // Auto-expand on drift
  $effect(() => {
    if (r?.has_drift) {
      expanded = true;
    }
  });

  // Computed meta strings
  let metaStatus = $derived(r ? `${statusLabel(r.response_a)}/${statusLabel(r.response_b)}` : '');
  let metaSize = $derived(r ? `${contentLength(r.response_a)}/${contentLength(r.response_b)} bytes` : '');
  let metaTiming = $derived(r ? `${r.response_a.elapsed_ms ?? '?'}/${r.response_b.elapsed_ms ?? '?'}ms` : '');

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
    return {
      title: session.title,
      memo: session.memo,
      hostA: session.hostA,
      hostB: session.hostB,
      memoA: session.memoA,
      memoB: session.memoB,
    };
  }

  function copyFullMd(btn) {
    if (!r) return;
    clipCopy(buildFullMd(r, sessionContext()), btn);
    copyMenuOpen = false;
  }

  function copyFullJson(btn) {
    if (!r) return;
    clipCopy(JSON.stringify(r, null, 2), btn);
    copyMenuOpen = false;
  }

  function formatReqHeaders(result, side) {
    const resp = side === 'a' ? result.response_a : result.response_b;
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

  function fmtBody(body) {
    if (body == null) return '(empty)';
    return typeof body === 'string' ? body : JSON.stringify(body, null, 2);
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
  <div class="ep-result">
    <div class="ep-result-header" onclick={toggleBody}>
      <span class="chevron" class:open={expanded}>&#9654;</span>
      <span class="ep-result-badge {r.has_drift ? 'badge-drift' : 'badge-ok'}">{r.has_drift ? 'DRIFT' : 'OK'}</span>
      <span class="result-meta">{metaStatus} {metaSize}</span>
      <span class="ep-result-timing">{metaTiming}</span>
    </div>

    <div class="ep-result-body" class:open={expanded}>
      <DiffView result={r} endpointId={endpoint.id} />

      <div class="side-by-side">
        <div class="has-copy">
          <button class="inline-copy" onclick={(e) => clipCopy(fmtBody(r.response_a.body), e.currentTarget)}>copy</button>
          <div class="side-label">Host A ({r.response_a.status || 'ERR'})</div>
          <div class="side-json">{jsonSummary(r.response_a.body, 2)}</div>
        </div>
        <div class="has-copy">
          <button class="inline-copy" onclick={(e) => clipCopy(fmtBody(r.response_b.body), e.currentTarget)}>copy</button>
          <div class="side-label">Host B ({r.response_b.status || 'ERR'})</div>
          <div class="side-json">{jsonSummary(r.response_b.body, 2)}</div>
        </div>
      </div>

      <div class="toggles-row">
        <button class="raw-toggle" onclick={() => rawDiffVisible = !rawDiffVisible}>
          {rawDiffVisible ? 'Hide' : 'Show'} raw diff JSON
        </button>
        {#if reqBodyFmt}
          <button class="raw-toggle" onclick={() => reqBodyVisible = !reqBodyVisible}>
            {reqBodyVisible ? 'Hide' : 'Show'} request body
          </button>
        {/if}
        <button class="raw-toggle" onclick={() => reqHeadersVisible = !reqHeadersVisible}>
          {reqHeadersVisible ? 'Hide' : 'Show'} request headers
        </button>
        <button class="raw-toggle" onclick={() => respHeadersVisible = !respHeadersVisible}>
          {respHeadersVisible ? 'Hide' : 'Show'} response headers
        </button>
        <div class="copy-menu">
          <button class="raw-toggle" onclick={() => copyMenuOpen = !copyMenuOpen}>Copy as...</button>
          {#if copyMenuOpen}
            <div class="copy-menu-items open">
              <button onclick={(e) => copyFullMd(e.currentTarget)}>Full result (markdown)</button>
              <button onclick={(e) => copyFullJson(e.currentTarget)}>Full result (json)</button>
            </div>
          {/if}
        </div>
      </div>

      {#if rawDiffVisible}
        <div class="has-copy raw-json" style="display:block">
          <button class="inline-copy" onclick={(e) => clipCopy(JSON.stringify(r.diff, null, 2), e.currentTarget)}>copy</button>
          {JSON.stringify(r.diff, null, 2)}
        </div>
      {/if}

      {#if reqBodyFmt && reqBodyVisible}
        <div class="has-copy raw-headers" style="display:block">
          <button class="inline-copy" onclick={(e) => clipCopy(reqBodyFmt.text, e.currentTarget)}>copy</button>
          <div class="side-label">Request Body <span style="font-size:0.85em;color:var(--text-dim);text-transform:none;letter-spacing:0;">({r.request_content_type || 'query'})</span></div>
          <div class="side-json">{@html reqBodyFmt.html}</div>
        </div>
      {/if}

      {#if reqHeadersVisible}
        <div class="raw-headers" style="display:block">
          <div class="side-by-side">
            <div class="has-copy">
              <button class="inline-copy" onclick={(e) => clipCopy(formatReqHeaders(r, 'a'), e.currentTarget)}>copy</button>
              <div class="side-label">Request to A</div>
              {formatReqHeaders(r, 'a')}
            </div>
            <div class="has-copy">
              <button class="inline-copy" onclick={(e) => clipCopy(formatReqHeaders(r, 'b'), e.currentTarget)}>copy</button>
              <div class="side-label">Request to B</div>
              {formatReqHeaders(r, 'b')}
            </div>
          </div>
        </div>
      {/if}

      {#if respHeadersVisible}
        <div class="raw-headers" style="display:block">
          <div class="side-by-side">
            <div class="has-copy">
              <button class="inline-copy" onclick={(e) => clipCopy(JSON.stringify(r.response_a.headers, null, 2), e.currentTarget)}>copy</button>
              <div class="side-label">Response A</div>
              {JSON.stringify(r.response_a.headers, null, 2)}
            </div>
            <div class="has-copy">
              <button class="inline-copy" onclick={(e) => clipCopy(JSON.stringify(r.response_b.headers, null, 2), e.currentTarget)}>copy</button>
              <div class="side-label">Response B</div>
              {JSON.stringify(r.response_b.headers, null, 2)}
            </div>
          </div>
        </div>
      {/if}
    </div>
  </div>
{/if}

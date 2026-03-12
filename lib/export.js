// drift-detector/lib/export.js
//
// Export/copy helpers for drift results.
// Used by DiffView.svelte and ResultDisplay.svelte.

import { parseDiff, jsonSummary } from './diff.js';
import { prettifyPath } from './format.js';

/**
 * Human-readable status from a response side object.
 */
export function statusLabel(resp) {
  return resp?.status != null ? resp.status : 'ERR';
}

/**
 * Content-Length string from response headers, with body-size fallback.
 */
export function contentLength(resp) {
  if (!resp || !resp.headers) return '?';
  const cl = resp.headers['content-length'] || resp.headers['Content-Length'];
  if (cl) return cl;
  if (resp.body != null) {
    const s = typeof resp.body === 'string' ? resp.body : JSON.stringify(resp.body);
    return '~' + s.length;
  }
  return '?';
}

// ── Context lines (title, memo, hosts) ──

function buildContextLines(format, ctx) {
  const title = ctx?.title || '';
  const memo = ctx?.memo || '';
  const hostA = ctx?.hostA || '';
  const hostB = ctx?.hostB || '';
  const memoA = ctx?.memoA || '';
  const memoB = ctx?.memoB || '';
  const lines = [];
  if (title) lines.push(format === 'md' ? `# ${title}` : title);
  if (memo) lines.push(memo);
  const aLabel = memoA ? `A=${hostA} (${memoA})` : `A=${hostA}`;
  const bLabel = memoB ? `B=${hostB} (${memoB})` : `B=${hostB}`;
  lines.push(format === 'md' ? `**Hosts:** ${aLabel} | ${bLabel}` : `Hosts: ${aLabel}  ${bLabel}`);
  if (lines.length) lines.push('');
  return lines;
}

// ── Drift summary (plain text, for copy button in DiffView) ──

/**
 * Build a plain-text drift summary for a single result.
 * @param {object} r - comparison result
 * @param {object} [ctx] - session context {title, memo, hostA, hostB, memoA, memoB}
 */
export function buildDriftSummary(r, ctx) {
  const a = r.response_a, b = r.response_b;
  let lines = buildContextLines('text', ctx);
  lines.push(`DRIFT: ${r.method} ${r.path}`);
  lines.push(`Status: ${statusLabel(a)}/${statusLabel(b)}  Size: ${contentLength(a)}/${contentLength(b)} bytes  Time: ${a.elapsed_ms ?? '?'}/${b.elapsed_ms ?? '?'}ms`);

  // Headers diff
  const hA = a.headers || {}, hB = b.headers || {};
  const allKeys = new Set([...Object.keys(hA), ...Object.keys(hB)]);
  const hDiffs = [];
  for (const k of allKeys) {
    const va = hA[k], vb = hB[k];
    if (va !== vb) {
      const valA = va !== undefined ? JSON.stringify(va) : '(absent)';
      const valB = vb !== undefined ? JSON.stringify(vb) : '(absent)';
      hDiffs.push(`  ${k}: ${valA} -> ${valB}`);
    }
  }
  if (hDiffs.length) {
    lines.push('Headers diff:');
    lines.push(...hDiffs);
  }

  // Body diff
  const sections = parseDiff(r.diff);
  if (sections.length) {
    lines.push('Body diff:');
    for (const sec of sections) {
      for (const e of sec.entries) {
        const pp = prettifyPath(e.path);
        if (e.oldVal !== undefined) {
          lines.push(`  ${pp} (${sec.textLabel}): ${jsonSummary(e.oldVal)} -> ${jsonSummary(e.newVal)}`);
        } else {
          lines.push(`  ${pp} (${sec.textLabel}): ${jsonSummary(e.raw)}`);
        }
      }
    }
  }

  return lines.join('\n');
}

// ── Full markdown (for "Copy as markdown" in ResultDisplay) ──

function fmtHeaders(headers) {
  if (!headers || !Object.keys(headers).length) return '(none)';
  return Object.entries(headers).map(([k, v]) => `${k}: ${v}`).join('\n');
}

function fmtBody(body) {
  if (body == null) return '(empty)';
  return typeof body === 'string' ? body : JSON.stringify(body, null, 2);
}

function buildSideMd(r, side, ctx) {
  const resp = side === 'a' ? r.response_a : r.response_b;
  const memo = side === 'a' ? (ctx?.memoA || '') : (ctx?.memoB || '');
  const label = memo ? `Host ${side.toUpperCase()} (${memo})` : `Host ${side.toUpperCase()}`;
  let md = `### ${label}\n\n`;
  md += `**${r.method}** \`${resp.request_url || r.path}\`\n`;
  md += `**Status:** ${resp.status || 'ERR'} | **Time:** ${resp.elapsed_ms ?? '?'}ms\n\n`;
  md += `#### Request Headers\n\n\`\`\`\n${fmtHeaders(resp.request_headers)}\n\`\`\`\n\n`;
  md += `#### Response Headers\n\n\`\`\`\n${fmtHeaders(resp.headers)}\n\`\`\`\n\n`;
  md += `#### Body\n\n\`\`\`json\n${fmtBody(resp.body)}\n\`\`\`\n`;
  return md;
}

/**
 * Full markdown report for a single comparison result.
 * @param {object} r - comparison result
 * @param {object} [ctx] - session context {title, memo, hostA, hostB, memoA, memoB}
 */
export function buildFullMd(r, ctx) {
  let md = buildContextLines('md', ctx).join('\n');
  md += `## ${r.method} ${r.path}\n\n`;
  md += `**Result:** ${r.has_drift ? 'DRIFT' : 'OK'}\n\n`;

  const sections = parseDiff(r.diff);
  if (sections.length) {
    md += `## Differences\n\n`;
    for (const sec of sections) {
      md += `**${sec.label}**\n\n`;
      for (const e of sec.entries) {
        const pp = prettifyPath(e.path);
        if (e.oldVal !== undefined) {
          md += `- \`${pp}\`: \`${jsonSummary(e.oldVal)}\` \u2192 \`${jsonSummary(e.newVal)}\`\n`;
        } else {
          md += `- \`${pp}\`: \`${jsonSummary(e.raw)}\`\n`;
        }
      }
      md += '\n';
    }
  }

  if (r.ignored_paths && r.ignored_paths.length) {
    md += `**Ignored fields (${r.ignored_paths.length}):** ${r.ignored_paths.map(p => '\`' + prettifyPath(p) + '\`').join(', ')}\n\n`;
  }

  md += buildSideMd(r, 'a', ctx) + '\n' + buildSideMd(r, 'b', ctx);
  return md;
}

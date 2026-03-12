// ── Formatting utilities ──

export function esc(s) { return s.replace(/"/g, '&quot;'); }

export function escHtml(s) { return s == null ? 'null' : String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// Convert dot notation (body.created) to DeepDiff path (root['body']['created'])
// Also accepts raw DeepDiff paths unchanged (starts with root[)
export function toDiffPath(p) {
  if (!p) return p;
  if (p.startsWith("root[")) return p; // already in DeepDiff format
  return "root['" + p.split('.').join("']['") + "']";
}

// Turns root['body']['metadata']['created'] into body.metadata.created
// Turns root['status'] into status
export function prettifyPath(p) {
  if (!p) return p;
  return p.replace(/^root/, '').replace(/\['/g, '.').replace(/']/g, '').replace(/^\./,'');
}

export function relativeTime(isoStr) {
  const date = new Date(isoStr);
  const now = new Date();
  const diffMs = now - date;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  // Older than a day: show MM-DD HH:MM
  return isoStr.slice(5, 10) + ' ' + isoStr.slice(11, 16);
}

export function driftIndicator(s) {
  // s has endpoint_count, drift_count, ok_count
  const total = s.endpoint_count || 0;
  const run = (s.ok_count || 0) + (s.drift_count || 0);
  if (run === 0) return { color: 'var(--text-dim)', symbol: '&#9675;', title: 'not run' };        // empty circle
  if (s.drift_count === 0) return { color: 'var(--green)', symbol: '&#9679;', title: 'all OK' };   // solid green
  const okPct = run > 0 ? (s.ok_count / run) : 0;
  if (okPct >= 0.8) return { color: 'var(--yellow)', symbol: '&#9679;', title: `${s.drift_count} drift` }; // orange/yellow
  return { color: 'var(--red)', symbol: '&#9679;', title: `${s.drift_count} drifts` };              // red
}

// Strip version prefix from operationId: "v2_concealSecret" -> "concealSecret"
export function stripOpIdPrefix(label) {
  if (!label) return '';
  return label.replace(/^(v\d+_|colonel_|account_|guest_)/, '');
}

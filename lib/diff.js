// ── Diff parsing and value summarization ──

// Single source of truth for interpreting deepdiff output.
// Both the HTML renderer (renderDiff) and text exporter (buildDriftSummary) consume this.
// When adding new deepdiff categories or changing labels, update ONLY here.
export const DIFF_CATEGORIES = [
  { key: 'values_changed',          label: 'Values Changed',    textLabel: 'value differs',    kind: 'changed' },
  { key: 'dictionary_item_added',   label: 'Added in B',        textLabel: 'field only in B',  kind: 'added'   },
  { key: 'dictionary_item_removed', label: 'Removed from B',    textLabel: 'field only in A',  kind: 'removed' },
  { key: 'type_changes',            label: 'Type Changes',      textLabel: 'type differs',     kind: 'changed' },
  { key: 'iterable_item_added',     label: 'Items Added in B',  textLabel: 'item only in B',   kind: 'added'   },
  { key: 'iterable_item_removed',   label: 'Items Removed from B', textLabel: 'item only in A', kind: 'removed' },
];

export const DIFF_CAT_KEYS = new Set(DIFF_CATEGORIES.map(c => c.key));

export const SEVERITY_LEVELS = {
  none:       { label: 'No Drift',   color: 'green',  bgClass: 'bg-green/20',  textClass: 'text-green',  order: 0 },
  cosmetic:   { label: 'Cosmetic',   color: 'cyan',   bgClass: 'bg-cyan/20',   textClass: 'text-cyan',   order: 1 },
  structural: { label: 'Structural', color: 'yellow', bgClass: 'bg-yellow/20', textClass: 'text-yellow', order: 2 },
  breaking:   { label: 'Breaking',   color: 'red',    bgClass: 'bg-red/20',    textClass: 'text-red',    order: 3 },
};

// Returns [{category, label, textLabel, kind, entries: [{path, oldVal, newVal, oldType, newType, raw}]}]
export function parseDiff(diff) {
  if (!diff) return [];
  const sections = [];

  for (const cat of DIFF_CATEGORIES) {
    const changes = diff[cat.key];
    if (!changes) continue;
    const entries = [];
    for (const [path, detail] of Object.entries(changes)) {
      if (detail && typeof detail === 'object' && detail.old_value !== undefined) {
        entries.push({ path, oldVal: detail.old_value, newVal: detail.new_value, oldType: detail.old_type, newType: detail.new_type });
      } else {
        entries.push({ path, raw: detail, kind: cat.kind });
      }
    }
    sections.push({ ...cat, entries });
  }

  // Catch-all for unknown deepdiff categories
  for (const [key, changes] of Object.entries(diff)) {
    if (DIFF_CAT_KEYS.has(key)) continue;
    sections.push({ key, label: key, textLabel: key, kind: 'other', entries: [{ path: key, raw: changes }] });
  }
  return sections;
}

export const SUMMARIZE_DEFAULTS = { maxStr: 1024, maxArr: 5, maxKeys: 10, depth: 0, maxDepth: 2 };

export function summarize(val, opts) {
  const o = { ...SUMMARIZE_DEFAULTS, ...opts };
  if (val === null || val === undefined) return val;

  if (typeof val === 'string') {
    if (val.length <= o.maxStr) return val;
    return val.slice(0, o.maxStr) + `... (${val.length} chars total)`;
  }

  if (Array.isArray(val)) {
    if (o.depth >= o.maxDepth) return val.length <= o.maxArr ? val : `[Array: ${val.length} items]`;
    const items = val.slice(0, o.maxArr).map(v => summarize(v, { ...o, depth: o.depth + 1 }));
    if (val.length > o.maxArr) items.push(`... (${val.length - o.maxArr} more, ${val.length} total)`);
    return items;
  }

  if (typeof val === 'object') {
    if (o.depth >= o.maxDepth) {
      const keys = Object.keys(val);
      return keys.length <= o.maxKeys ? val : `{Object: ${keys.length} keys}`;
    }
    const keys = Object.keys(val);
    const result = {};
    const shown = keys.slice(0, o.maxKeys);
    for (const k of shown) result[k] = summarize(val[k], { ...o, depth: o.depth + 1 });
    if (keys.length > o.maxKeys) result[`... (${keys.length - o.maxKeys} more keys)`] = `${keys.length} keys total`;
    return result;
  }

  return val;
}

// Stringify with summarization. Use everywhere instead of raw JSON.stringify for display.
export function jsonSummary(val, indent) {
  return JSON.stringify(summarize(val), null, indent);
}

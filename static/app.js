// ── State ──
let epId = 0;
let currentFilter = 'all';
const resultStore = {};  // epId -> full compare result object

// ── Document/Session tracking ──
let currentDocumentId = null;   // set after first save
let currentSessionNumber = 0;   // incremented on each save
let lastSavedStateHash = null;  // fingerprint of last saved state for dirty detection

// ── State fingerprinting for dirty detection ──
function stateFingerprint(state) {
  // Strip volatile fields that change every save but don't represent user changes
  const {savedAt, sessionNumber, version, ...rest} = state;
  const raw = JSON.stringify(rest, Object.keys(rest).sort());
  // Simple djb2 hash to string - fast, good enough for change detection
  let hash = 5381;
  for (let i = 0; i < raw.length; i++) {
    hash = ((hash << 5) + hash + raw.charCodeAt(i)) & 0xffffffff;
  }
  return hash.toString(36);
}

// ── Time formatting ──
function relativeTime(isoStr) {
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

// ── Drift status for sidebar ──
function driftIndicator(s) {
  // s has endpoint_count, drift_count, ok_count
  const total = s.endpoint_count || 0;
  const run = (s.ok_count || 0) + (s.drift_count || 0);
  if (run === 0) return { color: 'var(--text-dim)', symbol: '&#9675;', title: 'not run' };        // empty circle
  if (s.drift_count === 0) return { color: 'var(--green)', symbol: '&#9679;', title: 'all OK' };   // solid green
  const okPct = run > 0 ? (s.ok_count / run) : 0;
  if (okPct >= 0.8) return { color: 'var(--yellow)', symbol: '&#9679;', title: `${s.drift_count} drift` }; // orange/yellow
  return { color: 'var(--red)', symbol: '&#9679;', title: `${s.drift_count} drifts` };              // red
}

// ── Ignore paths ──
function toggleIgnorePanel() {
  document.getElementById('ignoreBody').classList.toggle('open');
  document.getElementById('ignoreChev').classList.toggle('open');
}
// Convert dot notation (body.created) to DeepDiff path (root['body']['created'])
// Also accepts raw DeepDiff paths unchanged (starts with root[)
function toDiffPath(p) {
  if (!p) return p;
  if (p.startsWith("root[")) return p; // already in DeepDiff format
  return "root['" + p.split('.').join("']['") + "']";
}
function getRawIgnoreLines() {
  const raw = document.getElementById('ignorePaths').value.trim();
  if (!raw) return [];
  return raw.split('\n').map(l => l.trim()).filter(Boolean);
}
function getIgnorePaths() {
  return getRawIgnoreLines().map(toDiffPath);
}
function updateIgnoreCount() {
  const n = getIgnorePaths().length;
  document.getElementById('ignoreCount').textContent = n > 0 ? `(${n} custom)` : '';
}
let serverDefaultsCache = null;
function toggleServerDefaults() {
  const el = document.getElementById('serverDefaults');
  const visible = el.style.display !== 'none';
  if (visible) { el.style.display = 'none'; return; }
  if (serverDefaultsCache) {
    el.textContent = serverDefaultsCache.map(prettifyPath).join('\n');
    el.style.display = 'block';
    return;
  }
  el.textContent = 'Loading...';
  el.style.display = 'block';
  fetch('/api/config').then(r => r.json()).then(cfg => {
    serverDefaultsCache = cfg.default_ignore || [];
    el.textContent = serverDefaultsCache.map(prettifyPath).join('\n');
  }).catch(() => { el.textContent = '(could not load)'; });
}
// Live-update count
document.addEventListener('DOMContentLoaded', () => {
  const ta = document.getElementById('ignorePaths');
  if (ta) ta.addEventListener('input', updateIgnoreCount);

  // Persist title changes on blur and refresh sidebar sort order
  const titleInput = document.getElementById('sessionTitle');
  if (titleInput) {
    let lastSyncedTitle = '';
    titleInput.addEventListener('focus', () => { lastSyncedTitle = titleInput.value; });
    titleInput.addEventListener('blur', async () => {
      const newTitle = titleInput.value.trim();
      if (!currentDocumentId || newTitle === lastSyncedTitle) return;
      lastSyncedTitle = newTitle;
      try {
        await fetch(`/api/documents/${currentDocumentId}`, {
          method: 'PATCH',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ title: newTitle || 'Untitled' }),
        });
        refreshSidebar();
      } catch (err) { /* silent */ }
    });
  }
});

// ── Path display helper ──
// Turns root['body']['metadata']['created'] into body.metadata.created
// Turns root['status'] into status
function prettifyPath(p) {
  if (!p) return p;
  return p.replace(/^root/, '').replace(/\['/g, '.').replace(/']/g, '').replace(/^\./,'');
}

const CT = {
  query: { value: 'query', label: 'QUERY', cls: 'query', placeholder: 'key=val&key2=val2 (query params)' },
  form:  { value: 'application/x-www-form-urlencoded', label: 'FORM', cls: 'form', placeholder: 'key=val&key2=val2 (form body)' },
  json:  { value: 'application/json', label: 'JSON', cls: 'json', placeholder: '{"key":"val"} (JSON body)' },
};
const CT_CYCLE = ['query', 'form', 'json'];
function ctInfo(v) { return v === 'application/json' ? CT.json : v === 'application/x-www-form-urlencoded' ? CT.form : CT.query; }

// ── Field schemas stored per-card ──
const cardFields = {};  // epId -> {fields, query_fields, path_fields}

// Strip version prefix from operationId: "v2_concealSecret" -> "concealSecret"
function stripOpIdPrefix(label) {
  if (!label) return '';
  return label.replace(/^(v\d+_|colonel_|account_|guest_)/, '');
}

// ── Endpoint card ──
function addEndpoint(method='GET', label='', path='', body='', contentType='query', group='', fields=null, queryFields=null, pathFields=null) {
  const id = epId++;
  const area = document.getElementById('endpointsArea');
  const card = document.createElement('div');
  card.className = 'ep-card';
  card.id = `ep-${id}`;
  card.dataset.testId = id;
  card.dataset.test = 'ep-card';
  card.dataset.contentType = contentType;
  card.dataset.group = group;
  card.dataset.state = 'idle';
  const ct = ctInfo(contentType);

  const hasBodyFields = fields && fields.length > 0;
  const hasPathParams = pathFields && pathFields.length > 0;
  const hasQueryFields = queryFields && queryFields.length > 0;
  const hasAnyFields = hasBodyFields || hasPathParams || hasQueryFields;

  // POST/PUT/PATCH: default to fields mode when fields exist
  // GET/DELETE: show fields panel if path params exist, but body input stays for query
  const isWriteMethod = ['POST','PUT','PATCH'].includes(method);
  const showFieldsByDefault = hasAnyFields && (isWriteMethod || hasPathParams);
  card.dataset.fieldsMode = showFieldsByDefault ? 'on' : 'off';

  // Store field schemas
  if (hasAnyFields) {
    cardFields[id] = { fields: fields || [], query_fields: queryFields || [], path_fields: pathFields || [] };
  }

  // Label: non-editable dim tag if from OpenAPI, editable input if manual
  const fromSpec = hasAnyFields || label.includes('_');
  const shortLabel = stripOpIdPrefix(label);

  // Determine whether kv-pairs UI should be shown initially
  const useKvPairs = ct !== CT.json && !(showFieldsByDefault && hasBodyFields);
  // body-input: hidden if kv-pairs shown OR if schema fields mode hides it
  const hideBodyInput = useKvPairs || (showFieldsByDefault && hasBodyFields);
  const bodyInputStyle = hideBodyInput ? ' style="display:none"' : (ct.cls === 'json' ? ' style="border-color:var(--accent)"' : '');

  card.innerHTML = `
    <div class="ep-config" data-test="ep-config">
      <select data-field="method" data-test="ep-method" name="method-${id}">
        <option ${method==='GET'?'selected':''}>GET</option>
        <option ${method==='POST'?'selected':''}>POST</option>
        <option ${method==='PUT'?'selected':''}>PUT</option>
        <option ${method==='DELETE'?'selected':''}>DELETE</option>
      </select>
      <input type="text" class="path-input" data-field="path" data-test="ep-path" name="path-${id}" placeholder="/api/v1/status" value="${esc(path)}">
      <input type="text" class="body-input" data-field="body" data-test="ep-body" name="body-${id}" placeholder="${ct.placeholder}" value="${esc(body)}"${bodyInputStyle}>
      <span class="ct-toggle ${ct.cls}" data-test="ep-ct-toggle" onclick="toggleCt(this)" title="query / form / json">${ct.label}</span>
      ${hasAnyFields ? `<span class="ep-fields-toggle${showFieldsByDefault?' active':''}" data-test="ep-fields-toggle" onclick="toggleFieldsMode(${id})" title="Toggle per-field inputs">FIELDS</span>` : ''}
      ${fromSpec
        ? `<span class="group-tag" data-test="ep-opid" title="${esc(label)}">${escHtml(shortLabel)}</span><input type="hidden" data-field="label" name="label-${id}" value="${esc(label)}">`
        : `<input type="text" class="label-input" data-field="label" data-test="ep-label" name="label-${id}" placeholder="label" value="${esc(label)}">`}
      ${group ? `<span class="group-tag" data-test="ep-group-tag">${escHtml(group)}</span>` : ''}
      <button class="ep-run-btn" data-test="ep-run" onclick="runOne(${id})" title="Run this endpoint">run</button>
      <button class="remove-btn" data-test="ep-remove" onclick="removeEndpoint(${id})" title="Remove">&times;</button>
    </div>
    <div class="kv-pairs" data-test="ep-kv" id="ep-kv-${id}"${useKvPairs ? '' : ' style="display:none"'}></div>
    <div class="ep-fields" data-test="ep-fields" id="ep-fields-${id}"${showFieldsByDefault?'':' style="display:none"'}></div>
    <div class="ep-result" data-test="ep-result" id="ep-result-${id}" style="display:none"></div>
  `;
  area.appendChild(card);
  if (hasAnyFields) renderFieldInputs(id);
  if (useKvPairs) renderKvPairs(id);
  updateTally();
}

function renderFieldInputs(id) {
  const info = cardFields[id];
  if (!info) return;
  const container = document.getElementById(`ep-fields-${id}`);
  let html = '';

  function renderFieldGroup(fields, groupLabel) {
    if (!fields || !fields.length) return '';
    let h = `<div style="font-size:0.65em;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-dim);margin:6px 0 4px">${groupLabel}</div>`;
    for (const f of fields) {
      const indent = (f.path.match(/\./g) || []).length;
      const indentCls = indent > 0 ? ` field-indent-${Math.min(indent, 2)}` : '';
      if (f.nested) {
        h += `<div class="field-row${indentCls}"><span class="field-name nested-parent">${escHtml(f.path)}</span><span class="field-type">object</span></div>`;
        continue;
      }
      const val = f.const != null ? f.const : (f.example != null ? f.example : '');
      const inputId = `fld-${id}-${f.path.replace(/\./g, '-')}`;
      let inputHtml;
      if (f.const != null) {
        inputHtml = `<span class="field-const">${escHtml(String(f.const))}</span><input type="hidden" id="${inputId}" data-field-path="${escHtml(f.path)}" value="${esc(String(f.const))}">`;
      } else if (f.enum) {
        inputHtml = `<select id="${inputId}" data-field-path="${escHtml(f.path)}">${f.enum.map(e => `<option${String(e)===String(val)?' selected':''}>${escHtml(String(e))}</option>`).join('')}</select>`;
      } else if (f.type === 'boolean') {
        inputHtml = `<select id="${inputId}" data-field-path="${escHtml(f.path)}"><option value="true"${val===true||val==='true'?' selected':''}>true</option><option value="false"${val===false||val==='false'?' selected':''}>false</option></select>`;
      } else {
        const inputType = (f.type === 'integer' || f.type === 'number') ? 'number' : 'text';
        inputHtml = `<input type="${inputType}" id="${inputId}" data-field-path="${escHtml(f.path)}" value="${esc(String(val))}"${f.min!=null?` min="${f.min}"`:''}${f.max!=null?` max="${f.max}"`:''}${f.description?` title="${esc(f.description)}"`:''}placeholder="${escHtml(f.type)}">`;
      }
      h += `<div class="field-row${indentCls}">
        <span class="field-name">${f.required?'<span class="req-dot" title="required"></span>':''}${escHtml(f.name)}</span>
        <span class="field-type">${escHtml(f.type)}</span>
        ${inputHtml}
      </div>`;
    }
    return h;
  }

  html += renderFieldGroup(info.path_fields, 'Path Parameters');
  html += renderFieldGroup(info.query_fields, 'Query Parameters');
  html += renderFieldGroup(info.fields, 'Request Body');
  container.innerHTML = html;
}

function toggleFieldsMode(id) {
  const card = document.getElementById(`ep-${id}`);
  const fieldsDiv = document.getElementById(`ep-fields-${id}`);
  const kvContainer = document.getElementById(`ep-kv-${id}`);
  const toggle = card.querySelector('.ep-fields-toggle');
  const bodyInput = card.querySelector('[data-field="body"]');
  const isOn = card.dataset.fieldsMode === 'on';
  const hasBodyFields = cardFields[id]?.fields?.length > 0;
  const ct = ctInfo(card.dataset.contentType);

  if (isOn) {
    // Switching OFF fields mode: assemble body from fields, hide fields
    card.dataset.fieldsMode = 'off';
    toggle.classList.remove('active');
    fieldsDiv.style.display = 'none';
    // Assemble body from current field values (only overwrites if body fields exist)
    if (hasBodyFields) {
      bodyInput.value = assembleBodyFromFields(id, card.dataset.contentType);
    }
    // Show kv-pairs for form/query, or body-input for json
    if (ct !== CT.json && kvContainer) {
      kvContainer.style.display = '';
      bodyInput.style.display = 'none';
      renderKvPairs(id);
    } else {
      bodyInput.style.display = '';
      if (kvContainer) kvContainer.style.display = 'none';
    }
  } else {
    // Switching ON fields mode: show fields, hide body and kv-pairs if body fields exist
    card.dataset.fieldsMode = 'on';
    toggle.classList.add('active');
    fieldsDiv.style.display = 'block';
    if (hasBodyFields) {
      bodyInput.style.display = 'none';
      // Sync kv values back to body before hiding
      if (kvContainer && kvContainer.style.display !== 'none') {
        syncKvToBody(id);
      }
      if (kvContainer) kvContainer.style.display = 'none';
    }
  }
}

function assembleBodyFromFields(id, contentType) {
  const info = cardFields[id];
  if (!info || !info.fields.length) return '';
  const fieldsDiv = document.getElementById(`ep-fields-${id}`);
  const inputs = fieldsDiv.querySelectorAll('[data-field-path]');
  // Build nested object from dot-paths
  const obj = {};
  inputs.forEach(inp => {
    const path = inp.dataset.fieldPath;
    const val = inp.value;
    if (val === '') return;
    setNestedValue(obj, path, val);
  });
  if (contentType === 'application/json') {
    return JSON.stringify(obj, null, 2);
  } else {
    // Flatten to key=val pairs
    const flat = flattenObj(obj);
    return Object.entries(flat).map(([k,v]) => `${k}=${v}`).join('&');
  }
}

function setNestedValue(obj, path, val) {
  const parts = path.split('.');
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (!(parts[i] in cur)) cur[parts[i]] = {};
    cur = cur[parts[i]];
  }
  // Try to parse typed values
  if (val === 'true') val = true;
  else if (val === 'false') val = false;
  else if (!isNaN(val) && val !== '') val = Number(val);
  cur[parts[parts.length - 1]] = val;
}

function flattenObj(obj, prefix = '') {
  const result = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      Object.assign(result, flattenObj(v, key));
    } else {
      result[key] = v;
    }
  }
  return result;
}

// ── Key/Value pair rows for form/query params ──
function parseKvString(str) {
  if (!str || !str.trim()) return [];
  return str.split('&').map(pair => {
    const eq = pair.indexOf('=');
    if (eq === -1) return { key: pair, val: '' };
    return { key: decodeURIComponent(pair.slice(0, eq)), val: decodeURIComponent(pair.slice(eq + 1)) };
  }).filter(p => p.key !== '');
}
function renderKvPairs(id) {
  const card = document.getElementById(`ep-${id}`);
  const container = document.getElementById(`ep-kv-${id}`);
  if (!container) return;
  const bodyInput = card.querySelector('[data-field="body"]');
  const pairs = parseKvString(bodyInput.value);
  const ctKey = ctInfo(card.dataset.contentType) === CT.query ? 'query' : 'form';
  const headerLabel = ctKey === 'query' ? 'Query Parameters' : 'Form Parameters';
  let html = `<div class="kv-header">${headerLabel}</div>`;
  if (pairs.length === 0) {
    html += kvRowHtml(id, '', '');
  } else {
    for (const p of pairs) html += kvRowHtml(id, p.key, p.val);
  }
  html += `<button class="kv-add-btn" onclick="addKvRow(${id})">+ Add</button>`;
  container.innerHTML = html;
}
function kvRowHtml(id, key, val) {
  return `<div class="kv-row"><input type="text" class="kv-key" placeholder="key" value="${esc(key)}"><span class="kv-sep">=</span><input type="text" class="kv-val" placeholder="value" value="${esc(val)}"><button class="kv-remove" onclick="removeKvRow(this, ${id})" title="Remove">&times;</button></div>`;
}
function addKvRow(id) {
  const container = document.getElementById(`ep-kv-${id}`);
  if (!container) return;
  const addBtn = container.querySelector('.kv-add-btn');
  const row = document.createElement('div');
  row.className = 'kv-row';
  row.innerHTML = `<input type="text" class="kv-key" placeholder="key" value=""><span class="kv-sep">=</span><input type="text" class="kv-val" placeholder="value" value=""><button class="kv-remove" onclick="removeKvRow(this, ${id})" title="Remove">&times;</button>`;
  container.insertBefore(row, addBtn);
}
function removeKvRow(btn, id) {
  const container = document.getElementById(`ep-kv-${id}`);
  if (!container) return;
  btn.closest('.kv-row').remove();
  if (!container.querySelector('.kv-row')) {
    const addBtn = container.querySelector('.kv-add-btn');
    const r = document.createElement('div'); r.className = 'kv-row';
    r.innerHTML = `<input type="text" class="kv-key" placeholder="key" value=""><span class="kv-sep">=</span><input type="text" class="kv-val" placeholder="value" value=""><button class="kv-remove" onclick="removeKvRow(this, ${id})" title="Remove">&times;</button>`;
    container.insertBefore(r, addBtn);
  }
}
function assembleKvPairs(id) {
  const container = document.getElementById(`ep-kv-${id}`);
  if (!container) return '';
  const pairs = [];
  container.querySelectorAll('.kv-row').forEach(row => {
    const key = row.querySelector('.kv-key').value.trim();
    const val = row.querySelector('.kv-val').value;
    if (key) pairs.push(encodeURIComponent(key) + '=' + encodeURIComponent(val));
  });
  return pairs.join('&');
}
function syncKvToBody(id) {
  const card = document.getElementById(`ep-${id}`);
  if (!card) return;
  const bodyInput = card.querySelector('[data-field="body"]');
  if (bodyInput) bodyInput.value = assembleKvPairs(id);
}
function shouldShowKvPairs(card, id) {
  const ct = ctInfo(card.dataset.contentType);
  if (ct === CT.json) return false;
  if (card.dataset.fieldsMode === 'on' && cardFields[id]?.fields?.length > 0) return false;
  return true;
}

function removeEndpoint(id) {
  const el = document.getElementById(`ep-${id}`);
  if (el) el.remove();
  updateTally();
}

function toggleCt(el) {
  const card = el.closest('.ep-card');
  const id = parseInt(card.id.replace('ep-', ''));
  const bodyInput = card.querySelector('[data-field="body"]');
  const kvContainer = document.getElementById(`ep-kv-${id}`);
  const cur = ctInfo(card.dataset.contentType);
  const idx = CT_CYCLE.indexOf(cur === CT.query ? 'query' : cur === CT.form ? 'form' : 'json');
  const next = CT[CT_CYCLE[(idx + 1) % CT_CYCLE.length]];

  // When leaving kv-pairs mode (form/query -> json), sync kv values back to body input
  const wasKv = cur !== CT.json && kvContainer && kvContainer.style.display !== 'none';
  if (wasKv) {
    syncKvToBody(id);
  }

  card.dataset.contentType = next.value;
  el.textContent = next.label;
  el.className = 'ct-toggle ' + next.cls;
  bodyInput.placeholder = next.placeholder;

  // Determine visibility: kv-pairs vs body-input
  const useKv = shouldShowKvPairs(card, id);
  if (kvContainer) {
    if (useKv) {
      kvContainer.style.display = '';
      bodyInput.style.display = 'none';
      bodyInput.style.borderColor = '';
      renderKvPairs(id);
    } else {
      kvContainer.style.display = 'none';
      // Only show body-input if not hidden by schema fields mode
      const hiddenByFields = card.dataset.fieldsMode === 'on' && cardFields[id]?.fields?.length > 0;
      bodyInput.style.display = hiddenByFields ? 'none' : '';
      bodyInput.style.borderColor = next.cls === 'json' ? 'var(--accent)' : '';
    }
  } else {
    bodyInput.style.display = '';
    bodyInput.style.borderColor = next.cls === 'json' ? 'var(--accent)' : '';
  }
}

function esc(s) { return s.replace(/"/g, '&quot;'); }
function escHtml(s) { return s == null ? 'null' : String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// Return typed value, falling back to placeholder (which holds the env var default)
function effectiveHost(id) { const el = document.getElementById(id); return el.value.trim() || el.placeholder || ''; }

async function testHost(side) {
  const btn = document.getElementById(`testBtn${side}`);
  const host = effectiveHost(`host${side}`);
  const auth = document.getElementById(`auth${side}`).value.trim();
  btn.textContent = '...';
  btn.className = 'host-test-btn';
  try {
    const resp = await fetch('/api/test-host', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ host, auth }),
    });
    const data = await resp.json();
    if (data.ok) {
      btn.textContent = `${data.status} ${data.elapsed_ms}ms`;
      btn.className = 'host-test-btn ok';
    } else {
      btn.textContent = data.error ? 'Error' : `${data.status}`;
      btn.className = 'host-test-btn fail';
      btn.title = data.error || '';
    }
  } catch (err) {
    btn.textContent = 'Error';
    btn.className = 'host-test-btn fail';
    btn.title = err.message;
  }
  setTimeout(() => { btn.textContent = 'Test'; btn.className = 'host-test-btn'; btn.title = ''; }, 5000);
}

function clearRuns() {
  document.querySelectorAll('.ep-card').forEach(card => {
    card.dataset.state = 'idle';
    card.className = 'ep-card';
    const resultDiv = card.querySelector('.ep-result');
    if (resultDiv) { resultDiv.style.display = 'none'; resultDiv.innerHTML = ''; }
  });
  // Clear result store
  for (const k of Object.keys(resultStore)) delete resultStore[k];
  // Reset filter
  filterCards('all');
  updateTally();
}

function readEndpoint(card) {
  const id = parseInt(card.id.replace('ep-', ''));
  let body = card.querySelector('[data-field="body"]').value || null;
  // If in fields mode with body fields defined, assemble body from field inputs.
  // Otherwise keep the body textarea value (covers path-params-only endpoints
  // where the user enters form/json body directly in the textarea).
  if (card.dataset.fieldsMode === 'on' && cardFields[id]?.fields?.length > 0) {
    body = assembleBodyFromFields(id, card.dataset.contentType) || null;
  }
  // If kv-pairs are visible, assemble body from the key/value rows
  const kvContainer = document.getElementById(`ep-kv-${id}`);
  if (kvContainer && kvContainer.style.display !== 'none') {
    body = assembleKvPairs(id) || null;
  }

  // Substitute path template variables from field inputs
  let path = card.querySelector('[data-field="path"]').value;
  const info = cardFields[id];
  if (info && info.path_fields.length) {
    const fieldsDiv = document.getElementById(`ep-fields-${id}`);
    for (const pf of info.path_fields) {
      const inp = fieldsDiv ? fieldsDiv.querySelector(`[data-field-path="${pf.path}"]`) : null;
      const val = inp ? inp.value : '';
      path = path.replace(`{${pf.name}}`, encodeURIComponent(val));
    }
  }

  return {
    method: card.querySelector('[data-field="method"]').value,
    label: card.querySelector('[data-field="label"]').value,
    path: path,
    body: body,
    content_type: card.dataset.contentType || 'query',
    group: card.dataset.group || null,
  };
}

// ── Group dividers ──
function insertGroupDividers() {
  document.querySelectorAll('#endpointsArea .group-divider').forEach(d => d.remove());
  const cards = document.querySelectorAll('#endpointsArea .ep-card');
  let lastGroup = null;
  cards.forEach(card => {
    const g = card.dataset.group;
    if (g && g !== lastGroup) {
      const count = [...cards].filter(c => c.dataset.group === g).length;
      const div = document.createElement('div');
      div.className = 'group-divider';
      div.dataset.group = g;
      div.dataset.test = 'group-divider';
      div.dataset.testGroup = g;
      div.innerHTML = `<span class="group-name" data-test="group-name">${escHtml(g)}</span>
        <span class="group-count" data-test="group-count">${count}</span>
        <span class="group-tally" data-test="group-tally" id="gtally-${g.replace(/\W/g,'_')}"></span>
        <button class="group-run-btn" data-test="group-run" onclick="runGroup('${esc(g)}')">run group</button>`;
      card.parentElement.insertBefore(div, card);
    }
    lastGroup = g;
  });
}

// ── Tally ──
function updateTally() {
  const cards = document.querySelectorAll('.ep-card');
  const total = cards.length;
  let ran = 0, drifts = 0, ok = 0;
  cards.forEach(c => {
    const s = c.dataset.state;
    if (s === 'done-drift') { ran++; drifts++; }
    else if (s === 'done-ok') { ran++; ok++; }
    else if (s === 'running') { ran++; }
  });

  const tally = document.getElementById('tally');
  if (ran === 0) {
    tally.innerHTML = `<span class="t-dim">${total} endpoint${total !== 1 ? 's' : ''}</span>`;
  } else {
    tally.innerHTML = `<span class="t-drift">${drifts} drift</span> <span class="t-ok">${ok} ok</span> <span class="t-dim">(${ran}/${total})</span>`;
  }

  // Show filter pills once there are results
  document.getElementById('filterPills').style.display = ran > 0 ? 'flex' : 'none';

  // Update group tallies
  const groups = new Map();
  cards.forEach(c => {
    const g = c.dataset.group;
    if (!g) return;
    if (!groups.has(g)) groups.set(g, { total: 0, drifts: 0, ok: 0 });
    const gs = groups.get(g);
    gs.total++;
    if (c.dataset.state === 'done-drift') gs.drifts++;
    else if (c.dataset.state === 'done-ok') gs.ok++;
  });
  groups.forEach((gs, g) => {
    const el = document.getElementById(`gtally-${g.replace(/\W/g,'_')}`);
    if (!el) return;
    if (gs.drifts + gs.ok === 0) { el.textContent = ''; return; }
    el.innerHTML = gs.drifts
      ? `<span style="color:var(--red)">${gs.drifts} drift</span>`
      : `<span style="color:var(--green)">all ok</span>`;
  });
}

// ── Run single endpoint ──
async function runOne(id) {
  const card = document.getElementById(`ep-${id}`);
  if (!card) return;
  const ep = readEndpoint(card);
  const hostA = effectiveHost('hostA');
  const hostB = effectiveHost('hostB');
  const authA = document.getElementById('authA').value || null;
  const authB = document.getElementById('authB').value || null;

  // Set running state
  card.dataset.state = 'running';
  card.className = 'ep-card state-running';
  const resultDiv = document.getElementById(`ep-result-${id}`);
  resultDiv.style.display = 'block';
  resultDiv.innerHTML = `<div class="ep-result-header" data-test="result-header"><span class="spinner" data-test="result-spinner"></span> <span style="color:var(--accent);font-size:0.85em" data-test="result-running-label">Running...</span></div>`;
  updateTally();

  try {
    const resp = await fetch('/api/compare', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        label: ep.label || ep.path,
        method: ep.method,
        path: ep.path,
        body: ep.body,
        content_type: ep.content_type,
        group: ep.group,
        host_a: hostA,
        host_b: hostB,
        auth_a: authA,
        auth_b: authB,
        ignore_paths: getIgnorePaths().length ? getIgnorePaths() : null,
      }),
    });
    const r = await resp.json();
    // Attach request body/content_type from the endpoint config so the result
    // renderer can display what was actually sent (the backend doesn't echo these).
    r.request_body = ep.body;
    r.request_content_type = ep.content_type;
    card.dataset.state = r.has_drift ? 'done-drift' : 'done-ok';
    card.className = `ep-card state-${r.has_drift ? 'drift' : 'ok'}`;
    renderResultInCard(id, r);
  } catch (err) {
    card.dataset.state = 'done-drift';
    card.className = 'ep-card state-drift';
    resultDiv.innerHTML = `<div class="ep-result-header" data-test="result-header"><span class="ep-result-badge badge-drift" data-test="result-badge" data-test-drift="true">ERR</span> <span data-test="result-error">${escHtml(err.message)}</span></div>`;
  }
  updateTally();
}

function contentLength(resp) {
  if (!resp || !resp.headers) return '?';
  const cl = resp.headers['content-length'] || resp.headers['Content-Length'];
  if (cl) return cl;
  // Fallback: estimate from body
  if (resp.body != null) {
    const s = typeof resp.body === 'string' ? resp.body : JSON.stringify(resp.body);
    return '~' + s.length;
  }
  return '?';
}

function statusLabel(resp) {
  return resp.status != null ? resp.status : 'ERR';
}

// ── Value summarization for display ──
// Structurally reduces large values so they stay scannable.
// - Strings: truncate to maxStr chars
// - Arrays: show first maxArr elements, append "(N more)"
// - Objects: show first maxKeys keys, append "(N more keys)"
// - Recurses one level deep for nested structures.
// Returns a new value safe for JSON.stringify.
const SUMMARIZE_DEFAULTS = { maxStr: 1024, maxArr: 5, maxKeys: 10, depth: 0, maxDepth: 2 };

function summarize(val, opts) {
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
function jsonSummary(val, indent) {
  return JSON.stringify(summarize(val), null, indent);
}

// ── Shared diff model ──
// Single source of truth for interpreting deepdiff output.
// Both the HTML renderer (renderDiff) and text exporter (buildDriftSummary) consume this.
// When adding new deepdiff categories or changing labels, update ONLY here.
const DIFF_CATEGORIES = [
  { key: 'values_changed',          label: 'Values Changed',    textLabel: 'value differs',    kind: 'changed' },
  { key: 'dictionary_item_added',   label: 'Added in B',        textLabel: 'field only in B',  kind: 'added'   },
  { key: 'dictionary_item_removed', label: 'Removed from B',    textLabel: 'field only in A',  kind: 'removed' },
  { key: 'type_changes',            label: 'Type Changes',      textLabel: 'type differs',     kind: 'changed' },
  { key: 'iterable_item_added',     label: 'Items Added in B',  textLabel: 'item only in B',   kind: 'added'   },
  { key: 'iterable_item_removed',   label: 'Items Removed from B', textLabel: 'item only in A', kind: 'removed' },
];
const DIFF_CAT_KEYS = new Set(DIFF_CATEGORIES.map(c => c.key));

// Returns [{category, label, textLabel, kind, entries: [{path, oldVal, newVal, oldType, newType, raw}]}]
function parseDiff(diff) {
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

// Context block for copy outputs (summary + full result)
function buildContextLines(format) {
  const title = document.getElementById('sessionTitle').value;
  const memo = document.getElementById('sessionMemo').value;
  const hostA = effectiveHost('hostA');
  const hostB = effectiveHost('hostB');
  const memoA = document.getElementById('memoA').value;
  const memoB = document.getElementById('memoB').value;
  const lines = [];
  if (title) lines.push(format === 'md' ? `# ${title}` : title);
  if (memo) lines.push(memo);
  const aLabel = memoA ? `A=${hostA} (${memoA})` : `A=${hostA}`;
  const bLabel = memoB ? `B=${hostB} (${memoB})` : `B=${hostB}`;
  lines.push(format === 'md' ? `**Hosts:** ${aLabel} | ${bLabel}` : `Hosts: ${aLabel}  ${bLabel}`);
  if (lines.length) lines.push('');
  return lines;
}

function buildDriftSummary(r) {
  const a = r.response_a, b = r.response_b;
  let lines = buildContextLines('text');
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

  // Body diff - uses shared DIFF_CATEGORIES
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

  // Ignored fields
  if (r.ignored_paths && r.ignored_paths.length) {
    lines.push(`Ignored (${r.ignored_paths.length}): ${r.ignored_paths.map(prettifyPath).join(', ')}`);
  }
  return lines.join('\n');
}

function copyDriftSummary(btn, id) {
  const r = resultStore[id];
  const data = r && r.has_drift ? buildDriftSummary(r) : '';
  navigator.clipboard.writeText(data).then(() => {
    btn.textContent = 'Copied';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'Copy summary'; btn.classList.remove('copied'); }, 1500);
  });
}

function renderResultInCard(id, r) {
  resultStore[id] = r;
  const resultDiv = document.getElementById(`ep-result-${id}`);
  const msA = r.response_a.elapsed_ms != null ? r.response_a.elapsed_ms : null;
  const msB = r.response_b.elapsed_ms != null ? r.response_b.elapsed_ms : null;
  const statusA = statusLabel(r.response_a);
  const statusB = statusLabel(r.response_b);
  const clA = contentLength(r.response_a);
  const clB = contentLength(r.response_b);

  const metaStatus = `${statusA}/${statusB}`;
  const metaSize = `${clA}/${clB} bytes`;
  const metaTiming = `${msA ?? '?'}/${msB ?? '?'}ms`;

  // Pre-compute request body display (null when no body was sent)
  const reqBodyFmt = formatRequestBody(r.request_body, r.request_content_type);

  resultDiv.style.display = 'block';
  resultDiv.innerHTML = `
    <div class="ep-result-header" data-test="result-header" onclick="toggleResultBody('rb-${id}','rc-${id}')">
      <span class="chevron" id="rc-${id}" data-test="result-chevron">&#9654;</span>
      <span class="ep-result-badge ${r.has_drift ? 'badge-drift' : 'badge-ok'}" data-test="result-badge" data-test-drift="${r.has_drift}">${r.has_drift ? 'DRIFT' : 'OK'}</span>
      <span class="result-meta" data-test="result-meta">${escHtml(metaStatus)} ${escHtml(metaSize)}</span>
      <span class="ep-result-timing" data-test="result-timing">${escHtml(metaTiming)}</span>
    </div>
    <div class="ep-result-body" data-test="result-body" id="rb-${id}" data-drift-summary="${r.has_drift ? escHtml(buildDriftSummary(r)) : ''}">
      ${renderDiff(r, id)}
      <div class="side-by-side" data-test="result-side-by-side">
        <div class="has-copy" data-test="result-response-a">
          <button class="inline-copy" onclick="inlineCopy(this,${id},'resp_a')">copy</button>
          <div class="side-label">Host A (${r.response_a.status || 'ERR'})</div>
          <div class="side-json" data-test="result-json-a">${escHtml(jsonSummary(r.response_a.body, 2))}</div>
        </div>
        <div class="has-copy" data-test="result-response-b">
          <button class="inline-copy" onclick="inlineCopy(this,${id},'resp_b')">copy</button>
          <div class="side-label">Host B (${r.response_b.status || 'ERR'})</div>
          <div class="side-json" data-test="result-json-b">${escHtml(jsonSummary(r.response_b.body, 2))}</div>
        </div>
      </div>
      <div class="toggles-row">
        <button class="raw-toggle" data-test="result-raw-toggle" onclick="toggleRaw('raw-${id}')">Show raw diff JSON</button>
        ${reqBodyFmt ? `<button class="raw-toggle" onclick="toggleRaw('req-body-${id}')">Show request body</button>` : ''}
        <button class="raw-toggle" onclick="toggleRaw('req-headers-${id}')">Show request headers</button>
        <button class="raw-toggle" onclick="toggleRaw('resp-headers-${id}')">Show response headers</button>
        <div class="copy-menu">
          <button class="raw-toggle" onclick="toggleCopyMenu(${id})">Copy as...</button>
          <div class="copy-menu-items" id="copy-menu-${id}">
            <button onclick="copyResultMd(${id},'full')">Full result (markdown)</button>
            <button onclick="copyResultJson(${id},'full')">Full result (json)</button>
          </div>
        </div>
      </div>
      <div class="has-copy raw-json" data-test="result-raw-json" id="raw-${id}"><button class="inline-copy" onclick="inlineCopy(this,${id},'raw_diff')">copy</button>${escHtml(JSON.stringify(r.diff, null, 2))}</div>
      ${reqBodyFmt ? `<div class="has-copy raw-headers" id="req-body-${id}" data-test="result-req-body"><button class="inline-copy" onclick="inlineCopy(this,${id},'req_body')">copy</button><div class="side-label">Request Body <span style="font-size:0.85em;color:var(--text-dim);text-transform:none;letter-spacing:0;">(${escHtml(r.request_content_type || 'query')})</span></div><div class="side-json">${reqBodyFmt.html}</div></div>` : ''}
      <div class="raw-headers" id="req-headers-${id}"><div class="side-by-side"><div class="has-copy"><button class="inline-copy" onclick="inlineCopy(this,${id},'req_a')">copy</button><div class="side-label">Request to A</div>${escHtml(formatReqHeaders(r, 'a'))}</div><div class="has-copy"><button class="inline-copy" onclick="inlineCopy(this,${id},'req_b')">copy</button><div class="side-label">Request to B</div>${escHtml(formatReqHeaders(r, 'b'))}</div></div></div>
      <div class="raw-headers" id="resp-headers-${id}"><div class="side-by-side"><div class="has-copy"><button class="inline-copy" onclick="inlineCopy(this,${id},'resp_headers_a')">copy</button><div class="side-label">Response A</div>${escHtml(JSON.stringify(r.response_a.headers, null, 2))}</div><div class="has-copy"><button class="inline-copy" onclick="inlineCopy(this,${id},'resp_headers_b')">copy</button><div class="side-label">Response B</div>${escHtml(JSON.stringify(r.response_b.headers, null, 2))}</div></div></div>
    </div>
  `;

  // Auto-expand drifts
  if (r.has_drift) {
    document.getElementById(`rb-${id}`).classList.add('open');
    document.getElementById(`rc-${id}`).classList.add('open');
  }
}

function formatReqHeaders(r, side) {
  const resp = side === 'a' ? r.response_a : r.response_b;
  let lines = [];
  if (resp.request_url) lines.push(`URL: ${resp.request_url}`);
  lines.push(`Method: ${r.method}`);
  if (resp.request_headers && Object.keys(resp.request_headers).length) {
    for (const [k, v] of Object.entries(resp.request_headers)) {
      lines.push(`${k}: ${v}`);
    }
  }
  return lines.join('\n');
}

// Format request body for display based on content type.
// Returns {html, text} where html is for rendering and text is for copy.
function formatRequestBody(body, contentType) {
  if (body == null || body === '') return null;

  const ct = contentType || 'query';

  // JSON content type
  if (ct === 'application/json') {
    try {
      const parsed = JSON.parse(body);
      const pretty = JSON.stringify(parsed, null, 2);
      return { html: escHtml(pretty), text: pretty, type: 'json' };
    } catch (_) {
      // Not valid JSON, show raw
      return { html: escHtml(body), text: body, type: 'raw' };
    }
  }

  // Form-encoded or query params: parse into key/value table
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
      // Also include raw form for reference
      html += `<div style="margin-top:6px;font-size:0.8em;color:var(--text-dim);">Raw: <code>${escHtml(body)}</code></div>`;

      const text = entries.map(([k, v]) => `${k}=${v}`).join('\n');
      return { html, text: body, type: label.toLowerCase() };
    } catch (_) {
      return { html: escHtml(body), text: body, type: 'raw' };
    }
  }

  // Fallback: raw display
  return { html: escHtml(body), text: body, type: 'raw' };
}

function toggleResultBody(bodyId, chevId) {
  document.getElementById(bodyId).classList.toggle('open');
  document.getElementById(chevId).classList.toggle('open');
}
function toggleRaw(id) {
  const el = document.getElementById(id);
  const visible = getComputedStyle(el).display !== 'none';
  el.style.display = visible ? 'none' : 'block';
}

// ── Copy menu ──
function toggleCopyMenu(id) {
  const menu = document.getElementById(`copy-menu-${id}`);
  const wasOpen = menu.classList.contains('open');
  document.querySelectorAll('.copy-menu-items.open').forEach(m => m.classList.remove('open'));
  if (!wasOpen) menu.classList.add('open');
}
document.addEventListener('click', e => {
  if (!e.target.closest('.copy-menu')) {
    document.querySelectorAll('.copy-menu-items.open').forEach(m => m.classList.remove('open'));
  }
});

function clipCopy(text, btnEl) {
  navigator.clipboard.writeText(text).then(() => {
    if (!btnEl) return;
    const orig = btnEl.textContent;
    btnEl.textContent = 'copied';
    btnEl.classList.add('copied');
    setTimeout(() => { btnEl.textContent = orig; btnEl.classList.remove('copied'); }, 1200);
  });
  document.querySelectorAll('.copy-menu-items.open').forEach(m => m.classList.remove('open'));
}

function fmtHeaders(headers) {
  if (!headers || !Object.keys(headers).length) return '(none)';
  return Object.entries(headers).map(([k, v]) => `${k}: ${v}`).join('\n');
}

function fmtBody(body) {
  if (body == null) return '(empty)';
  return typeof body === 'string' ? body : JSON.stringify(body, null, 2);
}

// ── Inline copy (per-container floating button) ──
function inlineCopy(btn, id, which) {
  const r = resultStore[id];
  if (!r) return;
  let text;
  switch (which) {
    case 'resp_a':          text = fmtBody(r.response_a.body); break;
    case 'resp_b':          text = fmtBody(r.response_b.body); break;
    case 'raw_diff':        text = JSON.stringify(r.diff, null, 2); break;
    case 'req_a':           text = formatReqHeaders(r, 'a'); break;
    case 'req_b':           text = formatReqHeaders(r, 'b'); break;
    case 'resp_headers_a':  text = JSON.stringify(r.response_a.headers, null, 2); break;
    case 'resp_headers_b':  text = JSON.stringify(r.response_b.headers, null, 2); break;
    case 'req_body': {
      const fmt = formatRequestBody(r.request_body, r.request_content_type);
      text = fmt ? fmt.text : '(no body)';
      break;
    }
    default: return;
  }
  clipCopy(text, btn);
}

// ── Full result formatters (for menu) ──
function buildSideMd(r, side) {
  const resp = side === 'a' ? r.response_a : r.response_b;
  const memoEl = document.getElementById(side === 'a' ? 'memoA' : 'memoB');
  const memo = memoEl ? memoEl.value : '';
  const label = memo ? `Host ${side.toUpperCase()} (${memo})` : `Host ${side.toUpperCase()}`;
  let md = `### ${label}\n\n`;
  md += `**${r.method}** \`${resp.request_url || r.path}\`\n`;
  md += `**Status:** ${resp.status || 'ERR'} | **Time:** ${resp.elapsed_ms ?? '?'}ms\n\n`;
  md += `#### Request Headers\n\n\`\`\`\n${fmtHeaders(resp.request_headers)}\n\`\`\`\n\n`;
  md += `#### Response Headers\n\n\`\`\`\n${fmtHeaders(resp.headers)}\n\`\`\`\n\n`;
  md += `#### Body\n\n\`\`\`json\n${fmtBody(resp.body)}\n\`\`\`\n`;
  return md;
}

function buildFullMd(r) {
  let md = buildContextLines('md').join('\n');
  md += `## ${r.method} ${r.path}\n\n`;
  md += `**Result:** ${r.has_drift ? 'DRIFT' : 'OK'}\n\n`;

  // Diff summary
  const sections = parseDiff(r.diff);
  if (sections.length) {
    md += `## Differences\n\n`;
    for (const sec of sections) {
      md += `**${sec.label}**\n\n`;
      for (const e of sec.entries) {
        const pp = prettifyPath(e.path);
        if (e.oldVal !== undefined) {
          md += `- \`${pp}\`: \`${jsonSummary(e.oldVal)}\` → \`${jsonSummary(e.newVal)}\`\n`;
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

  md += buildSideMd(r, 'a') + '\n' + buildSideMd(r, 'b');
  return md;
}

function copyResultMd(id, which) {
  const r = resultStore[id];
  if (!r) return;
  clipCopy(buildFullMd(r), event.target);
}

function copyResultJson(id, which) {
  const r = resultStore[id];
  if (!r) return;
  clipCopy(JSON.stringify(r, null, 2), event.target);
}

// ── Run all / run group ──
function visibleCards(selector) {
  return [...document.querySelectorAll(selector)].filter(c => !c.classList.contains('hidden-by-filter'));
}

async function runAll() {
  const btn = document.getElementById('runBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Running...';

  for (const card of visibleCards('.ep-card')) {
    const id = parseInt(card.id.replace('ep-', ''));
    await runOne(id);
  }

  btn.disabled = false;
  btn.textContent = 'Run All';
}

async function runGroup(groupName) {
  for (const card of visibleCards(`.ep-card[data-group="${groupName}"]`)) {
    const id = parseInt(card.id.replace('ep-', ''));
    await runOne(id);
  }
}

// ── Filter ──
function filterCards(filter) {
  currentFilter = filter;
  document.querySelectorAll('.filter-pills button').forEach(b => b.classList.remove('active'));
  const activeBtn = document.querySelector(`[data-test="filter-${filter}"]`);
  if (activeBtn) activeBtn.classList.add('active');

  // Collapse all result bodies
  document.querySelectorAll('.ep-result-body.open').forEach(b => b.classList.remove('open'));
  document.querySelectorAll('.chevron.open').forEach(c => c.classList.remove('open'));

  document.querySelectorAll('.ep-card').forEach(card => {
    const s = card.dataset.state;
    if (filter === 'all') card.classList.remove('hidden-by-filter');
    else if (filter === 'drift') card.classList.toggle('hidden-by-filter', s !== 'done-drift');
    else if (filter === 'ok') card.classList.toggle('hidden-by-filter', s !== 'done-ok');
  });
  document.querySelectorAll('.group-divider').forEach(div => {
    const g = div.dataset.group;
    const visible = document.querySelectorAll(`.ep-card[data-group="${g}"]:not(.hidden-by-filter)`);
    div.classList.toggle('hidden-by-filter', visible.length === 0);
  });
}

// ── Diff rendering (consumes shared parseDiff) ──
function renderDiff(r, id) {
  if (!r.has_drift) {
    const ignoredN = r.ignored_paths ? r.ignored_paths.length : 0;
    const ignoredNote = ignoredN > 0 ? ` <span class="ignored-badge" title="${r.ignored_paths.map(prettifyPath).join('\n')}">${ignoredN} fields ignored</span>` : '';
    return `<div data-test="diff-none" style="color:var(--green);font-size:0.85em;padding:4px 0">No differences detected.${ignoredNote}</div>`;
  }
  const sections = parseDiff(r.diff);
  const copyBtn = `<button class="copy-drift-btn" onclick="event.stopPropagation(); copyDriftSummary(this, ${id})">Copy summary</button>`;
  const ignoredN = r.ignored_paths ? r.ignored_paths.length : 0;
  const ignoredBadge = ignoredN > 0 ? `<span class="ignored-badge" title="${r.ignored_paths.map(prettifyPath).join('\n')}">${ignoredN} fields ignored</span>` : '';
  let html = '';
  let copyInserted = false;

  for (const sec of sections) {
    const btnHere = !copyInserted ? `${copyBtn} ${ignoredBadge}` : '';
    copyInserted = true;
    html += `<div class="diff-section" data-test="diff-${sec.key}"><h4>${escHtml(sec.label)} ${btnHere}</h4>`;

    for (const e of sec.entries) {
      const pp = prettifyPath(e.path);
      if (e.oldVal !== undefined && e.oldType) {
        html += `<div class="diff-entry" data-test="diff-entry"><span class="diff-path" data-test="diff-path" title="${escHtml(e.path)}">${escHtml(pp)}</span><br><span class="diff-old" data-test="diff-old">&minus; ${escHtml(jsonSummary(e.oldVal))} <span style="opacity:0.6">(${e.oldType})</span></span><br><span class="diff-new" data-test="diff-new">&plus; ${escHtml(jsonSummary(e.newVal))} <span style="opacity:0.6">(${e.newType})</span></span></div>`;
      } else if (e.oldVal !== undefined) {
        html += `<div class="diff-entry" data-test="diff-entry"><span class="diff-path" data-test="diff-path" title="${escHtml(e.path)}">${escHtml(pp)}</span><br><span class="diff-old" data-test="diff-old">&minus; ${escHtml(jsonSummary(e.oldVal))}</span><br><span class="diff-new" data-test="diff-new">&plus; ${escHtml(jsonSummary(e.newVal))}</span></div>`;
      } else if (e.kind === 'added') {
        html += `<div class="diff-entry" data-test="diff-entry"><span class="diff-path" data-test="diff-path" title="${escHtml(e.path)}">${escHtml(pp)}</span> <span class="diff-new" data-test="diff-new">&plus; ${escHtml(jsonSummary(e.raw))}</span></div>`;
      } else if (e.kind === 'removed') {
        html += `<div class="diff-entry" data-test="diff-entry"><span class="diff-path" data-test="diff-path" title="${escHtml(e.path)}">${escHtml(pp)}</span> <span class="diff-old" data-test="diff-old">&minus; ${escHtml(jsonSummary(e.raw))}</span></div>`;
      } else {
        html += `<div class="diff-entry" data-test="diff-entry">${escHtml(jsonSummary(e.raw, 2))}</div>`;
      }
    }
    html += '</div>';
  }
  if (!copyInserted) html += `${copyBtn} ${ignoredBadge}`;
  return html;
}

// ── Examples ──
const EXAMPLES = {
  'mixed': [
    {m:'GET',  l:'status-query',  p:'/api/v1/status', b:'',                              ct:'query'},
    {m:'POST', l:'share-form',    p:'/api/v1/share',  b:'secret=hello&ttl=3600',         ct:'application/x-www-form-urlencoded'},
    {m:'POST', l:'share-json',    p:'/api/v2/share',  b:'{"secret":"hello","ttl":3600}',  ct:'application/json'},
  ],
  'query-only': [
    {m:'GET', l:'v1-status', p:'/api/v1/status',      b:'', ct:'query'},
    {m:'GET', l:'v2-status', p:'/api/v2/status',      b:'', ct:'query'},
    {m:'GET', l:'v1-404',    p:'/api/v1/nonexistent', b:'', ct:'query'},
  ],
  'form-only': [
    {m:'POST', l:'v1-share',      p:'/api/v1/share',    b:'secret=test&ttl=3600',                    ct:'application/x-www-form-urlencoded'},
    {m:'POST', l:'v1-generate',   p:'/api/v1/generate', b:'ttl=3600',                                ct:'application/x-www-form-urlencoded'},
    {m:'POST', l:'v1-share-pass', p:'/api/v1/share',    b:'secret=test&ttl=3600&passphrase=abcdefgh', ct:'application/x-www-form-urlencoded'},
  ],
  'json-only': [
    {m:'POST', l:'v2-share',      p:'/api/v2/share',    b:'{"secret":"test","ttl":3600}',                          ct:'application/json'},
    {m:'POST', l:'v2-generate',   p:'/api/v2/generate', b:'{"ttl":3600}',                                          ct:'application/json'},
    {m:'POST', l:'v2-share-pass', p:'/api/v2/share',    b:'{"secret":"test","ttl":3600,"passphrase":"abcdefgh"}',   ct:'application/json'},
  ],
};

function loadExamples(name) {
  clearEndpoints();
  (EXAMPLES[name] || []).forEach(r => addEndpoint(r.m, r.l, r.p, r.b, r.ct));
  closeAllMenus();
}

// ── Action bar menus ──
function toggleActionMenu(id) {
  const menu = document.getElementById(id);
  const wasOpen = menu.classList.contains('open');
  closeAllMenus();
  if (!wasOpen) menu.classList.add('open');
}
function closeAllMenus() {
  document.querySelectorAll('.action-dropdown.open').forEach(m => m.classList.remove('open'));
}
document.addEventListener('click', e => {
  if (!e.target.closest('.action-menu')) closeAllMenus();
});

function clearEndpoints() {
  document.getElementById('endpointsArea').innerHTML = '';
  updateTally();
}

// ── Loader ──
function showBreadcrumb(src) { document.getElementById('breadcrumbSource').textContent = src; document.getElementById('loaderBreadcrumb').style.display = 'flex'; }
function dismissBreadcrumb() { document.getElementById('loaderBreadcrumb').style.display = 'none'; }

let parsedSpec = null;
function openLoaderModal() { document.getElementById('loaderModal').classList.add('open'); }
function closeLoaderModal() { document.getElementById('loaderModal').classList.remove('open'); }

async function loadSpecFromUrl() {
  const url = document.getElementById('openapiUrl').value.trim();
  if (!url) return;
  const fd = new FormData(); fd.append('url', url);
  await loadSpec(fd, url);
}
async function loadSpecFromFile(input) {
  if (!input.files.length) return;
  const fd = new FormData(); fd.append('file', input.files[0]);
  await loadSpec(fd, input.files[0].name);
}
async function loadSpec(fd, sourceName) {
  const info = document.getElementById('openapiInfo');
  const groups = document.getElementById('openapiGroups');
  const footer = document.getElementById('modalFooter');
  info.style.display = 'block'; info.textContent = 'Loading...';
  groups.innerHTML = ''; footer.classList.remove('has-spec');
  document.getElementById('openapiSelectBar').style.display = 'none';
  try {
    const resp = await fetch('/api/parse-openapi', { method: 'POST', body: fd });
    const data = await resp.json();
    if (data.error) { info.textContent = 'Error: ' + data.error; return; }
    parsedSpec = data; parsedSpec._src = sourceName;
    info.innerHTML = `<strong>${escHtml(data.title)}</strong> ${escHtml(data.version)} &mdash; ${data.total_operations} ops in ${data.groups.length} groups`;
    renderOAGroups(data.groups);
    footer.classList.add('has-spec');
    document.getElementById('openapiSelectBar').style.display = 'flex';
  } catch (err) { info.textContent = 'Error: ' + err.message; }
}

function renderOAGroups(groups) {
  const c = document.getElementById('openapiGroups'); c.innerHTML = '';
  groups.forEach((g, gi) => {
    const div = document.createElement('div'); div.className = 'openapi-group'; div.dataset.test = 'oa-group'; div.dataset.testGroup = g.name;
    div.innerHTML = `
      <div class="openapi-group-header" data-test="oa-group-header" onclick="toggleOAGroup(${gi})">
        <input type="checkbox" checked data-test="oa-group-checkbox" onclick="event.stopPropagation(); toggleOAGroupCheck(${gi}, this.checked)" id="gc-${gi}">
        <span class="chevron" id="gchev-${gi}">&#9654;</span>
        <span class="openapi-group-name" data-test="oa-group-name">${escHtml(g.name)}</span>
        <span class="openapi-group-count" data-test="oa-group-count">${g.count} ops</span>
      </div>
      <div class="openapi-group-body" data-test="oa-group-body" id="gbody-${gi}">
        ${g.operations.map((op,oi) => `<div class="openapi-op" data-test="oa-op" data-test-method="${op.method}" data-test-path="${escHtml(op.path)}">
          <input type="checkbox" checked data-test="oa-op-checkbox" data-group="${gi}" data-op="${oi}" id="op-${gi}-${oi}">
          <span class="op-method ${op.method.toLowerCase()}" data-test="oa-op-method">${op.method}</span>
          <span class="op-path" data-test="oa-op-path">${escHtml(op.path)}</span>
          ${op.summary?`<span class="op-summary" data-test="oa-op-summary">${escHtml(op.summary)}</span>`:''}
        </div>`).join('')}
      </div>`;
    c.appendChild(div);
  });
}
function toggleOAGroup(i) { document.getElementById(`gbody-${i}`).classList.toggle('open'); document.getElementById(`gchev-${i}`).classList.toggle('open'); }
function toggleOAGroupCheck(i, chk) { document.querySelectorAll(`input[data-group="${i}"]`).forEach(cb => cb.checked = chk); }
function openapiSelectAll(chk) { document.querySelectorAll('.openapi-groups input[type="checkbox"]').forEach(cb => cb.checked = chk); }

function loadSelectedToEndpoints() {
  if (!parsedSpec) return;
  const sel = [];
  parsedSpec.groups.forEach((g, gi) => {
    g.operations.forEach((op, oi) => {
      const cb = document.getElementById(`op-${gi}-${oi}`);
      if (cb && cb.checked) sel.push({ ...op, _group: g.name });
    });
  });
  if (!sel.length) { alert('No operations selected.'); return; }
  clearEndpoints();
  sel.forEach(op => {
    let body = op.body || '';
    if (op.content_type === 'application/json' && body && body.includes('=')) {
      try {
        const obj = {};
        body.split('&').forEach(pair => { const [k,v] = pair.split('=');
          if (v==='true'||v==='false') obj[k]=v==='true';
          else if (!isNaN(v)&&v!=='') obj[k]=Number(v);
          else obj[k]=decodeURIComponent(v); });
        body = JSON.stringify(obj);
      } catch(e) {}
    }
    addEndpoint(op.method, op.label, op.path, body, op.content_type, op._group,
                op.fields || null, op.query_fields || null, op.path_fields || null);
  });
  insertGroupDividers();
  showBreadcrumb(parsedSpec._src || 'OpenAPI spec');
  closeLoaderModal();
}

// ── Schema Diff ──
function openSchemaDiffModal() { document.getElementById('schemaDiffModal').classList.add('open'); }
function closeSchemaDiffModal() { document.getElementById('schemaDiffModal').classList.remove('open'); }

async function runSchemaDiff() {
  const status = document.getElementById('schemaDiffStatus');
  const results = document.getElementById('schemaDiffResults');
  status.innerHTML = '<span class="spinner"></span> Comparing schemas...';
  results.innerHTML = '';

  const fd = new FormData();
  const fileA = document.getElementById('schemaDiffFileA').files[0];
  const fileB = document.getElementById('schemaDiffFileB').files[0];
  const urlA = document.getElementById('schemaDiffUrlA').value.trim();
  const urlB = document.getElementById('schemaDiffUrlB').value.trim();

  if (fileA) fd.append('file_a', fileA);
  else if (urlA) fd.append('url_a', urlA);
  else { status.textContent = 'Provide spec A (file or URL)'; return; }

  if (fileB) fd.append('file_b', fileB);
  else if (urlB) fd.append('url_b', urlB);
  else { status.textContent = 'Provide spec B (file or URL)'; return; }

  try {
    const resp = await fetch('/api/diff-schemas', { method: 'POST', body: fd });
    const data = await resp.json();
    if (data.error) { status.textContent = 'Error: ' + data.error; return; }
    renderSchemaDiffResults(data);
    status.textContent = '';
  } catch (err) {
    status.textContent = 'Error: ' + err.message;
  }
}

function renderSchemaDiffResults(data) {
  const container = document.getElementById('schemaDiffResults');
  const s = data.summary;
  let html = `<div class="sd-summary">
    <span style="color:var(--text)">${escHtml(s.spec_a)} vs ${escHtml(s.spec_b)}</span>
    <span class="sd-stat" style="color:var(--yellow)">${s.changed} changed</span>
    <span class="sd-stat" style="color:var(--green)">${s.added} added</span>
    <span class="sd-stat" style="color:var(--red)">${s.removed} removed</span>
    <span class="sd-stat" style="color:var(--text-dim)">${s.identical} identical</span>
  </div>`;

  // Only show non-identical endpoints (skip the noise)
  const interesting = data.results.filter(r => r.status !== 'identical');
  if (!interesting.length) {
    html += '<div style="color:var(--green);font-size:0.85em;padding:8px 0">All request schemas are identical.</div>';
    container.innerHTML = html;
    return;
  }

  for (const r of interesting) {
    const rid = `sd-${r.method}-${r.path.replace(/\W/g, '_')}`;
    html += `<div class="sd-endpoint" data-test="sd-endpoint">
      <div class="sd-endpoint-header" onclick="document.getElementById('${rid}').classList.toggle('open');this.querySelector('.chevron').classList.toggle('open')">
        <span class="chevron">&#9654;</span>
        <span class="sd-badge ${r.status}">${r.status.replace('_', ' ')}</span>
        <span class="op-method ${r.method.toLowerCase()}" style="font-weight:600;width:52px;text-align:right">${r.method}</span>
        <span>${escHtml(r.path)}</span>
      </div>
      <div class="sd-body" id="${rid}">
        ${renderSchemaDiffDetail(r)}
      </div>
    </div>`;
  }
  container.innerHTML = html;

  // Auto-expand changed endpoints
  for (const r of interesting) {
    if (r.status === 'changed') {
      const rid = `sd-${r.method}-${r.path.replace(/\W/g, '_')}`;
      const el = document.getElementById(rid);
      if (el) {
        el.classList.add('open');
        el.previousElementSibling.querySelector('.chevron').classList.add('open');
      }
    }
  }
}

function renderSchemaDiffDetail(r) {
  if (r.status === 'added_in_b') {
    return `<div class="sd-section"><h5>New endpoint in Spec B</h5>${r.fields_b.map(f =>
      `<div class="sd-item" style="color:var(--green)">&plus; ${escHtml(f.path)} <span style="color:var(--text-dim)">(${f.type}${f.required?' req':''})</span></div>`).join('')}</div>`;
  }
  if (r.status === 'removed_from_b') {
    return `<div class="sd-section"><h5>Removed from Spec B</h5>${r.fields_a.map(f =>
      `<div class="sd-item" style="color:var(--red)">&minus; ${escHtml(f.path)} <span style="color:var(--text-dim)">(${f.type}${f.required?' req':''})</span></div>`).join('')}</div>`;
  }
  const d = r.diff;
  let html = '';
  if (d.possible_renames && d.possible_renames.length) {
    html += '<div class="sd-section"><h5>Possible Renames</h5>';
    for (const rn of d.possible_renames)
      html += `<div class="sd-item sd-rename"><span style="color:var(--red)">${escHtml(rn.old_path)}</span> &rarr; <span style="color:var(--green)">${escHtml(rn.new_path)}</span> <span style="color:var(--text-dim)">(${rn.type})</span></div>`;
    html += '</div>';
  }
  if (d.added && d.added.length) {
    html += '<div class="sd-section"><h5>Fields Added in B</h5>';
    for (const f of d.added)
      html += `<div class="sd-item" style="color:var(--green)">&plus; ${escHtml(f.path)} <span style="color:var(--text-dim)">(${f.type}${f.required?' req':''})</span></div>`;
    html += '</div>';
  }
  if (d.removed && d.removed.length) {
    html += '<div class="sd-section"><h5>Fields Removed from B</h5>';
    for (const f of d.removed)
      html += `<div class="sd-item" style="color:var(--red)">&minus; ${escHtml(f.path)} <span style="color:var(--text-dim)">(${f.type}${f.required?' req':''})</span></div>`;
    html += '</div>';
  }
  if (d.type_changed && d.type_changed.length) {
    html += '<div class="sd-section"><h5>Type Changes</h5>';
    for (const tc of d.type_changed)
      html += `<div class="sd-item"><span style="color:var(--yellow)">${escHtml(tc.path)}</span>: <span style="color:var(--red)">${tc.type_a}</span> &rarr; <span style="color:var(--green)">${tc.type_b}</span></div>`;
    html += '</div>';
  }
  if (d.const_changed && d.const_changed.length) {
    html += '<div class="sd-section"><h5>Const Changes</h5>';
    for (const cc of d.const_changed)
      html += `<div class="sd-item"><span style="color:var(--yellow)">${escHtml(cc.path)}</span>: <span style="color:var(--red)">${escHtml(String(cc.const_a))}</span> &rarr; <span style="color:var(--green)">${escHtml(String(cc.const_b))}</span></div>`;
    html += '</div>';
  }
  return html || '<div style="color:var(--text-dim)">No field-level differences.</div>';
}

// ── Session export/import ──
const DD_VERSION = '0.3.0';

function collectState() {
  const cards = [...document.querySelectorAll('.ep-card')];
  const endpoints = cards.map(card => {
    const id = parseInt(card.id.replace('ep-', ''));
    // Sync kv-pairs to body input before reading
    const kvC = document.getElementById(`ep-kv-${id}`);
    if (kvC && kvC.style.display !== 'none') syncKvToBody(id);
    const ep = {
      method: card.querySelector('[data-field="method"]').value,
      label: card.querySelector('[data-field="label"]').value,
      path: card.querySelector('[data-field="path"]').value,
      body: card.querySelector('[data-field="body"]').value,
      contentType: card.dataset.contentType || 'query',
      group: card.dataset.group || '',
      fieldsMode: card.dataset.fieldsMode || 'off',
      state: card.dataset.state || 'idle',
    };
    // Save field schemas if present
    if (cardFields[id]) {
      ep.cardFields = cardFields[id];
    }
    // Save current field input values
    const fieldsDiv = document.getElementById(`ep-fields-${id}`);
    if (fieldsDiv) {
      const inputs = fieldsDiv.querySelectorAll('[data-field-path]');
      const fieldValues = {};
      inputs.forEach(inp => { fieldValues[inp.dataset.fieldPath] = inp.value; });
      if (Object.keys(fieldValues).length) ep.fieldValues = fieldValues;
    }
    // Save result HTML if present
    const resultDiv = document.getElementById(`ep-result-${id}`);
    if (resultDiv && resultDiv.style.display !== 'none' && card.dataset.state !== 'idle') {
      ep.resultHtml = resultDiv.innerHTML;
    }
    return ep;
  });

  // Capture group divider ordering
  const breadcrumb = document.getElementById('loaderBreadcrumb');
  const breadcrumbSource = document.getElementById('breadcrumbSource').textContent;

  // UI view state
  const ignoreOpen = document.getElementById('ignoreBody').classList.contains('open');
  const filterPillsVisible = document.getElementById('filterPills').style.display !== 'none';

  return {
    version: DD_VERSION,
    savedAt: new Date().toISOString(),
    documentId: currentDocumentId,
    sessionNumber: currentSessionNumber,
    title: document.getElementById('sessionTitle').value,
    memo: document.getElementById('sessionMemo').value,
    hostA: effectiveHost('hostA'),
    hostB: effectiveHost('hostB'),
    memoA: document.getElementById('memoA').value,
    memoB: document.getElementById('memoB').value,
    authA: document.getElementById('authA').value,
    authB: document.getElementById('authB').value,
    specSource: breadcrumb.style.display !== 'none' ? breadcrumbSource : null,
    ignorePaths: getRawIgnoreLines(),
    endpoints: endpoints,
    // View state
    filter: currentFilter,
    ignoreOpen: ignoreOpen,
    filterPillsVisible: filterPillsVisible,
  };
}

function restoreState(snapshot) {
  // Restore document/session tracking if present
  if (snapshot.documentId) currentDocumentId = snapshot.documentId;
  if (snapshot.sessionNumber) currentSessionNumber = snapshot.sessionNumber;
  updateDocIndicator();

  // Set title and memo
  document.getElementById('sessionTitle').value = snapshot.title || '';
  document.getElementById('sessionMemo').value = snapshot.memo || '';

  // Set hosts, memos, and auth
  document.getElementById('hostA').value = snapshot.hostA || '';
  document.getElementById('hostB').value = snapshot.hostB || '';
  document.getElementById('memoA').value = snapshot.memoA || '';
  document.getElementById('memoB').value = snapshot.memoB || '';
  document.getElementById('authA').value = snapshot.authA || '';
  document.getElementById('authB').value = snapshot.authB || '';

  // Restore ignore paths
  if (snapshot.ignorePaths && snapshot.ignorePaths.length) {
    document.getElementById('ignorePaths').value = snapshot.ignorePaths.join('\n');
    updateIgnoreCount();
  }

  // Clear and rebuild endpoints
  clearEndpoints();
  epId = 0;

  for (const ep of snapshot.endpoints) {
    const fields = ep.cardFields ? ep.cardFields.fields : null;
    const queryFields = ep.cardFields ? ep.cardFields.query_fields : null;
    const pathFields = ep.cardFields ? ep.cardFields.path_fields : null;
    addEndpoint(ep.method, ep.label, ep.path, ep.body, ep.contentType, ep.group,
                fields, queryFields, pathFields);

    // The card was just added; get its id (epId - 1 since addEndpoint increments)
    const id = epId - 1;
    const card = document.getElementById(`ep-${id}`);
    if (!card) continue;

    // Restore field input values
    if (ep.fieldValues) {
      const fieldsDiv = document.getElementById(`ep-fields-${id}`);
      if (fieldsDiv) {
        for (const [path, val] of Object.entries(ep.fieldValues)) {
          const inp = fieldsDiv.querySelector(`[data-field-path="${path}"]`);
          if (inp) inp.value = val;
        }
      }
    }

    // Restore fields mode (addEndpoint may have set a default, override it)
    if (ep.fieldsMode === 'on' && card.dataset.fieldsMode !== 'on') {
      toggleFieldsMode(id);
    } else if (ep.fieldsMode === 'off' && card.dataset.fieldsMode !== 'off') {
      toggleFieldsMode(id);
    }

    // Restore result display
    if (ep.resultHtml && ep.state && ep.state !== 'idle') {
      card.dataset.state = ep.state;
      card.className = `ep-card state-${ep.state === 'done-drift' ? 'drift' : ep.state === 'done-ok' ? 'ok' : 'idle'}`;
      const resultDiv = document.getElementById(`ep-result-${id}`);
      resultDiv.style.display = 'block';
      resultDiv.innerHTML = ep.resultHtml;
    }
  }

  insertGroupDividers();

  // Restore breadcrumb
  if (snapshot.specSource) {
    showBreadcrumb(snapshot.specSource);
  }

  updateTally();

  // Restore view state
  if (snapshot.ignoreOpen) {
    document.getElementById('ignoreBody').classList.add('open');
    document.getElementById('ignoreChev').classList.add('open');
  } else {
    document.getElementById('ignoreBody').classList.remove('open');
    document.getElementById('ignoreChev').classList.remove('open');
  }
  // Show filter pills if there are any run results
  const hasResults = snapshot.endpoints && snapshot.endpoints.some(ep => ep.state && ep.state !== 'idle');
  if (snapshot.filterPillsVisible || hasResults) {
    document.getElementById('filterPills').style.display = 'flex';
  }
  // Apply saved filter (default to 'all')
  filterCards(snapshot.filter || 'all');
}

async function saveSession() {
  const btn = document.querySelector('[data-test="action-save"]');
  const orig = btn.textContent;
  btn.textContent = 'Saving...';
  btn.disabled = true;
  try {
    const state = collectState();
    const resp = await fetch('/api/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ state: state, documentId: currentDocumentId }),
    });
    const data = await resp.json();
    if (data.ok) {
      currentDocumentId = data.document.id;
      currentSessionNumber = data.session ? data.session.session_number : currentSessionNumber;
      lastSavedStateHash = stateFingerprint(state);
      updateDocIndicator();
      refreshSidebar();
      startAutosave();
      btn.textContent = 'Saved';
      btn.style.color = 'var(--green)';
      setTimeout(() => { btn.textContent = orig; btn.style.color = ''; btn.disabled = false; }, 1500);
    } else {
      btn.textContent = 'Error';
      btn.style.color = 'var(--red)';
      setTimeout(() => { btn.textContent = orig; btn.style.color = ''; btn.disabled = false; }, 2000);
    }
  } catch (err) {
    btn.textContent = 'Error';
    btn.style.color = 'var(--red)';
    setTimeout(() => { btn.textContent = orig; btn.style.color = ''; btn.disabled = false; }, 2000);
  }
}

function updateDocIndicator() {
  const el = document.getElementById('docIndicator');
  if (currentDocumentId) {
    el.textContent = `doc #${currentDocumentId} / session #${currentSessionNumber}`;
    el.style.display = 'inline';
  } else {
    el.style.display = 'none';
  }
}

function exportCurrentAsJson() {
  const state = collectState();
  const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  a.href = url;
  a.download = `drift-session-${ts}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

async function exportSavedSession(docId, sessionNumber) {
  try {
    const resp = await fetch(`/api/documents/${docId}/sessions/${sessionNumber}`);
    const data = await resp.json();
    if (data.error) { showDropToast('Session not found: ' + data.error, true); return; }
    const state = data.session.state;
    const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const ts = data.session.created_at.replace(/[:.]/g, '-').slice(0, 19);
    a.href = url;
    a.download = `drift-doc${docId}-session${sessionNumber}-${ts}.json`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    showDropToast('Export failed: ' + err.message, true);
  }
}

function resetModals() {
  // Close all modals
  closeLoaderModal();
  closeSchemaDiffModal();
  closeAllMenus();

  // Reset OpenAPI loader state
  parsedSpec = null;
  document.getElementById('openapiUrl').value = '';
  document.getElementById('openapiFile').value = '';
  document.getElementById('openapiInfo').style.display = 'none';
  document.getElementById('openapiInfo').textContent = '';
  document.getElementById('openapiGroups').innerHTML = '';
  document.getElementById('modalFooter').classList.remove('has-spec');
  document.getElementById('openapiSelectBar').style.display = 'none';

  // Reset Schema Diff modal state
  document.getElementById('schemaDiffUrlA').value = '';
  document.getElementById('schemaDiffUrlB').value = '';
  document.getElementById('schemaDiffFileA').value = '';
  document.getElementById('schemaDiffFileB').value = '';
  document.getElementById('schemaDiffStatus').innerHTML = '';
  document.getElementById('schemaDiffResults').innerHTML = '';
}

async function loadSavedSession(docId, sessionNumber) {
  try {
    const resp = await fetch(`/api/documents/${docId}/sessions/${sessionNumber}`);
    const data = await resp.json();
    if (data.error) { showDropToast('Session not found: ' + data.error, true); return; }
    resetModals();
    currentDocumentId = docId;
    currentSessionNumber = sessionNumber;
    restoreState(data.session.state);
    lastSavedStateHash = stateFingerprint(data.session.state);
    updateDocIndicator();
    showBreadcrumb(`doc #${docId} session #${sessionNumber}`);
    showDropToast(`Loaded session #${sessionNumber}`, false);
    refreshSidebar();
    startAutosave();
  } catch (err) {
    showDropToast('Load failed: ' + err.message, true);
  }
}

// ── Sidebar ──

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const expandBtn = document.getElementById('sidebarExpandBtn');
  sidebar.classList.toggle('collapsed');
  expandBtn.classList.toggle('visible', sidebar.classList.contains('collapsed'));
}

async function refreshSidebar() {
  const list = document.getElementById('sidebarList');
  try {
    const resp = await fetch('/api/documents');
    const data = await resp.json();
    if (!data.documents || !data.documents.length) {
      list.innerHTML = '<div style="padding:12px 14px;font-size:0.8em;color:var(--text-dim)">No documents yet.</div>';
      return;
    }
    let html = '';
    for (const d of data.documents) {
      const isCurrent = d.id === currentDocumentId;
      const isExpanded = isCurrent || expandedDocs.has(d.id);
      html += `<div class="sidebar-doc" data-doc-id="${d.id}">
        <div class="sidebar-doc-header${isCurrent ? ' active' : ''}" onclick="toggleDocInSidebar(${d.id})">
          <span class="chevron${isExpanded ? ' open' : ''}" style="font-size:0.7em">&#9654;</span>
          <span class="sidebar-doc-title">${escHtml(d.title || 'Untitled')}</span>
          <span class="sidebar-doc-count">${d.session_count}</span>
        </div>
        <div class="sidebar-sessions${isExpanded ? ' open' : ''}" id="sidebar-sessions-${d.id}"></div>
      </div>`;
    }
    list.innerHTML = html;
    // Load sessions for expanded docs
    for (const d of data.documents) {
      if (d.id === currentDocumentId || expandedDocs.has(d.id)) {
        loadSessionsInSidebar(d.id);
      }
    }
  } catch (err) {
    list.innerHTML = `<div style="padding:12px 14px;font-size:0.8em;color:var(--red)">Error loading documents</div>`;
  }
}

const expandedDocs = new Set();

async function toggleDocInSidebar(docId) {
  const sessionsDiv = document.getElementById(`sidebar-sessions-${docId}`);
  if (!sessionsDiv) return;
  const isOpen = sessionsDiv.classList.contains('open');
  if (isOpen) {
    sessionsDiv.classList.remove('open');
    sessionsDiv.previousElementSibling.querySelector('.chevron').classList.remove('open');
    expandedDocs.delete(docId);
  } else {
    sessionsDiv.classList.add('open');
    sessionsDiv.previousElementSibling.querySelector('.chevron').classList.add('open');
    expandedDocs.add(docId);
    loadSessionsInSidebar(docId);
  }
}

async function loadSessionsInSidebar(docId) {
  const container = document.getElementById(`sidebar-sessions-${docId}`);
  if (!container) return;
  try {
    const resp = await fetch(`/api/documents/${docId}/sessions`);
    const data = await resp.json();
    if (!data.sessions || !data.sessions.length) {
      container.innerHTML = '<div style="padding:4px 28px;font-size:0.75em;color:var(--text-dim)">No sessions</div>';
      return;
    }
    // Reverse chronological: newest first
    const sessions = [...data.sessions].reverse();
    container.innerHTML = sessions.map(s => {
      const isCurrent = docId === currentDocumentId && s.session_number === currentSessionNumber;
      const di = driftIndicator(s);
      const timeStr = relativeTime(s.created_at);
      // Save type: floppy disk for explicit save, clock for autosave
      const typeIcon = s.session_type === 'autosave'
        ? '<span title="autosave" style="opacity:0.5">&#8635;</span>'
        : '<span title="saved" style="color:var(--accent)">&#9646;</span>';
      const epCount = s.endpoint_count ? `<span style="opacity:0.6">${s.endpoint_count}ep</span>` : '';
      return `<div class="sidebar-session${isCurrent ? ' active' : ''}" onclick="loadSavedSession(${docId},${s.session_number})">
        <span class="ss-num">#${s.session_number}</span>
        <span style="color:${di.color};font-size:0.9em" title="${di.title}">${di.symbol}</span>
        ${typeIcon}
        ${epCount}
        <span class="ss-time">${timeStr}</span>
        <button class="ss-delete" onclick="deleteSession(${docId},${s.session_number},event)" title="Delete session">&times;</button>
      </div>`;
    }).join('');
  } catch (err) {
    container.innerHTML = `<div style="padding:4px 28px;font-size:0.75em;color:var(--red)">Error</div>`;
  }
}

async function deleteSession(docId, sessionNumber, event) {
  event.stopPropagation(); // don't trigger load
  try {
    const resp = await fetch(`/api/documents/${docId}/sessions/${sessionNumber}`, { method: 'DELETE' });
    const data = await resp.json();
    if (data.ok) {
      // If we just deleted the currently loaded session, stay on the page but mark as stale
      if (docId === currentDocumentId && sessionNumber === currentSessionNumber) {
        currentSessionNumber = 0;
        updateDocIndicator();
      }
      loadSessionsInSidebar(docId);
      refreshSidebar(); // update session counts
    }
  } catch (err) {
    // Silent failure
  }
}

function newDocument() {
  resetModals();
  currentDocumentId = null;
  currentSessionNumber = 0;
  lastSavedStateHash = null;
  updateDocIndicator();
  clearEndpoints();
  document.getElementById('sessionTitle').value = '';
  document.getElementById('sessionMemo').value = '';
  document.getElementById('ignorePaths').value = '';
  document.getElementById('ignoreBody').classList.remove('open');
  document.getElementById('ignoreChev').classList.remove('open');
  document.getElementById('filterPills').style.display = 'none';
  filterCards('all');
  dismissBreadcrumb();
  stopAutosave();
  addEndpoint();
  refreshSidebar();
}

// ── Autosave ──

let autosaveTimer = null;
const AUTOSAVE_INTERVAL_MS = 60000;  // 60 seconds

function startAutosave() {
  stopAutosave();
  autosaveTimer = setInterval(doAutosave, AUTOSAVE_INTERVAL_MS);
}

function stopAutosave() {
  if (autosaveTimer) { clearInterval(autosaveTimer); autosaveTimer = null; }
}

async function doAutosave() {
  // Only autosave if there's a current document (don't create new docs on autosave)
  if (!currentDocumentId) return;
  // Only autosave if there are endpoints with some state
  const cards = document.querySelectorAll('.ep-card');
  if (!cards.length) return;
  try {
    const state = collectState();
    // Client-side dirty check: skip if state hasn't changed since last save
    const fp = stateFingerprint(state);
    if (fp === lastSavedStateHash) return;
    const saveResp = await fetch('/api/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ state, documentId: currentDocumentId, sessionType: 'autosave' }),
    });
    const saveData = await saveResp.json();
    // Server-side dedup: if state hash matched, nothing was written
    if (saveData.skipped) {
      lastSavedStateHash = fp;
      return;
    }
    lastSavedStateHash = fp;
    // Silently update session number and refresh sidebar
    if (saveData.session) {
      currentSessionNumber = saveData.session.session_number;
      updateDocIndicator();
    }
    refreshSidebar();
  } catch (err) {
    // Silent failure for autosave
  }
}

async function exportAsHtml() {
  const state = collectState();
  // Get the full HTML source of the current page
  let html = document.documentElement.outerHTML;

  // Inline external CSS and JS so the snapshot is self-contained
  try {
    const [cssResp, jsResp] = await Promise.all([
      fetch('/static/style.css').then(r => r.text()),
      fetch('/static/app.js').then(r => r.text()),
    ]);
    // Replace <link rel="stylesheet" href="/static/style.css"> with inline <style>
    html = html.replace(/<link[^>]*href="\/static\/style\.css"[^>]*>/, `<style>\n${cssResp}\n</style>`);
    // Replace <script src="/static/app.js"></script> with inline <script>
    html = html.replace(/<script[^>]*src="\/static\/app\.js"[^>]*><\/script>/, `<script>\n${jsResp}\n<\/script>`);
  } catch (e) {
    // If fetch fails (e.g. offline), proceed with external refs
    console.warn('Could not inline CSS/JS for snapshot:', e);
  }

  // Inject the snapshot data as a script block before the closing </head>
  const snapshotScript = `<script>var DD_SNAPSHOT = ${JSON.stringify(state)};<\/script>`;
  html = html.replace('</head>', snapshotScript + '\n</head>');
  // Update the title to include context
  const src = state.title || state.specSource || 'manual';
  const ts = new Date().toISOString().slice(0, 10);
  html = html.replace(/<title>Drift Detector[^<]*<\/title>/, `<title>Drift Detector - ${escHtml(src)} - ${ts}</title>`);
  // Download
  const blob = new Blob(['<!DOCTYPE html>\n' + html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const tsFile = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  a.href = url;
  a.download = `drift-snapshot-${tsFile}.html`;
  a.click();
  URL.revokeObjectURL(url);
}

function importSession(input) {
  if (!input.files.length) return;
  const file = input.files[0];
  const name = file.name.toLowerCase();
  if (name.endsWith('.html') || name.endsWith('.htm')) {
    handleDropHtml(file);
  } else if (name.endsWith('.json')) {
    handleDropJson(file);
  } else {
    showDropToast('Unsupported file type. Expected .json or .html', true);
  }
  input.value = '';
}

// ── Drag & drop import ──
let dropDepth = 0;  // track nested dragenter/dragleave pairs
const overlay = document.getElementById('dropOverlay');
const toast = document.getElementById('dropToast');

function showDropToast(msg, isError) {
  toast.textContent = msg;
  toast.className = 'drop-toast ' + (isError ? 'error' : 'ok');
  toast.style.display = 'block';
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { toast.style.display = 'none'; }, 3500);
}

document.addEventListener('dragenter', e => {
  e.preventDefault();
  dropDepth++;
  if (dropDepth === 1) overlay.classList.add('active');
});
document.addEventListener('dragleave', e => {
  e.preventDefault();
  dropDepth--;
  if (dropDepth <= 0) { dropDepth = 0; overlay.classList.remove('active'); }
});
document.addEventListener('dragover', e => { e.preventDefault(); });
document.addEventListener('drop', e => {
  e.preventDefault();
  dropDepth = 0;
  overlay.classList.remove('active');

  const file = e.dataTransfer.files && e.dataTransfer.files[0];
  if (!file) return;
  const name = file.name.toLowerCase();

  if (name.endsWith('.html') || name.endsWith('.htm')) {
    handleDropHtml(file);
  } else if (name.endsWith('.json')) {
    handleDropJson(file);
  } else {
    showDropToast('Unsupported file type. Expected .json or .html', true);
  }
});

function handleDropHtml(file) {
  const reader = new FileReader();
  reader.onload = function(e) {
    const html = e.target.result;
    // Extract DD_SNAPSHOT from the embedded script
    const match = html.match(/var\s+DD_SNAPSHOT\s*=\s*(\{[\s\S]*?\});\s*<\/script>/);
    if (!match) {
      showDropToast('No snapshot data found in HTML file', true);
      return;
    }
    try {
      const snapshot = JSON.parse(match[1]);
      if (!snapshot.endpoints || !Array.isArray(snapshot.endpoints)) {
        showDropToast('HTML snapshot has no endpoints', true);
        return;
      }
      restoreState(snapshot);
      const src = snapshot.specSource || file.name;
      const when = snapshot.savedAt ? ' (' + snapshot.savedAt.slice(0, 19).replace('T', ' ') + ')' : '';
      showBreadcrumb('snapshot: ' + src + when);
      showDropToast('Loaded snapshot: ' + file.name, false);
    } catch (err) {
      showDropToast('Failed to parse snapshot: ' + err.message, true);
    }
  };
  reader.readAsText(file);
}

function handleDropJson(file) {
  const reader = new FileReader();
  reader.onload = function(e) {
    let data;
    try {
      data = JSON.parse(e.target.result);
    } catch (err) {
      showDropToast('Invalid JSON: ' + err.message, true);
      return;
    }

    // Session export: has endpoints array
    if (data.endpoints && Array.isArray(data.endpoints)) {
      restoreState(data);
      showBreadcrumb(data.specSource || file.name);
      showDropToast('Loaded session: ' + file.name, false);
      return;
    }

    // OpenAPI spec: has openapi/swagger field, or has paths object
    if (data.openapi || data.swagger || data.paths) {
      const fd = new FormData();
      fd.append('file', file);
      openLoaderModal();
      loadSpec(fd, file.name);
      showDropToast('Loading OpenAPI spec: ' + file.name, false);
      return;
    }

    // Unknown JSON
    showDropToast('Unrecognized JSON. Expected a session export or OpenAPI spec.', true);
  };
  reader.readAsText(file);
}

// ── Misc ──
window.addEventListener('scroll', () => {
  document.getElementById('backToTop').style.display = window.scrollY > 400 ? 'flex' : 'none';
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeLoaderModal(); closeSchemaDiffModal(); } });

// ── Init: seed host fields from server config (env vars) ──
fetch('/api/config').then(r => r.json()).then(cfg => {
  if (cfg.host_a) document.getElementById('hostA').placeholder = cfg.host_a;
  if (cfg.host_b) document.getElementById('hostB').placeholder = cfg.host_b;
}).catch(() => {}); // ignore if server not running (static file open)

// ── Init: restore from embedded snapshot, or load last document from DB, or start fresh ──
if (typeof DD_SNAPSHOT !== 'undefined' && DD_SNAPSHOT && DD_SNAPSHOT.endpoints) {
  restoreState(DD_SNAPSHOT);
  const src = DD_SNAPSHOT.specSource || 'snapshot';
  const when = DD_SNAPSHOT.savedAt ? ' (' + DD_SNAPSHOT.savedAt.slice(0, 19).replace('T', ' ') + ')' : '';
  showBreadcrumb('snapshot: ' + src + when);
  refreshSidebar();
} else {
  // Check DB for existing documents; load most recent if available
  fetch('/api/documents').then(r => r.json()).then(data => {
    if (data.documents && data.documents.length) {
      // Load the most recently updated document's latest session
      const mostRecent = data.documents[0]; // already sorted by updated_at DESC
      fetch(`/api/documents/${mostRecent.id}`).then(r => r.json()).then(docData => {
        if (docData.sessions && docData.sessions.length) {
          const latest = docData.sessions[docData.sessions.length - 1];
          loadSavedSession(mostRecent.id, latest.session_number);
        } else {
          addEndpoint();
          refreshSidebar();
        }
      }).catch(() => { addEndpoint(); refreshSidebar(); });
    } else {
      addEndpoint();
      refreshSidebar();
    }
  }).catch(() => {
    // Server not running or no DB; start fresh
    addEndpoint();
  });
}

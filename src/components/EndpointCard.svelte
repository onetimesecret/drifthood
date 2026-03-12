<script>
  import KvPairs from './KvPairs.svelte';
  import FieldInputs from './FieldInputs.svelte';
  import ResultDisplay from './ResultDisplay.svelte';
  import { CT, CT_CYCLE, ctInfo } from '../../lib/content-type.js';
  import { apiCompare } from '../../lib/api.js';
  import { setNestedValue, flattenObj } from '../../lib/params.js';
  import { stripOpIdPrefix } from '../../lib/format.js';
  import { toDiffPath } from '../../lib/format.js';
  import { updateEndpoint, removeEndpoint } from '../stores/endpoints.svelte.js';
  import { session } from '../stores/session.svelte.js';

  let { endpoint } = $props();

  // Derived state
  let ct = $derived(ctInfo(endpoint.contentType));
  let hasBodyFields = $derived(endpoint.cardFields?.fields?.length > 0);
  let hasPathParams = $derived(endpoint.cardFields?.path_fields?.length > 0);
  let hasQueryFields = $derived(endpoint.cardFields?.query_fields?.length > 0);
  let hasAnyFields = $derived(hasBodyFields || hasPathParams || hasQueryFields);
  let fromSpec = $derived(hasAnyFields || (endpoint.label && endpoint.label.includes('_')));
  let shortLabel = $derived(stripOpIdPrefix(endpoint.label));

  let showKvPairs = $derived(
    ct !== CT.json && !(endpoint.fieldsMode === 'on' && hasBodyFields)
  );
  let showFields = $derived(endpoint.fieldsMode === 'on' && hasAnyFields);
  let showBodyInput = $derived(!showKvPairs && !(endpoint.fieldsMode === 'on' && hasBodyFields));
  let hasResult = $derived(endpoint.result != null || endpoint.state === 'running');

  let stateClass = $derived(
    endpoint.state === 'done-drift' ? 'state-drift'
    : endpoint.state === 'done-ok' ? 'state-ok'
    : endpoint.state === 'running' ? 'state-running'
    : ''
  );

  let kvType = $derived(ct === CT.query ? 'query' : 'form');

  function toggleCt() {
    const curKey = ct === CT.query ? 'query' : ct === CT.form ? 'form' : 'json';
    const idx = CT_CYCLE.indexOf(curKey);
    const nextKey = CT_CYCLE[(idx + 1) % CT_CYCLE.length];
    const next = CT[nextKey];
    updateEndpoint(endpoint.id, { contentType: next.value });
  }

  function toggleFieldsMode() {
    if (endpoint.fieldsMode === 'on') {
      // Switching OFF: assemble body from field values if body fields exist
      const updates = { fieldsMode: 'off' };
      if (hasBodyFields) {
        updates.body = assembleBodyFromFields();
      }
      updateEndpoint(endpoint.id, updates);
    } else {
      // Switching ON
      updateEndpoint(endpoint.id, { fieldsMode: 'on' });
    }
  }

  function assembleBodyFromFields() {
    const info = endpoint.cardFields;
    if (!info || !info.fields.length) return '';
    const fv = endpoint.fieldValues || {};
    const obj = {};
    for (const f of info.fields) {
      if (f.nested) continue;
      const val = fv[f.path];
      if (val === undefined || val === '') continue;
      setNestedValue(obj, f.path, val);
    }
    if (endpoint.contentType === 'application/json') {
      return JSON.stringify(obj, null, 2);
    } else {
      const flat = flattenObj(obj);
      return Object.entries(flat).map(([k, v]) => `${k}=${v}`).join('&');
    }
  }

  function readEndpoint() {
    let body = endpoint.body || null;

    // If in fields mode with body fields, assemble from field inputs
    if (endpoint.fieldsMode === 'on' && hasBodyFields) {
      body = assembleBodyFromFields() || null;
    }

    // Substitute path template variables from field inputs
    let path = endpoint.path;
    const info = endpoint.cardFields;
    if (info && info.path_fields.length) {
      const fv = endpoint.fieldValues || {};
      for (const pf of info.path_fields) {
        const val = fv[pf.path] || '';
        path = path.replace(`{${pf.name}}`, encodeURIComponent(val));
      }
    }

    return {
      method: endpoint.method,
      label: endpoint.label || endpoint.path,
      path,
      body,
      content_type: endpoint.contentType || 'query',
      group: endpoint.group || null,
    };
  }

  async function runOne() {
    updateEndpoint(endpoint.id, { state: 'running', result: null });

    try {
      const ep = readEndpoint();
      const ignorePaths = session.ignorePaths.length
        ? session.ignorePaths.map(toDiffPath)
        : null;

      const r = await apiCompare({
        label: ep.label,
        method: ep.method,
        path: ep.path,
        body: ep.body,
        content_type: ep.content_type,
        group: ep.group,
        host_a: session.hostA,
        host_b: session.hostB,
        auth_a: session.authA || null,
        auth_b: session.authB || null,
        ignore_paths: ignorePaths,
      });

      // Attach request body/content_type for display
      r.request_body = ep.body;
      r.request_content_type = ep.content_type;

      updateEndpoint(endpoint.id, {
        state: r.has_drift ? 'done-drift' : 'done-ok',
        result: r,
      });
    } catch (err) {
      updateEndpoint(endpoint.id, {
        state: 'done-drift',
        result: {
          has_drift: true,
          error: err.message,
          diff: {},
          response_a: { status: null, headers: {}, body: null, elapsed_ms: null },
          response_b: { status: null, headers: {}, body: null, elapsed_ms: null },
        },
      });
    }
  }

  function remove() {
    removeEndpoint(endpoint.id);
  }
</script>

<div class="ep-card {stateClass}">
  <div class="ep-config">
    <select
      value={endpoint.method}
      onchange={(e) => updateEndpoint(endpoint.id, { method: e.target.value })}
    >
      <option>GET</option>
      <option>POST</option>
      <option>PUT</option>
      <option>DELETE</option>
    </select>

    <input
      type="text"
      class="path-input"
      placeholder="/api/v1/status"
      value={endpoint.path}
      oninput={(e) => updateEndpoint(endpoint.id, { path: e.target.value })}
    />

    {#if showBodyInput}
      <input
        type="text"
        class="body-input"
        placeholder={ct.placeholder}
        value={endpoint.body}
        oninput={(e) => updateEndpoint(endpoint.id, { body: e.target.value })}
        style={ct.cls === 'json' ? 'border-color:var(--accent)' : ''}
      />
    {/if}

    <span
      class="ct-toggle {ct.cls}"
      onclick={toggleCt}
      title="query / form / json"
    >{ct.label}</span>

    {#if hasAnyFields}
      <span
        class="ep-fields-toggle"
        class:active={endpoint.fieldsMode === 'on'}
        onclick={toggleFieldsMode}
        title="Toggle per-field inputs"
      >FIELDS</span>
    {/if}

    {#if fromSpec}
      <span class="group-tag" title={endpoint.label}>{shortLabel}</span>
    {:else}
      <input
        type="text"
        class="label-input"
        placeholder="label"
        value={endpoint.label}
        oninput={(e) => updateEndpoint(endpoint.id, { label: e.target.value })}
      />
    {/if}

    {#if endpoint.group}
      <span class="group-tag">{endpoint.group}</span>
    {/if}

    <button class="ep-run-btn" onclick={runOne} title="Run this endpoint">
      {#if endpoint.state === 'running'}
        <span class="spinner"></span>
      {:else}
        run
      {/if}
    </button>
    <button class="remove-btn" onclick={remove} title="Remove">&times;</button>
  </div>

  {#if showKvPairs}
    <KvPairs {endpoint} type={kvType} />
  {/if}

  {#if showFields}
    <FieldInputs {endpoint} />
  {/if}

  {#if hasResult}
    {#if endpoint.state === 'running' && !endpoint.result}
      <div class="ep-result">
        <div class="ep-result-header">
          <span class="spinner"></span>
          <span style="color:var(--accent);font-size:0.85em">Running...</span>
        </div>
      </div>
    {:else}
      <ResultDisplay {endpoint} />
    {/if}
  {/if}
</div>

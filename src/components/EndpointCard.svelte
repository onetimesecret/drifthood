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
  import { session, getEnvA, getEnvB } from '../stores/session.svelte.js';

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

  let stateBorder = $derived(
    endpoint.state === 'done-drift' ? 'border-red/40'
    : endpoint.state === 'done-ok' ? 'border-green/20'
    : endpoint.state === 'running' ? 'border-accent/30'
    : 'border-edge'
  );

  let ctClasses = $derived(
    ct.cls === 'json' ? 'text-accent border-accent'
    : ct.cls === 'form' ? 'text-yellow border-yellow'
    : 'text-text-dim border-edge'
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

      const envA = getEnvA();
      const envB = getEnvB();
      const r = await apiCompare({
        label: ep.label,
        method: ep.method,
        path: ep.path,
        body: ep.body,
        content_type: ep.content_type,
        group: ep.group,
        host_a: envA?.baseUrl || '',
        host_b: envB?.baseUrl || '',
        auth_a: envA?.auth || null,
        auth_b: envB?.auth || null,
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

<div class="bg-surface border {stateBorder} rounded-lg mb-2 overflow-hidden transition-colors duration-200">
  <div class="flex gap-2 items-center px-3 py-2">
    <select
      class="bg-bg border border-edge text-text-primary px-2 py-1 rounded text-[0.85em] font-mono w-[80px]"
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
      class="bg-bg border border-edge text-text-primary px-2 py-1 rounded text-[0.85em] font-mono flex-1 min-w-[180px]"
      placeholder="/api/v1/status"
      value={endpoint.path}
      oninput={(e) => updateEndpoint(endpoint.id, { path: e.target.value })}
    />

    {#if showBodyInput}
      <input
        type="text"
        class="bg-bg border text-text-primary px-2 py-1 rounded text-[0.85em] font-mono flex-[1.5] min-w-[180px] {ct.cls === 'json' ? 'border-accent' : 'border-edge'}"
        placeholder={ct.placeholder}
        value={endpoint.body}
        oninput={(e) => updateEndpoint(endpoint.id, { body: e.target.value })}
      />
    {/if}

    <button
      class="text-[0.65em] font-mono px-[7px] py-[3px] rounded cursor-pointer border bg-bg whitespace-nowrap min-w-[48px] text-center select-none uppercase tracking-wider {ctClasses}"
      type="button"
      onclick={toggleCt}
      title="query / form / json"
    >{ct.label}</button>

    {#if hasAnyFields}
      <button
        type="button"
        class="text-[0.65em] font-mono px-[7px] py-[3px] rounded cursor-pointer border border-edge bg-bg whitespace-nowrap select-none {endpoint.fieldsMode === 'on' ? 'text-purple border-purple' : 'text-text-dim'}"
        onclick={toggleFieldsMode}
        title="Toggle per-field inputs"
      >FIELDS</button>
    {/if}

    {#if fromSpec}
      <span class="text-[0.6em] text-text-dim font-mono bg-bg px-1.5 py-0.5 rounded-sm border border-edge" title={endpoint.label}>{shortLabel}</span>
    {:else}
      <input
        type="text"
        class="bg-bg border border-edge text-text-primary px-2 py-1 rounded text-[0.85em] font-mono w-[140px]"
        placeholder="label"
        value={endpoint.label}
        oninput={(e) => updateEndpoint(endpoint.id, { label: e.target.value })}
      />
    {/if}

    {#if endpoint.group}
      <span class="text-[0.6em] text-text-dim font-mono bg-bg px-1.5 py-0.5 rounded-sm border border-edge">{endpoint.group}</span>
    {/if}

    <button class="bg-transparent border border-edge text-text-dim cursor-pointer text-[0.75em] px-2 py-[3px] rounded font-mono hover:text-accent hover:border-accent" onclick={runOne} title="Run this endpoint">
      {#if endpoint.state === 'running'}
        <span class="inline-block w-3 h-3 border-2 border-edge border-t-accent rounded-full animate-spin"></span>
      {:else}
        run
      {/if}
    </button>
    <button class="bg-transparent border-none text-text-dim cursor-pointer text-[1.1em] px-1.5 py-0.5 rounded hover:text-red hover:bg-red/10" onclick={remove} title="Remove">&times;</button>
  </div>

  {#if showFields}
    <FieldInputs {endpoint} />
  {/if}

  {#if showKvPairs}
    <KvPairs {endpoint} type={kvType} />
  {/if}

  {#if hasResult}
    {#if endpoint.state === 'running' && !endpoint.result}
      <div class="border-t border-edge">
        <div class="flex items-center gap-2.5 px-3 py-2 text-[0.85em]">
          <span class="inline-block w-3 h-3 border-2 border-edge border-t-accent rounded-full animate-spin"></span>
          <span class="text-accent text-[0.85em]">Running...</span>
        </div>
      </div>
    {:else}
      <ResultDisplay {endpoint} />
    {/if}
  {/if}
</div>

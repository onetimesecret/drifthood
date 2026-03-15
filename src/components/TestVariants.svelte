<script>
  import { apiCompare } from '../../lib/api.js';
  import { toDiffPath } from '../../lib/format.js';
  import { session, getEnvA, getEnvB } from '../stores/session.svelte.js';
  import { setNestedValue, flattenObj } from '../../lib/params.js';

  let { endpoint, onvariantresult } = $props();

  let variants = $state([]);
  let running = $state(false);
  let generated = $state(false);

  let hasFields = $derived(
    endpoint.cardFields?.fields?.length > 0
  );

  function generateVariants() {
    if (!hasFields) return;
    const fields = endpoint.cardFields.fields;
    const fv = endpoint.fieldValues || {};
    const newVariants = [];

    for (const f of fields) {
      if (f.nested) continue;

      // Variant 1: omit required fields
      if (f.required) {
        newVariants.push({
          id: crypto.randomUUID(),
          type: 'omit-required',
          label: `Omit required: ${f.name}`,
          field: f,
          fieldValues: buildWithout(fv, f.path),
          state: 'idle',
          result: null,
        });
      }

      // Variant 2: invalid enum value
      if (f.enum && f.enum.length > 0) {
        newVariants.push({
          id: crypto.randomUUID(),
          type: 'invalid-enum',
          label: `Invalid enum: ${f.name}`,
          field: f,
          fieldValues: { ...fv, [f.path]: '__INVALID_ENUM_VALUE__' },
          state: 'idle',
          result: null,
        });
      }

      // Variant 3: out-of-range for integer/number fields
      if ((f.type === 'integer' || f.type === 'number') && f.min != null) {
        newVariants.push({
          id: crypto.randomUUID(),
          type: 'below-min',
          label: `Below min (${f.min}): ${f.name}`,
          field: f,
          fieldValues: { ...fv, [f.path]: String(f.min - 1) },
          state: 'idle',
          result: null,
        });
      }
      if ((f.type === 'integer' || f.type === 'number') && f.max != null) {
        newVariants.push({
          id: crypto.randomUUID(),
          type: 'above-max',
          label: `Above max (${f.max}): ${f.name}`,
          field: f,
          fieldValues: { ...fv, [f.path]: String(f.max + 1) },
          state: 'idle',
          result: null,
        });
      }
    }

    variants = newVariants;
    generated = true;
  }

  function buildWithout(fv, excludePath) {
    const copy = { ...fv };
    delete copy[excludePath];
    return copy;
  }

  function assembleBody(fieldValues) {
    const info = endpoint.cardFields;
    if (!info || !info.fields.length) return '';
    const obj = {};
    for (const f of info.fields) {
      if (f.nested) continue;
      const val = fieldValues[f.path];
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

  async function runVariant(variant) {
    variant.state = 'running';
    variant.result = null;

    try {
      let path = endpoint.path;
      const info = endpoint.cardFields;
      if (info && info.path_fields.length) {
        for (const pf of info.path_fields) {
          const val = variant.fieldValues[pf.path] || endpoint.fieldValues?.[pf.path] || '';
          path = path.replace(`{${pf.name}}`, encodeURIComponent(val));
        }
      }

      const body = assembleBody(variant.fieldValues) || null;

      // Pass response_schema to the backend; it derives ignore paths automatically
      const response_schema = (info && info.response_fields && Object.keys(info.response_fields).length > 0)
        ? info.response_fields
        : null;

      const envA = getEnvA();
      const envB = getEnvB();
      const ignorePaths = session.ignorePaths.length
        ? session.ignorePaths.map(toDiffPath)
        : null;

      const r = await apiCompare({
        label: `${endpoint.label} [${variant.label}]`,
        method: endpoint.method,
        path,
        body,
        content_type: endpoint.contentType || 'query',
        group: endpoint.group || null,
        host_a: envA?.baseUrl || '',
        host_b: envB?.baseUrl || '',
        auth_a: envA?.auth || null,
        auth_b: envB?.auth || null,
        ignore_paths: ignorePaths,
        response_schema,
      });

      variant.result = r;
      variant.state = r.has_drift ? 'done-drift' : 'done-ok';

      if (onvariantresult) {
        onvariantresult(variant, r);
      }
    } catch (err) {
      variant.state = 'done-drift';
      variant.result = { has_drift: true, error: err.message };
    }
  }

  async function runAll() {
    running = true;
    for (const v of variants) {
      await runVariant(v);
    }
    running = false;
  }

  function clear() {
    variants = [];
    generated = false;
  }
</script>

{#if hasFields}
  <div class="px-3 py-1.5 border-t border-edge">
    <div class="flex items-center gap-2 mb-1.5">
      <span class="text-[0.65em] uppercase tracking-wider text-text-dim">Test Variants</span>
      {#if !generated}
        <button
          class="text-[0.65em] font-mono px-[7px] py-[3px] rounded cursor-pointer border border-edge bg-bg text-purple hover:border-purple"
          onclick={generateVariants}
        >Generate</button>
      {:else}
        <button
          class="text-[0.65em] font-mono px-[7px] py-[3px] rounded cursor-pointer border border-edge bg-bg text-accent hover:border-accent"
          onclick={runAll}
          disabled={running}
        >{running ? 'Running...' : 'Run All'}</button>
        <button
          class="text-[0.65em] font-mono px-[7px] py-[3px] rounded cursor-pointer border border-edge bg-bg text-text-dim hover:text-red hover:border-red"
          onclick={clear}
        >Clear</button>
        <span class="text-[0.65em] text-text-dim font-mono">{variants.length} variants</span>
      {/if}
    </div>

    {#if generated && variants.length > 0}
      <div class="max-h-[200px] overflow-y-auto">
        {#each variants as v}
          <div class="flex items-center gap-2 py-0.5 text-[0.75em] font-mono">
            <span class="w-2 h-2 rounded-full shrink-0
              {v.state === 'done-ok' ? 'bg-green' : v.state === 'done-drift' ? 'bg-red' : v.state === 'running' ? 'bg-accent animate-pulse' : 'bg-edge'}">
            </span>
            <span class="text-[0.8em] px-1 py-px rounded bg-bg border border-edge text-text-dim uppercase">{v.type}</span>
            <span class="text-text-primary flex-1 truncate">{v.label}</span>
            {#if v.state === 'idle'}
              <button
                class="text-[0.7em] px-1.5 py-px rounded bg-transparent border border-edge text-text-dim cursor-pointer hover:text-accent hover:border-accent"
                onclick={() => runVariant(v)}
              >run</button>
            {:else if v.state === 'running'}
              <span class="inline-block w-3 h-3 border-2 border-edge border-t-accent rounded-full animate-spin"></span>
            {:else if v.result}
              <span class="text-[0.7em] {v.result.has_drift ? 'text-red' : 'text-green'}">
                {v.result.has_drift ? 'DRIFT' : 'OK'}
              </span>
              {#if v.result.response_a?.status != null}
                <span class="text-[0.65em] text-text-dim">{v.result.response_a.status}/{v.result.response_b?.status}</span>
              {/if}
            {/if}
          </div>
        {/each}
      </div>
    {:else if generated}
      <div class="text-[0.75em] text-text-dim py-1">No variants to generate (no required, enum, or bounded fields).</div>
    {/if}
  </div>
{/if}

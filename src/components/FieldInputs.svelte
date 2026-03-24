<!-- src/components/FieldInputs.svelte -->

<script>
  import { escHtml } from '../../lib/format.js';
  import { updateEndpoint } from '../stores/endpoints.svelte.js';

  let { endpoint } = $props();

  // Initialize fieldValues from endpoint or empty object
  let fieldValues = $state({});
  let syncing = false;

  // Sync from endpoint.fieldValues when it changes externally
  $effect(() => {
    const fv = endpoint.fieldValues;
    if (syncing) return;
    fieldValues = fv ? { ...fv } : {};
  });

  // Initialize defaults from field definitions
  $effect(() => {
    const info = endpoint.cardFields;
    if (!info) return;
    const allFields = [
      ...(info.path_fields || []),
      ...(info.query_fields || []),
      ...(info.fields || []),
    ];
    let changed = false;
    for (const f of allFields) {
      if (f.nested) continue;
      if (!(f.path in fieldValues)) {
        const defaultVal = f.const != null ? String(f.const)
          : f.example != null ? String(f.example)
          : '';
        fieldValues[f.path] = defaultVal;
        changed = true;
      }
    }
    if (changed) {
      syncToStore();
    }
  });

  function onFieldChange(path, value) {
    fieldValues[path] = value;
    syncToStore();
  }

  function syncToStore() {
    syncing = true;
    updateEndpoint(endpoint._localId, { fieldValues: { ...fieldValues } });
    queueMicrotask(() => { syncing = false; });
  }

  function indentClass(field) {
    const depth = (field.path.match(/\./g) || []).length;
    if (depth >= 2) return ' pl-8';
    if (depth >= 1) return ' pl-4';
    return '';
  }

  let pathFields = $derived(endpoint.cardFields?.path_fields || []);
  let queryFields = $derived(endpoint.cardFields?.query_fields || []);
  let bodyFields = $derived(endpoint.cardFields?.fields || []);
</script>

{#snippet fieldGroup(fields, label)}
  {#if fields.length > 0}
    <div class="text-[0.65em] uppercase tracking-wider text-text-dim my-1.5 mb-1">
      {label}
    </div>
    {#each fields as f}
      {#if f.nested}
        <div class="flex items-center gap-1.5 mb-1 text-[0.8em] font-mono{indentClass(f)}">
          <span class="min-w-[140px] text-text-dim font-semibold flex items-center gap-1">{f.path}</span>
          <span class="text-[0.85em] text-text-dim min-w-[52px]">object</span>
        </div>
      {:else}
        <div class="flex items-center gap-1.5 mb-1 text-[0.8em] font-mono{indentClass(f)}">
          <span class="min-w-[140px] text-text-primary flex items-center gap-1">
            {#if f.required}<span class="w-1.5 h-1.5 rounded-full bg-red shrink-0" title="required"></span>{/if}
            {f.name}
          </span>
          <span class="text-[0.85em] text-text-dim min-w-[52px]">{f.type}</span>

          {#if f.const != null}
            <span class="text-yellow text-[0.85em]">{String(f.const)}</span>
            <input type="hidden" value={String(f.const)} />
          {:else if f.enum}
            <select
              class="bg-bg border border-edge text-text-primary px-1.5 py-0.5 rounded font-mono text-[0.9em] flex-1 min-w-[100px]"
              value={fieldValues[f.path] ?? ''}
              onchange={(e) => onFieldChange(f.path, e.target.value)}
              data-testid="field-{f.path}-select"
            >
              {#each f.enum as opt}
                <option value={String(opt)} selected={String(opt) === String(fieldValues[f.path])}>{opt}</option>
              {/each}
            </select>
          {:else if f.type === 'boolean'}
            <select
              class="bg-bg border border-edge text-text-primary px-1.5 py-0.5 rounded font-mono text-[0.9em] flex-1 min-w-[100px]"
              value={fieldValues[f.path] ?? 'true'}
              onchange={(e) => onFieldChange(f.path, e.target.value)}
              data-testid="field-{f.path}-bool"
            >
              <option value="true" selected={fieldValues[f.path] === 'true'}>true</option>
              <option value="false" selected={fieldValues[f.path] === 'false'}>false</option>
            </select>
          {:else if f.type === 'integer' || f.type === 'number'}
            <input
              class="bg-bg border border-edge text-text-primary px-1.5 py-0.5 rounded font-mono text-[0.9em] flex-1 min-w-[100px]"
              type="number"
              value={fieldValues[f.path] ?? ''}
              min={f.min ?? undefined}
              max={f.max ?? undefined}
              title={f.description ?? undefined}
              placeholder={f.type}
              oninput={(e) => onFieldChange(f.path, e.target.value)}
              data-testid="field-{f.path}-number"
            />
          {:else}
            <input
              class="bg-bg border border-edge text-text-primary px-1.5 py-0.5 rounded font-mono text-[0.9em] flex-1 min-w-[100px]"
              type="text"
              value={fieldValues[f.path] ?? ''}
              title={f.description ?? undefined}
              placeholder={f.type}
              oninput={(e) => onFieldChange(f.path, e.target.value)}
              data-testid="field-{f.path}-text"
            />
          {/if}
        </div>
      {/if}
    {/each}
  {/if}
{/snippet}

<div class="px-3 py-1.5 pb-2.5 border-t border-edge">
  {@render fieldGroup(pathFields, 'Path Parameters')}
  {@render fieldGroup(queryFields, 'Query Parameters')}
  {@render fieldGroup(bodyFields, 'Request Body')}
</div>

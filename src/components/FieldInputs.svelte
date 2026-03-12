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
    updateEndpoint(endpoint.id, { fieldValues: { ...fieldValues } });
    queueMicrotask(() => { syncing = false; });
  }

  function indentClass(field) {
    const depth = (field.path.match(/\./g) || []).length;
    if (depth >= 2) return ' field-indent-2';
    if (depth >= 1) return ' field-indent-1';
    return '';
  }

  let pathFields = $derived(endpoint.cardFields?.path_fields || []);
  let queryFields = $derived(endpoint.cardFields?.query_fields || []);
  let bodyFields = $derived(endpoint.cardFields?.fields || []);
</script>

{#snippet fieldGroup(fields, label)}
  {#if fields.length > 0}
    <div style="font-size:0.65em;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-dim);margin:6px 0 4px">
      {label}
    </div>
    {#each fields as f}
      {#if f.nested}
        <div class="field-row{indentClass(f)}">
          <span class="field-name nested-parent">{f.path}</span>
          <span class="field-type">object</span>
        </div>
      {:else}
        <div class="field-row{indentClass(f)}">
          <span class="field-name">
            {#if f.required}<span class="req-dot" title="required"></span>{/if}
            {f.name}
          </span>
          <span class="field-type">{f.type}</span>

          {#if f.const != null}
            <span class="field-const">{String(f.const)}</span>
            <input type="hidden" value={String(f.const)} />
          {:else if f.enum}
            <select
              value={fieldValues[f.path] ?? ''}
              onchange={(e) => onFieldChange(f.path, e.target.value)}
            >
              {#each f.enum as opt}
                <option value={String(opt)} selected={String(opt) === String(fieldValues[f.path])}>{opt}</option>
              {/each}
            </select>
          {:else if f.type === 'boolean'}
            <select
              value={fieldValues[f.path] ?? 'true'}
              onchange={(e) => onFieldChange(f.path, e.target.value)}
            >
              <option value="true" selected={fieldValues[f.path] === 'true'}>true</option>
              <option value="false" selected={fieldValues[f.path] === 'false'}>false</option>
            </select>
          {:else if f.type === 'integer' || f.type === 'number'}
            <input
              type="number"
              value={fieldValues[f.path] ?? ''}
              min={f.min ?? undefined}
              max={f.max ?? undefined}
              title={f.description ?? undefined}
              placeholder={f.type}
              oninput={(e) => onFieldChange(f.path, e.target.value)}
            />
          {:else}
            <input
              type="text"
              value={fieldValues[f.path] ?? ''}
              title={f.description ?? undefined}
              placeholder={f.type}
              oninput={(e) => onFieldChange(f.path, e.target.value)}
            />
          {/if}
        </div>
      {/if}
    {/each}
  {/if}
{/snippet}

<div class="ep-fields">
  {@render fieldGroup(pathFields, 'Path Parameters')}
  {@render fieldGroup(queryFields, 'Query Parameters')}
  {@render fieldGroup(bodyFields, 'Request Body')}
</div>

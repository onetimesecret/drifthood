<!-- src/components/IgnoreConfig.svelte -->

<script>
  import { prettifyPath } from '../../lib/format.js';
  import { apiConfig } from '../../lib/api.js';
  import { session } from '../stores/session.svelte.js';
  import { ui } from '../stores/ui.svelte.js';

  let serverDefaults = $state(null);
  let showDefaults = $state(false);

  // Derive textarea content from ignorePaths array
  let textValue = $derived(session.ignorePaths.join('\n'));

  let customCount = $derived(session.ignorePaths.length);

  function onTextInput(e) {
    const lines = e.target.value.split('\n').map(l => l.trim()).filter(Boolean);
    session.ignorePaths = lines;
  }

  function togglePanel() {
    ui.ignoreOpen = !ui.ignoreOpen;
  }

  async function toggleDefaults(e) {
    e.preventDefault();
    if (showDefaults) {
      showDefaults = false;
      return;
    }
    showDefaults = true;
    if (serverDefaults) return;
    try {
      const cfg = await apiConfig();
      serverDefaults = cfg.default_ignore || [];
    } catch {
      serverDefaults = null;
    }
  }
</script>

<div class="mb-5">
  <div class="text-[0.7em] uppercase tracking-widest text-text-dim mb-1 font-semibold cursor-pointer flex items-center gap-1.5 select-none" onclick={togglePanel} role="button" tabindex="0" onkeydown={(e) => e.key === 'Enter' && togglePanel()} data-testid="ignore-config-toggle">
    <span class="text-[0.8em] chevron" class:open={ui.ignoreOpen}>&#9654;</span>
    Ignored Fields
    {#if customCount > 0}
      <span class="text-[0.7em] text-text-dim font-mono ml-auto">({customCount} custom)</span>
    {/if}
  </div>

  <div class="toggle-block" class:open={ui.ignoreOpen}>
    <textarea
      class="bg-bg border border-edge text-text-primary px-2.5 py-2 rounded-md font-mono text-[0.8em] w-full min-h-[80px] resize-y leading-relaxed"
      placeholder={"body.created\nbody.updated\nbody.custid"}
      value={textValue}
      oninput={onTextInput}
      data-testid="ignore-paths-input"
    ></textarea>
    <div class="text-[0.7em] text-text-dim mt-1">
      One path per line in dot notation (e.g. body.created). These fields will be excluded from comparison.
      The server has <button type="button" onclick={toggleDefaults} class="text-accent bg-transparent border-none p-0 font-[inherit] cursor-pointer no-underline" data-testid="btn-toggle-defaults">built-in defaults</button>;
      paths here are added on top.
    </div>

    {#if showDefaults}
      <div class="mt-1.5 px-2 py-1.5 bg-bg border border-edge rounded font-mono text-[0.75em] text-text-dim whitespace-pre-line">
        {#if serverDefaults}
          {serverDefaults.map(prettifyPath).join('\n')}
        {:else}
          (could not load)
        {/if}
      </div>
    {/if}
  </div>
</div>

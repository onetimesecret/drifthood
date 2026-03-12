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

<div class="ignore-config">
  <div class="ignore-label" onclick={togglePanel} role="button" tabindex="0" onkeydown={(e) => e.key === 'Enter' && togglePanel()}>
    <span class="chevron" class:open={ui.ignoreOpen}>&#9654;</span>
    Ignored Fields
    {#if customCount > 0}
      <span class="ignore-count">({customCount} custom)</span>
    {/if}
  </div>

  <div class="ignore-body" class:open={ui.ignoreOpen}>
    <textarea
      placeholder={"body.created\nbody.updated\nbody.custid"}
      value={textValue}
      oninput={onTextInput}
    ></textarea>
    <div class="ignore-hint">
      One path per line in dot notation (e.g. body.created). These fields will be excluded from comparison.
      The server has <button type="button" onclick={toggleDefaults} style="color:var(--accent);background:none;border:none;padding:0;font:inherit;cursor:pointer;text-decoration:none">built-in defaults</button>;
      paths here are added on top.
    </div>

    {#if showDefaults}
      <div style="margin-top:6px;padding:6px 8px;background:var(--bg);border:1px solid var(--border);border-radius:4px;font-family:var(--mono);font-size:0.75em;color:var(--text-dim);white-space:pre-line">
        {#if serverDefaults}
          {serverDefaults.map(prettifyPath).join('\n')}
        {:else}
          (could not load)
        {/if}
      </div>
    {/if}
  </div>
</div>

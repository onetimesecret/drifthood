<script>
  let config = $state(null);
  let error = $state(null);

  async function loadConfig() {
    try {
      const resp = await fetch('/api/config');
      config = await resp.json();
    } catch (err) {
      error = err.message;
    }
  }

  loadConfig();
</script>

<h1>Drift Detector <span style="font-size:0.5em;font-weight:400;opacity:0.5">v0.4.0</span></h1>

{#if error}
  <p style="color: #f85149">Error: {error}</p>
{:else if config}
  <pre style="color: #c9d1d9; background: #161b22; padding: 16px; border-radius: 8px; font-size: 0.85em">{JSON.stringify(config, null, 2)}</pre>
{:else}
  <p style="color: #8b949e">Loading config...</p>
{/if}

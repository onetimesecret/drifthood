<script>
  import { apiTestHost } from '../../lib/api.js';
  import { session, getEnvironment } from '../stores/session.svelte.js';

  let { side, onmanage } = $props();

  let testStatus = $state({ text: 'Test', cls: '' });

  let selectedKey = $derived(side === 'A' ? 'selectedA' : 'selectedB');
  let selectedId = $derived(session[selectedKey]);
  let selectedEnv = $derived(getEnvironment(selectedId));

  function onSelect(e) {
    if (side === 'A') {
      session.selectedA = e.target.value;
    } else {
      session.selectedB = e.target.value;
    }
  }

  async function testHostClick() {
    if (!selectedEnv) return;
    testStatus = { text: '...', cls: '' };
    try {
      const data = await apiTestHost(selectedEnv.baseUrl, selectedEnv.auth);
      if (data.ok) {
        testStatus = { text: `${data.status} ${data.elapsed_ms}ms`, cls: 'ok' };
      } else {
        testStatus = { text: data.error ? 'Error' : `${data.status}`, cls: 'fail' };
      }
    } catch {
      testStatus = { text: 'Error', cls: 'fail' };
    }
    setTimeout(() => {
      testStatus = { text: 'Test', cls: '' };
    }, 5000);
  }
</script>

<div class="flex flex-col gap-1.5 px-3 py-2.5 bg-surface border border-edge rounded-lg flex-1 min-w-[300px]">
  <div class="text-[0.75em] font-semibold text-text-primary mb-0.5 flex items-center gap-2">
    Environment {side}
    <button
      class="ml-auto text-text-dim hover:text-accent cursor-pointer bg-transparent border-none p-0 leading-none"
      onclick={onmanage}
      title="Manage environments"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
        <circle cx="12" cy="12" r="3"/>
      </svg>
    </button>
  </div>

  {#if session.environments.length === 0}
    <div class="text-[0.8em] text-text-dim py-2">
      No environments.
      <button
        class="text-accent hover:underline cursor-pointer bg-transparent border-none p-0 font-inherit text-inherit"
        onclick={onmanage}
      >Add one</button>
    </div>
  {:else}
    <select
      class="bg-surface border border-edge text-text-primary px-2.5 py-1.5 rounded-md font-mono text-[0.85em] w-full"
      value={selectedId}
      onchange={onSelect}
    >
      <option value="" disabled>Select environment...</option>
      {#each session.environments as env (env.id)}
        <option value={env.id}>{env.name || env.baseUrl}</option>
      {/each}
    </select>

    {#if selectedEnv}
      <div class="flex items-center gap-2">
        <span class="text-[0.8em] font-mono text-text-dim truncate flex-1" title={selectedEnv.baseUrl}>
          {selectedEnv.baseUrl}
        </span>
        <button
          class="text-[0.8em] px-2 py-0.5 rounded cursor-pointer bg-transparent border border-edge text-text-dim font-mono ml-auto hover:text-accent hover:border-accent {testStatus.cls === 'ok' ? 'text-green border-green' : ''} {testStatus.cls === 'fail' ? 'text-red border-red' : ''}"
          onclick={testHostClick}
        >{testStatus.text}</button>
      </div>
    {/if}
  {/if}
</div>

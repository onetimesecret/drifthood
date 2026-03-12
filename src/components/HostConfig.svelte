<script>
  import { apiTestHost, apiConfig } from '../../lib/api.js';
  import { session } from '../stores/session.svelte.js';

  let { side } = $props();

  let testStatus = $state({ text: 'Test', cls: '' });
  let placeholderHost = $state('');

  // Load server config defaults for placeholder
  apiConfig().then(cfg => {
    if (side === 'A' && cfg.host_a) placeholderHost = cfg.host_a;
    if (side === 'B' && cfg.host_b) placeholderHost = cfg.host_b;
  }).catch(() => {});

  let hostKey = $derived(side === 'A' ? 'hostA' : 'hostB');
  let authKey = $derived(side === 'A' ? 'authA' : 'authB');
  let memoKey = $derived(side === 'A' ? 'memoA' : 'memoB');

  function effectiveHost() {
    return session[hostKey].trim() || placeholderHost || '';
  }

  async function testHostClick() {
    testStatus = { text: '...', cls: '' };
    try {
      const data = await apiTestHost(effectiveHost(), session[authKey].trim());
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
    Host {side}
    <button
      class="text-[0.8em] px-2 py-0.5 rounded cursor-pointer bg-transparent border border-edge text-text-dim font-mono ml-auto hover:text-accent hover:border-accent {testStatus.cls === 'ok' ? 'text-green border-green' : ''} {testStatus.cls === 'fail' ? 'text-red border-red' : ''}"
      onclick={testHostClick}
    >{testStatus.text}</button>
  </div>

  <div class="flex flex-col gap-0.5">
    <label class="text-[0.7em] text-text-dim uppercase tracking-wider" for="host-url-{side}">URL</label>
    <input
      class="bg-surface border border-edge text-text-primary px-2.5 py-1.5 rounded-md font-mono text-[0.85em] w-full"
      id="host-url-{side}"
      type="text"
      bind:value={session[hostKey]}
      placeholder={placeholderHost || (side === 'A' ? 'http://localhost:10235' : 'http://localhost:10240')}
    />
  </div>

  <div class="flex flex-col gap-0.5">
    <label class="text-[0.7em] text-text-dim uppercase tracking-wider" for="host-auth-{side}">Auth (user:token)</label>
    <input
      class="bg-surface border border-edge text-text-primary px-2.5 py-1.5 rounded-md font-mono text-[0.85em] w-full"
      id="host-auth-{side}"
      type="text"
      bind:value={session[authKey]}
      placeholder="user@example.com:TOKEN"
    />
  </div>

  <div class="flex flex-col gap-0.5">
    <label class="text-[0.7em] text-text-dim uppercase tracking-wider" for="host-memo-{side}">Memo</label>
    <input
      class="bg-surface border border-edge text-text-dim px-2.5 py-1.5 rounded-md font-mono text-[0.85em] w-full italic placeholder:italic"
      id="host-memo-{side}"
      type="text"
      bind:value={session[memoKey]}
      placeholder={side === 'A' ? 'e.g. v3 stable branch' : 'e.g. v4 candidate'}
    />
  </div>
</div>

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

<div class="host-pair">
  <div class="pair-label">
    Host {side}
    <button
      class="host-test-btn {testStatus.cls}"
      onclick={testHostClick}
    >{testStatus.text}</button>
  </div>

  <div class="config-group">
    <label for="host-url-{side}">URL</label>
    <input
      id="host-url-{side}"
      type="text"
      bind:value={session[hostKey]}
      placeholder={placeholderHost || (side === 'A' ? 'http://localhost:10235' : 'http://localhost:10240')}
    />
  </div>

  <div class="config-group">
    <label for="host-auth-{side}">Auth (user:token)</label>
    <input
      id="host-auth-{side}"
      type="text"
      bind:value={session[authKey]}
      placeholder="user@example.com:TOKEN"
    />
  </div>

  <div class="config-group">
    <label for="host-memo-{side}">Memo</label>
    <input
      id="host-memo-{side}"
      type="text"
      class="host-memo"
      bind:value={session[memoKey]}
      placeholder={side === 'A' ? 'e.g. v3 stable branch' : 'e.g. v4 candidate'}
    />
  </div>
</div>

<!-- src/components/TokenGate.svelte -->

<script>
  import { auth, initAuth, setTokenWithKeys, setExtid, clearToken, getToken, getExtid } from '../stores/auth.svelte.js';
  import { apiGenerateToken, apiValidateToken } from '../../lib/api.js';
  import { resetDocuments } from '../stores/documents.svelte.js';
  import { clearEndpoints } from '../stores/endpoints.svelte.js';
  import { resetSession } from '../stores/session.svelte.js';
  import { initVibe, setVibe } from '../stores/vibe.svelte.js';

  let { children } = $props();

  // Local state
  let tokenInput = $state('');
  let rememberMe = $state(false);
  let loading = $state(false);
  let generatedToken = $state(null);
  let validationMessage = $state('');
  let validationError = $state(false);
  let copied = $state(false);
  let copiedBar = $state(false);
  let authReady = $state(false);

  // Initialize auth from storage or URL on mount
  $effect(() => {
    (async () => {
      await initAuth();
      initVibe();
      authReady = true;

      // Check for /s/{extid} in the URL
      const match = window.location.pathname.match(/^\/s\/(.+)/);
      if (match) {
        const urlExtid = decodeURIComponent(match[1]);
        if (!auth.token && !auth.extid) {
          // Extid in URL but no token in storage — user needs to enter their token
        } else if (auth.extid !== urlExtid && auth.token) {
          // Token in storage but URL extid doesn't match — re-derive with correct extid
          await setExtid(urlExtid);
        }
      }
    })();
  });

  // ── Landing page actions ──

  async function handleGenerate() {
    loading = true;
    generatedToken = null;
    validationMessage = '';
    try {
      const data = await apiGenerateToken();
      generatedToken = data.token;
      await setTokenWithKeys(data.token, data.extid, rememberMe);
      history.pushState(null, '', `/s/${encodeURIComponent(data.extid)}`);
      setVibe('new');
    } catch (err) {
      validationMessage = 'Failed to generate token: ' + err.message;
      validationError = true;
    } finally {
      loading = false;
    }
  }

  async function handleLoad() {
    let value = tokenInput.trim();
    if (!value) return;
    loading = true;
    validationMessage = '';
    validationError = false;

    try {
      let extid = null;
      let token = value;

      // Check for combined extid:token format (UUID contains hyphens, token is base64url)
      const colonIdx = value.indexOf(':');
      if (colonIdx > 0) {
        const maybExtid = value.slice(0, colonIdx);
        // UUIDv7 is 36 chars with hyphens
        if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(maybExtid)) {
          extid = maybExtid;
          token = value.slice(colonIdx + 1);
        }
      }

      // If no extid from paste, try URL or storage
      if (!extid) {
        const match = window.location.pathname.match(/^\/s\/(.+)/);
        if (match) {
          extid = decodeURIComponent(match[1]);
        } else {
          extid = getExtid();
        }
      }

      if (!extid) {
        validationMessage = 'Session ID required. Navigate to your /s/{extid} URL, or paste as extid:token.';
        validationError = true;
        return;
      }

      // Derive keys and store
      await setTokenWithKeys(token, extid, rememberMe);

      // Validate with the server (apiFetch now sends derived authKey)
      const data = await apiValidateToken();
      if (data.valid) {
        history.pushState(null, '', `/s/${encodeURIComponent(extid)}`);
        if (data.documentCount > 0) {
          validationMessage = `Found ${data.documentCount} document${data.documentCount === 1 ? '' : 's'} for this token.`;
        } else {
          validationMessage = 'No data found for this token — starting fresh.';
        }
        validationError = false;
      } else {
        validationMessage = 'Invalid token for this session.';
        validationError = true;
        clearToken();
      }
    } catch (err) {
      validationMessage = 'Validation failed: ' + err.message;
      validationError = true;
      clearToken();
    } finally {
      loading = false;
    }
  }

  function handleLoadKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleLoad();
    }
  }

  async function copyToken(token) {
    try {
      await navigator.clipboard.writeText(token);
      copied = true;
      setTimeout(() => { copied = false; }, 2000);
    } catch {
      // Fallback: select + copy not available in all contexts
    }
  }

  async function copyTokenBar() {
    const token = getToken();
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token);
      copiedBar = true;
      setTimeout(() => { copiedBar = false; }, 2000);
    } catch {
      // Silent
    }
  }

  async function handleSignOut() {
    // Server-side cleanup first, while auth credentials are still available
    await clearEndpoints();
    resetSession();
    resetDocuments();
    // Local cleanup — clears auth so no more server calls are possible
    clearToken();
    tokenInput = '';
    generatedToken = null;
    validationMessage = '';
    validationError = false;
    setVibe(null);
    history.pushState(null, '', '/');
  }

  function maskedToken(token) {
    if (!token || token.length < 12) return token || '';
    return token.slice(0, 8) + '...' + token.slice(-4);
  }

  /** Compute placeholder text based on whether we have an extid available */
  function getPlaceholder() {
    const match = window.location.pathname.match(/^\/s\/(.+)/);
    const hasExtid = match || getExtid();
    return hasExtid ? 'Paste your token' : 'Paste as extid:token';
  }
</script>

{#if !authReady}
  <!-- Waiting for key derivation -->
  <div class="flex items-center justify-center min-h-[80vh]">
    <div class="text-text-dim text-[0.85em]">Loading...</div>
  </div>
{:else if auth.token && auth.authKey && !generatedToken}
  <!-- Authenticated: show token bar + children -->
  <div data-testid="token-bar" class="flex items-center gap-3 px-3 py-1.5 bg-surface border-b border-edge text-[0.75em] font-mono -mx-5 -mt-5 mb-4">
    <span class="text-text-dim" title={getToken()}>
      {maskedToken(getToken())}
    </span>
    <button
      data-testid="btn-copy-token"
      class="bg-transparent border border-edge text-text-dim px-2 py-0.5 rounded cursor-pointer text-[0.85em] hover:text-accent hover:border-accent"
      onclick={copyTokenBar}
    >{copiedBar ? 'Copied' : 'Copy'}</button>
    <button
      data-testid="btn-sign-out"
      class="bg-transparent border border-edge text-text-dim px-2 py-0.5 rounded cursor-pointer text-[0.85em] ml-auto hover:text-red hover:border-red"
      onclick={handleSignOut}
    >Sign out</button>
  </div>

  {@render children()}
{:else}
  <!-- Unauthenticated: landing page -->
  <div data-testid="token-gate" class="flex items-center justify-center min-h-[80vh]">
    <div class="w-full max-w-md">
      <h1 class="text-[1.8em] font-semibold text-text-primary text-center mb-8">Drift Detector</h1>

      <!-- Generated token display -->
      {#if generatedToken}
        <div class="bg-surface border border-edge rounded-lg p-5 mb-5">
          <div class="text-[0.8em] font-semibold text-text-primary mb-2">Your token</div>
          <div class="bg-bg border border-edge rounded-md p-3 font-mono text-[0.8em] text-accent break-all mb-3 select-all">
            {generatedToken}
          </div>
          <div class="flex items-center gap-2 mb-3">
            <button
              data-testid="btn-copy-token"
              class="bg-transparent border border-edge text-text-dim px-3 py-1 rounded cursor-pointer text-[0.8em] hover:text-accent hover:border-accent"
              onclick={() => copyToken(generatedToken)}
            >{copied ? 'Copied' : 'Copy'}</button>
          </div>
          <p class="text-[0.75em] text-yellow leading-relaxed">
            Save this token -- it is the only way to access your data later.
          </p>
          <button
            class="mt-4 w-full bg-[#238636] border-[#2ea043] text-white px-4 py-2 rounded-md text-[0.85em] font-medium cursor-pointer hover:bg-[#2ea043]"
            onclick={() => { generatedToken = null; setVibe('fresh'); }}
          >Continue to app</button>
        </div>
      {:else}
        <!-- Start fresh -->
        <div class="bg-surface border border-edge rounded-lg p-5 mb-4">
          <div class="text-[0.8em] font-semibold text-text-primary mb-3">Start fresh</div>
          <button
            data-testid="btn-generate-token"
            class="w-full bg-[#238636] border border-[#2ea043] text-white px-4 py-2.5 rounded-md text-[0.85em] font-medium cursor-pointer hover:bg-[#2ea043] disabled:opacity-50 disabled:cursor-not-allowed"
            onclick={handleGenerate}
            disabled={loading}
          >{loading ? 'Generating...' : 'Generate new token'}</button>
        </div>

        <!-- I have a token -->
        <div class="bg-surface border border-edge rounded-lg p-5 mb-4">
          <div class="text-[0.8em] font-semibold text-text-primary mb-3">I have a token</div>
          <div class="flex gap-2">
            <input
              data-testid="token-input"
              class="flex-1 bg-bg border border-edge text-text-primary px-3 py-2 rounded-md font-mono text-[0.8em] placeholder:text-text-dim"
              type="text"
              placeholder={getPlaceholder()}
              bind:value={tokenInput}
              onkeydown={handleLoadKeydown}
            />
            <button
              data-testid="btn-load-token"
              class="bg-transparent border border-edge text-text-dim px-4 py-2 rounded-md text-[0.85em] font-medium cursor-pointer hover:text-accent hover:border-accent disabled:opacity-50 disabled:cursor-not-allowed"
              onclick={handleLoad}
              disabled={loading || !tokenInput.trim()}
            >{loading ? '...' : 'Load'}</button>
          </div>
        </div>

        <!-- Validation message -->
        {#if validationMessage}
          <div class="text-[0.8em] px-3 py-2 rounded-md mb-4 {validationError ? 'text-red bg-red/10 border border-red/20' : 'text-green bg-green/10 border border-green/20'}">
            {validationMessage}
          </div>
        {/if}
      {/if}

      <!-- Remember me -->
      <label class="flex items-center gap-2 text-[0.8em] text-text-dim cursor-pointer px-1">
        <input
          data-testid="checkbox-remember"
          type="checkbox"
          class="accent-accent"
          bind:checked={rememberMe}
        />
        Remember me on this device
      </label>
    </div>
  </div>
{/if}

<script>
  import { auth, initAuth, setToken, clearToken, getToken } from '../stores/auth.svelte.js';
  import { apiGenerateToken, apiValidateToken } from '../../lib/api.js';
  import { resetDocuments } from '../stores/documents.svelte.js';

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

  // Initialize auth from storage on mount
  $effect(() => {
    initAuth();
  });

  // ── Landing page actions ──

  async function handleGenerate() {
    loading = true;
    generatedToken = null;
    validationMessage = '';
    try {
      const data = await apiGenerateToken();
      generatedToken = data.token;
      setToken(data.token, rememberMe);
    } catch (err) {
      validationMessage = 'Failed to generate token: ' + err.message;
      validationError = true;
    } finally {
      loading = false;
    }
  }

  async function handleLoad() {
    const value = tokenInput.trim();
    if (!value) return;
    loading = true;
    validationMessage = '';
    validationError = false;
    try {
      setToken(value, rememberMe);
      const data = await apiValidateToken();
      if (data.documentCount > 0) {
        validationMessage = `Found ${data.documentCount} document${data.documentCount === 1 ? '' : 's'} for this token.`;
        validationError = false;
      } else {
        validationMessage = 'No data found for this token — starting fresh.';
        validationError = false;
      }
    } catch (err) {
      validationMessage = 'Validation failed: ' + err.message;
      validationError = true;
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

  function handleSignOut() {
    clearToken();
    resetDocuments();
    // Reset local state
    tokenInput = '';
    generatedToken = null;
    validationMessage = '';
    validationError = false;
  }

  function maskedToken(token) {
    if (!token || token.length < 12) return token || '';
    return token.slice(0, 8) + '...' + token.slice(-4);
  }
</script>

{#if auth.token && !generatedToken}
  <!-- Authenticated: show token bar + children -->
  <div class="flex items-center gap-3 px-3 py-1.5 bg-surface border-b border-edge text-[0.75em] font-mono -mx-5 -mt-5 mb-4">
    <span class="text-text-dim" title={getToken()}>
      {maskedToken(getToken())}
    </span>
    <button
      class="bg-transparent border border-edge text-text-dim px-2 py-0.5 rounded cursor-pointer text-[0.85em] hover:text-accent hover:border-accent"
      onclick={copyTokenBar}
    >{copiedBar ? 'Copied' : 'Copy'}</button>
    <button
      class="bg-transparent border border-edge text-text-dim px-2 py-0.5 rounded cursor-pointer text-[0.85em] ml-auto hover:text-red hover:border-red"
      onclick={handleSignOut}
    >Sign out</button>
  </div>

  {@render children()}
{:else}
  <!-- Unauthenticated: landing page -->
  <div class="flex items-center justify-center min-h-[80vh]">
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
              class="bg-transparent border border-edge text-text-dim px-3 py-1 rounded cursor-pointer text-[0.8em] hover:text-accent hover:border-accent"
              onclick={() => copyToken(generatedToken)}
            >{copied ? 'Copied' : 'Copy'}</button>
          </div>
          <p class="text-[0.75em] text-yellow leading-relaxed">
            Save this token -- it is the only way to access your data later.
          </p>
          <button
            class="mt-4 w-full bg-[#238636] border-[#2ea043] text-white px-4 py-2 rounded-md text-[0.85em] font-medium cursor-pointer hover:bg-[#2ea043]"
            onclick={() => { generatedToken = null; }}
          >Continue to app</button>
        </div>
      {:else}
        <!-- Start fresh -->
        <div class="bg-surface border border-edge rounded-lg p-5 mb-4">
          <div class="text-[0.8em] font-semibold text-text-primary mb-3">Start fresh</div>
          <button
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
              class="flex-1 bg-bg border border-edge text-text-primary px-3 py-2 rounded-md font-mono text-[0.8em] placeholder:text-text-dim"
              type="text"
              placeholder="Paste your token"
              bind:value={tokenInput}
              onkeydown={handleLoadKeydown}
            />
            <button
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
          type="checkbox"
          class="accent-accent"
          bind:checked={rememberMe}
        />
        Remember me on this device
      </label>
    </div>
  </div>
{/if}

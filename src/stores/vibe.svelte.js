// src/stores/vibe.svelte.js

//
// Vibes codify progressive disclosure as a URL-level concept:
//   new   → just generated a token, showing the "save this" screen
//   fresh → first time in the app, reduced UI surface
//   (none) → full experience, no training wheels
//
// Any component can import `vibe` to read the current vibe and adapt.
// Use setVibe() / clearVibe() to progress through the sequence;
// they update both the reactive state and the URL in lockstep.

export const vibe = $state({ current: null });

/** Read the vibe from the current URL. Call once on app init. */
export function initVibe() {
  const params = new URLSearchParams(window.location.search);
  vibe.current = params.get('v') || null;
}

/** Transition to a new vibe, updating the URL to match. */
export function setVibe(v) {
  vibe.current = v;
  const url = new URL(window.location.href);
  if (v) {
    url.searchParams.set('v', v);
  } else {
    url.searchParams.delete('v');
  }
  history.replaceState(null, '', url.pathname + url.search);
}

/** Clear the vibe entirely (graduate to full UI). */
export function clearVibe() {
  setVibe(null);
}

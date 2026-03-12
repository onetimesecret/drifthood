<script>
  let { open, onclose, maxWidth = '700px', children } = $props();

  function onKeydown(e) {
    if (e.key === 'Escape' && open) onclose();
  }

  $effect(() => {
    if (open) {
      document.addEventListener('keydown', onKeydown);
      return () => document.removeEventListener('keydown', onKeydown);
    }
  });
</script>

<div class="toggle-flex fixed inset-0 bg-black/60 z-50 items-center justify-center" class:open={open} role="presentation" onclick={(e) => e.target === e.currentTarget && onclose()} onkeydown={(e) => { if (e.key === 'Escape') onclose(); }}>
  <div class="bg-surface border border-edge rounded-xl w-[90%] max-h-[80vh] flex flex-col shadow-[0_16px_48px_rgba(0,0,0,0.5)]" role="dialog" aria-modal="true" style="max-width:{maxWidth}">
    {@render children()}
  </div>
</div>

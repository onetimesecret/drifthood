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

<div class="modal-overlay" class:open={open} onclick={(e) => e.target === e.currentTarget && onclose()}>
  <div class="modal" style="max-width:{maxWidth}">
    {@render children()}
  </div>
</div>

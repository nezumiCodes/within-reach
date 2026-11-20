<script lang="ts">
  /** One live region for every search message, so screen readers announce them (NFR-13). */
  let { text, onRetry }: { text: string; onRetry: (() => void) | null } = $props()
</script>

<div class="messages">
  <p role="status" class:has-text={text !== ''}>{text}</p>
  {#if onRetry}
    <button type="button" onclick={onRetry}>Try again</button>
  {/if}
</div>

<style>
  .messages {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
    min-height: 1.5rem;
  }
  p {
    margin: 0;
  }
  p.has-text {
    font-weight: 600;
  }
  button {
    font: inherit;
    padding: 0.25rem 0.75rem;
    border: 2px solid var(--accent);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    cursor: pointer;
  }
</style>

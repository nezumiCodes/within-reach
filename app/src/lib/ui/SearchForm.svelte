<script lang="ts">
  /** The postcode box. Nothing is submitted anywhere: the form only calls onSearch. */
  let { busy, onSearch }: { busy: boolean; onSearch: (postcode: string) => void } = $props()
  let value = $state('')

  function submit(event: SubmitEvent): void {
    event.preventDefault()
    onSearch(value)
  }
</script>

<form class="search" novalidate onsubmit={submit}>
  <label for="postcode">Postcode</label>
  <div class="row">
    <input
      id="postcode"
      type="text"
      autocomplete="off"
      autocapitalize="characters"
      spellcheck="false"
      inputmode="text"
      bind:value
    />
    <button type="submit" disabled={busy}>Search</button>
  </div>
</form>

<style>
  .search {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  label {
    font-weight: 600;
  }
  .row {
    display: flex;
    gap: 0.5rem;
  }
  input {
    font: inherit;
    padding: 0.4rem 0.6rem;
    width: 10rem;
    border: 2px solid var(--text);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    text-transform: uppercase;
  }
  button {
    font: inherit;
    font-weight: 600;
    padding: 0.4rem 1rem;
    border: 2px solid var(--accent);
    border-radius: 4px;
    background: var(--accent);
    color: var(--on-accent);
    cursor: pointer;
  }
  button:disabled {
    opacity: 0.7;
    cursor: progress;
  }
</style>

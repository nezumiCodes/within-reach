<script lang="ts">
  /** The numbered list, closest first, with the hours-unknown group and the hidden summary. */
  import type { Result } from '../engine/results'
  import ResultEntry from './ResultEntry.svelte'

  let {
    shown,
    unknownStartsAt,
    summary,
    total,
    selected,
    onSelect,
    onShowMore,
  }: {
    shown: Result[]
    unknownStartsAt: number | null
    summary: string | null
    total: number
    selected: number | null
    onSelect: (idx: number) => void
    onShowMore: () => void
  } = $props()

  const split = $derived(unknownStartsAt ?? shown.length)
  const confirmed = $derived(shown.slice(0, split))
  const unknown = $derived(shown.slice(split))
</script>

{#if total === 0}
  <p class="empty">No pharmacies nearby match these filters.</p>
{/if}

{#if confirmed.length > 0}
  <ol class="results">
    {#each confirmed as result, i (result.pharmacy.idx)}
      <ResultEntry {result} number={i + 1} selected={selected === result.pharmacy.idx} {onSelect} />
    {/each}
  </ol>
{/if}

{#if unknownStartsAt !== null && unknown.length > 0}
  <h3 class="group">Opening hours not known</h3>
  <p class="note">
    Scottish and Welsh pharmacy lists don't include opening hours, so these pharmacies can't be
    filtered.
  </p>
  <ol class="results">
    {#each unknown as result, i (result.pharmacy.idx)}
      <ResultEntry
        {result}
        number={split + i + 1}
        selected={selected === result.pharmacy.idx}
        {onSelect}
      />
    {/each}
  </ol>
{/if}

{#if shown.length < total}
  <button type="button" class="more" onclick={onShowMore}>Show 10 more</button>
{/if}

{#if summary}
  <p class="summary" data-testid="hidden-summary">{summary}</p>
{/if}

<style>
  .results {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .group {
    margin: 1.25rem 0 0.25rem;
  }
  .note,
  .summary,
  .empty {
    color: var(--muted);
  }
  .more {
    font: inherit;
    margin: 0.75rem 0;
    padding: 0.4rem 1rem;
    border: 2px solid var(--accent);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    cursor: pointer;
  }
</style>

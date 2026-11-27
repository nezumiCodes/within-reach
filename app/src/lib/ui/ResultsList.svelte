<script lang="ts">
  /** The numbered list, closest first, with the not-known group and the hidden summary. */
  import type { Result } from '../engine/results'
  import ResultEntry from './ResultEntry.svelte'

  let {
    shown,
    unknownStartsAt,
    unknownOf,
    activeServices,
    serviceNames,
    summary,
    emptyMessage,
    total,
    selected,
    onSelect,
    onHighlight,
    onShowMore,
  }: {
    shown: Result[]
    unknownStartsAt: number | null
    /** What the not-known pharmacies can't answer. */
    unknownOf: Set<'hours' | 'services'>
    /** Names of the service filters that are on. */
    activeServices: string[]
    /** Service key to name, for the tags on each entry. */
    serviceNames: Record<string, string>
    summary: string | null
    emptyMessage: string
    total: number
    selected: number | null
    onSelect: (idx: number) => void
    onHighlight: (idx: number | null) => void
    onShowMore: () => void
  } = $props()

  const split = $derived(unknownStartsAt ?? shown.length)
  const confirmed = $derived(shown.slice(0, split))
  const unknown = $derived(shown.slice(split))
  const unknownCopy = $derived.by(() => {
    if (unknownOf.has('services') && unknownOf.has('hours'))
      return {
        heading: 'Opening hours and services not known',
        text: "Scottish and Welsh pharmacy lists don't include opening hours or services, so these pharmacies can't be filtered.",
      }
    if (unknownOf.has('services'))
      return {
        heading: `${activeServices.join(' and ')} not known`,
        text: "Scottish and Welsh pharmacy lists don't include services, so these pharmacies can't be filtered.",
      }
    return {
      heading: 'Opening hours not known',
      text: "Scottish and Welsh pharmacy lists don't include opening hours, so these pharmacies can't be filtered.",
    }
  })
</script>

{#if total === 0}
  <p class="empty">{emptyMessage}</p>
{/if}

{#if confirmed.length > 0}
  <ol class="results" data-testid="matches">
    {#each confirmed as result, i (result.pharmacy.idx)}
      <ResultEntry
        {result}
        number={i + 1}
        {serviceNames}
        selected={selected === result.pharmacy.idx}
        {onSelect}
        {onHighlight}
      />
    {/each}
  </ol>
{/if}

{#if unknownStartsAt !== null && unknown.length > 0}
  <h3 class="group">{unknownCopy.heading}</h3>
  <p class="note">{unknownCopy.text}</p>
  <ol class="results">
    {#each unknown as result, i (result.pharmacy.idx)}
      <ResultEntry
        {result}
        number={split + i + 1}
        {serviceNames}
        selected={selected === result.pharmacy.idx}
        {onSelect}
        {onHighlight}
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

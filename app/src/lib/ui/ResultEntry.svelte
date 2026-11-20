<script lang="ts">
  /** One pharmacy in the list. Everything the map shows is here too (the list is the main view). */
  import { DAY_NAMES, formatDayHours, hasAnyHours, travelLine } from '../engine/format'
  import type { Result } from '../engine/results'

  let {
    result,
    number,
    selected,
    onSelect,
    onHighlight,
  }: {
    result: Result
    number: number
    selected: boolean
    onSelect: (idx: number) => void
    onHighlight: (idx: number | null) => void
  } = $props()
  const p = $derived(result.pharmacy)
</script>

<li
  class="entry"
  class:selected
  data-testid="result"
  data-ph-idx={p.idx}
  data-walk-m={result.walkM ?? ''}
  data-drive-s={result.driveS ?? ''}
  onmouseenter={() => onHighlight(p.idx)}
  onmouseleave={() => onHighlight(null)}
  onfocusin={() => onHighlight(p.idx)}
  onfocusout={() => onHighlight(null)}
>
  <span class="number" data-testid="number" aria-hidden="true">{number}</span>
  <div class="body">
    <h3><span class="visually-hidden">{number}. </span>{p.name}</h3>
    <p class="address">{p.address}, {p.postcode}</p>
    <p class="travel">{travelLine(result)}</p>
    {#if hasAnyHours(p.days)}
      <details>
        <summary>Opening hours</summary>
        <table>
          <tbody>
            {#each DAY_NAMES as day, i (day)}
              <tr><th scope="row">{day}</th><td>{formatDayHours(p.days[i])}</td></tr>
            {/each}
          </tbody>
        </table>
      </details>
    {:else}
      <p class="no-hours">No opening hours included</p>
    {/if}
    <button type="button" class="link" onclick={() => onSelect(p.idx)}>Show on map</button>
  </div>
</li>

<style>
  .entry {
    display: flex;
    gap: 0.75rem;
    padding: 0.75rem 0.5rem;
    border-bottom: 1px solid var(--rule);
  }
  .entry.selected {
    background: var(--highlight);
  }
  .number {
    flex: none;
    width: 1.75rem;
    height: 1.75rem;
    border-radius: 50%;
    background: var(--accent);
    color: var(--on-accent);
    font-weight: 700;
    display: grid;
    place-items: center;
    font-size: 0.9rem;
  }
  .body {
    min-width: 0;
  }
  h3 {
    margin: 0;
    font-size: 1.05rem;
  }
  p {
    margin: 0.15rem 0;
  }
  .address,
  .no-hours {
    color: var(--muted);
  }
  table {
    border-collapse: collapse;
    margin: 0.25rem 0;
  }
  th {
    text-align: left;
    font-weight: normal;
    padding-right: 1rem;
  }
  summary {
    cursor: pointer;
    color: var(--link);
  }
  .link {
    font: inherit;
    background: none;
    border: none;
    padding: 0;
    color: var(--link);
    text-decoration: underline;
    cursor: pointer;
  }
</style>

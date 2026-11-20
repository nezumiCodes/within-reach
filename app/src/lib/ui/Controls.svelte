<script lang="ts">
  /** Sort and filter controls (Phase 2 design, section 5). */
  import type { FilterKey, Filters } from '../engine/hours'
  import type { SortMode } from '../engine/results'

  let { mode = $bindable(), filters = $bindable() }: { mode: SortMode; filters: Filters } = $props()

  const FILTER_LABELS: [FilterKey, string][] = [
    ['saturday', 'Open Saturday'],
    ['sunday', 'Open Sunday'],
    ['late', 'Open late'],
  ]
  const active = $derived(FILTER_LABELS.filter(([key]) => filters[key]).map(([, label]) => label))
</script>

<div class="controls">
  <fieldset>
    <legend>Sort</legend>
    <label><input type="radio" name="sort" value="walk" bind:group={mode} /> Walking</label>
    <label><input type="radio" name="sort" value="drive" bind:group={mode} /> Driving</label>
  </fieldset>
  <fieldset>
    <legend>Filters</legend>
    {#each FILTER_LABELS as [key, label] (key)}
      <label><input type="checkbox" bind:checked={filters[key]} /> {label}</label>
    {/each}
  </fieldset>
  <p class="active">
    Sorted by {mode === 'walk' ? 'walking distance' : 'driving time'}.
    {#if active.length > 0}<span>Filters: {active.join(', ')}</span>{/if}
  </p>
</div>

<style>
  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem 1.5rem;
    align-items: flex-start;
  }
  fieldset {
    border: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem 1rem;
  }
  legend {
    font-weight: 600;
    padding: 0;
    margin-bottom: 0.25rem;
  }
  label {
    white-space: nowrap;
  }
  .active {
    flex-basis: 100%;
    margin: 0;
    color: var(--muted);
  }
</style>

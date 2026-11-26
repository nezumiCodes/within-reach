<script lang="ts">
  /** Sort and filter controls (Phase 2 design, section 5). */
  import type { Filters, HoursKey } from '../engine/hours'
  import type { SortMode } from '../engine/results'

  let {
    mode = $bindable(),
    filters = $bindable(),
    services,
  }: { mode: SortMode; filters: Filters; services: { key: string; name: string }[] } = $props()

  const FILTER_LABELS: [HoursKey, string][] = [
    ['saturday', 'Open Saturday'],
    ['sunday', 'Open Sunday'],
    ['late', 'Open late'],
  ]
  const active = $derived([
    ...FILTER_LABELS.filter(([key]) => filters[key]).map(([, label]) => label),
    ...services.filter((s) => filters.services[s.key]).map((s) => s.name),
  ])
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
  {#if services.length > 0}
    <fieldset>
      <legend>Services</legend>
      {#each services as service (service.key)}
        <label>
          <input
            type="checkbox"
            bind:checked={filters.services[service.key]}
            aria-describedby="services-note"
          />
          {service.name}
        </label>
      {/each}
      <p class="note" id="services-note">
        From pharmacies' NHS website listings. Some pharmacies that offer it don't list it. Phone to
        check.
      </p>
    </fieldset>
  {/if}
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
  .note {
    flex-basis: 100%;
    margin: 0;
    color: var(--muted);
  }
  .active {
    flex-basis: 100%;
    margin: 0;
    color: var(--muted);
  }
</style>

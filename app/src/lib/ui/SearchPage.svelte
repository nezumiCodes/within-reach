<script lang="ts">
  /**
   * The public search page (Phase 2 design, section 5). All state lives in memory: nothing is
   * written to the URL, history or browser storage (NFR-04).
   */
  import { onMount, tick } from 'svelte'
  import { DownloadError, IntegrityError, SessionFiles } from '../data/files'
  import { formatRelease, loadManifest, type Manifest } from '../data/release'
  import { Searcher, type SearchOutcome } from '../data/search'
  import { anyFilter, NO_FILTERS, type Filters } from '../engine/hours'
  import { groupByFilters, hiddenSummary, sortResults, type SortMode } from '../engine/results'
  import Controls from './Controls.svelte'
  import MapPanel from './MapPanel.svelte'
  import Messages from './Messages.svelte'
  import ResultsList from './ResultsList.svelte'
  import SearchForm from './SearchForm.svelte'

  const PAGE = 10

  let manifest = $state<Manifest | null>(null)
  let searcher: Searcher | null = null
  let files = $state<SessionFiles | null>(null)
  let outcome = $state<SearchOutcome | null>(null)
  let failure = $state<'download' | 'integrity' | null>(null)
  let busy = $state(false)
  let lastQuery = ''
  let mode = $state<SortMode>('walk')
  let filters = $state<Filters>({ ...NO_FILTERS, services: {} })
  let visible = $state(PAGE)
  let selected = $state<number | null>(null)
  let highlighted = $state<number | null>(null)

  /** A pin was clicked: select its entry and bring it into view (the list may be off screen). */
  async function selectFromMap(idx: number): Promise<void> {
    selected = idx
    await tick()
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
    document
      .querySelector(`[data-testid="result"][data-ph-idx="${idx}"]`)
      ?.scrollIntoView({ block: 'nearest', behavior: reduce ? 'auto' : 'smooth' })
  }

  async function ready(): Promise<Searcher> {
    if (searcher) return searcher
    manifest = manifest ?? (await loadManifest())
    if (manifest === null) throw new DownloadError('no data release')
    files = new SessionFiles(manifest.release)
    searcher = new Searcher(manifest, files)
    return searcher
  }

  async function run(query: string): Promise<void> {
    lastQuery = query
    busy = true
    failure = null
    try {
      const next = await (await ready()).search(query)
      outcome = next
      visible = PAGE
      selected = null
    } catch (error) {
      outcome = null
      failure = error instanceof IntegrityError ? 'integrity' : 'download'
    } finally {
      busy = false
    }
  }

  onMount(async () => {
    manifest = await loadManifest()
  })

  const found = $derived(outcome?.kind === 'found' ? outcome : null)
  const sorted = $derived(found ? sortResults(found.results, mode) : [])
  const grouped = $derived(groupByFilters(sorted, filters))
  const filtering = $derived(anyFilter(filters))
  const listed = $derived([...grouped.matches, ...grouped.unknown])
  const shown = $derived(listed.slice(0, visible))
  const unknownStartsAt = $derived(
    filtering && grouped.unknown.length > 0 && grouped.matches.length < shown.length
      ? grouped.matches.length
      : null,
  )
  const serviceNames = $derived(
    Object.fromEntries((manifest?.services ?? []).map((s) => [s.key, s.name])),
  )
  const summary = $derived(hiddenSummary(grouped, mode, serviceNames))

  const message = $derived.by(() => {
    if (busy) return 'Searching…'
    if (failure === 'download')
      return "Couldn't download the pharmacy data. Check your connection and try again."
    if (failure === 'integrity')
      return "The downloaded data didn't pass its integrity check, so it hasn't been used."
    if (outcome?.kind === 'invalid') return 'Enter a full UK postcode, for example CH2 3JQ.'
    if (outcome?.kind === 'northern-ireland')
      return "Northern Ireland isn't covered yet. Within Reach covers England, Scotland and Wales."
    if (outcome?.kind === 'not-found')
      return `We couldn't find ${outcome.postcode}. Check it's correct and still in use.`
    return ''
  })
</script>

<div class="page">
  <header>
    <div class="title">
      <h1>Within Reach</h1>
      {#if manifest}<p class="release">Data from {formatRelease(manifest.release)}</p>{/if}
    </div>
    <SearchForm {busy} onSearch={run} />
  </header>

  <main>
    <Messages text={message} onRetry={failure && !busy ? () => run(lastQuery) : null} />

    {#if found}
      <div class="results-layout">
        <section class="map-column" aria-label="Map">
          {#if files}
            {#key found.area.code}
              <MapPanel
                {files}
                area={found.area}
                origin={{ lat: found.lat, lon: found.lon }}
                {shown}
                {selected}
                {highlighted}
                onSelect={selectFromMap}
              />
            {/key}
          {/if}
        </section>
        <section class="list-column" aria-labelledby="results-heading">
          <h2 id="results-heading">Pharmacies near {found.postcode}</h2>
          <Controls bind:mode bind:filters />
          <ResultsList
            {shown}
            {unknownStartsAt}
            {summary}
            total={listed.length}
            {selected}
            onSelect={(idx) => (selected = idx)}
            onHighlight={(idx) => (highlighted = idx)}
            onShowMore={() => (visible += PAGE)}
          />
        </section>
      </div>
    {:else if !outcome && !failure}
      <p class="intro">
        Type a postcode to see the nearest pharmacies on a map and in a list. The search runs in
        your browser: the postcode is never sent anywhere.
      </p>
    {/if}
  </main>

  <footer>
    {#each manifest?.attribution ?? [] as line (line)}<p>{line}</p>{/each}
  </footer>
</div>

<style>
  .page {
    max-width: 80rem;
    margin: 0 auto;
    padding: 1rem 1.25rem 2rem;
  }
  header {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    justify-content: space-between;
    gap: 1rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--rule);
    margin-bottom: 1rem;
  }
  h1 {
    margin: 0;
    font-size: 1.75rem;
  }
  .release {
    margin: 0;
    color: var(--muted);
  }
  h2 {
    font-size: 1.25rem;
    margin: 0 0 0.75rem;
  }
  .results-layout {
    display: grid;
    gap: 1.5rem;
    margin-top: 1rem;
  }
  .map-column:empty {
    display: none;
  }
  @media (min-width: 900px) {
    .results-layout {
      grid-template-columns: 3fr 2fr;
      align-items: start;
    }
    .map-column {
      position: sticky;
      top: 1rem;
    }
  }
  footer {
    margin-top: 2.5rem;
    font-size: 0.875rem;
    color: var(--muted);
  }
  footer p {
    margin: 0.25rem 0;
  }
</style>

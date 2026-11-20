<script lang="ts">
  /**
   * The area map: a visual extra next to the list, which carries all the same information
   * (NFR-13). If WebGL is missing or the map can't load, the list still works.
   */
  import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl'
  import { onDestroy, onMount } from 'svelte'
  import type { SessionFiles } from '../data/files'
  import { loadAreaMap } from '../data/map-file'
  import type { AreaEntry } from '../data/release'
  import type { Result } from '../engine/results'
  import { pinsGeoJson } from './map-style'

  let {
    files,
    area,
    origin,
    shown,
    selected,
    highlighted,
    onSelect,
  }: {
    files: SessionFiles
    area: AreaEntry
    origin: { lat: number; lon: number }
    shown: Result[]
    selected: number | null
    highlighted: number | null
    onSelect: (idx: number) => void
  } = $props()

  let container: HTMLDivElement
  let map: MapLibreMap | null = null
  let mapState = $state<'loading' | 'ready' | 'unavailable'>('loading')
  let received = $state(0)
  let lastFit = ''
  // Set when this panel is replaced (another area searched) before its map finished loading.
  let destroyed = false

  function hasWebGL(): boolean {
    try {
      const canvas = document.createElement('canvas')
      return (canvas.getContext('webgl2') ?? canvas.getContext('webgl')) !== null
    } catch {
      return false
    }
  }

  function fit(): void {
    if (!map) return
    const points = [origin, ...shown.map((r) => r.pharmacy)]
    const key = points.map((p) => `${p.lat},${p.lon}`).join(';')
    if (key === lastFit) return
    lastFit = key
    const lons = points.map((p) => p.lon)
    const lats = points.map((p) => p.lat)
    map.fitBounds([Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)], {
      padding: 40,
      maxZoom: 15,
      animate: false,
    })
  }

  function draw(): void {
    if (!map) return
    const source = map.getSource('pins') as GeoJSONSource | undefined
    source?.setData(pinsGeoJson(shown, origin, selected, highlighted))
    fit()
  }

  onMount(async () => {
    if (!area.map || !hasWebGL()) {
      mapState = 'unavailable'
      return
    }
    try {
      const data = await loadAreaMap(files, area.map, (n) => (received = n))
      if (destroyed) return
      const lib = await import('./map-lib')
      if (destroyed) return
      const created = await lib.createMap(container, area.code, data)
      if (destroyed) {
        created.remove()
        return
      }
      map = created
      // Exposed for the browser tests, which need pin positions on the canvas.
      Object.defineProperty(container, 'maplibre', { value: created, configurable: true })
      map.on('click', 'pins', (event) => {
        const idx = event.features?.[0]?.properties?.idx
        if (typeof idx === 'number') onSelect(idx)
      })
      map.on('mouseenter', 'pins', () => map && (map.getCanvas().style.cursor = 'pointer'))
      map.on('mouseleave', 'pins', () => map && (map.getCanvas().style.cursor = ''))
      mapState = 'ready'
      draw()
    } catch {
      map?.remove()
      map = null
      if (!destroyed) mapState = 'unavailable'
    }
  })

  onDestroy(() => {
    destroyed = true
    map?.remove()
  })

  $effect(() => {
    void [shown, origin, selected, highlighted]
    if (mapState === 'ready') draw()
  })

  $effect(() => {
    if (mapState !== 'ready' || !map || selected === null) return
    const pin = shown.find((r) => r.pharmacy.idx === selected)
    if (pin) map.easeTo({ center: [pin.pharmacy.lon, pin.pharmacy.lat], duration: 300 })
  })
</script>

<div
  class="map"
  role="group"
  aria-label={`Map of the postcode and the ${shown.length} pharmacies listed`}
  data-testid="map"
  data-map-state={mapState}
  data-pin-count={shown.length}
  data-selected-idx={selected ?? ''}
  data-highlighted-idx={highlighted ?? ''}
>
  <div class="canvas" bind:this={container}></div>
  {#if mapState === 'loading'}
    <div class="overlay">
      <p>Loading map…</p>
      <progress max={area.map?.bytes ?? 1} value={received}></progress>
    </div>
  {:else if mapState === 'unavailable'}
    <div class="overlay">
      <p>Map not available on this device. The list below has all the details.</p>
    </div>
  {/if}
</div>

<style>
  .map {
    position: relative;
    height: 40vh;
    min-height: 16rem;
    border: 1px solid var(--rule);
    border-radius: 4px;
    overflow: hidden;
    background: #f2efe9;
  }
  @media (min-width: 900px) {
    .map {
      height: calc(100vh - 2rem);
      max-height: 48rem;
    }
  }
  .canvas {
    position: absolute;
    inset: 0;
  }
  .overlay {
    position: absolute;
    inset: 0;
    display: grid;
    place-content: center;
    gap: 0.5rem;
    padding: 1rem;
    text-align: center;
    background: var(--bg);
    color: var(--text);
  }
  .overlay p {
    margin: 0;
  }
</style>

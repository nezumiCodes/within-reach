/**
 * Everything that needs MapLibre, loaded only after the first search so the first page stays
 * small. The worker is a separate same-origin file (CSP worker-src 'self'); tiles come from the
 * in-memory PMTiles file through a registered pmtiles:// protocol, never from the network.
 */
import * as maplibregl from 'maplibre-gl'
import type { Map as MapLibreMap, StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { PMTiles, Protocol } from 'pmtiles'
import { MemorySource } from '../data/map-file'
import { buildStyle } from './map-style'

let protocol: Protocol | null = null

function registerProtocol(): Protocol {
  if (protocol) return protocol
  maplibregl.setWorkerUrl(workerUrl)
  protocol = new Protocol()
  // pmtiles' tilev4 is the MapLibre v4+ protocol handler; its declared return type is looser
  // than MapLibre's (data: unknown), so it needs a cast.
  maplibregl.addProtocol('pmtiles', protocol.tilev4 as unknown as maplibregl.AddProtocolAction)
  return protocol
}

export async function createMap(
  container: HTMLElement,
  areaCode: string,
  data: ArrayBuffer,
): Promise<MapLibreMap> {
  const key = `area-${areaCode}`
  const tiles = new PMTiles(new MemorySource(key, data))
  registerProtocol().add(tiles)
  const header = await tiles.getHeader()
  const response = await fetch('/map/style.json')
  if (!response.ok) throw new Error(`map style: HTTP ${response.status}`)
  const base = (await response.json()) as StyleSpecification
  const style = buildStyle(
    base,
    `pmtiles://${key}`,
    `${location.origin}/map/glyphs/{fontstack}/{range}.pbf`,
  )
  const map = new maplibregl.Map({
    container,
    style,
    bounds: [header.minLon, header.minLat, header.maxLon, header.maxLat],
    maxZoom: 16,
    minZoom: Math.max(0, header.minZoom),
    attributionControl: { compact: false },
    cooperativeGestures: false,
  })
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
  await new Promise<void>((resolve, reject) => {
    map.once('load', () => resolve())
    map.once('error', (event) =>
      reject((event as unknown as { error?: Error }).error ?? new Error('map failed to load')),
    )
  })
  return map
}

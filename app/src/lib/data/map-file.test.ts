import { PMTiles } from 'pmtiles'
import { describe, expect, it } from 'vitest'
import { IntegrityError, SessionFiles } from './files'
import { loadAreaMap, MemorySource } from './map-file'
import type { MapRef } from './release'
import fixtureManifest from '../../../tests/fixtures/data/2026-11/manifest.json?raw'
import { fakeFetch, refFor } from './test-helpers'

const RELEASE = '2026-11'

async function mapFixture(whole: Uint8Array, chunk: number) {
  const files = new Map<string, Uint8Array>()
  const parts = []
  for (let start = 0, n = 0; start < whole.length; start += chunk, n++) {
    const data = whole.slice(start, start + chunk)
    const path = `areas/A/map.pmtiles.${String(n).padStart(3, '0')}`
    files.set(path, data)
    parts.push(await refFor(path, data))
  }
  const map: MapRef = { ...(await refFor('', whole)), parts }
  const served = fakeFetch(RELEASE, files)
  return { map, served, files: new SessionFiles(RELEASE, served.fetch) }
}

/** Reads a fixture file in Node (tests only; the app never touches the file system). */
async function readFixture(path: string): Promise<Uint8Array> {
  const fs = await import(/* @vite-ignore */ ['node', 'fs/promises'].join(':'))
  const url = new URL(`../../../tests/fixtures/data/2026-11/${path}`, import.meta.url)
  return new Uint8Array(await fs.readFile(url))
}

describe('loadAreaMap', () => {
  it('joins parts in order and checks the whole hash', async () => {
    const whole = Uint8Array.from({ length: 10 }, (_, i) => i)
    const { map, files } = await mapFixture(whole, 4)
    expect(new Uint8Array(await loadAreaMap(files, map))).toEqual(whole)
  })

  it('rejects a whole-file hash mismatch even when parts are valid', async () => {
    const { map, files } = await mapFixture(new Uint8Array(10), 4)
    await expect(loadAreaMap(files, { ...map, sha256: '0'.repeat(64) })).rejects.toBeInstanceOf(
      IntegrityError,
    )
  })

  it('reports progress up to the total', async () => {
    const { map, files } = await mapFixture(new Uint8Array(1000), 300)
    const seen: [number, number][] = []
    await loadAreaMap(files, map, (received, total) => seen.push([received, total]))
    expect(seen.at(-1)).toEqual([1000, 1000])
  })

  it('downloads each part once, whole', async () => {
    const { map, files, served } = await mapFixture(new Uint8Array(10), 4)
    await loadAreaMap(files, map)
    await loadAreaMap(files, map)
    expect(served.calls.map((c) => c.url)).toEqual(map.parts.map((p) => `/data/2026-11/${p.path}`))
  })
})

describe('MemorySource', () => {
  it('serves byte ranges', async () => {
    const source = new MemorySource('k', Uint8Array.from({ length: 10 }, (_, i) => i).buffer)
    expect(source.getKey()).toBe('k')
    expect(new Uint8Array((await source.getBytes(2, 3)).data)).toEqual(Uint8Array.from([2, 3, 4]))
  })

  it('reads the fixture map header', async () => {
    const manifest = JSON.parse(fixtureManifest)
    const area = manifest.areas.find((a: { code: string }) => a.code === 'E06000050')
    const parts = await Promise.all(
      area.map.parts.map((p: { path: string }) => readFixture(p.path)),
    )
    const whole = new Uint8Array(parts.reduce((n, p) => n + p.length, 0))
    parts.reduce((offset, p) => (whole.set(p, offset), offset + p.length), 0)
    const header = await new PMTiles(new MemorySource('area-E06000050', whole.buffer)).getHeader()
    expect(header.maxZoom).toBe(13)
    expect(header.minLon).toBeLessThan(-2.89)
    expect(header.maxLat).toBeGreaterThan(53.2)
  })
})

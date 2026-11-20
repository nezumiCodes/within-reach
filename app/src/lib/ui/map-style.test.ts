import { describe, expect, it } from 'vitest'
import style from '../../../public/map/style.json?raw'
import { parseDay } from '../engine/hours'
import type { Result } from '../engine/results'
import type { Pharmacy } from '../engine/types'
import { buildStyle, pinsGeoJson } from './map-style'

const base = JSON.parse(style)

function result(idx: number, lon: number, lat: number): Result {
  const pharmacy: Pharmacy = {
    idx,
    nation: 'England',
    code: `F${idx}`,
    name: `P${idx}`,
    address: '',
    postcode: 'CH1 1AA',
    lat,
    lon,
    days: Array.from({ length: 7 }, () => parseDay('')),
  }
  return { pharmacy, straightM: 0, walkM: 0, walkS: 0, driveS: 0 }
}

describe('buildStyle', () => {
  it('sets the source url and glyphs only', () => {
    const built = buildStyle(
      base,
      'pmtiles://area-E06000050',
      'https://x/map/glyphs/{fontstack}/{range}.pbf',
    )
    expect(built.sources.area).toEqual({ ...base.sources.area, url: 'pmtiles://area-E06000050' })
    expect(built.glyphs).toBe('https://x/map/glyphs/{fontstack}/{range}.pbf')
    expect(built.layers).toEqual(base.layers)
    expect(base.sources.area.url).not.toBe('pmtiles://area-E06000050') // input untouched
  })

  it('uses only self-hosted fonts and credits OpenStreetMap', () => {
    const fonts = new Set(
      base.layers.flatMap(
        (l: { layout?: Record<string, unknown> }) =>
          (l.layout?.['text-font'] as string[] | undefined) ?? [],
      ),
    )
    expect([...fonts].sort()).toEqual(['Noto Sans Medium', 'Noto Sans Regular'])
    expect(base.sources.area.attribution).toContain('© OpenStreetMap contributors')
  })
})

describe('pinsGeoJson', () => {
  it('numbers pins from 1 and marks the origin, the selected and the highlighted pin', () => {
    const fc = pinsGeoJson(
      [result(7, -2.9, 53.2), result(3, -2.8, 53.1)],
      { lat: 53.19, lon: -2.89 },
      3,
      7,
    )
    expect(fc.features.map((f) => f.properties)).toEqual([
      { kind: 'origin' },
      { kind: 'pharmacy', n: 1, idx: 7, selected: false, highlighted: true },
      { kind: 'pharmacy', n: 2, idx: 3, selected: true, highlighted: false },
    ])
    expect(fc.features[0].geometry).toEqual({ type: 'Point', coordinates: [-2.89, 53.19] })
    expect(fc.features[1].geometry).toEqual({ type: 'Point', coordinates: [-2.9, 53.2] })
  })
})

describe('map glyphs', () => {
  const files = Object.keys(import.meta.glob('../../../public/map/glyphs/**/*.pbf'))

  it.each(['Noto Sans Regular', 'Noto Sans Medium'])(
    '%s covers Latin, punctuation and Welsh letters such as ẁ and ỳ',
    (font) => {
      const ranges = files
        .filter((f) => f.includes(`/${font}/`))
        .map((f) => f.split('/').pop())
        .sort()
      // 7680-7935 is Latin Extended Additional (Welsh ẁ ẃ ẅ ỳ): a missing range stops the map.
      expect(ranges).toEqual(['0-255.pbf', '256-511.pbf', '7680-7935.pbf', '8192-8447.pbf'])
    },
  )
})

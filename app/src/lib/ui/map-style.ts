/** Pure helpers for the map: the style for one area, and the pins as GeoJSON. */
import type { Feature, FeatureCollection, Point } from 'geojson'
import type { StyleSpecification, VectorSourceSpecification } from 'maplibre-gl'
import type { Result } from '../engine/results'

export type PinProperties =
  | { kind: 'origin' }
  | { kind: 'pharmacy'; n: number; idx: number; selected: boolean; highlighted: boolean }

/** Copy of the base style with this area's map source and the absolute glyph URL. */
export function buildStyle(
  base: StyleSpecification,
  sourceUrl: string,
  glyphsUrl: string,
): StyleSpecification {
  const area = base.sources.area as VectorSourceSpecification
  return {
    ...base,
    glyphs: glyphsUrl,
    sources: { ...base.sources, area: { ...area, url: sourceUrl } },
  }
}

function point(lon: number, lat: number, properties: PinProperties): Feature<Point, PinProperties> {
  return { type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] }, properties }
}

/** The searched postcode plus one numbered pin per listed pharmacy, in list order. */
export function pinsGeoJson(
  shown: Result[],
  origin: { lat: number; lon: number },
  selected: number | null,
  highlighted: number | null = null,
): FeatureCollection<Point, PinProperties> {
  return {
    type: 'FeatureCollection',
    features: [
      point(origin.lon, origin.lat, { kind: 'origin' }),
      ...shown.map((r, i) =>
        point(r.pharmacy.lon, r.pharmacy.lat, {
          kind: 'pharmacy',
          n: i + 1,
          idx: r.pharmacy.idx,
          selected: r.pharmacy.idx === selected,
          highlighted: r.pharmacy.idx === highlighted,
        }),
      ),
    ],
  }
}

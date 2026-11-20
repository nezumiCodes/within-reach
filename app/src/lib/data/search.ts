/**
 * Postcode search (Phase 2 design, section 6). The postcode never leaves this module: only
 * whole files named in the manifest are requested, so the host learns at most the area.
 */
import { parseDistricts, parsePharmacies, parsePostcodes, parseTravel } from '../engine/csv'
import { isNorthernIreland, normalisePostcode } from '../engine/postcode'
import { buildResults, type Result } from '../engine/results'
import type { Pharmacy, PostcodeRow, TravelRow } from '../engine/types'
import type { SessionFiles } from './files'
import type { AreaEntry, FileRef, Manifest } from './release'

export type SearchOutcome =
  | { kind: 'invalid' }
  | { kind: 'northern-ireland' }
  | { kind: 'not-found'; postcode: string }
  | {
      kind: 'found'
      postcode: string
      area: AreaEntry
      lat: number
      lon: number
      results: Result[]
    }

function findPostcode(rows: PostcodeRow[], postcode: string): PostcodeRow | null {
  let lo = 0
  let hi = rows.length - 1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    const value = rows[mid].postcode
    if (value === postcode) return rows[mid]
    if (value < postcode) lo = mid + 1
    else hi = mid - 1
  }
  return null
}

export class Searcher {
  private readonly parsed = new Map<string, Promise<unknown>>()

  constructor(
    private readonly manifest: Manifest,
    private readonly files: SessionFiles,
  ) {}

  /** Throws DownloadError or IntegrityError when a file can't be used. */
  async search(raw: string): Promise<SearchOutcome> {
    const postcode = normalisePostcode(raw)
    if (postcode === null) return { kind: 'invalid' }
    if (isNorthernIreland(postcode)) return { kind: 'northern-ireland' }

    const districts = await this.table(this.manifest.districts, parseDistricts)
    const codes = districts.get(postcode.split(' ')[0]) ?? []
    const areas = codes
      .map((code) => this.manifest.areas.find((a) => a.code === code))
      .filter((a): a is AreaEntry => a !== undefined)

    for (const area of areas) {
      const row = findPostcode(await this.table(area.files.postcodes, parsePostcodes), postcode)
      if (row === null) continue
      const [travel, pharmacies] = await Promise.all([
        this.table<TravelRow[]>(area.files.travel, parseTravel),
        this.table<Pharmacy[]>(this.manifest.directory, parsePharmacies),
      ])
      return {
        kind: 'found',
        postcode,
        area,
        lat: row.lat,
        lon: row.lon,
        results: buildResults(row.idx, travel, pharmacies),
      }
    }
    return { kind: 'not-found', postcode }
  }

  private table<T>(ref: FileRef, parse: (text: string) => T): Promise<T> {
    const existing = this.parsed.get(ref.path)
    if (existing) return existing as Promise<T>
    const promise = this.files.text(ref).then(parse)
    this.parsed.set(ref.path, promise)
    promise.catch(() => this.parsed.delete(ref.path))
    return promise
  }
}

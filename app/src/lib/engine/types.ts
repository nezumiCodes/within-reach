/**
 * Shared engine types, matching the data release format (docs/data-format.md).
 * Pure data: no input or output of their own.
 */

export type Nation = 'England' | 'Scotland' | 'Wales'

/** Minutes after midnight. An end at or before its start means the range runs past midnight. */
export type Range = { start: number; end: number }

export type DayHours = { kind: 'unknown' } | { kind: 'closed' } | { kind: 'open'; ranges: Range[] }

export type Pharmacy = {
  idx: number
  nation: Nation
  code: string
  name: string
  address: string
  postcode: string
  lat: number
  lon: number
  /** Seven entries, Monday first. */
  days: DayHours[]
}

export type PostcodeRow = { idx: number; postcode: string; lat: number; lon: number }

export type TravelRow = {
  pcIdx: number
  phIdx: number
  straightM: number
  walkM: number | null
  walkS: number | null
  driveS: number | null
}

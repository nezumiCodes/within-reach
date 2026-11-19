/**
 * Search results for one postcode: building, sorting and filter grouping
 * (Phase 2 design, section 5; spec NFR-11 for tie-breaking).
 */
import { filterStatus, type FilterKey, type Filters } from './hours'
import type { Pharmacy, TravelRow } from './types'

export type Result = {
  pharmacy: Pharmacy
  straightM: number
  walkM: number | null
  walkS: number | null
  driveS: number | null
}

export type SortMode = 'walk' | 'drive'

export type Grouped = {
  matches: Result[]
  unknown: Result[]
  hidden: { result: Result; reasons: FilterKey[] }[]
}

export function buildResults(pcIdx: number, travel: TravelRow[], pharmacies: Pharmacy[]): Result[] {
  return travel
    .filter((row) => row.pcIdx === pcIdx)
    .map((row) => ({
      pharmacy: pharmacies[row.phIdx],
      straightM: row.straightM,
      walkM: row.walkM,
      walkS: row.walkS,
      driveS: row.driveS,
    }))
}

/** Distance in the chosen mode, missing routes last, then straight line, nation, code. */
export function compareResults(mode: SortMode): (a: Result, b: Result) => number {
  const key = (r: Result): number | null => (mode === 'walk' ? r.walkM : r.driveS)
  return (a, b) => {
    const ka = key(a)
    const kb = key(b)
    if ((ka === null) !== (kb === null)) return ka === null ? 1 : -1
    if (ka !== null && kb !== null && ka !== kb) return ka - kb
    if (a.straightM !== b.straightM) return a.straightM - b.straightM
    if (a.pharmacy.nation !== b.pharmacy.nation)
      return a.pharmacy.nation < b.pharmacy.nation ? -1 : 1
    if (a.pharmacy.code !== b.pharmacy.code) return a.pharmacy.code < b.pharmacy.code ? -1 : 1
    return 0
  }
}

export function sortResults(results: Result[], mode: SortMode): Result[] {
  return [...results].sort(compareResults(mode))
}

/** Split sorted results into matches, hours-unknown and hidden, keeping their order. */
export function groupByFilters(sorted: Result[], filters: Filters): Grouped {
  const grouped: Grouped = { matches: [], unknown: [], hidden: [] }
  for (const result of sorted) {
    const status = filterStatus(result.pharmacy.days, filters)
    if (status.kind === 'match') grouped.matches.push(result)
    else if (status.kind === 'unknown') grouped.unknown.push(result)
    else grouped.hidden.push({ result, reasons: status.reasons })
  }
  return grouped
}

const REASON_TEXT: Record<FilterKey, string> = {
  saturday: 'not open on Saturdays',
  sunday: 'not open on Sundays',
  late: 'not open late',
}
const REASON_ORDER: readonly FilterKey[] = ['saturday', 'sunday', 'late']

/** For example "4 closer pharmacies hidden: not open on Sundays." */
export function hiddenSummary(grouped: Grouped, mode: SortMode): string | null {
  const n = grouped.hidden.length
  if (n === 0) return null
  const lastShown = grouped.unknown.at(-1) ?? grouped.matches.at(-1)
  const compare = compareResults(mode)
  const closer =
    lastShown === undefined || grouped.hidden.some((h) => compare(h.result, lastShown) < 0)
  const used = new Set(grouped.hidden.flatMap((h) => h.reasons))
  const reasons = REASON_ORDER.filter((k) => used.has(k))
    .map((k) => REASON_TEXT[k])
    .join(' or ')
  return `${n} ${closer ? 'closer ' : ''}pharmac${n === 1 ? 'y' : 'ies'} hidden: ${reasons}.`
}

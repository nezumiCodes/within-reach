/**
 * Search results for one postcode: building, sorting and filter grouping
 * (Phase 2 design, section 5; spec NFR-11 for tie-breaking).
 */
import { filterStatus, type FilterKey, type Filters, type HoursKey } from './hours'
import type { Pharmacy, TravelRow } from './types'

export type Result = {
  pharmacy: Pharmacy
  straightM: number
  walkM: number | null
  walkS: number | null
  driveS: number | null
  walkCycle: boolean
}

export type SortMode = 'walk' | 'drive'

export type Grouped = {
  matches: Result[]
  unknown: Result[]
  /** What the pharmacies in `unknown` could not answer. */
  unknownOf: Set<'hours' | 'services'>
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
      walkCycle: row.walkCycle,
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

/** Split sorted results into matches, not-known and hidden, keeping their order. */
export function groupByFilters(sorted: Result[], filters: Filters): Grouped {
  const grouped: Grouped = { matches: [], unknown: [], unknownOf: new Set(), hidden: [] }
  for (const result of sorted) {
    const status = filterStatus(result.pharmacy, filters)
    if (status.kind === 'match') grouped.matches.push(result)
    else if (status.kind === 'unknown') {
      grouped.unknown.push(result)
      for (const of of status.of) grouped.unknownOf.add(of)
    } else grouped.hidden.push({ result, reasons: status.reasons })
  }
  return grouped
}

const HOURS_REASON_TEXT: Record<HoursKey, string> = {
  saturday: 'not open on Saturdays',
  sunday: 'not open on Sundays',
  late: 'not open late',
}
const HOURS_ORDER: readonly HoursKey[] = ['saturday', 'sunday', 'late']
const SERVICE_PREFIX = 'service:'

/** For example "4 closer pharmacies hidden: not open on Sundays." Services follow hours. */
export function hiddenSummary(
  grouped: Grouped,
  mode: SortMode,
  serviceNames: Record<string, string>,
): string | null {
  const n = grouped.hidden.length
  if (n === 0) return null
  const lastShown = grouped.unknown.at(-1) ?? grouped.matches.at(-1)
  const compare = compareResults(mode)
  const closer =
    lastShown === undefined || grouped.hidden.some((h) => compare(h.result, lastShown) < 0)
  const used = new Set<FilterKey>(grouped.hidden.flatMap((h) => h.reasons))
  const hours = HOURS_ORDER.filter((k) => used.has(k)).map((k) => HOURS_REASON_TEXT[k])
  const services = Object.entries(serviceNames)
    .filter(([key]) => used.has(`${SERVICE_PREFIX}${key}`))
    .map(([, name]) => `not listed for ${name.toLowerCase()}`)
  const reasons = [...hours, ...services].join(' or ')
  return `${n} ${closer ? 'closer ' : ''}pharmac${n === 1 ? 'y' : 'ies'} hidden: ${reasons}.`
}

const DEFAULT_REACH_M = 25000

/** The empty-list message: names the service when no result passes the service filters alone. */
export function noResultsMessage(
  sorted: Result[],
  filters: Filters,
  serviceNames: Record<string, string>,
  reachCapM: number,
): string {
  const keys = Object.keys(serviceNames).filter((key) => filters.services[key])
  const servicesOnly: Filters = { ...filters, saturday: false, sunday: false, late: false }
  const anyPasses = sorted.some((r) => filterStatus(r.pharmacy, servicesOnly).kind !== 'hidden')
  if (keys.length > 0 && !anyPasses) {
    const names = keys.map((key) => serviceNames[key].toLowerCase()).join(' or ')
    const reach = Number.isFinite(reachCapM) && reachCapM > 0 ? reachCapM : DEFAULT_REACH_M
    return `No pharmacies listing ${names} were found within ${reach / 1000} km.`
  }
  return 'No pharmacies nearby match these filters.'
}

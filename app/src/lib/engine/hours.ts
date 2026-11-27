/**
 * Opening hours and the public search filters (Phase 2 design, section 5).
 * A pharmacy whose hours can't answer a filter is "unknown", never hidden (spec FR-15).
 */
import type { DayHours, Pharmacy, Range } from './types'

export type HoursKey = 'saturday' | 'sunday' | 'late'
export type FilterKey = HoursKey | `service:${string}`
export type Filters = Record<HoursKey, boolean> & { services: Record<string, boolean> }
export const NO_FILTERS: Filters = { saturday: false, sunday: false, late: false, services: {} }

export type FilterStatus =
  | { kind: 'match' }
  | { kind: 'unknown'; of: ('hours' | 'services')[] }
  | { kind: 'hidden'; reasons: FilterKey[] }

const HOURS_ORDER: readonly HoursKey[] = ['saturday', 'sunday', 'late']
const SATURDAY = 5
const SUNDAY = 6
const WEEKDAYS = [0, 1, 2, 3, 4]
const LATE_MINUTES = 19 * 60
const RANGE = /^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-4]):([0-5]\d)$/

function parseRange(text: string): Range {
  const match = RANGE.exec(text)
  if (match === null) throw new Error(`unreadable opening hours: ${text}`)
  const [, sh, sm, eh, em] = match.map(Number)
  return { start: sh * 60 + sm, end: eh * 60 + em }
}

/** '' → unknown, 'CLOSED' → closed, otherwise ranges like '09:00-13:00;14:00-17:30'. */
export function parseDay(cell: string): DayHours {
  if (cell === '') return { kind: 'unknown' }
  if (cell === 'CLOSED') return { kind: 'closed' }
  return { kind: 'open', ranges: cell.split(';').map(parseRange) }
}

type Answer = 'pass' | 'fail' | 'unknown'

function openOn(day: DayHours): Answer {
  if (day.kind === 'unknown') return 'unknown'
  return day.kind === 'open' ? 'pass' : 'fail'
}

function isLate(range: Range): boolean {
  return range.end >= LATE_MINUTES || range.end <= range.start
}

function openLate(days: DayHours[]): Answer {
  const weekdays = WEEKDAYS.map((i) => days[i])
  if (weekdays.some((d) => d.kind === 'open' && d.ranges.some(isLate))) return 'pass'
  return weekdays.some((d) => d.kind === 'unknown') ? 'unknown' : 'fail'
}

function answer(key: HoursKey, days: DayHours[]): Answer {
  if (key === 'saturday') return openOn(days[SATURDAY])
  if (key === 'sunday') return openOn(days[SUNDAY])
  return openLate(days)
}

/** A service is not listed when the pharmacy has no entry for it; 'unknown' is never hidden. */
function serviceAnswer(pharmacy: Pharmacy, key: string): Answer {
  const state = pharmacy.services[key]
  if (state === undefined) return 'fail'
  return state === 'listed' ? 'pass' : 'unknown'
}

/** Hidden if any active filter fails, otherwise unknown if any can't be answered, else a match. */
export function filterStatus(pharmacy: Pharmacy, filters: Filters): FilterStatus {
  const hours = HOURS_ORDER.filter((key) => filters[key]).map(
    (key) => [key as FilterKey, 'hours' as const, answer(key, pharmacy.days)] as const,
  )
  const services = Object.keys(filters.services)
    .filter((key) => filters.services[key])
    .map(
      (key) =>
        [`service:${key}` as FilterKey, 'services' as const, serviceAnswer(pharmacy, key)] as const,
    )
  const answers = [...hours, ...services]
  const reasons = answers.filter(([, , a]) => a === 'fail').map(([key]) => key)
  if (reasons.length > 0) return { kind: 'hidden', reasons }
  const unknownOf = (['hours', 'services'] as const).filter((of) =>
    answers.some(([, from, a]) => from === of && a === 'unknown'),
  )
  if (unknownOf.length > 0) return { kind: 'unknown', of: unknownOf }
  return { kind: 'match' }
}

export function anyFilter(filters: Filters): boolean {
  return (
    filters.saturday ||
    filters.sunday ||
    filters.late ||
    Object.values(filters.services).some(Boolean)
  )
}

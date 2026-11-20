/**
 * Opening hours and the public search filters (Phase 2 design, section 5).
 * A pharmacy whose hours can't answer a filter is "unknown", never hidden (spec FR-15).
 */
import type { DayHours, Range } from './types'

export type FilterKey = 'saturday' | 'sunday' | 'late'
export type Filters = Record<FilterKey, boolean>
export const NO_FILTERS: Filters = { saturday: false, sunday: false, late: false }

export type FilterStatus =
  { kind: 'match' } | { kind: 'unknown' } | { kind: 'hidden'; reasons: FilterKey[] }

const FILTER_ORDER: readonly FilterKey[] = ['saturday', 'sunday', 'late']
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

function answer(key: FilterKey, days: DayHours[]): Answer {
  if (key === 'saturday') return openOn(days[SATURDAY])
  if (key === 'sunday') return openOn(days[SUNDAY])
  return openLate(days)
}

export function filterStatus(days: DayHours[], filters: Filters): FilterStatus {
  const active = FILTER_ORDER.filter((key) => filters[key])
  const answers = active.map((key) => [key, answer(key, days)] as const)
  const reasons = answers.filter(([, a]) => a === 'fail').map(([key]) => key)
  if (reasons.length > 0) return { kind: 'hidden', reasons }
  if (answers.some(([, a]) => a === 'unknown')) return { kind: 'unknown' }
  return { kind: 'match' }
}

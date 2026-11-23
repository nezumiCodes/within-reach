/** Display text for distances, times and opening hours (Phase 2 design, section 5). */
import type { Result } from './results'
import type { DayHours } from './types'

export const DAY_NAMES: readonly string[] = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

/** "650 m" below 995 m (nearest 10 m), otherwise "1.3 km". */
export function formatDistance(metres: number): string {
  if (metres < 995) return `${Math.round(metres / 10) * 10} m`
  return `${(metres / 1000).toFixed(1)} km`
}

/** Whole minutes, rounded up, at least 1. */
export function formatMinutes(seconds: number): string {
  return `${Math.max(1, Math.ceil(seconds / 60))} min`
}

/** "800 m · 11 min walk · 3 min drive", with plain words for missing routes. */
export function travelLine(r: Result): string {
  const walk =
    r.walkM === null || r.walkS === null
      ? 'No walking route found'
      : `${formatDistance(r.walkM)} · ${formatMinutes(r.walkS)} walk` +
        (r.walkCycle ? ', partly on a cycle path' : '')
  const drive = r.driveS === null ? 'No driving route found' : `${formatMinutes(r.driveS)} drive`
  return `${walk} · ${drive}`
}

function clock(minutes: number): string {
  const m = minutes % (24 * 60)
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`
}

export function formatDayHours(day: DayHours): string {
  if (day.kind === 'unknown') return 'Not known'
  if (day.kind === 'closed') return 'Closed'
  return day.ranges.map((r) => `${clock(r.start)}–${clock(r.end)}`).join(', ')
}

export function hasAnyHours(days: DayHours[]): boolean {
  return days.some((d) => d.kind !== 'unknown')
}

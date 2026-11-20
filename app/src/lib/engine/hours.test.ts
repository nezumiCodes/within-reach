import { describe, expect, it } from 'vitest'
import { filterStatus, NO_FILTERS, parseDay, type Filters } from './hours'
import type { DayHours } from './types'

const open = (cell: string): DayHours => parseDay(cell)
const CLOSED: DayHours = { kind: 'closed' }
const UNKNOWN: DayHours = { kind: 'unknown' }
const weekdays = (cell: string): DayHours[] => Array.from({ length: 5 }, () => open(cell))
const week = (weekday: string, sat: DayHours, sun: DayHours): DayHours[] => [
  ...weekdays(weekday),
  sat,
  sun,
]
const only = (on: Partial<Filters>): Filters => ({ ...NO_FILTERS, ...on })

describe('parseDay', () => {
  it('reads blank, CLOSED and ranges', () => {
    expect(parseDay('')).toEqual({ kind: 'unknown' })
    expect(parseDay('CLOSED')).toEqual({ kind: 'closed' })
    expect(parseDay('09:00-13:00;14:00-17:30')).toEqual({
      kind: 'open',
      ranges: [
        { start: 540, end: 780 },
        { start: 840, end: 1050 },
      ],
    })
  })

  it('rejects a malformed cell', () => {
    expect(() => parseDay('9-5')).toThrow()
  })
})

describe('filterStatus', () => {
  it('saturday filter passes an open saturday and hides a closed one', () => {
    const f = only({ saturday: true })
    expect(filterStatus(week('09:00-17:30', open('09:00-12:00'), CLOSED), f)).toEqual({
      kind: 'match',
    })
    expect(filterStatus(week('09:00-17:30', CLOSED, CLOSED), f)).toEqual({
      kind: 'hidden',
      reasons: ['saturday'],
    })
  })

  it('saturday filter treats a blank saturday as unknown even when weekdays are known', () => {
    expect(filterStatus(week('09:00-17:30', UNKNOWN, CLOSED), only({ saturday: true }))).toEqual({
      kind: 'unknown',
    })
  })

  it('sunday filter uses sunday', () => {
    const f = only({ sunday: true })
    expect(filterStatus(week('09:00-17:30', CLOSED, open('10:00-16:00')), f).kind).toBe('match')
    expect(filterStatus(week('09:00-17:30', open('10:00-16:00'), CLOSED), f).kind).toBe('hidden')
  })

  it('late filter passes a weekday closing at 19:00 exactly', () => {
    const days = week('09:00-17:30', CLOSED, CLOSED)
    days[2] = open('09:00-19:00')
    expect(filterStatus(days, only({ late: true })).kind).toBe('match')
  })

  it('late filter hides a pharmacy closing at 18:59', () => {
    expect(filterStatus(week('09:00-18:59', CLOSED, CLOSED), only({ late: true }))).toEqual({
      kind: 'hidden',
      reasons: ['late'],
    })
  })

  it('late filter ignores a saturday closing at 22:00', () => {
    const days = week('09:00-17:30', open('09:00-22:00'), CLOSED)
    expect(filterStatus(days, only({ late: true })).kind).toBe('hidden')
  })

  it('late filter passes a past-midnight range', () => {
    const days = week('09:00-17:30', CLOSED, CLOSED)
    days[4] = open('18:00-01:00')
    expect(filterStatus(days, only({ late: true })).kind).toBe('match')
  })

  it('late filter is unknown when no weekday qualifies and one weekday is blank', () => {
    const days = week('09:00-17:30', CLOSED, CLOSED)
    days[1] = UNKNOWN
    expect(filterStatus(days, only({ late: true }))).toEqual({ kind: 'unknown' })
  })

  it('late filter passes on one late weekday even when another is blank', () => {
    const days = week('09:00-17:30', CLOSED, CLOSED)
    days[1] = UNKNOWN
    days[3] = open('08:00-21:00')
    expect(filterStatus(days, only({ late: true })).kind).toBe('match')
  })

  it('several filters: any failure hides, listing every failing reason in order', () => {
    const f = { saturday: true, sunday: true, late: true }
    expect(filterStatus(week('09:00-17:30', CLOSED, CLOSED), f)).toEqual({
      kind: 'hidden',
      reasons: ['saturday', 'sunday', 'late'],
    })
  })

  it('failure beats unknown', () => {
    const f = only({ saturday: true, sunday: true })
    expect(filterStatus(week('09:00-17:30', CLOSED, UNKNOWN), f)).toEqual({
      kind: 'hidden',
      reasons: ['saturday'],
    })
  })

  it('no filters means match even with no hours', () => {
    expect(
      filterStatus(
        Array.from({ length: 7 }, () => UNKNOWN),
        NO_FILTERS,
      ),
    ).toEqual({
      kind: 'match',
    })
  })
})

import { describe, expect, it } from 'vitest'
import { filterStatus, NO_FILTERS, parseDay, type Filters } from './hours'
import type { DayHours, Pharmacy, ServiceState } from './types'

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
const NSP: Filters = { ...NO_FILTERS, services: { nsp: true } }

function pharmacyWith(days: DayHours[], services: Record<string, ServiceState> = {}): Pharmacy {
  return {
    idx: 0,
    nation: 'England',
    code: 'F000',
    name: 'Pharmacy 0',
    address: '1 High Street',
    postcode: 'CH1 1AA',
    lat: 53.19,
    lon: -2.89,
    days,
    services,
  }
}
const statusOf = (
  days: DayHours[],
  filters: Filters,
  services: Record<string, ServiceState> = {},
) => filterStatus(pharmacyWith(days, services), filters)

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
    expect(statusOf(week('09:00-17:30', open('09:00-12:00'), CLOSED), f)).toEqual({
      kind: 'match',
    })
    expect(statusOf(week('09:00-17:30', CLOSED, CLOSED), f)).toEqual({
      kind: 'hidden',
      reasons: ['saturday'],
    })
  })

  it('saturday filter treats a blank saturday as unknown even when weekdays are known', () => {
    expect(statusOf(week('09:00-17:30', UNKNOWN, CLOSED), only({ saturday: true }))).toEqual({
      kind: 'unknown',
      of: ['hours'],
    })
  })

  it('sunday filter uses sunday', () => {
    const f = only({ sunday: true })
    expect(statusOf(week('09:00-17:30', CLOSED, open('10:00-16:00')), f).kind).toBe('match')
    expect(statusOf(week('09:00-17:30', open('10:00-16:00'), CLOSED), f).kind).toBe('hidden')
  })

  it('late filter passes a weekday closing at 19:00 exactly', () => {
    const days = week('09:00-17:30', CLOSED, CLOSED)
    days[2] = open('09:00-19:00')
    expect(statusOf(days, only({ late: true })).kind).toBe('match')
  })

  it('late filter hides a pharmacy closing at 18:59', () => {
    expect(statusOf(week('09:00-18:59', CLOSED, CLOSED), only({ late: true }))).toEqual({
      kind: 'hidden',
      reasons: ['late'],
    })
  })

  it('late filter ignores a saturday closing at 22:00', () => {
    const days = week('09:00-17:30', open('09:00-22:00'), CLOSED)
    expect(statusOf(days, only({ late: true })).kind).toBe('hidden')
  })

  it('late filter passes a past-midnight range', () => {
    const days = week('09:00-17:30', CLOSED, CLOSED)
    days[4] = open('18:00-01:00')
    expect(statusOf(days, only({ late: true })).kind).toBe('match')
  })

  it('late filter is unknown when no weekday qualifies and one weekday is blank', () => {
    const days = week('09:00-17:30', CLOSED, CLOSED)
    days[1] = UNKNOWN
    expect(statusOf(days, only({ late: true }))).toEqual({ kind: 'unknown', of: ['hours'] })
  })

  it('late filter passes on one late weekday even when another is blank', () => {
    const days = week('09:00-17:30', CLOSED, CLOSED)
    days[1] = UNKNOWN
    days[3] = open('08:00-21:00')
    expect(statusOf(days, only({ late: true })).kind).toBe('match')
  })

  it('several filters: any failure hides, listing every failing reason in order', () => {
    const f = only({ saturday: true, sunday: true, late: true })
    expect(statusOf(week('09:00-17:30', CLOSED, CLOSED), f)).toEqual({
      kind: 'hidden',
      reasons: ['saturday', 'sunday', 'late'],
    })
  })

  it('failure beats unknown', () => {
    const f = only({ saturday: true, sunday: true })
    expect(statusOf(week('09:00-17:30', CLOSED, UNKNOWN), f)).toEqual({
      kind: 'hidden',
      reasons: ['saturday'],
    })
  })

  it('no filters means match even with no hours', () => {
    expect(
      statusOf(
        Array.from({ length: 7 }, () => UNKNOWN),
        NO_FILTERS,
      ),
    ).toEqual({
      kind: 'match',
    })
  })
})

describe('filterStatus with a service filter', () => {
  const week7 = week('09:00-17:30', CLOSED, CLOSED)

  it('a pharmacy with no nsp entry is hidden: not listed', () => {
    expect(statusOf(week7, NSP)).toEqual({ kind: 'hidden', reasons: ['service:nsp'] })
  })

  it('a pharmacy listing nsp matches', () => {
    expect(statusOf(week7, NSP, { nsp: 'listed' })).toEqual({ kind: 'match' })
  })

  it('an unknown nsp is not hidden, and says services are unknown', () => {
    expect(statusOf(week7, NSP, { nsp: 'unknown' })).toEqual({ kind: 'unknown', of: ['services'] })
  })

  it('hours failure is the reason when the service is listed', () => {
    const f: Filters = { ...only({ sunday: true }), services: { nsp: true } }
    expect(statusOf(week7, f, { nsp: 'listed' })).toEqual({ kind: 'hidden', reasons: ['sunday'] })
  })

  it('lists hours reasons before service reasons', () => {
    const f: Filters = { ...only({ sunday: true }), services: { nsp: true } }
    expect(statusOf(week7, f)).toEqual({ kind: 'hidden', reasons: ['sunday', 'service:nsp'] })
  })

  it('reports both kinds of unknown', () => {
    const f: Filters = { ...only({ saturday: true }), services: { nsp: true } }
    expect(statusOf(week('09:00-17:30', UNKNOWN, CLOSED), f, { nsp: 'unknown' })).toEqual({
      kind: 'unknown',
      of: ['hours', 'services'],
    })
  })

  it('ignores a service filter that is switched off', () => {
    const f: Filters = { ...NO_FILTERS, services: { nsp: false } }
    expect(statusOf(week7, f)).toEqual({ kind: 'match' })
  })
})

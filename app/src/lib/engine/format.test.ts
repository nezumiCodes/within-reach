import { describe, expect, it } from 'vitest'
import {
  DAY_NAMES,
  formatDayHours,
  formatDistance,
  formatMinutes,
  hasAnyHours,
  travelLine,
} from './format'
import { parseDay } from './hours'
import type { Result } from './results'
import type { Pharmacy } from './types'

const p = { days: [] } as unknown as Pharmacy
const r = (walkM: number | null, walkS: number | null, driveS: number | null): Result => ({
  pharmacy: p,
  straightM: 0,
  walkM,
  walkS,
  driveS,
})

describe('formatDistance', () => {
  it('uses metres to the nearest 10 below 995 m, otherwise km to 1 dp', () => {
    expect(formatDistance(650)).toBe('650 m')
    expect(formatDistance(654)).toBe('650 m')
    expect(formatDistance(994)).toBe('990 m')
    expect(formatDistance(995)).toBe('1.0 km')
    expect(formatDistance(1349)).toBe('1.3 km')
  })
})

describe('formatMinutes', () => {
  it('rounds up with a minimum of 1', () => {
    expect(formatMinutes(30)).toBe('1 min')
    expect(formatMinutes(600)).toBe('10 min')
    expect(formatMinutes(601)).toBe('11 min')
  })
})

describe('travelLine', () => {
  it('shows walk distance, walk time and drive time', () => {
    expect(travelLine(r(800, 650, 170))).toBe('800 m · 11 min walk · 3 min drive')
  })

  it('says when there is no walking route', () => {
    expect(travelLine(r(null, null, 170))).toBe('No walking route found · 3 min drive')
  })

  it('says when there is no driving route', () => {
    expect(travelLine(r(1300, 960, null))).toBe('1.3 km · 16 min walk · No driving route found')
  })
})

describe('opening hours text', () => {
  it('formats ranges, closed and unknown days', () => {
    expect(formatDayHours(parseDay('09:00-13:00;14:00-17:30'))).toBe('9:00–13:00, 14:00–17:30')
    expect(formatDayHours(parseDay('CLOSED'))).toBe('Closed')
    expect(formatDayHours(parseDay(''))).toBe('Not known')
    expect(formatDayHours(parseDay('08:00-00:00'))).toBe('8:00–0:00')
  })

  it('knows whether any day has hours', () => {
    expect(hasAnyHours(Array.from({ length: 7 }, () => parseDay('')))).toBe(false)
    expect(
      hasAnyHours([parseDay('CLOSED'), ...Array.from({ length: 6 }, () => parseDay(''))]),
    ).toBe(true)
  })

  it('names the days Monday first', () => {
    expect(DAY_NAMES).toEqual([
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ])
  })
})

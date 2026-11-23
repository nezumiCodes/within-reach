import { describe, expect, it } from 'vitest'
import { NO_FILTERS, parseDay } from './hours'
import { buildResults, groupByFilters, hiddenSummary, sortResults, type Result } from './results'
import type { Nation, Pharmacy, TravelRow } from './types'

const WEEKDAY = '09:00-17:30'

function pharmacy(
  idx: number,
  sat = 'CLOSED',
  sun = 'CLOSED',
  nation: Nation = 'England',
): Pharmacy {
  return {
    idx,
    nation,
    code: `F${String(idx).padStart(3, '0')}`,
    name: `Pharmacy ${idx}`,
    address: `${idx} High Street`,
    postcode: 'CH1 1AA',
    lat: 53.19,
    lon: -2.89,
    days: [WEEKDAY, WEEKDAY, WEEKDAY, WEEKDAY, WEEKDAY, sat, sun].map(parseDay),
  }
}

function result(p: Pharmacy, walkM: number | null, driveS: number | null, straightM = 100): Result {
  return { pharmacy: p, straightM, walkM, walkS: walkM, driveS, walkCycle: false }
}

const codes = (rs: Result[]): string[] => rs.map((r) => r.pharmacy.code)

describe('buildResults', () => {
  it('keeps only rows for the postcode and joins the pharmacy', () => {
    const pharmacies = [pharmacy(0), pharmacy(1)]
    const travel: TravelRow[] = [
      { pcIdx: 0, phIdx: 1, straightM: 50, walkM: 60, walkS: 45, driveS: 30, walkCycle: true },
      { pcIdx: 1, phIdx: 0, straightM: 10, walkM: 10, walkS: 8, driveS: 5, walkCycle: false },
    ]
    expect(buildResults(0, travel, pharmacies)).toEqual([
      {
        pharmacy: pharmacies[1],
        straightM: 50,
        walkM: 60,
        walkS: 45,
        driveS: 30,
        walkCycle: true,
      },
    ])
  })
})

describe('sortResults', () => {
  it('walking sort puts missing walks last, ordered by straight line', () => {
    const rs = [
      result(pharmacy(1), null, 100, 900),
      result(pharmacy(2), 500, 100),
      result(pharmacy(3), null, 100, 300),
      result(pharmacy(4), 200, 100),
    ]
    expect(codes(sortResults(rs, 'walk'))).toEqual(['F004', 'F002', 'F003', 'F001'])
  })

  it('ties break by straight line, then nation, then code', () => {
    const rs = [
      result(pharmacy(3, 'CLOSED', 'CLOSED', 'Wales'), 400, 1, 100),
      result(pharmacy(2), 400, 1, 100),
      result(pharmacy(1, 'CLOSED', 'CLOSED', 'Wales'), 400, 1, 100),
      result(pharmacy(9), 400, 1, 50),
    ]
    expect(codes(sortResults(rs, 'walk'))).toEqual(['F009', 'F002', 'F001', 'F003'])
  })

  it('driving sort uses drive_s', () => {
    const rs = [result(pharmacy(1), 100, 300), result(pharmacy(2), 900, 120)]
    expect(codes(sortResults(rs, 'drive'))).toEqual(['F002', 'F001'])
    expect(codes(rs)).toEqual(['F001', 'F002']) // input untouched
  })
})

describe('groupByFilters', () => {
  it('keeps order and puts unknown hours after matches', () => {
    const rs = [
      result(pharmacy(1, 'CLOSED', ''), 100, 1),
      result(pharmacy(2, 'CLOSED', '10:00-16:00'), 200, 1),
      result(pharmacy(3, 'CLOSED', 'CLOSED'), 300, 1),
      result(pharmacy(4, 'CLOSED', '10:00-16:00'), 400, 1),
    ]
    const grouped = groupByFilters(rs, { ...NO_FILTERS, sunday: true })
    expect(codes(grouped.matches)).toEqual(['F002', 'F004'])
    expect(codes(grouped.unknown)).toEqual(['F001'])
    expect(grouped.hidden.map((h) => [h.result.pharmacy.code, h.reasons])).toEqual([
      ['F003', ['sunday']],
    ])
  })

  it('shows everything as matches with no filters', () => {
    const rs = [result(pharmacy(1, '', ''), 100, 1)]
    expect(groupByFilters(rs, NO_FILTERS)).toEqual({ matches: rs, unknown: [], hidden: [] })
  })
})

describe('hiddenSummary', () => {
  it('counts closer hidden pharmacies', () => {
    const rs = [
      result(pharmacy(1, 'CLOSED', 'CLOSED'), 100, 1),
      result(pharmacy(2, 'CLOSED', '10:00-16:00'), 200, 1),
      result(pharmacy(3, 'CLOSED', '10:00-16:00'), 300, 1),
    ]
    const grouped = groupByFilters(rs, { ...NO_FILTERS, sunday: true })
    expect(hiddenSummary(grouped, 'walk')).toBe('1 closer pharmacy hidden: not open on Sundays.')
  })

  it('joins reasons with or', () => {
    const late = '09:00-20:00'
    const shown = result(
      {
        ...pharmacy(0, '09:00-12:00'),
        days: [late, late, late, late, late, '09:00-12:00', 'CLOSED'].map(parseDay),
      },
      50,
      1,
    )
    const hidden = [1, 2, 3, 4, 5, 6].map((i) =>
      result(pharmacy(i, i % 2 ? '09:00-12:00' : 'CLOSED'), 100 * i, 1),
    )
    const grouped = groupByFilters([shown, ...hidden], {
      ...NO_FILTERS,
      saturday: true,
      late: true,
    })
    expect(grouped.hidden).toHaveLength(6)
    expect(hiddenSummary(grouped, 'walk')).toBe(
      '6 pharmacies hidden: not open on Saturdays or not open late.',
    )
  })

  it('says closer when nothing is shown', () => {
    const grouped = groupByFilters([result(pharmacy(1), 100, 1)], { ...NO_FILTERS, sunday: true })
    expect(hiddenSummary(grouped, 'walk')).toBe('1 closer pharmacy hidden: not open on Sundays.')
  })

  it('compares against the last unknown entry when there is one', () => {
    const rs = [
      result(pharmacy(1, 'CLOSED', '10:00-16:00'), 100, 1),
      result(pharmacy(2, 'CLOSED', 'CLOSED'), 200, 1),
      result(pharmacy(3, 'CLOSED', ''), 300, 1),
    ]
    const grouped = groupByFilters(rs, { ...NO_FILTERS, sunday: true })
    expect(hiddenSummary(grouped, 'walk')).toBe('1 closer pharmacy hidden: not open on Sundays.')
  })

  it('is null with nothing hidden', () => {
    const grouped = groupByFilters([result(pharmacy(1), 100, 1)], NO_FILTERS)
    expect(hiddenSummary(grouped, 'walk')).toBeNull()
  })
})

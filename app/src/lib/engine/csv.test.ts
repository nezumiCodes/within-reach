import { describe, expect, it } from 'vitest'
import { parseCsv, parseDistricts, parsePharmacies, parsePostcodes, parseTravel } from './csv'

const PHARMACY_HEADER =
  'ph_idx,nation,code,name,address,postcode,lat,lon,mon,tue,wed,thu,fri,sat,sun'

describe('parseCsv', () => {
  it('handles quotes, commas and doubled quotes', () => {
    expect(parseCsv('a,b\n"x, y","say ""hi"""\n')).toEqual([['x, y', 'say "hi"']])
  })

  it('accepts CRLF', () => {
    expect(parseCsv('a,b\r\n1,2\r\n3,4\r\n')).toEqual([
      ['1', '2'],
      ['3', '4'],
    ])
  })

  it('keeps empty cells and a final line without a newline', () => {
    expect(parseCsv('a,b,c\n1,,3')).toEqual([['1', '', '3']])
  })

  it('returns the header row through the header option', () => {
    expect(parseCsv('a,b\n1,2\n', { header: true })).toEqual([
      ['a', 'b'],
      ['1', '2'],
    ])
  })
})

describe('release files', () => {
  it('parseDistricts splits space-separated area codes', () => {
    const text = 'outward,area_codes\nCH1,E06000050\nSY14,E06000050 W11000023\n'
    expect(parseDistricts(text)).toEqual(
      new Map([
        ['CH1', ['E06000050']],
        ['SY14', ['E06000050', 'W11000023']],
      ]),
    )
  })

  it('parseTravel turns blank cells into null', () => {
    const text = 'pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s\n0,5,300,,,120\n'
    expect(parseTravel(text)).toEqual([
      {
        pcIdx: 0,
        phIdx: 5,
        straightM: 300,
        walkM: null,
        walkS: null,
        driveS: 120,
        walkCycle: false,
      },
    ])
  })

  it('parseTravel reads the 7-column travel file', () => {
    const rows = parseTravel(
      'pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s,walk_cycle\n' +
        '0,1,900,1400,1080,300,1\n0,2,950,1500,1150,310,\n',
    )
    expect(rows.map((r) => r.walkCycle)).toEqual([true, false])
  })

  it('parseTravel reads the older 6-column file with no notes', () => {
    const rows = parseTravel(
      'pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s\n0,1,900,1400,1080,300\n',
    )
    expect(rows[0].walkCycle).toBe(false)
  })

  it('parseTravel rejects any other header', () => {
    expect(() => parseTravel('pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s,extra\n')).toThrow(
      'unexpected columns in travel',
    )
  })

  it('parseTravel rejects a walk_cycle value other than 1 or blank', () => {
    expect(() =>
      parseTravel('pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s,walk_cycle\n0,1,9,9,9,9,yes\n'),
    ).toThrow()
  })

  it('parsePostcodes reads rows in order', () => {
    const text = 'pc_idx,postcode,lat,lon\n0,CH1 1AA,53.190000,-2.890000\n'
    expect(parsePostcodes(text)).toEqual([{ idx: 0, postcode: 'CH1 1AA', lat: 53.19, lon: -2.89 }])
  })

  it('parsePharmacies reads hours per day', () => {
    const row =
      '7,England,FA001,"Boughton Pharmacy","12 Christleton Rd, Chester",CH3 5UF,53.191000,-2.870000,' +
      '09:00-13:00;14:00-17:30,09:00-17:30,09:00-17:30,09:00-17:30,09:00-17:30,CLOSED,'
    const [pharmacy] = parsePharmacies(`${PHARMACY_HEADER}\n${row}\n`)
    expect(pharmacy.idx).toBe(7)
    expect(pharmacy.nation).toBe('England')
    expect(pharmacy.address).toBe('12 Christleton Rd, Chester')
    expect(pharmacy.days[0]).toEqual({
      kind: 'open',
      ranges: [
        { start: 540, end: 780 },
        { start: 840, end: 1050 },
      ],
    })
    expect(pharmacy.days[5]).toEqual({ kind: 'closed' })
    expect(pharmacy.days[6]).toEqual({ kind: 'unknown' })
  })

  it('parsers reject an unexpected header', () => {
    expect(() => parseTravel('a,b\n')).toThrow('unexpected columns in travel')
    expect(() => parsePharmacies('ph_idx,name\n')).toThrow('unexpected columns in pharmacies')
  })

  it('parsePharmacies rejects an unknown nation', () => {
    const row = '0,Atlantis,X1,N,A,CH1 1AA,53,-2,,,,,,,'
    expect(() => parsePharmacies(`${PHARMACY_HEADER}\n${row}\n`)).toThrow()
  })
})

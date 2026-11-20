/**
 * Parsers for the data release files (docs/data-format.md). Input is decompressed CSV text.
 * Each file's header is checked, so a format change fails loudly instead of misreading columns.
 */
import { parseDay } from './hours'
import type { Nation, Pharmacy, PostcodeRow, TravelRow } from './types'

/** RFC 4180 CSV: quoted fields, doubled quotes, LF or CRLF. Drops the header unless asked. */
export function parseCsv(text: string, options: { header?: boolean } = {}): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"'
        i++
      } else if (ch === '"') {
        quoted = false
      } else {
        field += ch
      }
    } else if (ch === '"') {
      quoted = true
    } else if (ch === ',') {
      row.push(field)
      field = ''
    } else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++
      row.push(field)
      rows.push(row)
      row = []
      field = ''
    } else {
      field += ch
    }
  }
  if (field !== '' || row.length > 0) {
    row.push(field)
    rows.push(row)
  }
  return options.header ? rows : rows.slice(1)
}

function rowsOf(text: string, file: string, columns: readonly string[]): string[][] {
  const rows = parseCsv(text, { header: true })
  if (rows.length === 0 || rows[0].join(',') !== columns.join(',')) {
    throw new Error(`unexpected columns in ${file}`)
  }
  return rows.slice(1)
}

function int(cell: string): number {
  const value = Number(cell)
  if (cell === '' || !Number.isInteger(value)) throw new Error(`not a whole number: ${cell}`)
  return value
}

function intOrNull(cell: string): number | null {
  return cell === '' ? null : int(cell)
}

function num(cell: string): number {
  const value = Number(cell)
  if (cell === '' || !Number.isFinite(value)) throw new Error(`not a number: ${cell}`)
  return value
}

const NATIONS: readonly Nation[] = ['England', 'Scotland', 'Wales']

function nation(cell: string): Nation {
  const found = NATIONS.find((n) => n === cell)
  if (found === undefined) throw new Error(`unknown nation: ${cell}`)
  return found
}

export function parseDistricts(text: string): Map<string, string[]> {
  const rows = rowsOf(text, 'districts', ['outward', 'area_codes'])
  return new Map(rows.map(([outward, areas]) => [outward, areas.split(' ').filter(Boolean)]))
}

const PHARMACY_COLUMNS = [
  'ph_idx',
  'nation',
  'code',
  'name',
  'address',
  'postcode',
  'lat',
  'lon',
  'mon',
  'tue',
  'wed',
  'thu',
  'fri',
  'sat',
  'sun',
] as const

export function parsePharmacies(text: string): Pharmacy[] {
  return rowsOf(text, 'pharmacies', PHARMACY_COLUMNS).map((r) => ({
    idx: int(r[0]),
    nation: nation(r[1]),
    code: r[2],
    name: r[3],
    address: r[4],
    postcode: r[5],
    lat: num(r[6]),
    lon: num(r[7]),
    days: r.slice(8, 15).map(parseDay),
  }))
}

export function parsePostcodes(text: string): PostcodeRow[] {
  return rowsOf(text, 'postcodes', ['pc_idx', 'postcode', 'lat', 'lon']).map((r) => ({
    idx: int(r[0]),
    postcode: r[1],
    lat: num(r[2]),
    lon: num(r[3]),
  }))
}

const TRAVEL_COLUMNS = ['pc_idx', 'ph_idx', 'straight_m', 'walk_m', 'walk_s', 'drive_s'] as const

export function parseTravel(text: string): TravelRow[] {
  return rowsOf(text, 'travel', TRAVEL_COLUMNS).map((r) => ({
    pcIdx: int(r[0]),
    phIdx: int(r[1]),
    straightM: int(r[2]),
    walkM: intOrNull(r[3]),
    walkS: intOrNull(r[4]),
    driveS: intOrNull(r[5]),
  }))
}

import { describe, expect, it } from 'vitest'
import { SessionFiles } from './files'
import type { AreaEntry, Manifest } from './release'
import { Searcher } from './search'
import { fakeFetch, gzip, refFor } from './test-helpers'

const RELEASE = '2026-11'
const POSTCODE_IN_TEXT = /\b(?:[A-Z]{1,2}[0-9][A-Z0-9]?|GIR)\s*[0-9][A-Z]{2}\b/i
const PH_HEADER = 'ph_idx,nation,code,name,address,postcode,lat,lon,mon,tue,wed,thu,fri,sat,sun'
const TRAVEL_HEADER = 'pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s'

/** Two areas, A (England) and B (Wales); district SY14 spans both, with SY14 9ZZ only in B. */
async function fixture() {
  const files = new Map<string, Uint8Array>()
  const add = async (path: string, text: string) => {
    const data = await gzip(text)
    files.set(path, data)
    return refFor(path, data)
  }
  const directory = await add(
    'pharmacies.csv.gz',
    `${PH_HEADER}\n0,England,FA1,One,1 Road,CH1 1AB,53.19,-2.89,,,,,,,\n1,Wales,FW1,Two,2 Road,LL11 1AB,53.05,-3.00,,,,,,,\n`,
  )
  const districts = await add('districts.csv.gz', 'outward,area_codes\nCH1,A\nLL11,B\nSY14,A B\n')
  const area = async (code: string, postcodes: string, travel: string): Promise<AreaEntry> => ({
    code,
    name: `Area ${code}`,
    nation: code === 'A' ? 'England' : 'Wales',
    files: {
      postcodes: await add(
        `areas/${code}/postcodes.csv.gz`,
        `pc_idx,postcode,lat,lon\n${postcodes}`,
      ),
      travel: await add(`areas/${code}/travel.csv.gz`, `${TRAVEL_HEADER}\n${travel}`),
    },
  })
  const a = await area(
    'A',
    '0,CH1 1AA,53.190,-2.890\n1,CH1 1AD,53.191,-2.891\n',
    '0,0,100,120,90,60\n0,1,9000,,,900\n1,0,200,220,160,80\n',
  )
  const b = await area(
    'B',
    '0,LL11 1AA,53.050,-3.000\n1,SY14 9ZZ,53.048,-3.001\n',
    '0,1,50,60,40,20\n1,1,300,350,250,90\n1,0,9100,,,950\n',
  )
  const manifest: Manifest = {
    release: RELEASE,
    builtAt: '2026-11-02T03:00:00Z',
    attribution: ['© OpenStreetMap contributors'],
    directory,
    districts,
    areas: [a, b],
  }
  const served = fakeFetch(RELEASE, files)
  return {
    manifest,
    served,
    searcher: new Searcher(manifest, new SessionFiles(RELEASE, served.fetch)),
  }
}

describe('Searcher', () => {
  it('rejects invalid input, Northern Ireland and unknown districts', async () => {
    const { searcher, served } = await fixture()
    expect(await searcher.search('hello')).toEqual({ kind: 'invalid' })
    expect(await searcher.search('bt1 1aa')).toEqual({ kind: 'northern-ireland' })
    expect(served.calls).toEqual([])
    expect(await searcher.search('ZZ1 1AA')).toEqual({ kind: 'not-found', postcode: 'ZZ1 1AA' })
  })

  it('finds a postcode in the second area of a district', async () => {
    const { searcher, served } = await fixture()
    const outcome = await searcher.search('sy149zz')
    expect(outcome.kind).toBe('found')
    if (outcome.kind !== 'found') return
    expect(outcome.postcode).toBe('SY14 9ZZ')
    expect(outcome.area.code).toBe('B')
    expect([outcome.lat, outcome.lon]).toEqual([53.048, -3.001])
    const urls = served.calls.map((c) => c.url)
    expect(urls).toContain('/data/2026-11/areas/A/postcodes.csv.gz')
    expect(urls).toContain('/data/2026-11/areas/B/postcodes.csv.gz')
    expect(urls).toContain('/data/2026-11/areas/B/travel.csv.gz')
    expect(urls).not.toContain('/data/2026-11/areas/A/travel.csv.gz')
  })

  it('returns not-found for a postcode absent from its areas', async () => {
    const { searcher } = await fixture()
    expect(await searcher.search('CH1 9ZZ')).toEqual({ kind: 'not-found', postcode: 'CH1 9ZZ' })
  })

  it('results come from the found postcode travel rows', async () => {
    const { searcher } = await fixture()
    const outcome = await searcher.search('CH1 1AD')
    if (outcome.kind !== 'found') throw new Error(outcome.kind)
    expect(outcome.results.map((r) => [r.pharmacy.code, r.walkM, r.driveS])).toEqual([
      ['FA1', 220, 80],
    ])
  })

  it('downloads nothing new for a second search in the same area', async () => {
    const { searcher, served } = await fixture()
    await searcher.search('CH1 1AA')
    const before = served.calls.length
    await searcher.search('CH1 1AD')
    expect(served.calls.length).toBe(before)
  })

  it('no requested URL contains the postcode', async () => {
    const { searcher, served } = await fixture()
    await searcher.search('SY14 9ZZ')
    await searcher.search('CH1 1AA')
    expect(served.calls.filter((c) => POSTCODE_IN_TEXT.test(c.url))).toEqual([])
  })
})

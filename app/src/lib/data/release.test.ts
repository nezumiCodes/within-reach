import { describe, expect, it } from 'vitest'
import { formatRelease, loadRelease, parseRelease } from './release'

const manifest = { release: '2026-11', built_at: '2026-11-02T03:00:00Z' }

describe('parseRelease', () => {
  it('reads a matching latest.json and manifest', () => {
    expect(parseRelease({ release: '2026-11' }, manifest)).toEqual({
      release: '2026-11',
      builtAt: '2026-11-02T03:00:00Z',
    })
  })

  it.each([
    [{ release: '../x' }, manifest],
    [{ release: '2026-11' }, { ...manifest, release: '2026-10' }],
    [null, manifest],
    [{ release: '2026-11' }, { release: '2026-11' }],
    ['2026-11', manifest],
  ])('rejects malformed input %#', (latest, man) => {
    expect(parseRelease(latest, man)).toBeNull()
  })
})

describe('formatRelease', () => {
  it('shows month and year in British English', () => {
    expect(formatRelease('2026-11')).toBe('November 2026')
    expect(formatRelease('2027-01')).toBe('January 2027')
  })
})

describe('loadRelease', () => {
  it('fetches latest.json then that release manifest', async () => {
    const urls: string[] = []
    const fake = (async (url: string) => {
      urls.push(url)
      const body = url.endsWith('latest.json') ? { release: '2026-11' } : manifest
      return new Response(JSON.stringify(body), { status: 200 })
    }) as typeof fetch
    expect(await loadRelease(fake)).toEqual({ release: '2026-11', builtAt: manifest.built_at })
    expect(urls).toEqual(['/data/latest.json', '/data/2026-11/manifest.json'])
  })

  it('returns null when there is no data release', async () => {
    const fake = (async () => new Response('', { status: 404 })) as typeof fetch
    expect(await loadRelease(fake)).toBeNull()
  })

  it('returns null on network errors', async () => {
    const fake = (async () => {
      throw new TypeError('offline')
    }) as typeof fetch
    expect(await loadRelease(fake)).toBeNull()
  })
})

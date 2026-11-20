import { describe, expect, it } from 'vitest'
import { DownloadError, fetchVerified, gunzipText, IntegrityError, SessionFiles } from './files'
import { fakeFetch, gzip, refFor } from './test-helpers'

const RELEASE = '2026-11'

describe('fetchVerified', () => {
  it('returns bytes whose hash matches', async () => {
    const data = new TextEncoder().encode('hello')
    const ref = await refFor('areas/A/x.bin', data)
    const { fetch } = fakeFetch(RELEASE, new Map([[ref.path, data]]))
    expect(await fetchVerified(RELEASE, ref, fetch)).toEqual(data)
  })

  it('rejects a body whose hash differs', async () => {
    const ref = await refFor('x.bin', new TextEncoder().encode('hello'))
    const { fetch } = fakeFetch(RELEASE, new Map([['x.bin', new TextEncoder().encode('hellp')]]))
    await expect(fetchVerified(RELEASE, ref, fetch)).rejects.toBeInstanceOf(IntegrityError)
  })

  it('rejects a wrong byte count', async () => {
    const data = new TextEncoder().encode('hello')
    const ref = { ...(await refFor('x.bin', data)), bytes: 6 }
    const { fetch } = fakeFetch(RELEASE, new Map([['x.bin', data]]))
    await expect(fetchVerified(RELEASE, ref, fetch)).rejects.toBeInstanceOf(IntegrityError)
  })

  it('turns a 404 into DownloadError', async () => {
    const ref = await refFor('missing.bin', new Uint8Array([1]))
    const { fetch } = fakeFetch(RELEASE, new Map())
    await expect(fetchVerified(RELEASE, ref, fetch)).rejects.toBeInstanceOf(DownloadError)
  })

  it('turns a network failure into DownloadError', async () => {
    const ref = await refFor('x.bin', new Uint8Array([1]))
    const failing = (async () => {
      throw new TypeError('offline')
    }) as typeof fetch
    await expect(fetchVerified(RELEASE, ref, failing)).rejects.toBeInstanceOf(DownloadError)
  })

  it('refuses a path with ..', async () => {
    const ref = await refFor('../secret', new Uint8Array([1]))
    const { fetch, calls } = fakeFetch(RELEASE, new Map())
    await expect(fetchVerified(RELEASE, ref, fetch)).rejects.toBeInstanceOf(IntegrityError)
    expect(calls).toEqual([])
  })

  it('requests with cache no-store', async () => {
    const data = new Uint8Array([1, 2])
    const ref = await refFor('x.bin', data)
    const { fetch, calls } = fakeFetch(RELEASE, new Map([['x.bin', data]]))
    await fetchVerified(RELEASE, ref, fetch)
    expect(calls).toEqual([{ url: '/data/2026-11/x.bin', init: { cache: 'no-store' } }])
  })

  it('reports progress as bytes arrive', async () => {
    const data = new Uint8Array(1000)
    const ref = await refFor('x.bin', data)
    const { fetch } = fakeFetch(RELEASE, new Map([['x.bin', data]]))
    const seen: number[] = []
    await fetchVerified(RELEASE, ref, fetch, (n) => seen.push(n))
    expect(seen.at(-1)).toBe(1000)
  })
})

describe('gunzipText', () => {
  it('decompresses gzip to text', async () => {
    expect(await gunzipText(await gzip('a,b\n1,2\n'))).toBe('a,b\n1,2\n')
  })
})

describe('SessionFiles', () => {
  it('fetches each path once', async () => {
    const data = await gzip('x')
    const ref = await refFor('x.gz', data)
    const { fetch, calls } = fakeFetch(RELEASE, new Map([['x.gz', data]]))
    const files = new SessionFiles(RELEASE, fetch)
    await Promise.all([files.bytes(ref), files.bytes(ref), files.text(ref)])
    expect(await files.text(ref)).toBe('x')
    expect(calls).toHaveLength(1)
  })

  it('retries after a failure', async () => {
    const data = new Uint8Array([7])
    const ref = await refFor('x.bin', data)
    const served = new Map<string, Uint8Array>()
    const { fetch, calls } = fakeFetch(RELEASE, served)
    const files = new SessionFiles(RELEASE, fetch)
    await expect(files.bytes(ref)).rejects.toBeInstanceOf(DownloadError)
    served.set('x.bin', data)
    expect(await files.bytes(ref)).toEqual(data)
    expect(calls).toHaveLength(2)
  })
})

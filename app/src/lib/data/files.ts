/**
 * Downloads release files whole, checks them against the manifest (NFR-05) and keeps them in
 * memory for the session only (NFR-04). Nothing is written to browser storage, and requests
 * use cache: 'no-store' so the browser's HTTP cache doesn't keep them either.
 */
import type { FileRef } from './release'

export class DownloadError extends Error {}
export class IntegrityError extends Error {}

const SAFE_PATH = /^[A-Za-z0-9_./-]+$/

export async function sha256Hex(data: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', data as Uint8Array<ArrayBuffer>)
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

async function readBody(
  response: Response,
  onProgress?: (received: number) => void,
): Promise<Uint8Array> {
  if (response.body === null) return new Uint8Array(await response.arrayBuffer())
  const reader = response.body.getReader()
  const chunks: Uint8Array[] = []
  let received = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
    received += value.length
    onProgress?.(received)
  }
  const data = new Uint8Array(received)
  let offset = 0
  for (const chunk of chunks) {
    data.set(chunk, offset)
    offset += chunk.length
  }
  return data
}

/** GET /data/<release>/<path>, checked against the manifest's byte count and SHA-256. */
export async function fetchVerified(
  release: string,
  ref: FileRef,
  fetchFn: typeof fetch = fetch,
  onProgress?: (received: number) => void,
): Promise<Uint8Array> {
  if (!SAFE_PATH.test(ref.path) || ref.path.split('/').includes('..')) {
    throw new IntegrityError(`unsafe path in manifest: ${ref.path}`)
  }
  let data: Uint8Array
  try {
    const response = await fetchFn(`/data/${release}/${ref.path}`, { cache: 'no-store' })
    if (!response.ok) throw new DownloadError(`${ref.path}: HTTP ${response.status}`)
    data = await readBody(response, onProgress)
  } catch (error) {
    if (error instanceof DownloadError) throw error
    throw new DownloadError(`${ref.path}: ${String(error)}`)
  }
  if (data.length !== ref.bytes || (await sha256Hex(data)) !== ref.sha256) {
    throw new IntegrityError(`${ref.path} does not match the manifest`)
  }
  return data
}

export async function gunzipText(data: Uint8Array): Promise<string> {
  const stream = new Blob([data as Uint8Array<ArrayBuffer>])
    .stream()
    .pipeThrough(new DecompressionStream('gzip'))
  return new Response(stream).text()
}

/** Verified files for one release, kept in memory for this tab only. */
export class SessionFiles {
  private readonly raw = new Map<string, Promise<Uint8Array>>()
  private readonly texts = new Map<string, Promise<string>>()

  constructor(
    readonly release: string,
    private readonly fetchFn: typeof fetch = fetch,
  ) {}

  bytes(ref: FileRef, onProgress?: (received: number) => void): Promise<Uint8Array> {
    return this.memo(this.raw, ref.path, () =>
      fetchVerified(this.release, ref, this.fetchFn, onProgress),
    )
  }

  text(ref: FileRef): Promise<string> {
    return this.memo(this.texts, ref.path, async () => gunzipText(await this.bytes(ref)))
  }

  private memo<T>(cache: Map<string, Promise<T>>, key: string, load: () => Promise<T>): Promise<T> {
    const existing = cache.get(key)
    if (existing) return existing
    const promise = load()
    cache.set(key, promise)
    promise.catch(() => cache.delete(key)) // so Try again re-downloads
    return promise
  }
}

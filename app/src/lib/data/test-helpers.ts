/** Shared helpers for the data-layer unit tests. Not imported by the app. */
import { sha256Hex } from './files'
import type { FileRef } from './release'

export async function gzip(text: string): Promise<Uint8Array> {
  const stream = new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

export async function refFor(path: string, data: Uint8Array): Promise<FileRef> {
  return { path, sha256: await sha256Hex(data), bytes: data.length }
}

export type Recorded = { url: string; init?: RequestInit }

/** A fetch that serves /data/<release>/<path> from a map and records every call. */
export function fakeFetch(
  release: string,
  files: Map<string, Uint8Array>,
): { fetch: typeof fetch; calls: Recorded[] } {
  const calls: Recorded[] = []
  const fn = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push({ url, init })
    const prefix = `/data/${release}/`
    const body = url.startsWith(prefix) ? files.get(url.slice(prefix.length)) : undefined
    if (body === undefined) return new Response('', { status: 404 })
    return new Response(body.slice(), { status: 200 })
  }) as typeof fetch
  return { fetch: fn, calls }
}

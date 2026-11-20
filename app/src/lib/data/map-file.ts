/**
 * The area map, downloaded whole and read from memory (Phase 2 design, sections 4c and 6).
 * The map library asks for byte ranges, but they are served from memory here: no HTTP range or
 * tile requests ever leave the browser, so the host learns only which area was opened.
 */
import type { RangeResponse, Source } from 'pmtiles'
import { IntegrityError, sha256Hex, type SessionFiles } from './files'
import type { MapRef } from './release'

/** Fetch and verify every part, join them, and verify the whole file. */
export async function loadAreaMap(
  files: SessionFiles,
  map: MapRef,
  onProgress?: (received: number, total: number) => void,
): Promise<ArrayBuffer> {
  const received = map.parts.map(() => 0)
  const report = (): void => onProgress?.(Math.min(sumOf(received), map.bytes), map.bytes)
  const parts = await Promise.all(
    map.parts.map((ref, i) =>
      files.bytes(ref, (n) => {
        received[i] = n
        report()
      }),
    ),
  )
  const whole = new Uint8Array(sumOf(parts.map((p) => p.length)))
  let offset = 0
  for (const part of parts) {
    whole.set(part, offset)
    offset += part.length
  }
  if (whole.length !== map.bytes || (await sha256Hex(whole)) !== map.sha256) {
    throw new IntegrityError('the joined map does not match the manifest')
  }
  onProgress?.(map.bytes, map.bytes)
  return whole.buffer
}

function sumOf(values: number[]): number {
  return values.reduce((a, b) => a + b, 0)
}

/** A PMTiles source backed by an in-memory copy of the whole file. */
export class MemorySource implements Source {
  constructor(
    private readonly key: string,
    private readonly data: ArrayBuffer,
  ) {}

  getKey(): string {
    return this.key
  }

  async getBytes(offset: number, length: number): Promise<RangeResponse> {
    return { data: this.data.slice(offset, offset + length) }
  }
}

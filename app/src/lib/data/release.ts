/**
 * The published data release (spec FR-05): which month's data the site is serving.
 * Reads /data/latest.json, then that release's manifest. Same-origin GETs only (NFR-01).
 */

export type ReleaseInfo = { release: string; builtAt: string }
export type FileRef = { path: string; sha256: string; bytes: number }
export type MapRef = { bytes: number; sha256: string; parts: FileRef[] }
export type AreaEntry = {
  code: string
  name: string
  nation: string
  files: { postcodes: FileRef; travel: FileRef }
  map?: MapRef
}
export type Manifest = {
  release: string
  builtAt: string
  attribution: string[]
  directory: FileRef
  districts: FileRef
  areas: AreaEntry[]
}

const RELEASE_NAME = /^\d{4}-(0[1-9]|1[0-2])$/
const SHA256 = /^[0-9a-f]{64}$/

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

class Malformed extends Error {}

function fileRef(value: unknown): FileRef {
  if (
    !isRecord(value) ||
    typeof value.path !== 'string' ||
    typeof value.sha256 !== 'string' ||
    !SHA256.test(value.sha256) ||
    typeof value.bytes !== 'number'
  ) {
    throw new Malformed()
  }
  return { path: value.path, sha256: value.sha256, bytes: value.bytes }
}

function mapRef(value: unknown): MapRef | undefined {
  if (value === undefined) return undefined
  if (!isRecord(value) || !Array.isArray(value.parts) || value.parts.length === 0) {
    throw new Malformed()
  }
  const { sha256, bytes } = fileRef({ ...value, path: '' })
  return { sha256, bytes, parts: value.parts.map(fileRef) }
}

function areaEntry(value: unknown): AreaEntry {
  if (!isRecord(value) || !isRecord(value.files)) throw new Malformed()
  const { code, name, nation } = value
  if (typeof code !== 'string' || typeof name !== 'string' || typeof nation !== 'string') {
    throw new Malformed()
  }
  const map = mapRef(value.map)
  return {
    code,
    name,
    nation,
    files: { postcodes: fileRef(value.files.postcodes), travel: fileRef(value.files.travel) },
    ...(map ? { map } : {}),
  }
}

/** The manifest of the release latest.json names, or null if anything doesn't match. */
export function parseManifest(latest: unknown, manifest: unknown): Manifest | null {
  if (!isRecord(latest) || !isRecord(manifest)) return null
  const release = latest.release
  if (typeof release !== 'string' || !RELEASE_NAME.test(release)) return null
  if (manifest.release !== release || typeof manifest.built_at !== 'string') return null
  try {
    const attribution = Array.isArray(manifest.attribution)
      ? manifest.attribution.filter((line): line is string => typeof line === 'string')
      : []
    if (!Array.isArray(manifest.areas)) throw new Malformed()
    return {
      release,
      builtAt: manifest.built_at,
      attribution,
      directory: fileRef(manifest.directory),
      districts: fileRef(manifest.districts),
      areas: manifest.areas.map(areaEntry),
    }
  } catch (error) {
    if (error instanceof Malformed) return null
    throw error
  }
}

export function parseRelease(latest: unknown, manifest: unknown): ReleaseInfo | null {
  if (!isRecord(latest) || !isRecord(manifest)) return null
  const release = latest.release
  if (typeof release !== 'string' || !RELEASE_NAME.test(release)) return null
  if (manifest.release !== release || typeof manifest.built_at !== 'string') return null
  return { release, builtAt: manifest.built_at }
}

export function formatRelease(release: string): string {
  const [year, month] = release.split('-').map(Number)
  return new Intl.DateTimeFormat('en-GB', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, 1)))
}

async function getJson(fetchFn: typeof fetch, url: string): Promise<unknown> {
  const response = await fetchFn(url, { cache: 'no-cache' })
  if (!response.ok) throw new Error(`${url}: ${response.status}`)
  return response.json()
}

async function loadRaw(fetchFn: typeof fetch): Promise<[unknown, unknown] | null> {
  try {
    const latest = await getJson(fetchFn, '/data/latest.json')
    if (!isRecord(latest) || typeof latest.release !== 'string') return null
    if (!RELEASE_NAME.test(latest.release)) return null // validated before use in a path
    return [latest, await getJson(fetchFn, `/data/${latest.release}/manifest.json`)]
  } catch {
    return null
  }
}

export async function loadRelease(fetchFn: typeof fetch = fetch): Promise<ReleaseInfo | null> {
  const raw = await loadRaw(fetchFn)
  return raw ? parseRelease(...raw) : null
}

export async function loadManifest(fetchFn: typeof fetch = fetch): Promise<Manifest | null> {
  const raw = await loadRaw(fetchFn)
  return raw ? parseManifest(...raw) : null
}

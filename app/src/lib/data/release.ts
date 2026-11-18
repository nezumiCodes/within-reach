/**
 * The published data release (spec FR-05): which month's data the site is serving.
 * Reads /data/latest.json, then that release's manifest. Same-origin GETs only (NFR-01).
 */

export type ReleaseInfo = { release: string; builtAt: string }

const RELEASE_NAME = /^\d{4}-(0[1-9]|1[0-2])$/

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
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

export async function loadRelease(fetchFn: typeof fetch = fetch): Promise<ReleaseInfo | null> {
  try {
    const latest = await getJson(fetchFn, '/data/latest.json')
    if (!isRecord(latest) || typeof latest.release !== 'string') return null
    if (!RELEASE_NAME.test(latest.release)) return null // validated before use in a path
    const manifest = await getJson(fetchFn, `/data/${latest.release}/manifest.json`)
    return parseRelease(latest, manifest)
  } catch {
    return null
  }
}

import { readFileSync } from 'node:fs'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vitest/config'

/** Read the `/*` block of public/_headers so `vite preview` serves the same headers as Cloudflare. */
function siteHeaders(): Record<string, string> {
  const lines = readFileSync(new URL('./public/_headers', import.meta.url), 'utf8').split('\n')
  const headers: Record<string, string> = {}
  let inSiteBlock = false
  for (const line of lines) {
    if (line.trim() === '' || line.trimStart().startsWith('#')) continue
    if (!line.startsWith(' ')) {
      inSiteBlock = line.trim() === '/*'
      continue
    }
    if (inSiteBlock) {
      const at = line.indexOf(':')
      headers[line.slice(0, at).trim()] = line.slice(at + 1).trim()
    }
  }
  return headers
}

/**
 * The local preview runs on plain http://localhost. WebKit applies upgrade-insecure-requests
 * even to localhost, which breaks loading, so drop that one directive locally. The live site
 * keeps it (checked by running the browser tests with LIVE_URL).
 */
function localPreviewHeaders(): Record<string, string> {
  const headers = siteHeaders()
  const csp = headers['Content-Security-Policy']
  if (csp) {
    headers['Content-Security-Policy'] = csp
      .split(';')
      .map((directive) => directive.trim())
      .filter((directive) => directive !== 'upgrade-insecure-requests')
      .join('; ')
  }
  return headers
}

export default defineConfig({
  plugins: [svelte()],
  build: {
    // Keep everything as same-origin files; no inline scripts, so the CSP needs no 'unsafe-inline'.
    modulePreload: { polyfill: false },
    assetsInlineLimit: 0,
    sourcemap: false,
  },
  preview: {
    headers: localPreviewHeaders(),
  },
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
  },
})

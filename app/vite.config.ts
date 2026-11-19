import { readFileSync } from 'node:fs'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import type { Plugin } from 'vite'
import { defineConfig } from 'vitest/config'

/** Read the path blocks of public/_headers (for example `/*` and `/data/*`) into header maps. */
function headerBlocks(): Map<string, Record<string, string>> {
  const lines = readFileSync(new URL('./public/_headers', import.meta.url), 'utf8').split('\n')
  const blocks = new Map<string, Record<string, string>>()
  let current: Record<string, string> | null = null
  for (const line of lines) {
    if (line.trim() === '' || line.trimStart().startsWith('#')) continue
    if (!line.startsWith(' ')) {
      const path = line.trim()
      current = path.startsWith('/') ? {} : null // skip host-specific blocks such as https://…
      if (current) blocks.set(path, current)
      continue
    }
    if (current) {
      const at = line.indexOf(':')
      current[line.slice(0, at).trim()] = line.slice(at + 1).trim()
    }
  }
  return blocks
}

/** The `/*` block, served on every response, as Cloudflare does. */
function siteHeaders(): Record<string, string> {
  return { ...(headerBlocks().get('/*') ?? {}) }
}

/** Serve the `/data/*` block on /data/ responses in `vite preview`, as Cloudflare does. */
function dataHeadersPlugin(): Plugin {
  const dataHeaders = headerBlocks().get('/data/*') ?? {}
  return {
    name: 'within-reach-data-headers',
    configurePreviewServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url?.startsWith('/data/')) {
          for (const [name, value] of Object.entries(dataHeaders)) res.setHeader(name, value)
        }
        next()
      })
    },
  }
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
  plugins: [svelte(), dataHeadersPlugin()],
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
    // NFR-15: at least 85% line coverage of the pure engine.
    coverage: {
      provider: 'v8',
      include: ['src/lib/engine/**/*.ts'],
      exclude: ['src/lib/engine/**/*.test.ts'],
      thresholds: { lines: 85 },
    },
  },
})

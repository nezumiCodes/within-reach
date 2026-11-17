/**
 * Privacy guard for every browser test (spec test level 5, NFR-01, AC-07).
 *
 * Import `test` and `expect` from this file instead of '@playwright/test'. Each test then
 * automatically fails if the page:
 *   - makes any request other than GET,
 *   - requests anything from a host other than the site's own,
 *   - sends a UK postcode or a synthetic client reference (SYN-...) in a URL, header or body,
 *   - triggers a Content Security Policy violation.
 */
import { test as base, expect, type Request } from '@playwright/test'

const POSTCODE_IN_TEXT = /\b(?:[A-Z]{1,2}[0-9][A-Z0-9]?|GIR)\s*[0-9][A-Z]{2}\b/i
const CLIENT_REF_IN_TEXT = /\bSYN-[A-Z0-9-]+\b/i

export function privacyProblems(request: Request, siteHost: string): string[] {
  const problems: string[] = []
  const url = new URL(request.url())
  if (url.protocol === 'data:' || url.protocol === 'blob:') return problems

  if (request.method() !== 'GET') problems.push(`non-GET request: ${request.method()} ${url.href}`)
  if (url.host !== siteHost) problems.push(`request to another host: ${url.href}`)

  const haystacks = [
    decodeURIComponent(url.pathname + url.search + url.hash),
    JSON.stringify(request.headers()),
    request.postData() ?? '',
  ]
  for (const text of haystacks) {
    if (POSTCODE_IN_TEXT.test(text)) problems.push(`postcode-like text sent: ${url.href}`)
    if (CLIENT_REF_IN_TEXT.test(text)) problems.push(`client reference sent: ${url.href}`)
  }
  return problems
}

type GuardOptions = {
  /** Set to true only in tests that deliberately trigger a CSP block (AC-08). */
  expectCspBlock: boolean
}

export const test = base.extend<GuardOptions & { privacyGuard: void }>({
  expectCspBlock: [false, { option: true }],
  privacyGuard: [
    async ({ context, page, baseURL, expectCspBlock }, use) => {
      const siteHost = new URL(baseURL ?? 'http://localhost:4173').host
      const problems: string[] = []

      // context-level listener also catches service worker and popup requests.
      context.on('request', (request) => problems.push(...privacyProblems(request, siteHost)))
      page.on('console', (msg) => {
        const isCsp = /Content[- ]Security[- ]Policy/i.test(msg.text())
        if (msg.type() === 'error' && isCsp && !expectCspBlock) {
          problems.push(`CSP violation: ${msg.text()}`)
        }
      })

      await use()

      expect(problems, 'privacy guard').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }

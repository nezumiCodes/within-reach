import AxeBuilder from '@axe-core/playwright'
import { expect, test } from './fixtures.ts'

test('placeholder page loads under the site CSP', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: 'Within Reach' })).toBeVisible()
})

test('the site sets no cookies and stores nothing', async ({ page, context }) => {
  await page.goto('/')
  expect(await context.cookies()).toEqual([])
  const stored = await page.evaluate(async () => ({
    local: localStorage.length,
    session: sessionStorage.length,
    idb: (await indexedDB.databases()).length,
  }))
  expect(stored).toEqual({ local: 0, session: 0, idb: 0 })
})

test('security headers are served', async ({ page }) => {
  const response = await page.goto('/')
  const headers = response?.headers() ?? {}
  const csp = headers['content-security-policy'] ?? ''
  expect(csp).toContain("default-src 'self'")
  expect(csp).toContain("script-src 'self'")
  expect(csp).not.toContain('unsafe-inline')
  expect(csp).toContain("frame-ancestors 'none'")
  expect(headers['referrer-policy']).toBe('no-referrer')
  expect(headers['x-content-type-options']).toBe('nosniff')
})

test.describe('CSP enforcement', () => {
  test.use({ expectCspBlock: true })

  test('the page blocks requests to other domains (AC-08)', async ({ page }) => {
    await page.goto('/')
    const result = await page.evaluate(async () => {
      try {
        await fetch('https://example.com/', { mode: 'no-cors' })
        return 'allowed'
      } catch {
        return 'blocked'
      }
    })
    expect(result).toBe('blocked')
  })
})

test('placeholder page has no accessibility violations (WCAG 2.2 AA)', async ({ page }) => {
  await page.goto('/')
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(results.violations).toEqual([])
})

test('data release date is shown (FR-05)', async ({ page }) => {
  await page.route('**/data/latest.json', (route) =>
    route.fulfill({ json: { release: '2026-11', previous: null } }),
  )
  await page.route('**/data/2026-11/manifest.json', (route) =>
    route.fulfill({ json: { release: '2026-11', built_at: '2026-11-02T03:00:00Z' } }),
  )
  await page.goto('/')
  await expect(page.getByText('Data release: November 2026')).toBeVisible()
})

test('no data release shows nothing', async ({ page }) => {
  await page.route('**/data/**', (route) => route.fulfill({ status: 404, body: '' }))
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByText('Data release')).toHaveCount(0)
})

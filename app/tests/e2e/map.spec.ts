/**
 * The private area map (Phase 2 design, sections 4 and 5): downloaded whole, read from memory,
 * pins linked to the list. Runs against the fixture release, or the live site with LIVE_URL.
 */
import AxeBuilder from '@axe-core/playwright'
import type { Page, Request } from '@playwright/test'
import { expect, test } from './fixtures.ts'

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
const TILE_PATH = /\/\d+\/\d+\/\d+(\.pbf|\.mvt)?$/

async function search(page: Page, postcode: string): Promise<void> {
  await page.getByLabel('Postcode', { exact: true }).fill(postcode)
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(page.getByTestId('result').first()).toBeVisible()
}

const map = (page: Page) => page.getByTestId('map')

test.beforeEach(async ({ page, request }) => {
  // The live site has no maps until the first data release built with them.
  const latest = await (await request.get('/data/latest.json')).json()
  const manifest = await (await request.get(`/data/${latest.release}/manifest.json`)).json()
  test.skip(!manifest.areas?.[0]?.map, 'this data release has no maps')
  await page.goto('/')
})

test('a search draws the map with a pin per listed pharmacy', async ({ page }) => {
  await search(page, 'CH2 3JQ')
  await expect(map(page)).toHaveAttribute('data-map-state', 'ready', { timeout: 20_000 })
  await expect(map(page)).toHaveAttribute('data-pin-count', '10')
  await expect(map(page)).toHaveAttribute(
    'aria-label',
    'Map of the postcode and the 10 pharmacies listed',
  )
  await expect(map(page).getByText('© OpenStreetMap contributors')).toBeVisible()
  await page.getByRole('button', { name: 'Show 10 more' }).click()
  await expect(map(page)).toHaveAttribute('data-pin-count', '18')
})

test('the map file is downloaded whole, once per part, with no range or tile requests', async ({
  page,
  context,
}) => {
  const requests: Request[] = []
  context.on('request', (r) => requests.push(r))
  await search(page, 'CH2 3JQ') // Cheshire West and Chester: map in two parts
  await expect(map(page)).toHaveAttribute('data-map-state', 'ready', { timeout: 20_000 })
  const mapRequests = requests.filter((r) => r.url().includes('map.pmtiles'))
  expect(mapRequests.map((r) => new URL(r.url()).pathname).sort()).toEqual([
    '/data/2026-11/areas/E06000050/map.pmtiles.000',
    '/data/2026-11/areas/E06000050/map.pmtiles.001',
  ])
  for (const r of mapRequests) expect(r.headers()['range']).toBeUndefined()
  expect(requests.filter((r) => TILE_PATH.test(new URL(r.url()).pathname))).toEqual([])
})

test('a second search in the same area downloads nothing new', async ({ page, context }) => {
  await search(page, 'CH2 3JQ')
  await expect(map(page)).toHaveAttribute('data-map-state', 'ready', { timeout: 20_000 })
  const later: string[] = []
  context.on('request', (r) => later.push(new URL(r.url()).pathname))
  await page.getByLabel('Postcode', { exact: true }).fill('CH2 1HU')
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(page.getByRole('heading', { name: 'Pharmacies near CH2 1HU' })).toBeVisible()
  await expect(map(page)).toHaveAttribute('data-map-state', 'ready')
  expect(later.filter((p) => p.startsWith('/data/'))).toEqual([])
})

test('clicking Show on map selects the pin', async ({ page }) => {
  await search(page, 'CH2 3JQ')
  await expect(map(page)).toHaveAttribute('data-map-state', 'ready', { timeout: 20_000 })
  const third = page.getByTestId('result').nth(2)
  await third.getByRole('button', { name: 'Show on map' }).click()
  await expect(map(page)).toHaveAttribute(
    'data-selected-idx',
    (await third.getAttribute('data-ph-idx')) ?? '',
  )
})

test('map page passes axe', async ({ page }) => {
  await search(page, 'CH2 3JQ')
  await expect(map(page)).toHaveAttribute('data-map-state', 'ready', { timeout: 20_000 })
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze()
  expect(results.violations).toEqual([])
})

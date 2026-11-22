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
  // Some headless browsers (Firefox on Linux CI) have no WebGL, so the map can't draw there;
  // that path is covered by map-no-webgl.spec.ts.
  const webgl = await page.evaluate(() => {
    const gl = document.createElement('canvas').getContext('webgl')
    gl?.getExtension('WEBGL_lose_context')?.loseContext()
    return gl !== null
  })
  test.skip(!webgl, 'this browser has no WebGL')
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
  // The expected parts come from the manifest, so this runs on the live release too.
  const latest = await (await page.request.get('/data/latest.json')).json()
  const manifest = await (await page.request.get(`/data/${latest.release}/manifest.json`)).json()
  const area = manifest.areas.find((a: { code: string }) => a.code === 'E06000050')
  const expected = area.map.parts.map((p: { path: string }) => `/data/${latest.release}/${p.path}`)
  // The fixture's map is split in two, so splitting is always exercised in CI.
  if (!process.env.LIVE_URL) expect(expected).toHaveLength(2)
  const requests: Request[] = []
  context.on('request', (r) => requests.push(r))
  await search(page, 'CH2 3JQ') // Cheshire West and Chester
  await expect(map(page)).toHaveAttribute('data-map-state', 'ready', { timeout: 20_000 })
  const mapRequests = requests.filter((r) => r.url().includes('map.pmtiles'))
  expect(mapRequests.map((r) => new URL(r.url()).pathname).sort()).toEqual(expected.sort())
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

test('searching another area while a map loads abandons the first map', async ({ page }) => {
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => (release = resolve))
  await page.route('**/areas/E06000050/map.pmtiles*', async (route) => {
    await held
    await route.continue()
  })
  const styleFetches: string[] = []
  page.on('request', (r) => {
    if (new URL(r.url()).pathname === '/map/style.json') styleFetches.push(r.url())
  })
  await search(page, 'CH2 3JQ') // England: its map download is held
  await search(page, 'LL11 1AL') // Wales: a different area
  await expect(map(page)).toHaveAttribute('data-map-state', 'ready', { timeout: 20_000 })
  release()
  await page.waitForTimeout(1500)
  expect(styleFetches).toHaveLength(1) // only the Welsh map was ever created
  await expect(page.locator('canvas.maplibregl-canvas')).toHaveCount(1)
})

test('hovering or focusing a list entry highlights its pin', async ({ page }) => {
  await search(page, 'CH2 3JQ')
  await expect(map(page)).toHaveAttribute('data-map-state', 'ready', { timeout: 20_000 })
  const second = page.getByTestId('result').nth(1)
  const idx = (await second.getAttribute('data-ph-idx')) ?? ''
  await second.hover()
  await expect(map(page)).toHaveAttribute('data-highlighted-idx', idx)
  // Keyboard focus without the pointer resting on another entry (whichever happens last wins).
  await page.getByRole('heading', { level: 1 }).hover()
  await expect(map(page)).toHaveAttribute('data-highlighted-idx', '')
  const fourth = page.getByTestId('result').nth(3)
  await fourth.getByRole('button', { name: 'Show on map' }).focus()
  await expect(map(page)).toHaveAttribute(
    'data-highlighted-idx',
    (await fourth.getAttribute('data-ph-idx')) ?? '',
  )
})

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('clicking a pin selects its entry and scrolls it into view', async ({ page }) => {
    await search(page, 'CH2 3JQ')
    await expect(map(page)).toHaveAttribute('data-map-state', 'ready', { timeout: 20_000 })
    // Find pin 7 on screen through the map instance the panel exposes for tests.
    const point = await page.evaluate(() => {
      type Feature = { properties: { n: number }; geometry: { coordinates: [number, number] } }
      const m = (
        document.querySelector('[data-testid=map] .canvas') as unknown as {
          maplibre: {
            queryRenderedFeatures: (o: object) => Feature[]
            project: (c: [number, number]) => { x: number; y: number }
          }
        }
      ).maplibre
      const pin = m.queryRenderedFeatures({ layers: ['pins'] }).find((f) => f.properties.n === 7)
      return pin ? m.project(pin.geometry.coordinates) : null
    })
    expect(point).not.toBeNull()
    const box = await map(page).locator('canvas').boundingBox()
    await page.mouse.click(box!.x + point!.x, box!.y + point!.y)
    const seventh = page.getByTestId('result').nth(6)
    await expect(map(page)).toHaveAttribute(
      'data-selected-idx',
      (await seventh.getAttribute('data-ph-idx')) ?? '',
    )
    await expect(seventh).toBeInViewport()
  })
})

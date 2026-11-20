/** The map is an extra: without WebGL the list still works (Phase 2 design, section 5). */
import { expect, test } from './fixtures.ts'

// Chromium-only flags: skip before any other browser is launched with them.
test.skip(({ browserName }) => browserName !== 'chromium', 'launch flags are Chromium-only')
test.use({ launchOptions: { args: ['--disable-webgl', '--disable-3d-apis'] } })

test("with WebGL disabled the list works and the map says it isn't available", async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Postcode', { exact: true }).fill('CH2 3JQ')
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(page.getByTestId('result')).toHaveCount(10)
  await expect(page.getByTestId('map')).toHaveAttribute('data-map-state', 'unavailable')
  await expect(
    page.getByText('Map not available on this device. The list below has all the details.'),
  ).toBeVisible()
})

/**
 * Public postcode search (Phase 2 design, section 5), run against the fixture release
 * (tests/fixtures/data: parts of Chester and Wrexham from the November 2026 data).
 */
import AxeBuilder from '@axe-core/playwright'
import type { Page } from '@playwright/test'
import { expect, test } from './fixtures.ts'

const PC = {
  chester: 'CH2 3JQ', // 18 nearby pharmacies; the closest is closed on Sundays
  chesterOther: 'CH2 1HU',
  wrexham: 'LL11 1AL', // Welsh: no opening hours
  twoArea: 'SY14 9ZZ', // district mapped to both areas; postcode in the second
  cycle: 'CH4 7DJ', // Lache: every way out on foot uses a cycle path not signed for walkers
}
const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

async function search(page: Page, postcode: string): Promise<void> {
  await page.getByLabel('Postcode', { exact: true }).fill(postcode)
  await page.getByRole('button', { name: 'Search' }).click()
}

const results = (page: Page) => page.getByTestId('result')

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('a search lists pharmacies closest first, numbered from 1', async ({ page }) => {
  await search(page, PC.chester)
  await expect(results(page)).toHaveCount(10)
  const numbers = await results(page).locator('[data-testid="number"]').allTextContents()
  expect(numbers).toEqual(['1', '2', '3', '4', '5', '6', '7', '8', '9', '10'])
  const walks = (await results(page).evaluateAll((els) =>
    els.map((el) => Number(el.getAttribute('data-walk-m'))),
  )) as number[]
  expect(walks).toEqual([...walks].sort((a, b) => a - b))
  await expect(results(page).first()).toContainText(/min walk · \d+ min drive/)
})

test('driving sort reorders the list', async ({ page }) => {
  await search(page, PC.chester)
  await page.getByLabel('Driving').check()
  const drives = (await results(page).evaluateAll((els) =>
    els.map((el) => Number(el.getAttribute('data-drive-s'))),
  )) as number[]
  expect(drives).toEqual([...drives].sort((a, b) => a - b))
})

test('Open Sunday hides closed pharmacies and summarises them', async ({ page }) => {
  await search(page, PC.chester)
  await page.getByLabel('Open Sunday').check()
  await expect(page.getByTestId('hidden-summary')).toHaveText(
    /^\d+ closer pharmac(y|ies) hidden: not open on Sundays\.$/,
  )
  await expect(page.getByText('Filters: Open Sunday')).toBeVisible()
})

test('Welsh pharmacies stay listed under Opening hours not known when a filter is on', async ({
  page,
}) => {
  await search(page, PC.wrexham)
  await page.getByLabel('Open late').check()
  await expect(page.getByRole('heading', { name: 'Opening hours not known' })).toBeVisible()
  await expect(
    page.getByText(
      "Scottish and Welsh pharmacy lists don't include opening hours, so these pharmacies can't be filtered.",
    ),
  ).toBeVisible()
  await expect(results(page)).toHaveCount(10)
  await expect(results(page).first()).toContainText('No opening hours included')
})

test('Show 10 more adds entries until all are shown', async ({ page }) => {
  await search(page, PC.chester)
  await page.getByRole('button', { name: 'Show 10 more' }).click()
  await expect(results(page)).toHaveCount(18)
  await expect(page.getByRole('button', { name: 'Show 10 more' })).toHaveCount(0)
})

test('a walk that needs an unsigned cycle path says so', async ({ page }) => {
  test.skip(!!process.env.LIVE_URL, 'depends on the fixture release')
  await search(page, PC.cycle)
  await expect(results(page)).toHaveCount(10)
  await expect(results(page).first()).toContainText('min walk, partly on a cycle path')
  await search(page, PC.chester)
  await expect(results(page).first()).not.toContainText('cycle path')
})

test('opening hours open in a details element', async ({ page }) => {
  await search(page, PC.chester)
  const first = results(page).first()
  await first.getByText('Opening hours').click()
  await expect(first.getByRole('table')).toContainText('Monday')
  await expect(first.getByRole('table')).toContainText('Sunday')
})

test('invalid, Northern Ireland and not-found messages', async ({ page }) => {
  const status = page.getByRole('status')
  await search(page, 'hello')
  await expect(status).toHaveText('Enter a full UK postcode, for example CH2 3JQ.')
  await search(page, 'bt1 1aa')
  await expect(status).toHaveText(
    "Northern Ireland isn't covered yet. Within Reach covers England, Scotland and Wales.",
  )
  await search(page, 'ch29zz')
  await expect(status).toHaveText("We couldn't find CH2 9ZZ. Check it's correct and still in use.")
  await expect(results(page)).toHaveCount(0)
})

test('a district spanning two areas finds the postcode', async ({ page }) => {
  test.skip(!!process.env.LIVE_URL, 'SY14 9ZZ is a made-up postcode that only the fixture has')
  await search(page, PC.twoArea)
  await expect(results(page)).toHaveCount(10)
})

test('a failed download shows Try again, and Try again recovers', async ({ page }) => {
  await page.route('**/travel.csv.gz', (route) => route.abort())
  await search(page, PC.chester)
  await expect(page.getByRole('status')).toHaveText(
    "Couldn't download the pharmacy data. Check your connection and try again.",
  )
  await page.unroute('**/travel.csv.gz')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(results(page)).toHaveCount(10)
})

test('a tampered travel file shows the integrity message', async ({ page }) => {
  await page.route('**/travel.csv.gz', async (route) => {
    const response = await route.fetch()
    const body = Buffer.concat([await response.body(), Buffer.from([0])])
    await route.fulfill({ response, body })
  })
  await search(page, PC.chester)
  await expect(page.getByRole('status')).toHaveText(
    "The downloaded data didn't pass its integrity check, so it hasn't been used.",
  )
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible()
  await expect(results(page)).toHaveCount(0)
})

test('the search leaves no trace', async ({ page, context }) => {
  const historyBefore = await page.evaluate(() => history.length)
  await search(page, PC.chester)
  await expect(results(page)).toHaveCount(10)
  expect(new URL(page.url()).pathname + new URL(page.url()).search + new URL(page.url()).hash).toBe(
    '/',
  )
  const stored = await page.evaluate(async () => ({
    history: history.length,
    local: localStorage.length,
    session: sessionStorage.length,
    idb: (await indexedDB.databases()).length,
    caches: (await caches.keys()).length,
  }))
  expect(stored).toEqual({ history: historyBefore, local: 0, session: 0, idb: 0, caches: 0 })
  expect(await context.cookies()).toEqual([])
})

test('keyboard only: search, sort, filter, open hours, show more', async ({ page }) => {
  await page.keyboard.press('Tab') // skip link or first focusable
  await page.getByLabel('Postcode', { exact: true }).focus()
  await page.keyboard.type(PC.chester)
  await page.keyboard.press('Enter')
  await expect(results(page)).toHaveCount(10)

  await page.getByLabel('Walking').focus()
  await page.keyboard.press('ArrowDown')
  await expect(page.getByLabel('Driving')).toBeChecked()

  await page.getByLabel('Open Saturday').focus()
  await page.keyboard.press('Space')
  await expect(page.getByLabel('Open Saturday')).toBeChecked()

  const summary = results(page).first().locator('summary')
  await summary.focus()
  await page.keyboard.press('Enter')
  await expect(results(page).first().getByRole('table')).toBeVisible()

  const more = page.getByRole('button', { name: 'Show 10 more' })
  if ((await more.count()) > 0) {
    await more.focus()
    await page.keyboard.press('Enter')
  }
})

test('results page passes axe, with a filter on and with an error', async ({
  page,
  browserName,
}) => {
  // In Firefox, a full axe scan after Playwright focuses or clicks a form control crashes the
  // page process (Playwright's Firefox driver; the same scan after a script-driven focus passes).
  // Firefox still runs the at-rest axe scan in site.spec.ts and every functional test here.
  test.skip(browserName === 'firefox', 'Playwright Firefox driver crashes during this scan')
  await search(page, PC.chester)
  await page.getByLabel('Open Sunday').check()
  await results(page).first().getByText('Opening hours').click()
  const withResults = await new AxeBuilder({ page }).withTags(WCAG).analyze()
  expect(withResults.violations).toEqual([])

  await search(page, 'hello')
  const withError = await new AxeBuilder({ page }).withTags(WCAG).analyze()
  expect(withError.violations).toEqual([])
})

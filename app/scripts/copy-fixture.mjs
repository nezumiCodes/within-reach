// Copies the test data release (tests/fixtures/data) into the preview build's /data/, unless a
// real data release is already there. Used only by the browser tests (playwright.config.ts).
import { cpSync, existsSync } from 'node:fs'

const target = new URL('../dist/data/', import.meta.url)
if (existsSync(new URL('latest.json', target))) {
  console.log('dist/data already has a release; leaving it.')
} else {
  cpSync(new URL('../tests/fixtures/data/', import.meta.url), target, { recursive: true })
  console.log('Copied the test data release into dist/data.')
}

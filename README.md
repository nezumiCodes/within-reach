# Within Reach

Finds the nearest suitable pharmacies for a postcode in England, Scotland and Wales, for drug and
alcohol services reviewing where clients collect supervised doses.

**Client data never leaves the browser.** A monthly pipeline turns public data into static lookup
files. The web app downloads whole-area files and does all matching locally. The site has no
server-side code, sets no cookies, and makes no requests to any other domain.

Live site (when released): https://withinreach.vasnik.net

## Repository layout

| Path | What |
|---|---|
| `pipeline/` | Python 3.12 pipeline: public data → per-area bundles (public data only) |
| `app/` | Svelte + TypeScript static web app. `src/lib/engine` holds pure matching logic; `data`, `files` and `ui` hold the rest |
| `app/public/_headers` | Security headers (CSP and others) served by Cloudflare Pages and by the local preview |
| `app/tests/e2e/` | Playwright tests. Every test runs a privacy guard that fails on off-site, non-GET or postcode-bearing requests |
| `fixtures/synthetic/` | Synthetic test data only (`SYN-` references) |
| `scripts/check_client_data.py` | Pre-commit guard that blocks real-looking client data |
| `docs/` | Setup steps and decision record |

## Development

```sh
# One-off
uvx pre-commit install
(cd pipeline && uv sync)
(cd app && npm ci && npx playwright install chromium firefox webkit)

# Pipeline
cd pipeline && uv run pytest . ../scripts && uv run ruff check . ../scripts && uv run mypy

# App
cd app
npm run dev        # local dev server
npm test           # engine unit tests (Vitest)
npm run check      # type checks
npm run test:e2e   # browser, privacy, CSP and accessibility tests (builds first)
```

Never commit real client data. Spreadsheets and CSVs are ignored by git, except under
`fixtures/synthetic/`, and the pre-commit hook checks those too.

## Attribution

When released, this tool will use:

- Public sector information licensed under the Open Government Licence v3.0 (ONS Postcode
  Directory, NHSBSA, Public Health Scotland, NHS Organisation Data Service)
- Contains OS data © Crown copyright and database right
- Map data © OpenStreetMap contributors, available under the Open Database Licence. The
  published travel tables are offered under the ODbL.

## Licence

Code: [GNU AGPL-3.0](LICENSE).

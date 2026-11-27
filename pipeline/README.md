# Within Reach pipeline

Turns public data (ONSPD, the three national pharmacy lists, OpenStreetMap) into per-area static bundles. It handles public data only.

The stages are built in Phase 1. Run the checks with `uv run pytest . ../scripts`, `uv run ruff check . ../scripts` and `uv run mypy`.

## Area maps

`build --maps tilemaker` also builds each area's street map (`areas/<code>/map.pmtiles`, see `docs/data-format.md`). It needs Docker, the water polygons that `fetch` downloads into `.cache/coastline/`, and the tilemaker image pinned in `config.toml`. The tilemaker settings are in `maps/config-openmaptiles.json`.

Walking routes use UK rules, `osrm/foot-gb.lua`: OSRM's stock foot profile plus cycle paths, bridleways and trunk roads with a pavement. Cycle paths not signed for walkers are put in an excludable class, so the build can mark walks that need one (`walk_cycle`). The pipeline mounts `osrm/` into the OSRM container. `config.toml` also sets how far the search widens when the nearest pharmacies can't be reached (`reach_cap_m`, `reach_max_rounds`) and the threshold for the cycle path note (`cycle_note_min_extra_m`). See `docs/data-format.md`.

The test that runs real tilemaker is skipped unless you set `RUN_TILEMAKER=1`, in the same way as `RUN_OSRM=1` for the routing tests.

To regenerate the app's test data from a published release, see `scripts/make_fixture_release.py`.

## Pharmacy services (needle exchange)

`fetch-services` downloads each pharmacy's listed services from NHS England's Directory of Healthcare Services (DoHS) API, v3, and writes `dohs_services.json` into the cache. `build` reads it. The services are set in `config.toml` (`[services]` and `[[services.catalogue]]`: key, name, DoHS code and nations). For the first one, `nsp` is needle exchange, code `SRV0274`, England only. The release format is in `docs/data-format.md`.

```
uv run within-reach-pipeline fetch --cache .cache
uv run within-reach-pipeline fetch-services --cache .cache
uv run within-reach-pipeline build --cache .cache --release 2026-12 --out out
```

- `[services] enabled = false` until production access to the DoHS API is approved. With it off, `fetch-services` writes nothing, and `build` writes empty `services` cells, `config.services = []` and `services = {}`. While it is off, no run fetches services. After switch-on, branch runs will be configured to build with services off (plan Task 11).
- `NHS_DOHS_API_KEY` is the API key. `fetch-services` fails if it is missing.
- `NHS_DOHS_API_BASE` optionally replaces `api_base` from the config. The integration (test) base is `https://int.api.service.nhs.uk/service-search-api/`.
- `WITHIN_REACH_CONFIG` is the path to a `config.toml`, used instead of the default one by every command. An explicit config passed in code wins, then this variable, then the default.
- The key must never appear in logs, the cache, the release or error messages. Never write it into a file in the repo.
- The API allows 1 request a second. The pipeline asks for 1,000 pharmacies a page, about 12 requests, in ODS code order (`$orderby=ODSCode`) so no pharmacy shifts between pages.
- The fetch also asks for `$count=true`. It fails, writing no snapshot, if the records received don't add up to `@odata.count` or the count changes between pages. ODS codes with more than one DoHS record keep every service any of their records lists.
- DoHS requests don't follow redirects, because the `apikey` header would go to the new host: a 3xx fails the fetch. (This applies to any JSON request that sends extra headers, which only the DoHS fetch does. Other JSON requests and file downloads still follow redirects.) HTTP 429 is retried within the usual 5 attempts, waiting for `Retry-After` seconds (at most 60 s), or the usual backoff if the header is absent or not a number.
- Release checks for services: at least `min_listed` (1,000) pharmacies listed, within `listed_tolerance` (20%) of the previous release, `missing_dohs` under `max_missing_share` (10%) of English pharmacies, and every `services` cell a configured key (with or without `?`). A full release also fails unless every service's `source_host` in the manifest is the production host, `api.service.nhs.uk`. With `--allow-partial` the host isn't checked, so local builds against the integration API still pass.

### Local runs with the integration key

Store the integration key in the macOS Keychain under the service name `within-reach-dohs-int`, and pass it in for one command:

```
WITHIN_REACH_CONFIG=/path/to/services-on.toml \
NHS_DOHS_API_BASE=https://int.api.service.nhs.uk/service-search-api/ \
NHS_DOHS_API_KEY="$(security find-generic-password -s within-reach-dohs-int -w)" \
uv run within-reach-pipeline fetch-services --cache .cache
```

`/path/to/services-on.toml` is a copy of `config.toml` with `enabled = true`. Keep it outside the repo.

**Data fetched with the integration key is test data. Never publish or commit it**, not in a fixture, a partial release or anywhere else. The app's test fixture uses made-up services (`fixtures/synthetic/fixture_services.csv`, through `scripts/make_fixture_release.py --services`), not DoHS data.

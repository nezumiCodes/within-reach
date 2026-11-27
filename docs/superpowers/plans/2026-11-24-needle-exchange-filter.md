# Needle Exchange Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an England "Needle exchange" filter. Pharmacy services come from NHS England's DoHS API, every postcode is routed to its nearest service pharmacies, and the app hides pharmacies that don't list the service.

**Architecture:**
- A new `fetch-services` command saves a DoHS snapshot into the cache. It is the only step that needs the API key.
- `build` turns the snapshot into:
  - a per-pharmacy `services` cell (`nsp` listed, `nsp?` not known, empty = not listed);
  - extra service candidates, chosen before the area extract is sized, then routed and widened like the reach rows;
  - manifest fields.
- The app reads the new column and manifest entries, and adds a generic Services filter group.
- Everything sits behind `[services] enabled`, which stays `false` in this branch.

**Tech Stack:** Python 3.12 (uv, pytest, ruff, mypy strict), OSRM, tilemaker; TypeScript + Svelte 5 (Vitest, Playwright, axe).

**Spec:** `docs/superpowers/specs/2026-11-24-needle-exchange-filter-design.md`

## Global Constraints

- **The service** (config): key `nsp`, name `Needle exchange`, DoHS code `SRV0274`, nations `["England"]`.
- **Settings:**
  - `service_min = 5` (a total: service pharmacies already among the candidates count);
  - cap `reach_cap_m` (25 km);
  - widening rounds `reach_max_rounds`.
- **DoHS API:**
  - production base `https://api.service.nhs.uk/service-search-api/`;
  - integration base `https://int.api.service.nhs.uk/service-search-api/`;
  - `api-version=3`, header `apikey`;
  - filter `OrganisationTypeId eq 'PHA'`, `$top=1000` paged with `$skip`, at most 1 request a second.
- **The key** comes from the env var `NHS_DOHS_API_KEY`, and the base URL override from `NHS_DOHS_API_BASE`. The key must never appear in logs, the cache, the release, exceptions or test output.
- **`[services] enabled = false`** in `pipeline/config.toml` on this branch. With it off:
  - `fetch-services` writes nothing;
  - `build` writes an empty `services` cell for every pharmacy;
  - the manifest has `config.services = []` and `services = {}`;
  - the app shows no Services group.
- **The `services` cell grammar:** `key` (listed), `key?` (not known), absent (not listed), joined by `;`.
- **Attribution line**, appended only when services are enabled: `Contains information from NHS England, licensed under the current version of the Open Government Licence.`
- **App copy (exact):**
  - filter label `Needle exchange`, in a fieldset with legend `Services`;
  - note under the filter: `From pharmacies' NHS website listings. Some pharmacies that offer it don't list it. Phone to check.`;
  - hidden reason: `not listed for needle exchange`;
  - unknown heading with only a service filter: `Needle exchange not known`, text `Scottish and Welsh pharmacy lists don't include services, so these pharmacies can't be filtered.`;
  - no results: `No pharmacies listing needle exchange were found within 25 km.`
- **Wording:** always "not listed", never "doesn't offer".
- **Release checks:**
  - `listed` ≥ 1,000;
  - `listed` within ±20% of the previous release;
  - `missing_dohs` < 10% of English pharmacies;
  - every cell value is a configured key, with or without `?`.
- **Never published:** integration data, whether in a committed fixture, a partial release, or anything else.
- **Git:**
  - commits use the repo's noreply identity, with no AI attribution trailers;
  - branch `service-filters-needle-exchange`;
  - merge only via a PR with CI green.

## Review Focus

1. **The DoHS API fails part-way through paging** (429 or 5xx after retries, or a short page then an error). `fetch-services` must fail and leave no snapshot file, never a partial one. Test in Task 2.
2. **The API key leaking** through logs or exception text when a request fails. Test in Task 2 (caplog plus exception message).
3. **A pharmacy that's both among the nearest 40 and a service pharmacy** must be stored once, and the 40 cap must not drop service rows. Test in Task 4.
4. **An older release** (no `services` column, no `config.services` in the manifest) must still load in the new app, with no Services group. Tests in Tasks 6 and 8.
5. **A postcode with no service pharmacy within 25 km** (Scottish islands, or any postcode when only England is covered and the postcode is far north) must show the no-results message, not an empty list or a crash. Test in Task 7.

---

### Task 1: Config and fetcher headers

**Files:**
- Modify: `pipeline/config.toml`, `pipeline/src/within_reach_pipeline/config.py`, `pipeline/src/within_reach_pipeline/http.py`, `pipeline/tests/fakes.py`
- Test: `pipeline/tests/test_config.py`, `pipeline/tests/test_http.py`

**Interfaces:**
- Produces:
  - `ServiceDef(key: str, name: str, code: str, nations: tuple[str, ...])` (frozen dataclass, in `config.py`);
  - `PipelineConfig.services_enabled: bool`;
  - `services: tuple[ServiceDef, ...]`;
  - `service_min: int`;
  - `services_api_base: str`;
  - `services_min_listed: int`;
  - `services_listed_tolerance: float`;
  - `services_max_missing_share: float`;
  - `Fetcher.get_json(url, params=None, headers: dict[str, str] | None = None) -> Any`.

- [ ] **Step 1: Write failing tests**

```python
def test_services_config_loads() -> None:
    config = load_config()
    assert config.services_enabled is False
    assert config.service_min == 5
    assert config.services == (ServiceDef("nsp", "Needle exchange", "SRV0274", ("England",)),)
    assert config.services_api_base == "https://api.service.nhs.uk/service-search-api/"
    assert (config.services_min_listed, config.services_listed_tolerance,
            config.services_max_missing_share) == (1000, 0.20, 0.10)

def test_get_json_sends_extra_headers() -> None:  # test_http.py, MockTransport records request
    ...  # assert request.headers["apikey"] == "k" and User-Agent still set
```

- [ ] **Step 2: Run them to check they fail:** `cd pipeline && uv run pytest tests/test_config.py tests/test_http.py -q`. Expected: FAIL (no `ServiceDef`, unexpected `headers`).

- [ ] **Step 3: Implement.**
  - Add to `config.toml`:

    ```toml
    [services]
    # Pharmacy services from NHS England's Directory of Healthcare Services (DoHS) API, v3.
    # Off until the production key exists (needle exchange filter design, section 7).
    enabled = false
    service_min = 5
    api_base = "https://api.service.nhs.uk/service-search-api/"
    min_listed = 1000          # release check: fewer means a broken API response
    listed_tolerance = 0.20    # ±20% of the previous release
    max_missing_share = 0.10   # NHSBSA pharmacies with no DoHS record

    [[services.catalogue]]
    key = "nsp"
    name = "Needle exchange"
    code = "SRV0274"
    nations = ["England"]
    ```

  - Load these in `load_config`.
  - Add `headers` to the `Fetcher` protocol, to `HttpxFetcher.get_json` (merged with Accept) and to `FakeFetcher.get_json`, recording the headers' keys in the calls, never their values.

- [ ] **Step 4: Run** `uv run pytest -q && uv run ruff check && uv run mypy src tests`. Expected: all pass.

- [ ] **Step 5: Commit:** `git commit -m "pipeline: services config and request headers for the DoHS API"`

### Task 2: `fetch-services` command and snapshot

**Files:**
- Create: `pipeline/src/within_reach_pipeline/services.py`, `pipeline/tests/test_services.py`, `pipeline/tests/fixtures/dohs_page.json` (a small, made-up DoHS response: 3 pharmacies, one listing SRV0274, one in lowercase `fa002`, one with `Services: []`)
- Modify: `pipeline/src/within_reach_pipeline/cli.py`

**Interfaces:**
- Consumes (Task 1): `PipelineConfig.services*`, `Fetcher.get_json(..., headers=)`.
- Produces:
  - `SERVICES_FILE = "dohs_services.json"` in `cli.py`;
  - `Snapshot(fetched_at: str, api_base: str, listed: dict[str, frozenset[str]])` (frozen); `listed` maps an upper-cased ODS code to the service codes it lists, and every DoHS pharmacy has an entry, even an empty one;
  - `fetch_snapshot(fetcher: Fetcher, api_base: str, api_key: str, sleep: Callable[[float], None] = time.sleep) -> Snapshot`;
  - `save_snapshot(snapshot: Snapshot, path: Path) -> None` (atomic: write `path.tmp`, then rename);
  - `load_snapshot(path: Path) -> Snapshot | None` (None if the file is absent);
  - CLI: `within-reach-pipeline fetch-services --cache DIR`.

- [ ] **Step 1: Write failing tests**

```python
def test_fetch_snapshot_pages_and_normalises(fake) -> None:
    # fake serves 1000 records, then 2; params carry $top=1000 and $skip=0 then 1000
    snap = fetch_snapshot(fake, BASE, "secret-key", sleep=lambda s: None)
    assert len(snap.listed) == 1002
    assert snap.listed["FA002"] == frozenset()          # lower-case code normalised
    assert "SRV0274" in snap.listed["FE412"]
    assert all(c.headers_keys == {"apikey"} for c in fake.calls)

def test_failed_page_leaves_no_snapshot(tmp_path, caplog) -> None:
    # second page raises httpx.HTTPStatusError(429) whose request URL is the API URL
    with pytest.raises(ServicesFetchError) as err:
        run(["fetch-services", "--cache", str(tmp_path)], fetcher=failing, env=KEYED)
    assert not (tmp_path / "dohs_services.json").exists()
    assert "secret-key" not in str(err.value) and "secret-key" not in caplog.text

def test_fetch_services_disabled_writes_nothing(tmp_path) -> None:
    assert run(["fetch-services", "--cache", str(tmp_path)], env={}) == 0
    assert not (tmp_path / "dohs_services.json").exists()

def test_fetch_services_enabled_without_key_fails(tmp_path) -> None:
    with pytest.raises(SystemExit, match="NHS_DOHS_API_KEY"):
        run(["fetch-services", "--cache", str(tmp_path)], env={}, config=ENABLED)

def test_snapshot_round_trip(tmp_path) -> None: ...  # save then load equals; absent -> None
```

Make `run` accept `env: Mapping[str, str] | None = None` (default `os.environ`) and `config: PipelineConfig | None = None` (default `load_config()`), so tests can inject both.

- [ ] **Step 2: Run** `uv run pytest tests/test_services.py -q`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement.**
  - `$select=ODSCode,Services` and `$filter=OrganisationTypeId eq 'PHA'`; stop paging when a page has fewer than 1,000 records.
  - Sleep 1.1 s between pages.
  - Wrap any `httpx.HTTPError` in `ServicesFetchError(f"DoHS request failed at $skip={skip}: HTTP {status}")`. The message must not include the URL or headers. Raise with `from None`, so the original exception (whose request carries the header) isn't chained into tracebacks.
  - CLI:
    - disabled → log `services disabled in config; no snapshot written`, return 0;
    - enabled with no key → `SystemExit("NHS_DOHS_API_KEY is not set")`;
    - the base comes from `env.get("NHS_DOHS_API_BASE", config.services_api_base)`.

- [ ] **Step 4: Run** `uv run pytest -q && uv run ruff check && uv run mypy src tests`. Expected: all pass.

- [ ] **Step 5: Commit:** `git commit -m "pipeline: fetch-services saves a DoHS services snapshot (no partial files, key never logged)"`

### Task 3: Services in the directory, manifest and attribution

**Files:**
- Modify: `pipeline/src/within_reach_pipeline/services.py`, `bundle.py` (`write_directory`), `build.py`
- Test: `pipeline/tests/test_services.py`, `pipeline/tests/test_bundle.py`, `pipeline/tests/test_build_cli.py`

**Interfaces:**
- Consumes: `Snapshot`, `load_snapshot`, `ServiceDef`, `SERVICES_FILE`.
- Produces:
  - `ServiceAssignment(cells: list[str], listed: dict[str, frozenset[int]], counts: dict[str, dict[str, int]])`. `cells` is indexed by `ph_idx`. `listed` maps a service key to the `ph_idx` values that list it. `counts[key]` has `listed`, `unmatched_dohs` and `missing_dohs`.
  - `assign_services(pharmacies: Sequence[Pharmacy], defs: Sequence[ServiceDef], snapshot: Snapshot | None) -> ServiceAssignment`. With `snapshot is None` or no defs: every cell is empty, and `listed`/`counts` are empty.
  - `write_directory(out, pharmacies, services: Sequence[str]) -> FileInfo`, with header `..., "sun", "services"`.
  - `SERVICES_ATTRIBUTION` (the exact line from Global Constraints).
  - Manifest:
    - `config.services` = list of `{key, name, nations, source, source_fetched_at}`;
    - `config.service_min`;
    - top-level `services` = `counts`.

    `source` is the attribution line. Both are empty when services are off.

- [ ] **Step 1: Write failing tests**

```python
def test_assign_services_cells() -> None:
    # England FA001 listed, England FA002 in DoHS without it, England FA003 not in DoHS,
    # Scotland and Wales pharmacies; snapshot also has FZZZZ (no NHSBSA match)
    a = assign_services(pharmacies, [NSP], snapshot)
    assert a.cells == ["nsp", "", "", "nsp?", "nsp?"]
    assert a.listed == {"nsp": frozenset({0})}
    assert a.counts == {"nsp": {"listed": 1, "unmatched_dohs": 1, "missing_dohs": 1}}

def test_assign_services_off() -> None:
    assert assign_services(pharmacies, [NSP], None).cells == [""] * 5

def test_build_with_snapshot_writes_services(tmp_path) -> None:
    # fake-router build of the sample cache plus a saved snapshot, config enabled
    manifest = ...
    assert manifest["config"]["services"][0]["key"] == "nsp"
    assert manifest["services"]["nsp"]["listed"] >= 1
    assert SERVICES_ATTRIBUTION in manifest["attribution"]
    header = next(csv.reader(gzip.open(tmp_path / "out" / "pharmacies.csv.gz", "rt")))
    assert header[-1] == "services"

def test_build_without_snapshot_has_empty_services(tmp_path) -> None:
    assert manifest["config"]["services"] == [] and manifest["services"] == {}
```

- [ ] **Step 2: Run** `uv run pytest tests/test_services.py tests/test_bundle.py tests/test_build_cli.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.**
  - In `build_release`, call `load_snapshot(cache / SERVICES_FILE)` only when `config.services_enabled`. Otherwise pass `None`.
  - Match DoHS codes to English pharmacies on the upper-cased `raw.code`.
  - Check that `merge_manifests` keeps the base's top-level `services` and `config.services`. The shards carry the same values. Add a test that the merge output equals the base for these keys.

- [ ] **Step 4: Run** the full pipeline suite, plus ruff and mypy. Expected: pass.

- [ ] **Step 5: Commit:** `git commit -m "pipeline: services column in the pharmacy file, manifest fields and NHS England attribution"`

### Task 4: Service candidates, extract sizing and routing

**Files:**
- Modify: `pipeline/src/within_reach_pipeline/candidates.py`, `reach.py`, `build.py`
- Test: `pipeline/tests/test_candidates.py`, `pipeline/tests/test_reach.py`, `pipeline/tests/test_build_cli.py`

**Interfaces:**
- Consumes: `ServiceAssignment.listed`, `config.service_min`, `config.reach_cap_m`, `config.reach_max_rounds`.
- Produces:
  - `select_service_candidates(postcodes, pharmacies, candidates: Sequence[list[Candidate]], listed: frozenset[int], count: int, cap_m: int) -> list[list[Candidate]]`. For each postcode: the nearest `count - (listed already among its candidates)` pharmacies in `listed` that aren't among its candidates, within `cap_m`, ordered by `(straight_m, ph_idx)`. Uses a KD-tree over the listed pharmacies only.
  - `route_reachable(..., services: Mapping[str, frozenset[int]] = {}, service_min: int = 0)`. These are new keyword arguments; existing callers are unchanged.
  - `ReachResult.service_short: dict[str, set[int]]`: postcodes ending with fewer than `service_min` reachable rows listing the service.
  - Manifest area entry: `services: {key: {"postcodes_short": n}}`, empty when services are off.

**Algorithm, which the signatures don't determine:**
1. In `build.py`:
   - for each service, call `select_service_candidates` on the first-pass candidates;
   - merge the results into each postcode's candidate list (union by `ph_idx`);
   - only then build `points` and `bbox` from all candidates, so the extract and map cover the service pharmacies.
2. In `route_reachable`:
   - the first pass routes the merged candidates, as now;
   - reach widening is unchanged;
   - then, for each service, while rounds remain: for postcodes with fewer than `service_min` reachable listed rows, `next_candidates` is limited to `allowed & services[key]`, with `count = shortfall`, and the results are routed.
3. Final rows per postcode:
   - from the reachable rows (or the first pass if none are reachable, as now), keep the nearest `max_candidates` by `(straight_m, ph_idx)`;
   - plus, for each service, the nearest `service_min` reachable rows listing it;
   - deduplicate by `ph_idx` and sort by `(straight_m, ph_idx)`.

- [ ] **Step 1: Write failing tests**

```python
def test_service_candidates_count_existing() -> None:
    # 3 listed pharmacies already among candidates, count 5 -> 2 more, nearest first
    assert [c.ph_idx for c in select_service_candidates(...)[0]] == [7, 9]

def test_service_candidates_respect_cap() -> None:
    # only listed pharmacy is 30 km away, cap 25 km -> []

def test_service_rows_survive_the_40_cap() -> None:
    # 45 nearby non-listed pharmacies + 5 listed at 8-12 km; FakeRouter; max_candidates 40
    rows = route_reachable(..., services={"nsp": listed}, service_min=5).rows
    assert len(rows) == 45 and {r.ph_idx for r in rows} >= listed

def test_listed_pharmacy_among_nearest_is_stored_once() -> None:
    assert len({r.ph_idx for r in rows}) == len(rows)

def test_unreachable_service_rows_widen_then_short() -> None:
    # FakeRouter(unreachable={listed_a}) -> next listed added; still short -> service_short
    assert result.service_short == {"nsp": {0}}

def test_build_extract_includes_service_pharmacies(tmp_path, monkeypatch) -> None:
    # capture the bbox passed to _area_extract; a listed pharmacy 15 km away lies inside it
```

- [ ] **Step 2: Run** `uv run pytest tests/test_candidates.py tests/test_reach.py tests/test_build_cli.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement**, following the algorithm above. With `services={}`, behaviour must be unchanged. Every existing test in `test_reach.py` and `test_build_cli.py` must pass without edits. Add `test_no_services_matches_previous_rows`, which runs `route_reachable` on the existing widening scenario with and without `services={}` and asserts the rows are equal.

- [ ] **Step 4: Run** the full suite, plus `RUN_OSRM=1 uv run pytest tests/test_osrm.py -q` (Docker), ruff and mypy. Expected: pass.

- [ ] **Step 5: Commit:** `git commit -m "pipeline: route every postcode to its nearest service pharmacies (up to 25 km)"`

### Task 5: Release checks

**Files:**
- Modify: `pipeline/src/within_reach_pipeline/checks.py`, `pipeline/reference/expectations.toml` (format support only; cases come in Task 10)
- Test: `pipeline/tests/test_checks.py`

**Interfaces:**
- Consumes: the manifest fields from Tasks 3 and 4, and `config.services_*`.
- Produces:
  - `_check_services(release, manifest, config) -> list[CheckFailure]`;
  - `_check_service_counts(manifest, previous, tolerance) -> list[CheckFailure]`;
  - a reference case form `service = "nsp"`, `min_rows = 1`, `beyond_m = 5000`: the postcode has at least `min_rows` rows listing the service with `straight_m > beyond_m` and a walk or drive route.

- [ ] **Step 1: Write failing tests:**
  - `listed` 999 fails with `services`;
  - `missing_dohs` at 10% of England's count fails;
  - a cell `xyz` fails;
  - `nsp?` and `nsp` pass;
  - services off with a non-empty cell fails;
  - the previous release had 1,500 listed and this one has 1,100: fails at ±20%;
  - a service reference case passes with a routed row at 6 km and fails without one.

- [ ] **Step 2: Run** `uv run pytest tests/test_checks.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement**, and wire both into `run_checks`. The counts check only runs when both manifests have the service.

- [ ] **Step 4: Run** the full suite, plus ruff and mypy. Expected: pass.

- [ ] **Step 5: Commit:** `git commit -m "pipeline: release checks for service data"`

### Task 6: App data layer

**Files:**
- Modify: `app/src/lib/engine/types.ts`, `app/src/lib/engine/csv.ts`, `app/src/lib/data/release.ts`
- Test: `app/src/lib/engine/csv.test.ts`, `app/src/lib/data/release.test.ts`

**Interfaces:**
- Produces:
  - `type ServiceState = 'listed' | 'unknown'`;
  - `Pharmacy.services: Record<string, ServiceState>` (absent key = not listed);
  - `parsePharmacies` accepts the current header and the header with `services` added;
  - `Manifest.services: { key: string; name: string }[]` (from `config.services`, default `[]`);
  - `Manifest.reachCapM: number` (from `config.reach_cap_m`, default `25000`).

- [ ] **Step 1: Write failing tests:**

```ts
it('reads the services column', () => {
  const [a, b, c] = parsePharmacies(withServices(['nsp', '', 'nsp?']))
  expect(a.services).toEqual({ nsp: 'listed' })
  expect(b.services).toEqual({})
  expect(c.services).toEqual({ nsp: 'unknown' })
})
it('still reads the layout without services', () => {
  expect(parsePharmacies(oldLayout)[0].services).toEqual({})
})
it('manifest services default to none for older releases', () => {
  expect(parseManifest(latest, oldManifest)!.services).toEqual([])
})
it('manifest exposes services and the reach cap', () => { ... })
```

- [ ] **Step 2: Run** `cd app && npx vitest run src/lib/engine/csv.test.ts src/lib/data/release.test.ts`. Expected: FAIL.

- [ ] **Step 3: Implement.** A malformed services entry (not a key with an optional `?`) throws the same parse error as other bad cells.

- [ ] **Step 4: Run** `npm test && npm run check && npm run lint`. Expected: pass.

- [ ] **Step 5: Commit:** `git commit -m "app: read pharmacy services and service definitions from the release"`

### Task 7: App filter logic

**Files:**
- Modify: `app/src/lib/engine/hours.ts`, `app/src/lib/engine/results.ts`
- Test: `app/src/lib/engine/hours.test.ts`, `app/src/lib/engine/results.test.ts`

**Interfaces:**
- Consumes: `Pharmacy.services`, `Manifest.services`, `Manifest.reachCapM`.
- Produces:
  - `type HoursKey = 'saturday' | 'sunday' | 'late'`;
  - `type FilterKey = HoursKey | \`service:${string}\``;
  - `type Filters = Record<HoursKey, boolean> & { services: Record<string, boolean> }`;
  - `NO_FILTERS` (with `services: {}`);
  - `filterStatus(pharmacy: Pharmacy, filters: Filters): FilterStatus`. `FilterStatus.unknown` becomes `{ kind: 'unknown'; of: ('hours' | 'services')[] }`. The rule: hidden if any active filter fails, otherwise unknown if any is unknown, otherwise match.
  - `Grouped.unknownOf: Set<'hours' | 'services'>`;
  - `groupByFilters(sorted, filters)`;
  - `hiddenSummary(grouped, mode, serviceNames: Record<string, string>)`. The reasons are hours first, then services in manifest order. Service reason text: `not listed for ${name.toLowerCase()}`.
  - `noResultsMessage(sorted: Result[], filters: Filters, serviceNames: Record<string, string>, reachCapM: number): string`. If no result passes the active service filters alone (hours ignored): `No pharmacies listing ${names joined with ' or '} were found within ${reachCapM / 1000} km.` Otherwise the existing `No pharmacies nearby match these filters.`
  - `anyFilter(filters: Filters): boolean`.

- [ ] **Step 1: Write failing tests:**
  - Welsh pharmacy with `{ nsp: 'unknown' }` and the nsp filter → `{kind:'unknown', of:['services']}`;
  - English pharmacy without nsp → hidden with reason `service:nsp`;
  - nsp filter plus Sunday on an English pharmacy closed Sundays that lists nsp → hidden, reason `sunday`;
  - summary: `"3 closer pharmacies hidden: not listed for needle exchange."`;
  - combined summary: `"... hidden: not open on Sundays or not listed for needle exchange."`;
  - no results with only non-listed pharmacies → `"No pharmacies listing needle exchange were found within 25 km."` (Review Focus 5);
  - the existing hours tests updated to the new `filterStatus` signature and still passing.

- [ ] **Step 2: Run** `npx vitest run src/lib/engine`. Expected: FAIL.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run** `npm test && npm run check`. Expected: pass. Fix the call sites in `SearchPage.svelte` (`anyFilter`, the new arguments) so `check` passes.

- [ ] **Step 5: Commit:** `git commit -m "app: service filters in the filter engine (hidden, not known, summary, no results)"`

### Task 8: App UI, fixture and end-to-end tests

**Files:**
- Modify: `app/src/lib/ui/Controls.svelte`, `ResultsList.svelte`, `ResultEntry.svelte`, `SearchPage.svelte`, `scripts/make_fixture_release.py`, `scripts/test_make_fixture_release.py`, `app/tests/e2e/search.spec.ts`
- Create: `scripts/fixture_services.csv` (made up, not from DoHS: `nation,code,services`, marking 3 English pharmacies near CH2 3JQ as `nsp`, leaving the other English ones empty, and every Welsh pharmacy as `nsp?`)
- Regenerate: `app/tests/fixtures/data/2026-11/**`

**Interfaces:**
- Consumes: Tasks 6 and 7.
- Produces:
  - `make_fixture_release.py --services scripts/fixture_services.csv`. This adds the `services` column and writes `config.services = [{key:"nsp", name:"Needle exchange", nations:["England"], source:<attribution>, source_fetched_at:"2026-11-24T00:00:00Z"}]`. Without the flag, output is unchanged.
  - The UI copy, exactly as in Global Constraints.

UI rules:
- **Controls:** a `<fieldset><legend>Services</legend>` appears only when `services.length > 0`, with one checkbox per service bound to `filters.services[key]`, and the note `<p class="note">` under it. The "Filters:" line lists the active service names after the hours labels.
- **ResultsList:**
  - the heading and text for the unknown group come from `unknownOf`: hours only → existing copy; services only → `${names} not known` plus the services text;
  - both → heading `Opening hours and services not known`, text `Scottish and Welsh pharmacy lists don't include opening hours or services, so these pharmacies can't be filtered.` (builder may refine, same style);
  - the empty message uses `noResultsMessage`.
- **ResultEntry:** for each listed service, `<p class="services" data-testid="services"><span class="visually-hidden">Services: </span>Needle exchange</p>`.

- [ ] **Step 1: Write the failing e2e tests** (fixture, so skip on `LIVE_URL`):

```ts
test('Needle exchange hides pharmacies that do not list it', async ({ page }) => {
  await search(page, PC.chester)
  await page.getByLabel('Needle exchange').check()
  await expect(results(page)).toHaveCount(3)
  await expect(page.getByTestId('hidden-summary')).toHaveText(
    /^\d+ closer pharmac(y|ies) hidden: not listed for needle exchange\.$/)
  await expect(results(page).first().getByTestId('services')).toContainText('Needle exchange')
  await expect(page.getByText("From pharmacies' NHS website listings.", { exact: false })).toBeVisible()
})
test('Welsh pharmacies show under Needle exchange not known', async ({ page }) => {
  await search(page, PC.wrexham)
  await page.getByLabel('Needle exchange').check()
  await expect(page.getByRole('heading', { name: 'Needle exchange not known' })).toBeVisible()
})
```

Also add a Vitest component-free test in `release.test.ts` that the fixture manifest has `services` (fixture consistency), and a `test_make_fixture_release.py` case for `--services`.

- [ ] **Step 2: Run** `npx playwright test tests/e2e/search.spec.ts --project=chromium`. Expected: FAIL (no checkbox).

- [ ] **Step 3: Implement** the UI. Regenerate the fixture with `--services` (same command as the README's fixture section, plus the flag). Run the axe test `results page passes axe` with the nsp filter checked as well: add `await page.getByLabel('Needle exchange').check()` before the first scan.

- [ ] **Step 4: Run** `npm test && npm run check && npm run lint && npx playwright test` (all browsers; the Firefox axe crash is pre-existing and already skipped) and `uv run pytest ../scripts -q`. Expected: pass.

- [ ] **Step 5: Commit:** `git commit -m "app: Needle exchange filter, service tags and not-known group; fixture with made-up services"`

### Task 9: Documentation

**Files:**
- Modify: `docs/data-format.md` (services column grammar, manifest `config.services`, `config.service_min`, top-level `services`, area `services`), `pipeline/README.md` (`fetch-services`, `NHS_DOHS_API_KEY`, `NHS_DOHS_API_BASE`, Keychain item `within-reach-dohs-int` for local runs, integration data never published), `docs/decisions.md` (new section: service filters; research summary; why DoHS; why routed service candidates; switch off until the production key)

- [ ] **Step 1:** Write the docs. Every field name must match the code from Tasks 2–5.
- [ ] **Step 2:** Run `npx prettier --check ../docs` from `app` if docs are covered, otherwise skip. Run `git diff --stat` to confirm only the docs changed.
- [ ] **Step 3: Commit:** `git commit -m "docs: service filters data format, pipeline usage and decisions"`

### Task 10: Measure on real data (local, integration key)

No code is committed from this task except `docs/decisions.md` numbers and reference cases.

- [ ] **Step 1:** Fetch an integration snapshot into the existing local cache:

  ```bash
  NHS_DOHS_API_KEY="$(security find-generic-password -s within-reach-dohs-int -w)" \
  NHS_DOHS_API_BASE=https://int.api.service.nhs.uk/service-search-api/ \
  uv run within-reach-pipeline fetch-services --cache .cache
  ```

  Run this with a temporary local config copy that has `enabled = true`. Don't commit that copy. Never echo the key.
- [ ] **Step 2:** Build E06000050, E06000035, W11000023 and S12000017 with `--maps tilemaker`, twice: services off, then on, into separate `out-before` and `out-after` directories outside the repo. Record per area:
  - travel rows;
  - travel bytes;
  - map bytes;
  - build seconds;
  - `services.nsp.postcodes_short`.
- [ ] **Step 3: Stop condition.** If any map grows by more than 50%, stop and report the numbers to the user before continuing (spec §3.2).
- [ ] **Step 4:** Run `uv run within-reach-pipeline check --release-dir out-after --allow-partial`. Expected: pass, except reference cases outside the built areas, which are skipped for partial releases.
- [ ] **Step 5:** Pick two reference cases from `out-after`, add them to `pipeline/reference/expectations.toml`, and note that they were chosen from integration data and must be rechecked on the first production run:
  - a rural English postcode whose nearest nsp pharmacy is more than 5 km away;
  - a Chester town postcode with nsp rows and all 40 nearest kept.
- [ ] **Step 6:** Add the measurements table to the new section of `docs/decisions.md`, then commit: `git commit -m "docs: measured effect of service candidates on files, maps and build time"`

### Release order (before Task 11 and before any data run)

Merging this branch changes the data even with `enabled = false`: `write_directory` adds the `services` column to `pharmacies.csv.gz`. The live app, v0.2.0, only accepts the exact old header, so it would reject the file. The scheduled Pipeline run (2 December 2026, 03:00 UTC) builds from `main`, and `deploy.yml` then redeploys the latest `v*` tag with that data.

- [ ] **Step 1:** Merge this branch only once CI passes.
- [ ] **Step 2:** Tag `v0.3.0` from `main` straight after the merge, before any data run, and before the scheduled run on 2 December 2026 at 03:00 UTC. The user does this: don't tag without asking.
- [ ] **Step 3:** If the merge can't be followed by the tag before that run, hold the merge until after it.
- [ ] **Step 4:** Check the live site loads after the tag deploys. Then the production key (Task 11), then the switch on.

### Task 11 (BLOCKED: needs the production key and the user's approval of a new GitHub environment)

Don't start this until the user says so. It changes security settings (CLAUDE.md).

- **A new job `services` in `.github/workflows/pipeline.yml`:**
  - `if: github.ref == 'refs/heads/main'`;
  - `environment: dohs` (restricted to `main`, holding `NHS_DOHS_API_KEY`);
  - runs `within-reach-pipeline fetch-services --cache .cache-services`;
  - uploads `dohs_services.json` as an artifact if it exists.
- **`build` and `assemble`** `needs:` it, with `if: always()` guards, and download the artifact into `.cache` when present.
- **Branch runs switch services off explicitly.** Once `enabled = true` is on `main`, branches inherit it, and with no snapshot `build` raises `FileNotFoundError`. `_check_services` and the service reference cases would also fail on a release built with services off. So on non-main runs the workflow writes a copy of `config.toml` with `enabled = false`, points `WITHIN_REACH_CONFIG` at it, and runs `build`, `check` and `assemble` with that same config. Main runs use the committed config.
- **Switch-on PR:** set `[services] enabled = true` and `api_base` stays production.
- **First production run:** recheck the Task 10 reference cases against production data.

**Before switch-on checklist** (from the final review; fix in code before `enabled = true`):
- [x] Page DoHS results with a stable `$orderby`, or check the total against `@odata.count`, so no pharmacy is skipped or repeated. Done 27 Nov 2026: both (`$orderby=ODSCode`, and the fetch fails unless the total matches `@odata.count`).
- [x] Union, don't overwrite, duplicate ODS codes. Done 27 Nov 2026.
- [x] Turn off redirect-following for DoHS requests. The `apikey` header isn't stripped on cross-host redirects. Done 27 Nov 2026 (any `get_json` request with headers, which only DoHS sends; a 3xx fails).
- [x] Retry 429 with backoff, honouring `Retry-After`. Done 27 Nov 2026 (capped at 60 s).
- [x] Record the snapshot's source host in the manifest, and have `check` refuse a non-production base for full releases. Done 27 Nov 2026 (`config.services[].source_host`).

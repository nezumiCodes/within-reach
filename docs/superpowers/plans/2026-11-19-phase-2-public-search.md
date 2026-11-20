# Phase 2: Public Search with a Private Map — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public page where someone types a postcode and sees the nearest pharmacies on a street map and in a numbered list. Nothing about the search ever leaves the browser beyond which area's files were downloaded.

**Architecture:**
- **Pipeline:** gains a per-area map step. tilemaker builds a slimmed PMTiles file from the area's existing osmium extract. Files over 20 MiB are split into byte chunks. Each map is recorded in the manifest, checked, and published as a separate `maps-YYYY-MM.tar.gz` release asset.
- **App:** the Svelte app replaces its placeholder with a search page. A pure engine parses the release files, builds, sorts and filters results. A data layer downloads whole files, verifies their SHA-256 and keeps them in memory for the session. MapLibre (CSP build) draws the area map from an in-memory PMTiles source, with no tile or range requests.

**Tech Stack:**
- **Pipeline:** Python 3.12 (uv, ruff, mypy strict, pytest), tilemaker in Docker, osmium.
- **App:** Svelte 5, TypeScript, Vite, Vitest, Playwright plus axe, `maplibre-gl`, `pmtiles`.

**Spec:** `docs/superpowers/specs/2026-11-18-phase-2-public-search-design.md` (approved 19 Nov 2026). Project spec: `~/Downloads/Within Reach Tool.md` (draft 0.6).

## Global Constraints

- **Network (NFR-01):**
  - Only GET requests, only to the site's own host.
  - No postcode in any URL, header or body. `app/tests/e2e/fixtures.ts` enforces this on every e2e test, so every spec imports `test` and `expect` from there.
- **CSP in `app/public/_headers` is unchanged:** no `'unsafe-inline'`, no `'unsafe-eval'`, no new origins.
  - If MapLibre provably needs `blob:` in `img-src` or `worker-src`, add only that.
  - Add it with a comment in `_headers` and an e2e test proving it's needed.
  - Record a ledger `Ruling:` for it.
- **Storage (NFR-04):** nothing about a search goes to localStorage, sessionStorage, IndexedDB, Cache Storage, cookies, the URL, the hash or history. Responses under `/data/` carry `Cache-Control: no-store`.
- **Integrity (NFR-05):** every data file and every map part is verified against the manifest SHA-256 and byte count before use.
- **File sizes:** map chunks are at most 20 MiB (`20 * 1024 * 1024` bytes). Every published file stays under `max_file_bytes` (24 MiB, `pipeline/config.toml`).
- **Copy:** user-facing text is exactly as written in the spec's section 5. The postcode field label is exactly `Postcode`.
- **Accessibility (NFR-13):** WCAG 2.2 AA. The list is the full accessible view; the map is supplementary.
- **Browsers (NFR-08):** current Edge, Chrome, Firefox and Safari. The Playwright projects already exist.
- **Code quality:** engine coverage of 85% or more (NFR-15). Existing checks pass: `npm run lint`, `npm run check`, `npm test`, `npm run test:e2e`, plus `uv run ruff check`, `uv run mypy`, `uv run pytest`.
- **Ties (NFR-11):** distance, then `straight_m`, then nation, then code.
- **Git (`~/.claude/CLAUDE.md`):**
  - Work on branch `phase-2-public-search`; never commit to `main`.
  - No `Co-Authored-By` or other AI attribution lines in commits or PRs.
  - Commit as the GitHub noreply identity already configured in the repo.
- **Manifest naming:** byte counts are called `bytes` (as in the existing `FileInfo.as_dict()`), not `size` as the design wrote. *Ruling recorded here.*

## Review Focus

1. **A district that spans two areas, with the postcode in the second:** the right area is used, and the map loads for that area only. Pinned in Task 9 (`searchPostcode finds a postcode in the second area of a district`).
2. **A pharmacy whose hours are known for some days but blank on the filtered day:** it's grouped under "Opening hours not known" and never hidden. Pinned in Task 5 (`saturday filter treats a blank saturday as unknown even when weekdays are known`).
3. **A second search in the same area:** no new data or map requests. Pinned in Task 12 (`a second search in the same area downloads nothing new`).
4. **The served body differs from the manifest** (re-encoded by a host, truncated or tampered): the integrity message is shown and the data isn't used. Pinned in Task 9 (`fetchVerified rejects a body whose hash differs`) and Task 10 (`a tampered travel file shows the integrity message`).
5. **WebGL unavailable or the map fails:** the list still renders and the map panel shows its message. Pinned in Task 12 (`with WebGL disabled the list works and the map says it isn't available`).

---

## File structure

**Pipeline**
- Create `pipeline/src/within_reach_pipeline/maps.py`: map bounding box, tilemaker command, chunking, manifest map entry and the PMTiles header reader.
- Create `pipeline/maps/config-openmaptiles.json`: the slimmed tilemaker config, copied from the measured `slim13.json` (in the session scratchpad). Its content is listed in Task 1.
- Modify `pipeline/src/within_reach_pipeline/build.py`: split the extract out of `_routers`; build maps; `maps` parameter.
- Modify `pipeline/src/within_reach_pipeline/cli.py`: `fetch` downloads water polygons; `build --maps {tilemaker,none}`.
- Modify `pipeline/src/within_reach_pipeline/sources.py`: water polygons source constant.
- Modify `pipeline/src/within_reach_pipeline/checks.py`: map parts in the file checks; new `_check_maps`.
- Modify `pipeline/config.toml` and `config.py`: `[maps] tilemaker_image`, `chunk_bytes`.
- Tests: `pipeline/tests/test_maps.py`, `test_build_cli.py`, `test_checks.py`, `test_cli.py`.
- Modify `.github/workflows/pipeline.yml`, `.github/workflows/deploy.yml`, `.github/workflows/live-check.yml`.
- Modify `docs/data-format.md`.

**App**
- `app/src/lib/engine/`:
  - `types.ts`: shared types;
  - `csv.ts`: CSV and file parsers;
  - `hours.ts`: opening hours and filters;
  - `results.ts`: results, sort, filter grouping, hidden summary;
  - `format.ts`: distance, time and hours text;
  - each with a `*.test.ts`.
- `app/src/lib/data/`:
  - `release.ts` (extend): typed manifest;
  - `files.ts`: verified fetch, gunzip, session cache;
  - `search.ts`: postcode → outcome;
  - `map-file.ts`: chunk join and in-memory PMTiles source;
  - each with a `*.test.ts`.
- `app/src/lib/ui/`:
  - `SearchPage.svelte`, `SearchForm.svelte`, `Messages.svelte`, `Controls.svelte` (sort and filters), `ResultsList.svelte`, `ResultEntry.svelte`, `MapPanel.svelte`;
  - delete `Placeholder.svelte`.
- `app/src/App.svelte`: renders `SearchPage`.
- `app/public/map/`:
  - `style.json`;
  - `glyphs/Noto Sans Regular/*.pbf` and `glyphs/Noto Sans Bold/*.pbf`;
  - `glyphs/OFL.txt`.
- `app/public/_headers`: `/data/*` block.
- `app/vite.config.ts`: preview applies path blocks from `_headers`.
- `scripts/make_fixture_release.py` plus `scripts/test_make_fixture_release.py`.
- `app/tests/fixtures/data/`: the generated fixture release.
- `app/scripts/copy-fixture.mjs`.
- `app/tests/e2e/search.spec.ts`, `map.spec.ts`; delete `placeholder.spec.ts` after moving its header, storage and CSP tests into `site.spec.ts`.

---

### Task 1: Map building primitives (pipeline)

**Files:**
- Create: `pipeline/src/within_reach_pipeline/maps.py`, `pipeline/maps/config-openmaptiles.json`
- Modify: `pipeline/config.toml`, `pipeline/src/within_reach_pipeline/config.py`
- Test: `pipeline/tests/test_maps.py`, `pipeline/tests/test_config.py`

**Interfaces:**
- Consumes: `area_bbox(points, margin_m) -> BBox` and `coord(v)` from `routing/osrm.py`; `FileInfo` and `_info` pattern from `bundle.py`.
- Produces:
  - `map_bbox(points: Sequence[LatLon]) -> BBox`: `area_bbox(points, margin_m=1000)`.
  - `tilemaker_command(image: str, pbf: Path, bbox: BBox, config: Path, coastline: Path, dest: Path) -> list[str]`
  - `split_map(path: Path, chunk_bytes: int) -> list[Path]`
  - `write_map_entry(out: Path, area: str, built: Path, chunk_bytes: int) -> dict[str, Any]`, returning `{"bytes", "sha256", "parts": [FileInfo.as_dict(), ...]}`.
  - `pmtiles_bounds(header: bytes) -> BBox`
  - `PipelineConfig.tilemaker_image: str`, `PipelineConfig.map_chunk_bytes: int`

- [ ] **Step 1: Write the failing tests** in `pipeline/tests/test_maps.py`:

```python
def test_map_bbox_has_1km_margin() -> None:
    box = map_bbox([(53.0, -3.0), (53.1, -2.9)])
    assert box[1] == pytest.approx(53.0 - 1000 / 111_195.0)

def test_tilemaker_command_uses_plain_decimal_bbox(tmp_path: Path) -> None:
    cmd = tilemaker_command("img@sha256:x", tmp_path / "a.osm.pbf", (-0.000077, 51.0, 0.1, 51.2),
                            tmp_path / "c.json", tmp_path / "coastline", tmp_path / "out" / "map.pmtiles")
    assert "--bbox" in cmd and cmd[cmd.index("--bbox") + 1] == "-0.000077,51.000000,0.100000,51.200000"
    assert cmd[:3] == ["docker", "run", "--rm"] and "img@sha256:x" in cmd

def test_large_map_is_split_into_numbered_chunks(tmp_path: Path) -> None:
    built = tmp_path / "built.pmtiles"; built.write_bytes(bytes(range(10)))
    entry = write_map_entry(tmp_path / "rel", "E06000050", built, chunk_bytes=4)
    assert [p["path"] for p in entry["parts"]] == [
        "areas/E06000050/map.pmtiles.000", "areas/E06000050/map.pmtiles.001", "areas/E06000050/map.pmtiles.002"]
    assert [p["bytes"] for p in entry["parts"]] == [4, 4, 2]
    assert entry["bytes"] == 10 and entry["sha256"] == hashlib.sha256(bytes(range(10))).hexdigest()

def test_map_at_or_under_chunk_size_is_not_split(tmp_path: Path) -> None:
    built = tmp_path / "built.pmtiles"; built.write_bytes(b"abcd")
    entry = write_map_entry(tmp_path / "rel", "E06000050", built, chunk_bytes=4)
    assert [p["path"] for p in entry["parts"]] == ["areas/E06000050/map.pmtiles"]

def test_pmtiles_bounds_reads_v3_header() -> None:
    header = bytearray(127); header[:7] = b"PMTiles"; header[7] = 3
    struct.pack_into("<iiii", header, 102, -30_000_000, 530_000_000, -28_000_000, 532_000_000)
    assert pmtiles_bounds(bytes(header)) == (-3.0, 53.0, -2.8, 53.2)

def test_pmtiles_bounds_rejects_other_files() -> None:
    with pytest.raises(ValueError):
        pmtiles_bounds(b"not a pmtiles file".ljust(127, b"\0"))
```

Add to `test_config.py`: `test_maps_settings_load` asserts `load_config().map_chunk_bytes == 20 * 1024 * 1024` and that `tilemaker_image` contains `@sha256:`.

- [ ] **Step 2: Run them to see them fail**

Run: `cd pipeline && uv run pytest tests/test_maps.py tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: within_reach_pipeline.maps` and an `AttributeError` for the config fields.

- [ ] **Step 3: Implement `maps.py` and the config**
- **`tilemaker_command`:**
  - mounts `pbf.parent` read-only, `config.parent` read-only, `coastline` read-only at `/coastline`, and `dest.parent` writable;
  - runs `--input`, `--output`, `--bbox`, `--config`, `--process resources/process-openmaptiles.lua`, with the working directory set to `/usr/src/app` (the image's own Lua process file, pinned by the image digest).
- **Config file:** in `config-openmaptiles.json`, the `ocean` layer's `source` is `/coastline/water_polygons.shp`. Otherwise it's the measured slim13 config:
  - `place`, `transportation`, `transportation_name`, `waterway`, `water`, `ocean`, `water_name` kept, all with maxzoom 13;
  - every other layer set to minzoom and maxzoom 99;
  - settings maxzoom and basezoom 13, `compress: gzip`.
- **`pmtiles_bounds`:** checks `header[:7] == b"PMTiles"` and `header[7] == 3`, then unpacks four little-endian int32 values at offset 102 and divides by 1e7.
- **`write_map_entry`:** writes chunks only when `size > chunk_bytes`; otherwise it copies to `areas/<area>/map.pmtiles`.
- **`config.toml`:** add `[maps]` with `tilemaker_image = "ghcr.io/systemed/tilemaker@sha256:<digest>"` and `chunk_bytes = 20_971_520`. Get the digest with `docker pull ghcr.io/systemed/tilemaker:master && docker inspect --format '{{index .RepoDigests 0}}' ghcr.io/systemed/tilemaker:master`. If the upstream image publishes a release tag, use that tag's digest instead.

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd pipeline && uv run pytest tests/test_maps.py tests/test_config.py -v && uv run mypy && uv run ruff check .`
Expected: all PASS, no mypy or ruff errors.

- [ ] **Step 5: Commit**

```bash
git add pipeline/src/within_reach_pipeline/maps.py pipeline/maps pipeline/config.toml pipeline/src/within_reach_pipeline/config.py pipeline/tests/test_maps.py pipeline/tests/test_config.py
git commit -m "pipeline: map building primitives (bbox, tilemaker command, chunking)"
```

---

### Task 2: Fetch coastline and build maps per area (pipeline)

**Files:**
- Modify: `pipeline/src/within_reach_pipeline/sources.py`, `cli.py`, `build.py`
- Test: `pipeline/tests/test_cli.py`, `pipeline/tests/test_build_cli.py`, `pipeline/tests/test_maps.py`

**Interfaces:**
- Consumes: everything Task 1 produces.
- Produces:
  - `WATER_POLYGONS_URL = "https://osmdata.openstreetmap.de/download/water-polygons-split-4326.zip"` in `sources.py`.
  - `COASTLINE_DIR = "coastline"` in `cli.py`; `fetch` extracts the zip's `.shp`, `.shx`, `.dbf`, `.prj` and `.cpg` files flat into `cache/coastline/` and records a `{"name": "water_polygons", ...}` source.
  - `build_release(..., maps: Literal["tilemaker", "none"] = "none")`. When it's `"tilemaker"`, each area entry gains `"map": write_map_entry(...)`, and `manifest["config"]["maps"]` equals `maps`.
  - CLI: `build --maps {tilemaker,none}`, default `none`.
  - `build.py` helper `_area_extract(stack, cache, points) -> Path`, the osmium clip that used to live inside `_routers`. `_routers` now takes the extract path.

- [ ] **Step 1: Write the failing tests**
- `test_cli.py::test_fetch_downloads_water_polygons`: using the existing fake fetcher pattern, serve a zip holding `water-polygons-split-4326/water_polygons.shp`, `.shx` and `.dbf`. Assert that `cache/coastline/water_polygons.shp` exists, and that `sources.json` has a `water_polygons` entry with the right URL and SHA-256.
- `test_build_cli.py::test_build_without_maps_has_no_map_entries`: the existing fake-router build gets `config["maps"] == "none"` and no `"map"` key on any area.
- `test_build_cli.py::test_build_with_maps_records_map_entry`: monkeypatch `within_reach_pipeline.build.build_area_map`, a new function, so it writes a 10-byte file at its `dest` argument instead of running Docker. Also monkeypatch `_area_extract` to return a dummy path. Run `build_release(..., router="fake", maps="tilemaker")` and assert:
  - each area has `map.parts[0].path == f"areas/{code}/map.pmtiles"`;
  - the file exists;
  - `config["maps"] == "tilemaker"`.
- `test_maps.py::test_build_area_map_bbox_covers_neighbouring_pharmacies`: given postcodes around (53.19, -2.89) and one pharmacy at (53.05, -3.0), the bbox passed to `tilemaker_command` contains (53.05, -3.0). Capture the command via a fake `run` callable.
- `test_maps.py::test_tilemaker_end_to_end` (`skipif RUN_TILEMAKER != "1"`, the same pattern as `test_osrm.py`): build Rutland from the existing OSRM test extract. Assert the output starts with `b"PMTiles"` and that `pmtiles_bounds` covers the bbox.

- [ ] **Step 2: Run them to see them fail**

Run: `cd pipeline && uv run pytest tests/test_cli.py tests/test_build_cli.py tests/test_maps.py -v`
Expected: the new tests FAIL (`build_area_map` doesn't exist, `maps` is an unexpected keyword, no coastline in the cache). The end-to-end test is SKIPPED.

- [ ] **Step 3: Implement**
- **`build_area_map(image: str, pbf: Path, points: Sequence[LatLon], config_file: Path, coastline: Path, dest: Path, run: Callable[[list[str]], None] = _run) -> None`** in `maps.py`.
- **In `build_release`:** when `maps == "tilemaker"` or `router == "osrm"`, call `_area_extract` once per area inside the existing `ExitStack`. The map is built from the same extract as the routes, with points = the area's postcodes plus its used pharmacies, into a temp file, then passed to `write_map_entry(out, code, tmp, config.map_chunk_bytes)`.
- **Config file path:** `Path(__file__).resolve().parents[2] / "maps" / "config-openmaptiles.json"`.

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd pipeline && uv run pytest -q && uv run mypy && uv run ruff check . ../scripts`
Expected: all PASS (the end-to-end test skipped).

Then run locally once: `RUN_TILEMAKER=1 uv run pytest tests/test_maps.py::test_tilemaker_end_to_end -v`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline
git commit -m "pipeline: build a map file per area from the routing extract"
```

---

### Task 3: Map release checks (pipeline)

**Files:**
- Modify: `pipeline/src/within_reach_pipeline/checks.py`
- Test: `pipeline/tests/test_checks.py`

**Interfaces:**
- Consumes: manifest `area["map"]` from Task 2; `pmtiles_bounds` from Task 1.
- Produces: `_files(manifest)` also yields every `area["map"]["parts"]` entry, so the checksum and size checks cover them. New `_check_maps(release, manifest) -> list[CheckFailure]`, called by `run_checks` only when `manifest["config"].get("maps") == "tilemaker"`.

- [ ] **Step 1: Write the failing tests** in `test_checks.py`, built on the existing release-fixture helper with a fake map entry:
- `test_map_part_checksum_mismatch_fails`: alter one byte of a part → a `CheckFailure("checksums", ...)` naming the part path.
- `test_map_part_over_limit_fails`: a part over `max_file_bytes` → a `"size"` failure.
- `test_area_without_map_fails_when_maps_built`: `config.maps == "tilemaker"` and one area with no `map` key → `CheckFailure("maps", "<code> has no map")`.
- `test_joined_map_hash_must_match`: parts individually valid, but `map.sha256` wrong → a `"maps"` failure.
- `test_map_bounds_must_cover_area_postcodes`: a header whose bounds exclude one postcode → a `"maps"` failure naming the area.
- `test_maps_none_skips_map_checks`: `config.maps == "none"` and no map keys → no `"maps"` failures.

- [ ] **Step 2: Run them to see them fail**

Run: `cd pipeline && uv run pytest tests/test_checks.py -v`
Expected: the six new tests FAIL.

- [ ] **Step 3: Implement** `_check_maps`: join the parts in order, compare the joined SHA-256 and byte count, read the bounds from the first 127 bytes, and check that every postcode's lat/lon from `areas/<code>/postcodes.csv.gz` falls within them.

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd pipeline && uv run pytest -q && uv run mypy`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline
git commit -m "pipeline: release checks cover map files"
```

---

### Task 4: Publish and deploy maps (workflows, headers, docs)

**Files:**
- Modify: `.github/workflows/pipeline.yml`, `.github/workflows/deploy.yml`, `.github/workflows/live-check.yml`, `app/public/_headers`, `app/vite.config.ts`, `docs/data-format.md`

**Interfaces:**
- Consumes: `build --maps tilemaker` (Task 2).
- Produces:
  - **Release assets:** `data-$RELEASE.tar.gz` (no map files) and `maps-$RELEASE.tar.gz` (only `*/areas/*/map.pmtiles*`), each with a `.sha256`. Partial releases use the `-partial` suffix on both.
  - **Deployed site:** `/data/<latest>/areas/<code>/map.pmtiles[.NNN]` for the latest release only.
  - **Headers:** responses under `/data/*` carry `Cache-Control: no-store`, in production and in `vite preview`.

- [ ] **Step 1: Write the failing test** `app/tests/e2e/site.spec.ts`. Move the four tests from `placeholder.spec.ts` here unchanged, except that the heading test keeps `Within Reach`. Add:

```ts
test('data files are served with no-store', async ({ request }) => {
  const response = await request.get('/data/latest.json')
  expect(response.headers()['cache-control']).toBe('no-store')
})
```

Delete `placeholder.spec.ts`. The preview build has no `/data/` files until the fixture is copied in (Task 8), so mark this one test `test.fixme` here; Task 10 removes the `fixme`.

- [ ] **Step 2: Workflows**
- **`pipeline.yml`:**
  - In the build job: `docker pull` the `tilemaker_image` read from `config.toml`, and add `--maps tilemaker` to the build command.
  - In `prepare`: `fetch` already downloads water polygons, cached through the existing `actions/cache` path.
  - Change `Previous release` to `--pattern 'data-*.tar.gz'`.
  - Change `Publish release` to create both tarballs (`tar --exclude='map.pmtiles*'` for data; a `find … -name 'map.pmtiles*'` list for maps) and attach both, plus their `.sha256` files, to `gh release create`.
- **`deploy.yml`:**
  - In "Add data releases", download `--pattern 'data-*.tar.gz' --pattern 'data-*.tar.gz.sha256'` for both tags.
  - For `tags[0]` only, also download `maps-${tags[0]#data-}.tar.gz` and its `.sha256`, check it, and extract it into `app/dist/data`.
  - If the maps asset is missing (the November 2026 release predates this), print `No maps for $tag; deploying without maps.` and continue.
- **`live-check.yml`:** after the existing header check, if `manifest.areas[0].map` exists, `curl -fsSI` its first part and assert `cache-control: no-store` and HTTP 200.
- **`_headers`:** add, after the `/*` block:
  ```
  /data/*
    Cache-Control: no-store
  ```
- **`vite.config.ts`:** generalise `siteHeaders()` to `headerBlocks(): Map<string, Record<string,string>>`, and add a `configurePreviewServer` middleware that sets the `/data/*` block's headers on requests whose path starts with `/data/`. The existing `/*` behaviour, including dropping `upgrade-insecure-requests` locally, stays as it is.
- **`docs/data-format.md`:**
  - add the `areas/<area>/map.pmtiles[.NNN]` row;
  - add the manifest `map` fields (`bytes`, `sha256`, `parts`) and `config.maps`;
  - add the `maps-YYYY-MM.tar.gz` asset;
  - add "Map files © OpenStreetMap contributors, ODbL; schema OpenMapTiles (CC-BY)".

- [ ] **Step 3: Verify**

Run: `actionlint .github/workflows/*.yml && cd app && npm run lint && npm run check && npm run test:e2e -- site.spec.ts`
Expected: actionlint clean; the moved tests PASS; the no-store test reports `fixme`.

- [ ] **Step 4: Commit**

```bash
git add .github app/public/_headers app/vite.config.ts app/tests/e2e docs/data-format.md
git commit -m "Publish maps as their own release asset; no-store for /data"
```

---

### Task 5: Engine types, opening hours and filters (app)

**Files:**
- Create: `app/src/lib/engine/types.ts`, `app/src/lib/engine/hours.ts`
- Test: `app/src/lib/engine/hours.test.ts`

**Interfaces:**
- Produces `types.ts` (every engine type lives here):

```ts
export type Nation = 'England' | 'Scotland' | 'Wales'
export type Range = { start: number; end: number } // minutes after midnight; end <= start means past midnight
export type DayHours = { kind: 'unknown' } | { kind: 'closed' } | { kind: 'open'; ranges: Range[] }
export type Pharmacy = {
  idx: number; nation: Nation; code: string; name: string; address: string; postcode: string
  lat: number; lon: number; days: DayHours[] // 7 entries, Monday first
}
export type PostcodeRow = { idx: number; postcode: string; lat: number; lon: number }
export type TravelRow = { pcIdx: number; phIdx: number; straightM: number
  walkM: number | null; walkS: number | null; driveS: number | null }
```
- Produces `hours.ts`:
- Produces:

```ts
export type FilterKey = 'saturday' | 'sunday' | 'late'
export type Filters = Record<FilterKey, boolean>
export const NO_FILTERS: Filters
export function parseDay(cell: string): DayHours          // '' → unknown, 'CLOSED' → closed, ranges otherwise
export type FilterStatus = { kind: 'match' } | { kind: 'unknown' } | { kind: 'hidden'; reasons: FilterKey[] }
export function filterStatus(days: DayHours[], filters: Filters): FilterStatus
```

- **Rules:**
  - **saturday:** `days[5]` open → pass; closed → fail; unknown → unknown.
  - **sunday:** the same rule with `days[6]`.
  - **late:**
    - if any of `days[0..4]` has a range with `end >= 19*60`, or `end <= start` (past midnight) → pass;
    - else if any of `days[0..4]` is unknown → unknown;
    - else fail.
  - **Combining:** any fail → hidden, with reasons listing every failing filter in the order saturday, sunday, late. Else any unknown → unknown. Else match. With no filters on → match.
- `parseDay` throws on a malformed cell (for example `9-5`), because the pipeline guarantees `HH:MM-HH:MM` joined with `;`.

- [ ] **Step 1: Write the failing tests** in `hours.test.ts`:
- `parseDay reads blank, CLOSED and ranges`.
- `saturday filter passes an open saturday and hides a closed one` → `{kind:'hidden', reasons:['saturday']}`.
- `saturday filter treats a blank saturday as unknown even when weekdays are known`.
- `late filter passes a weekday closing at 19:00 exactly`; `late filter ignores a saturday closing at 22:00`; `late filter passes a past-midnight range` (`'18:00-01:00'`).
- `late filter is unknown when no weekday qualifies and one weekday is blank`.
- `several filters: any failure hides, listing every failing reason in order`: sat closed, sun closed, weekdays to 17:30 → `reasons: ['saturday','sunday','late']`.
- `failure beats unknown`: sat closed, sun blank, with saturday and sunday on → hidden `['saturday']`.
- `no filters means match even with no hours`.

- [ ] **Step 2: Run them to see them fail**

Run: `cd app && npx vitest run src/lib/engine/hours.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement** `hours.ts`.

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd app && npx vitest run src/lib/engine`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/src/lib/engine
git commit -m "app: engine types, opening hours and weekend/late filters"
```

---

### Task 6: CSV parsers (app)

**Files:**
- Create: `app/src/lib/engine/csv.ts`
- Test: `app/src/lib/engine/csv.test.ts`

**Interfaces:**
- Consumes: `Pharmacy`, `PostcodeRow`, `TravelRow` from `types.ts` and `parseDay` from `hours.ts` (both from Task 5).

- Produces (in `csv.ts`):
  - `parseCsv(text: string): string[][]`: RFC 4180 rules (quoted fields, doubled quotes, CRLF or LF); drops the header row and a trailing empty line.
  - `parseDistricts(text: string): Map<string, string[]>`
  - `parsePharmacies(text: string): Pharmacy[]`: uses `parseDay`.
  - `parsePostcodes(text: string): PostcodeRow[]`
  - `parseTravel(text: string): TravelRow[]`
  - **Column order is checked against the header, exactly as in `docs/data-format.md`.** A different header throws `Error('unexpected columns in <file>')`.


- [ ] **Step 1: Write the failing tests** in `csv.test.ts`:
- `parseCsv handles quotes, commas and doubled quotes`: `'a,b\n"x, y","say ""hi"""\n'` → `[['x, y', 'say "hi"']]`.
- `parseCsv accepts CRLF`.
- `parseDistricts splits space-separated area codes`: `'outward,area_codes\nCH1,E06000050\nSY14,E06000050 W11000023\n'` → `Map { 'CH1' => ['E06000050'], 'SY14' => ['E06000050','W11000023'] }`.
- `parseTravel turns blank cells into null`: `'pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s\n0,5,300,,,120\n'` → `{pcIdx:0, phIdx:5, straightM:300, walkM:null, walkS:null, driveS:120}`.
- `parsePharmacies reads hours per day`: a row with mon `09:00-13:00;14:00-17:30`, sat `CLOSED`, sun blank → `days[0]` open with two ranges, `days[5]` closed, `days[6]` unknown, `idx` from `ph_idx`.
- `parsers reject an unexpected header`: `parseTravel('a,b\n')` throws `unexpected columns in travel`.

- [ ] **Step 2: Run them to see them fail**

Run: `cd app && npx vitest run src/lib/engine/csv.test.ts`
Expected: FAIL, module not found.

- [ ] **Step 3: Implement** `csv.ts`.

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd app && npx vitest run src/lib/engine && npm run check`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add app/src/lib/engine
git commit -m "app: release file parsers"
```

---

### Task 7: Results, sorting, grouping and text (app)

**Files:**
- Create: `app/src/lib/engine/results.ts`, `app/src/lib/engine/format.ts`
- Test: `app/src/lib/engine/results.test.ts`, `app/src/lib/engine/format.test.ts`

**Interfaces:**
- Consumes: the types, `filterStatus`, `Filters`, `FilterKey` (Task 5).
- Produces:

```ts
// results.ts
export type Result = { pharmacy: Pharmacy; straightM: number; walkM: number | null; walkS: number | null; driveS: number | null }
export type SortMode = 'walk' | 'drive'
export function buildResults(pcIdx: number, travel: TravelRow[], pharmacies: Pharmacy[]): Result[]
export function sortResults(results: Result[], mode: SortMode): Result[]   // new array
export type Grouped = { matches: Result[]; unknown: Result[]; hidden: { result: Result; reasons: FilterKey[] }[] }
export function groupByFilters(sorted: Result[], filters: Filters): Grouped
export function hiddenSummary(grouped: Grouped, mode: SortMode): string | null
// format.ts
export function formatDistance(metres: number): string     // <995: nearest 10 m, "650 m"; else km to 1 dp, "1.3 km"
export function formatMinutes(seconds: number): string     // "11 min", ceil, min 1
export function travelLine(r: Result): string              // see tests
export function formatDayHours(day: DayHours): string      // "Closed" | "Not known" | "9:00–13:00, 14:00–17:30"
export function hasAnyHours(days: DayHours[]): boolean
export const DAY_NAMES: readonly string[]                  // ['Monday', …, 'Sunday']
```

- **Sort key:**
  - walk: `[walkM === null, walkM ?? 0, straightM, nation, code]`;
  - drive: `[driveS === null, driveS ?? 0, straightM, nation, code]`.
- **Hidden summary:**
  - `null` when `hidden` is empty;
  - otherwise `${n} ${closer}pharmac${n === 1 ? 'y' : 'ies'} hidden: ${reasons}.`;
  - `closer` is `'closer '` when any hidden result sorts before the last shown one (the last of `unknown`, else the last of `matches`), or when nothing is shown;
  - reasons are the union in the order saturday, sunday, late, labelled `not open on Saturdays`, `not open on Sundays`, `not open late`, joined with `' or '`.

- [ ] **Step 1: Write the failing tests:**
- `buildResults keeps only rows for the postcode and joins the pharmacy`.
- `walking sort puts missing walks last, ordered by straight line`.
- `ties break by straight line, then nation, then code` (NFR-11).
- `driving sort uses drive_s`.
- `groupByFilters keeps order and puts unknown hours after matches`.
- `hiddenSummary counts closer hidden pharmacies`: three results, the closest closed on Sunday, sunday filter on → `'1 closer pharmacy hidden: not open on Sundays.'`.
- `hiddenSummary joins reasons with or`: → `'6 pharmacies hidden: not open on Saturdays or not open late.'` (all hidden ones sort after the last shown).
- `hiddenSummary is null with nothing hidden`.
- `formatDistance`: `650 → '650 m'`, `654 → '650 m'`, `994 → '990 m'`, `995 → '1.0 km'`, `1349 → '1.3 km'`. (Rule: below 995 m, round to the nearest 10 m; otherwise km to 1 dp.)
- `formatMinutes`: `30 → '1 min'`, `600 → '10 min'`, `601 → '11 min'`.
- `travelLine`: `{walkM: 800, walkS: 650, driveS: 170}` → `'800 m · 11 min walk · 3 min drive'`; `{walkM:null, walkS:null, driveS:170}` → `'No walking route found · 3 min drive'`; `{walkM: 1300, walkS: 960, driveS: null}` → `'1.3 km · 16 min walk · No driving route found'`.
- `formatDayHours`: open `[{540,780},{840,1050}]` → `'9:00–13:00, 14:00–17:30'`; closed → `'Closed'`; unknown → `'Not known'`.

- [ ] **Step 2: Run them to see them fail**

Run: `cd app && npx vitest run src/lib/engine`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement** `results.ts` and `format.ts`.

- [ ] **Step 4: Run the tests to see them pass, with coverage**

Run: `cd app && npx vitest run src/lib/engine --coverage --coverage.include='src/lib/engine/**' --coverage.thresholds.lines=85`
Expected: PASS, with lines at 85% or more. If `@vitest/coverage-v8` is missing, add it as a devDependency in this step and wire `npm test` in `package.json` to enforce the same threshold.

- [ ] **Step 5: Commit**

```bash
git add app
git commit -m "app: results, sorting, filter grouping and display text"
```

---

### Task 8: Fixture release (scripts, test data)

**Files:**
- Create: `scripts/make_fixture_release.py`, `scripts/test_make_fixture_release.py`, `app/tests/fixtures/data/**`, `app/scripts/copy-fixture.mjs`
- Modify: `app/playwright.config.ts`, `app/package.json`

**Interfaces:**
- Consumes: a real published release directory (`data-2026-11` extracted) and the pipeline's `maps.py` (for one tiny map).
- Produces:
  - **`app/tests/fixtures/data/latest.json`:** `{"release": "2026-11", "previous": null}`.
  - **`app/tests/fixtures/data/2026-11/`:** a valid release (manifest, `pharmacies.csv.gz`, `districts.csv.gz`, areas) trimmed to:
    - **districts:** `CH2`, `CH4` and `LL11`;
    - **areas:** `E06000050` (Cheshire West and Chester) and `W11000023` (Betsi Cadwaladr);
    - **pharmacies:** only those referenced by kept travel rows, renumbered `ph_idx` 0..n in nation, code order;
    - **postcodes:** only the kept districts' postcodes, renumbered `pc_idx`;
    - **the manifest's** `areas[].files` checksums recomputed.
  - **One map per area,** built by tilemaker over the kept postcodes. `E06000050`'s map is written with `chunk_bytes` set so it splits into at least 2 parts; `W11000023` stays a single file.
  - **`districts.csv.gz`** also contains a synthetic district `SY14 → "E06000050 W11000023"` mapping to two areas, plus one kept postcode from `W11000023` re-labelled into `SY14`, so the two-area path is exercised. Test postcode: the first `LL11` postcode, re-labelled `SY14 9ZZ`. The script prints it.
  - **`copy-fixture.mjs`:** copies `tests/fixtures/data` into `dist/data` unless `dist/data/latest.json` already exists.
  - **`playwright.config.ts`** webServer command: `npm run build && node scripts/copy-fixture.mjs && npm run preview -- --port 4173 --strictPort`.

- [ ] **Step 1: Write the failing test** `scripts/test_make_fixture_release.py`. It runs the script's `trim_release(src: Path, dest: Path, districts: list[str], chunk_bytes: int | None, build_map: Callable | None)` on a tiny synthetic release built in `tmp_path` with the pipeline's fake router, with `build_map=None`, and checks:
- the output passes `run_checks(dest, load_config(), None, None, allow_partial=True)` with no failures;
- every travel `ph_idx` exists in `pharmacies.csv.gz`;
- postcodes are sorted and renumbered.

- [ ] **Step 2: Run it to see it fail**

Run: `cd pipeline && uv run pytest ../scripts/test_make_fixture_release.py -v`
Expected: FAIL, the module doesn't exist.

- [ ] **Step 3: Implement the script and generate the fixture**

Run: `gh release download data-2026-11 --pattern 'data-*.tar.gz' --dir "$TMPDIR/rel" && tar -xzf "$TMPDIR/rel"/*.tar.gz -C "$TMPDIR/rel" && cd pipeline && uv run python ../scripts/make_fixture_release.py "$TMPDIR/rel/2026-11" ../app/tests/fixtures/data --districts CH2 CH4 LL11 --split-area E06000050`

Expected: a printed summary of postcodes, pharmacies and map parts. The fixture is under 8 MB in total (`du -sh app/tests/fixtures/data`). If it's bigger, drop `CH4` and record a ledger ruling.

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd pipeline && uv run pytest ../scripts -q && uv run mypy --strict ../scripts && uv run ruff check ../scripts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts app/tests/fixtures app/scripts app/playwright.config.ts app/package.json
git commit -m "test: trimmed real-data fixture release with split map"
```

---

### Task 9: Data layer: verified files and postcode search (app)

**Files:**
- Create: `app/src/lib/data/files.ts`, `app/src/lib/data/search.ts`
- Modify: `app/src/lib/data/release.ts`
- Test: `app/src/lib/data/files.test.ts`, `app/src/lib/data/search.test.ts`, `app/src/lib/data/release.test.ts`

**Interfaces:**
- Consumes: the parsers (Task 6), `buildResults` (Task 7), `normalisePostcode` and `isNorthernIreland` (existing).
- Produces:

```ts
// release.ts (added)
export type FileRef = { path: string; sha256: string; bytes: number }
export type MapRef = { bytes: number; sha256: string; parts: FileRef[] }
export type AreaEntry = { code: string; name: string; nation: string; files: { postcodes: FileRef; travel: FileRef }; map?: MapRef }
export type Manifest = { release: string; builtAt: string; attribution: string; directory: FileRef; districts: FileRef; areas: AreaEntry[] }
export function parseManifest(latest: unknown, manifest: unknown): Manifest | null   // parseRelease stays, built on this
export async function loadManifest(fetchFn?: typeof fetch): Promise<Manifest | null>
// files.ts
export class DownloadError extends Error {}
export class IntegrityError extends Error {}
export async function sha256Hex(data: Uint8Array): Promise<string>
export async function fetchVerified(release: string, ref: FileRef, fetchFn?: typeof fetch,
  onProgress?: (received: number) => void): Promise<Uint8Array>   // GET /data/<release>/<path>, cache:'no-store'
export async function gunzipText(data: Uint8Array): Promise<string> // DecompressionStream('gzip')
export class SessionFiles {                                          // in-memory only
  constructor(release: string, fetchFn?: typeof fetch)
  bytes(ref: FileRef, onProgress?: (received: number) => void): Promise<Uint8Array> // memoised by path
  text(ref: FileRef): Promise<string>                                // gunzip of bytes(), memoised
}
// search.ts
export type SearchOutcome =
  | { kind: 'invalid' } | { kind: 'northern-ireland' } | { kind: 'not-found'; postcode: string }
  | { kind: 'found'; postcode: string; area: AreaEntry; lat: number; lon: number; results: Result[] }
export class Searcher {
  constructor(manifest: Manifest, files: SessionFiles)
  search(raw: string): Promise<SearchOutcome>   // throws DownloadError | IntegrityError
}
```

- **Path safety:** `fetchVerified` rejects a `ref.path` that doesn't match `/^[A-Za-z0-9_./-]+$/`, or that contains `..`, by throwing `IntegrityError`. Paths come from the manifest, but they're validated before use in a URL.
- **Failures:** a network failure or non-OK status → `DownloadError`; a wrong hash or byte count → `IntegrityError`. A failed promise is evicted from the `SessionFiles` memo so that Try again re-fetches.
- **`Searcher.search` steps:**
  1. normalise, which may return `invalid`;
  2. BT → `northern-ireland`;
  3. districts (lazy, via `files`), where an unknown outward code → `not-found`;
  4. for each area code that's in the manifest, load its postcodes and binary-search them;
  5. on the first hit, load that area's travel file plus `pharmacies.csv.gz`, and return `found` with `buildResults`;
  6. if there's no hit → `not-found`.

  Parsed tables are memoised per path inside `Searcher`.

- [ ] **Step 1: Write the failing tests.** Build files in-test with `CompressionStream('gzip')` (Node 22 has it) and a fake `fetch` that serves a `Map<string, Uint8Array>` and records requested URLs.
- `fetchVerified returns bytes whose hash matches`.
- `fetchVerified rejects a body whose hash differs` → `IntegrityError`.
- `fetchVerified rejects a wrong byte count` → `IntegrityError`.
- `fetchVerified turns a 404 into DownloadError`.
- `fetchVerified refuses a path with ..`.
- `fetchVerified requests with cache no-store`: assert the init passed to the fake fetch.
- `SessionFiles fetches each path once`.
- `SessionFiles retries after a failure`.
- `search: invalid, northern-ireland, unknown district`.
- `searchPostcode finds a postcode in the second area of a district`: district `SY14 → [A, B]` with the postcode only in B. The outcome is `found` with `area.code === 'B'`, the requested URLs include A's and B's postcode files, and travel only for B.
- `search returns not-found for a postcode absent from its areas`.
- `search results come from the found postcode's travel rows`.
- `no requested URL contains the postcode`: assert over the recorded URLs, using the same postcode regex as `fixtures.ts`.
- `parseManifest reads areas, files and map refs` (`release.test.ts`).

- [ ] **Step 2: Run them to see them fail**

Run: `cd app && npx vitest run src/lib/data`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement** `files.ts`, `search.ts` and the `release.ts` additions. `loadRelease` keeps its signature and delegates to `loadManifest`.

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd app && npm test && npm run check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/src/lib/data
git commit -m "app: verified session-only downloads and postcode search"
```

---

### Task 10: Search page: form, messages, controls and list (app)

**Files:**
- Create: `app/src/lib/ui/SearchPage.svelte`, `SearchForm.svelte`, `Messages.svelte`, `Controls.svelte`, `ResultsList.svelte`, `ResultEntry.svelte`
- Modify: `app/src/App.svelte`, `app/src/app.css`
- Delete: `app/src/lib/ui/Placeholder.svelte`
- Test: `app/tests/e2e/search.spec.ts`; remove the `fixme` from the no-store test in `site.spec.ts`

**Interfaces:**
- Consumes: `loadManifest`, `SessionFiles`, `Searcher`, `DownloadError`, `IntegrityError` (Task 9); `sortResults`, `groupByFilters`, `hiddenSummary` (Task 7); the format functions (Task 7); `formatRelease` (existing).
- Produces:
  - **`SearchPage` state** (Svelte 5 runes, memory only): `outcome`, `mode: SortMode` (default `'walk'`), `filters: Filters` (all false), `visible: number` (10, reset on each search), `selected: number | null` (a pharmacy idx, shared with the map in Task 11).
  - **`ResultsList` props:** `shown: Result[]` (matches then unknown, sliced to `visible`), `unknownStartsAt: number | null`, `summary: string | null`, `selected`, `onSelect(idx)`, `onShowMore()`.
  - **Markup:** each entry is an `<li data-testid="result" data-ph-idx={idx}>` whose number is its 1-based position in `shown`.

**Exact copy** (from the spec's section 5):
- **Header:** `Within Reach` (h1); `Data from {formatRelease(release)}`.
- **Form:** label `Postcode`, button `Search`. The form has `novalidate` and calls `preventDefault`; there's no `action` attribute and no `name`-based submission.
- **Messages, in a `role="status"` live region:**
  - `Enter a full UK postcode, for example CH2 3JQ.`
  - `Northern Ireland isn't covered yet. Within Reach covers England, Scotland and Wales.`
  - `We couldn't find {postcode}. Check it's correct and still in use.`
  - `Couldn't download the pharmacy data. Check your connection and try again.` plus a `Try again` button
  - `The downloaded data didn't pass its integrity check, so it hasn't been used.` plus a `Try again` button
- **Controls:**
  - a `Sort` fieldset with radios `Walking` and `Driving`;
  - a `Filters` fieldset with checkboxes `Open Saturday`, `Open Sunday`, `Open late`.
- **Unknown group:** heading `Opening hours not known` plus `Scottish and Welsh pharmacy lists don't include opening hours, so these pharmacies can't be filtered.`
- **No matches:** `No pharmacies nearby match these filters.`
- **Paging:** `Show 10 more`.
- **Entries:**
  - name (h3), then address and postcode, then `travelLine(r)`;
  - then `<details><summary>Opening hours</summary>` with a table of `DAY_NAMES` against `formatDayHours`, or `No opening hours included` when `!hasAnyHours`;
  - a `Show on map` button, which sets `selected`.
- **Footer:** the manifest attribution text.

**Layout** (`app.css`, my call within the design):
- a CSS grid, two columns (map 3fr, list 2fr) at 900 px and wider;
- a single column below 900 px, in the order form, map (`height: 40vh`), controls, list;
- visible focus styles;
- colour contrast at least 4.5:1.

- [ ] **Step 1: Write the failing e2e tests** in `search.spec.ts`. Each one starts with `page.goto('/')`, fills `getByLabel('Postcode')` and presses Enter. Use real fixture postcodes; the script printed them in Task 8. Put them in a `const PC = {...}` at the top.
- `a search lists pharmacies closest first, numbered from 1`: 10 items; numbers 1–10; walking order (assert that the first entry's walk distance ≤ the second's by reading `data-walk-m` on each `li`, an attribute added for tests).
- `driving sort reorders the list`.
- `Open Sunday hides closed pharmacies and summarises them`: the summary matches `/^\d+ (closer )?pharmac(y|ies) hidden: not open on Sundays\.$/`.
- `Welsh pharmacies stay listed under Opening hours not known when a filter is on` (an `LL11` postcode).
- `Show 10 more adds ten entries`.
- `opening hours open in a details element`.
- `invalid, Northern Ireland and not-found messages`: `'hello'`, `'BT1 1AA'`, `'CH2 9ZZ'`; the not-found text includes the normalised postcode.
- `a district spanning two areas finds the postcode` (`SY14 9ZZ`).
- `a failed download shows Try again, and Try again recovers`: `page.route('**/travel.csv.gz', r => r.abort())` once, then unroute and click.
- `a tampered travel file shows the integrity message`: `route.fulfill` with the body plus one extra byte.
- `the search leaves no trace`: after a search, `page.url()` ends with `/`; `history.length` hasn't grown; localStorage, sessionStorage and IndexedDB are empty; `caches.keys()` is empty; cookies are empty.
- `keyboard only: search, sort, filter, open hours, show more`, using only `page.keyboard`.
- `results page passes axe`, with a filter on, and again with an error showing.

- [ ] **Step 2: Run them to see them fail**

Run: `cd app && npm run test:e2e -- search.spec.ts --project=chromium`
Expected: FAIL (no Postcode field).

- [ ] **Step 3: Implement the components**, render `SearchPage` from `App.svelte`, delete `Placeholder.svelte`, and remove `test.fixme` from the no-store test.

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd app && npm run lint && npm run check && npm test && npm run test:e2e`
Expected: all PASS in chromium, firefox and webkit, with the privacy guard green.

- [ ] **Step 5: Commit**

```bash
git add app
git commit -m "app: public postcode search with sort, filters and list"
```

---

### Task 11: In-memory map file (app)

**Files:**
- Create: `app/src/lib/data/map-file.ts`
- Modify: `app/package.json` (add `pmtiles`, `maplibre-gl` as dependencies, at the exact versions resolved by `npm install`)
- Test: `app/src/lib/data/map-file.test.ts`

**Interfaces:**
- Consumes: `SessionFiles.bytes`, `sha256Hex`, `IntegrityError`, `MapRef` (Task 9).
- Produces:

```ts
export async function loadAreaMap(files: SessionFiles, map: MapRef,
  onProgress?: (received: number, total: number) => void): Promise<ArrayBuffer>  // verifies parts, joins, verifies whole
export class MemorySource implements import('pmtiles').Source {
  constructor(key: string, data: ArrayBuffer)
  getKey(): string
  getBytes(offset: number, length: number): Promise<import('pmtiles').RangeResponse>
}
```

- [ ] **Step 1: Write the failing tests:**
- `loadAreaMap joins parts in order and checks the whole hash`.
- `loadAreaMap rejects a whole-file hash mismatch even when parts are valid` → `IntegrityError`.
- `loadAreaMap reports progress up to the total`.
- `MemorySource serves byte ranges`: `getBytes(2, 3)` on `[0..9]` → `[2,3,4]`.
- `MemorySource reads the fixture map header`: `new PMTiles(new MemorySource('k', <fixture E06000050 parts joined>)).getHeader()` gives `minZoom`/`maxZoom` with `maxZoom === 13`. Read the fixture from `../../../tests/fixtures/data/2026-11/...` via `node:fs` in the test.

- [ ] **Step 2: Run them to see them fail**

Run: `cd app && npx vitest run src/lib/data/map-file.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement** after `npm install pmtiles maplibre-gl`. Check `npm audit --audit-level=high --omit=dev` is clean.

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd app && npm test && npm run check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app
git commit -m "app: load a whole area map into memory as a PMTiles source"
```

---

### Task 12: Map panel (app)

**Files:**
- Create: `app/src/lib/ui/MapPanel.svelte`, `app/src/lib/ui/map-style.ts`, `app/public/map/style.json`, `app/public/map/glyphs/**`, `app/src/types/maplibre-csp.d.ts`
- Modify: `app/src/lib/ui/SearchPage.svelte`
- Test: `app/tests/e2e/map.spec.ts`, `app/src/lib/ui/map-style.test.ts`

**Interfaces:**
- Consumes: `loadAreaMap`, `MemorySource` (Task 11); `selected` and `onSelect` from `SearchPage` (Task 10); the outcome's `lat`/`lon` and `shown`.
- Produces:
  - **`MapPanel` props:** `files: SessionFiles`, `area: AreaEntry`, `origin: {lat, lon}`, `shown: Result[]`, `selected: number | null`, `onSelect(idx: number)`.
  - **`buildStyle(base: StyleSpecification, sourceUrl: string, glyphsUrl: string): StyleSpecification`** in `map-style.ts`: sets the vector source's `url` to `sourceUrl` and `glyphs` to `glyphsUrl`, without changing anything else.
  - **`pinsGeoJson(shown: Result[], origin): FeatureCollection`**: the origin feature carries `kind: 'origin'`; pins carry `kind: 'pharmacy'`, `n` (1-based) and `idx`.
- **Container attributes:**
  - `role="img"`, with `aria-label` set to `Map of the postcode and the {n} pharmacies listed`;
  - `data-testid="map"`;
  - `data-pin-count={n}`;
  - `data-map-state` = `loading` | `ready` | `unavailable`.

**Decisions:**
- **Loading:** MapLibre is imported lazily (`await import('maplibre-gl/dist/maplibre-gl-csp.js')`) inside `onMount` after the first `found` outcome. The worker URL comes from `import workerUrl from 'maplibre-gl/dist/maplibre-gl-csp-worker.js?url'` plus `maplibregl.setWorkerUrl(workerUrl)`, and the CSS from `import 'maplibre-gl/dist/maplibre-gl.css'`.
- **Protocol:** register it once with `const protocol = new Protocol(); maplibregl.addProtocol('pmtiles', protocol.tile)`, then `protocol.add(new PMTiles(new MemorySource('area-' + code, buffer)))`. The source URL is `pmtiles://area-<code>`.
- **Glyphs:** `${location.origin}/map/glyphs/{fontstack}/{range}.pbf`. Fonts are `Noto Sans Regular` and `Noto Sans Bold`, ranges `0-255`, `256-511` and `8192-8447`. Take them from `protomaps/basemaps-assets` (OFL), pinned to a commit. Record the commit and the SHA-256 of each `.pbf` in `app/public/map/glyphs/SOURCE.md`, and include `OFL.txt`.
- **`style.json`:**
  - layers: background, water, waterway, transportation (by class), transportation_name, place labels;
  - a calm light palette;
  - attribution `© OpenStreetMap contributors` on the source.
- **Pins:** a GeoJSON source with:
  - a circle layer (radius 11, a fill colour with contrast of 3:1 or more against the background, white stroke);
  - a symbol layer with `text-field: ['get','n']`, font `Noto Sans Bold`;
  - a distinct origin circle;
  - the selected pin drawn larger through a `['==', ['get','idx'], selected]` expression.
- **Map settings:** `maxZoom: 16`. The view fits the bounds of the origin and `shown`, with 40 px padding, and re-fits when `shown` changes. A click on the pin layer calls `onSelect(idx)`. `selected` changing pans to that pin.
- **WebGL:**
  - check first with `document.createElement('canvas').getContext('webgl2') ?? …getContext('webgl')`;
  - if there's no context, or the map emits an `error` before `load`, set the state to `unavailable` and show `Map not available on this device. The list below has all the details.`
- **While loading:** `Loading map…` with a `<progress>` (value = received, max = `map.bytes`).
- **SearchPage:** the list renders as soon as the outcome is ready and never awaits the map.
- **Area without a map** (the first release predates maps): state `unavailable`, with the same message.

- [ ] **Step 1: Write the failing tests:**
- `map-style.test.ts`: `buildStyle sets the source url and glyphs only`; `pinsGeoJson numbers pins from 1 and marks the origin`.
- `map.spec.ts`:
  - `a search draws the map with a pin per listed pharmacy`: `data-map-state="ready"`, `data-pin-count="10"`, attribution text visible; after `Show 10 more`, `data-pin-count="20"`.
  - `the map file is downloaded whole, once per part, with no range or tile requests`: record `context.on('request')`. Every request whose path contains `map.pmtiles` has no `range` header. Each part path is requested exactly once. No request path matches `/\/\d+\/\d+\/\d+(\.pbf|\.mvt)?$/`.
  - `a second search in the same area downloads nothing new`: count `/data/` requests after the second search of another `CH2` postcode → 0.
  - `clicking Show on map selects the pin`: `data-selected-idx` on the container equals the entry's `data-ph-idx`.
  - `with WebGL disabled the list works and the map says it isn't available`: `test.use({ launchOptions: { args: ['--disable-webgl', '--disable-3d-apis'] } })`, chromium only (`test.skip(browserName !== 'chromium')`).
  - `map page passes axe`.
- The privacy guard must stay green throughout. A CSP violation fails the test, which is how a missing `blob:` would show up.

- [ ] **Step 2: Run them to see them fail**

Run: `cd app && npx vitest run src/lib/ui && npm run test:e2e -- map.spec.ts --project=chromium`
Expected: FAIL.

- [ ] **Step 3: Implement**, including fetching and checking in the glyphs.

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd app && npm run lint && npm run check && npm test && npm run build && npm run test:e2e`
Expected: all PASS in every project.

Then record the initial JS size of `dist/assets/index-*.js` (gzipped) and the MapLibre chunk size in the commit body. The initial bundle must not include MapLibre (it's lazy).

- [ ] **Step 5: Commit**

```bash
git add app
git commit -m "app: private area map with numbered pins linked to the list"
```

---

### Task 13: End-to-end privacy pass, performance notes and spec update

**Files:**
- Modify: `app/tests/e2e/search.spec.ts` (if any gaps remain), `docs/decisions.md`, `~/Downloads/Within Reach Tool.md` (the spec, outside the repo), `pipeline/README.md`
- Create: `docs/phase-2-measurements.md`

**Interfaces:**
- Consumes: everything above.
- Produces: spec draft 0.7, and recorded measurements.

- [ ] **Step 1: Write any missing tests.** Confirm these exist and pass, and add any that are missing:
- `a second search in the same area downloads nothing new` (Task 12);
- `a tampered travel file shows the integrity message` (Task 10);
- the no-store header test (Task 4).

Run: `cd app && npm run test:e2e`
Expected: all PASS.

- [ ] **Step 2: Real-area measurements.** Build the maps locally for `E08000025` (Birmingham), `E10000016` (Kent) and `S12000017` (Highland) with:

`uv run within-reach-pipeline build --cache .cache --release 2026-11 --out /tmp/m --areas <code> --router fake --maps tilemaker`

Record the following in `docs/phase-2-measurements.md`:
- the map size and number of parts;
- the build time;
- with `vite preview` and Chrome DevTools throttling at "Fast 4G" plus no throttling: the time from Search to the list showing, and to `data-map-state=ready`.

The design's targets are a list within 3 s and a map within 6 s on average broadband. Record misses; don't hide them.

- [ ] **Step 3: Spec draft 0.7.** Edit `~/Downloads/Within Reach Tool.md` per the design's section 11:
- Phase 2 becomes public search with a map; service Musts and D7, D8, D10, D12 move to Phase 3;
- the FR-13 wording;
- a new FR for the area map;
- the FR-08 wording;
- the data format, plus map checks in FR-04;
- AC-18, AC-19, AC-20;
- a change-log row dated on the day of the edit.

Back up first to `~/Downloads/Within Reach Tool 0.6_<DD_MM_YYYY>.md`, following the home-folder duplicate rule. Add a "Phase 2 choices" section to `docs/decisions.md` listing the calls from the design doc.

- [ ] **Step 4: Full verification**

Run: `cd pipeline && uv run pytest -q && uv run mypy && cd ../app && npm run lint && npm run check && npm test && npm run test:e2e`
Expected: all PASS.

- [ ] **Step 5: Commit, push and open a PR**

```bash
git add docs pipeline/README.md app/tests
git commit -m "docs: Phase 2 measurements and decisions"
git push -u origin phase-2-public-search
gh pr create --title "Phase 2: public search with a private map" --body-file <(printf '%s\n' "Implements docs/superpowers/specs/2026-11-18-phase-2-public-search-design.md." "" "See docs/phase-2-measurements.md for sizes and timings.")
```

Merge only when CI is green. The first monthly run with `--maps tilemaker` happens on 2 December, or can be triggered by hand after the merge. Until then the live site shows the list, and the map shows `Map not available on this device…` because the November release has no maps. *Ruling: this is acceptable for the PR; the owner decides whether to trigger a manual pipeline run before tagging a production release.*

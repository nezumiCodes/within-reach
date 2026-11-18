# Phase 1: Cloud Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A monthly, public-data-only pipeline that builds per-area lookup bundles for Great Britain. Each bundle holds postcodes and, for each postcode, nearby pharmacies with straight-line distance, walking distance and time, and driving time. The pipeline checks the bundles and publishes them as a versioned data release that the deploy job serves at `/data/`.

**Architecture:**
1. Download ONSPD, the NHSBSA and PHS pharmacy lists, NHS ODS (for Wales) and the Geofabrik UK extract.
2. Map the three pharmacy lists into one directory, leaving out online-only (distance-selling) pharmacies flagged in NHSBSA Contractor Details. Pharmacies are geocoded to their postcode's centroid.
3. Assign postcodes to areas. For each postcode, pick candidate pharmacies with a k-d tree.
4. Route candidate pairs through OSRM (foot and car), with one OSRM instance per area on a clipped extract.
5. Write gzipped CSV bundles and a manifest with SHA-256 checksums.
6. Run the release checks. Publish a GitHub Release `data-YYYY-MM` only if every check passes.
7. The deploy workflow merges the latest and previous releases into the site.

**Tech Stack:** Python 3.12 (uv, ruff, mypy strict, pytest); httpx, numpy, scipy (`cKDTree`); OSRM `ghcr.io/project-osrm/osrm-backend:v26.11.0-debian` in Docker; osmium-tool; GitHub Actions; GitHub Releases.

**Spec:** `~/Downloads/Within Reach Tool.md` (draft 0.5), FR-01 to FR-05, NFR-09, NFR-11, sections 8 and 11. Breakdown plan: `~/.claude/plans/i-am-working-on-indexed-fountain.md`. Decisions: `docs/decisions.md`.

## Global Constraints

- **Public data only.** No client data anywhere in the pipeline, its fixtures or its outputs (NFR-06).
- **Postcodes:** ONSPD rows are kept only when the country is `E92000001`, `S92000003` or `W92000004`. Northern Ireland (BT), the Channel Islands and the Isle of Man are dropped. No `BT` postcode may appear in any published file (C3, FR-04).
- **Pharmacy identity** is always `(nation, code)`, where nation ∈ {`England`, `Scotland`, `Wales`}. Codes: the ODS code in England and Wales, the PHS `DispCode` in Scotland (spec 0.5).
- **Ordering is deterministic (NFR-11):** candidates sort by `straight_m`, then nation, then code. Postcodes sort by postcode. Pharmacies sort by nation, then code.
- **Catchment** (`pipeline/config.toml`): `radius_m = 5000`, `max_candidates = 40`, `min_candidates = 5`.
- **File size:** every published file must be at most `24 MiB` (25,165,824 bytes), which leaves headroom under Cloudflare Pages' 25 MiB limit (FR-03).
- **Release checks:** pharmacy counts per nation and total postcodes must be within ±10% of the previous release (`count_tolerance = 0.10`).
- **Routing:** OSRM image pinned to `v26.11.0-debian` (multi-platform: linux/amd64 for GitHub runners, linux/arm64 for Apple Silicon), algorithm MLD, profiles `foot.lua` and `car.lua`.
- **Format:** gzipped UTF-8 CSV with a header row and `\n` line endings. Lat/lon are written with 6 decimals; distances in whole metres; times in whole seconds. A blank cell means unknown.
- **Attribution** goes in every manifest (NFR-16): OGL v3.0 (ONS, NHSBSA, PHS, NHS ODS), OS data © Crown copyright, © OpenStreetMap contributors (ODbL).
- **Dependencies:** only `httpx`, `numpy` and `scipy` at runtime. Dev: `pytest`, `ruff`, `mypy`, `types-*` stubs as needed.
- **Python checks** run from `pipeline/`: `uv run ruff check . ../scripts`, `uv run ruff format --check . ../scripts`, `uv run mypy`, `uv run pytest . ../scripts`.

## Review Focus

1. **The ONSPD column suffixes change every release** (`lad26cd` becomes `lad27cd`). Columns must be found by pattern, so a renamed header still parses. The test lives in Task 2.
2. **A pharmacy's postcode isn't in ONSPD** (a new build, or terminated). The pharmacy is left out of the directory and listed under `geocode_failures` in the manifest. The release check fails if a nation's failures exceed 1%. Tests in Tasks 3 and 9.
3. **No route exists** (islands without a ferry in OSM, gaps in the network). OSRM returns null. The walk and drive cells stay blank, the straight-line distance is kept, and nothing crashes. The test lives in Task 6.
4. **Odd opening-hours text** (`; ` separators, `Closed` in mixed case, anything unexpected). Unparseable days become unknown, with a warning count in the manifest, and never crash the run. The test lives in Task 3.
5. **Remote postcodes with no pharmacy within 5 km** (the Highlands, the islands) still get the nearest 5. The test lives in Task 5.

---

## File structure

```
pipeline/
  config.toml                         # catchment, tolerances, image tags, source endpoints
  reference/expectations.toml         # hand-checked reference cases (Task 10)
  src/within_reach_pipeline/
    __init__.py                       # main() -> cli.run()
    cli.py                            # argparse: fetch | build | merge | check
    config.py                         # PipelineConfig, load_config()
    models.py                         # Nation, Postcode, Pharmacy, OpeningHours, Candidate, TravelRow
    postcodes.py                      # (exists) normalise_postcode, is_northern_ireland
    http.py                           # Fetcher protocol + HttpxFetcher (download with sha256)
    sources.py                        # discover latest release URLs; SourceRelease
    onspd.py                          # resolve_columns, read_onspd, area_code_for, read_area_names
    pharmacies/__init__.py            # build_directory(): merge + geocode
    pharmacies/hours.py               # parse_day_hours
    pharmacies/england.py             # read_nhsbsa
    pharmacies/scotland.py            # read_phs
    pharmacies/wales.py               # fetch_ods_wales
    candidates.py                     # select_candidates (cKDTree)
    routing/__init__.py               # Router protocol, TableResult, route_candidates (tiling)
    routing/osrm.py                   # OsrmRouter, osrm_server(), clip_extract()
    routing/fake.py                   # FakeRouter for tests
    bundle.py                         # write_area, write_directory, write_district_index, write_manifest
    checks.py                         # run_checks -> list[CheckFailure]
  tests/
    fixtures/                         # tiny real-format samples (public data only)
    test_*.py                         # one per module
.github/workflows/pipeline.yml        # monthly build -> checks -> GitHub Release
.github/workflows/deploy.yml          # (modify) merge data releases into dist/data
app/src/lib/data/release.ts           # fetch /data/latest.json + manifest (FR-05)
app/src/lib/ui/Placeholder.svelte     # (modify) show data release date
docs/data-format.md                   # bundle schema for the app (Phase 2) and the public
```

## Published release layout (served at `/data/`)

```
data/latest.json                      {"release": "2026-12", "previous": "2026-11" | null}
data/<release>/manifest.json
data/<release>/pharmacies.csv.gz      ph_idx,nation,code,name,address,postcode,lat,lon,mon,tue,wed,thu,fri,sat,sun
data/<release>/districts.csv.gz       outward,area_codes        (area_codes space-separated; for FR-12/AC-13)
data/<release>/areas/<code>/postcodes.csv.gz   pc_idx,postcode,lat,lon
data/<release>/areas/<code>/travel.csv.gz      pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s
```

- **Day columns:** a blank cell is unknown, `CLOSED` is closed, and opening times look like `09:00-13:00;14:00-17:30`.
- **`address`:** address lines joined with `, `.
- **Indexes:** `ph_idx` is 0-based in directory order. `pc_idx` is 0-based within the area file.

`manifest.json` keys: `release`, `built_at` (ISO 8601 UTC), `sources` (one entry per source, each with `label`, `url`, `sha256` or `fetched_at`), `config` (`radius_m`, `max_candidates`, `min_candidates`, `osrm_version`), `attribution` (list of strings), `directory` (`path`, `sha256`, `bytes`, `count_by_nation`), `districts` (file info), `geocode_failures` (list of `{nation, code, postcode}`), `hours_warnings` (int), `excluded_distance_selling` (int: English pharmacies left out because they are online-only), and `areas` (list of `{code, name, nation, postcodes, pairs, files: {postcodes, travel}}`, where each file entry has `path`, `sha256` and `bytes`).

---

### Task 1: Config, models and HTTP fetcher

**Files:**
- Create: `pipeline/config.toml`, `src/within_reach_pipeline/config.py`, `models.py`, `http.py`
- Modify: `pipeline/pyproject.toml` (add `httpx`, `numpy`, `scipy`)
- Test: `tests/test_config.py`, `tests/test_http.py`

**Interfaces:**
- Produces:
  - `Nation = Literal["England", "Scotland", "Wales"]`
  - `@dataclass(frozen=True) PipelineConfig(radius_m: int, max_candidates: int, min_candidates: int, max_file_bytes: int, count_tolerance: float, geocode_failure_limit: float, osrm_image: str, user_agent: str)`
  - `load_config(path: Path) -> PipelineConfig`
  - `Weekday = Literal["mon","tue","wed","thu","fri","sat","sun"]`
  - `OpeningHours = dict[Weekday, tuple[tuple[str, str], ...] | None]`. `()` means closed; `None` means unknown that day.
  - `@dataclass(frozen=True) Postcode(postcode: str, lat: float, lon: float, east: int, north: int, nation: Nation, area_code: str)`
  - `@dataclass(frozen=True) RawPharmacy(nation: Nation, code: str, name: str, address: tuple[str, ...], postcode: str, hours: OpeningHours | None)`. `hours=None` means the source has no hours.
  - `@dataclass(frozen=True) Pharmacy(raw: RawPharmacy, lat: float, lon: float, east: int, north: int)`
  - `class Fetcher(Protocol)`: `get_json(url: str, params: dict[str, str] | None = None) -> Any`, `download(url: str, dest: Path) -> str` (returns the hex sha256), `get_text(url: str) -> str`
  - `HttpxFetcher(user_agent: str, transport: httpx.BaseTransport | None = None)`

- [ ] **Step 1: Write failing tests.**
  - `test_load_config_defaults` loads the repo's `config.toml` and asserts `radius_m == 5000`, `max_candidates == 40`, `min_candidates == 5`, `max_file_bytes == 25_165_824`, `count_tolerance == 0.10`, `geocode_failure_limit == 0.01`, and that `osrm_image` ends with `:v26.11.0-debian`.
  - `test_download_writes_file_and_returns_sha256` uses `httpx.MockTransport` serving `b"abc"` and asserts the result is `"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"`.
  - `test_fetcher_sends_user_agent` checks that the request header `User-Agent` equals the configured value. That value is `"within-reach-pipeline (+https://withinreach.vasnik.net)"`, with no personal email.
- [ ] **Step 2:** Run `uv run pytest tests/test_config.py tests/test_http.py`. Expected: FAIL (modules missing).
- [ ] **Step 3:** Implement. `load_config` uses `tomllib`. `download` streams to `dest.with_suffix(dest.suffix + ".part")` and renames when complete, hashing as it goes, with timeout 60 s and retries 3. Add the dependencies with `uv add httpx numpy scipy`.
- [ ] **Step 4:** Run the tests and the full Python checks. Expected: PASS.
- [ ] **Step 5: Commit** with message `pipeline: config, models and HTTP fetcher`.

### Task 2: ONSPD reader and area assignment

**Files:**
- Create: `src/within_reach_pipeline/onspd.py`, `tests/fixtures/onspd_sample.csv` (header copied exactly from `ONSPD_AUG_2026_UK.csv`, plus about 12 hand-made rows), `tests/fixtures/onspd_names/` (three small names CSVs in the real formats)
- Test: `tests/test_onspd.py`

**Interfaces:**
- Consumes: `Postcode`, `Nation` (Task 1); `normalise_postcode` (existing)
- Produces:
  - `@dataclass(frozen=True) OnspdColumns(pcds: str, doterm: str, ctry: str, cty: str, lad: str, hlth: str, east: str, north: str, lat: str, lon: str)`
  - `resolve_columns(header: Sequence[str]) -> OnspdColumns`. Matching patterns: `^pcds$`, `^doterm$`, `^ctry\d{2}cd$`, `^cty\d{2}cd$`, `^lad\d{2}cd$`, `^hlth\d{2}cd$`, `^east1m$`, `^north1m$`, `^lat$`, `^long$`. Raises `ValueError` naming any column it can't find.
  - `area_code_for(nation: Nation, cty: str, lad: str, hlth: str) -> str`. England: `cty` unless it is `E99999999`, otherwise `lad`. Scotland: `lad`. Wales: `hlth`.
  - `read_onspd(csv_path: Path) -> Iterator[Postcode]`. Yields live GB postcodes only.
  - `read_area_names(documents_dir: Path) -> dict[str, str]`. Reads files globbed as `LAD Local Authority District names*.csv`, `CTY County names*.csv` and `HLTH health authority names*.csv`. Takes the first column ending `CD` and the first ending `NM`.
  - `ONSPD_COUNTRIES: dict[str, Nation] = {"E92000001": "England", "S92000003": "Scotland", "W92000004": "Wales"}`

- [ ] **Step 1: Write failing tests.**
  - `test_resolve_columns_real_header` checks against the August 2026 header that `lad == "lad26cd"` and `hlth == "hlth19cd"`.
  - `test_resolve_columns_future_suffixes` renames `lad26cd` to `lad27cd` and `ctry26cd` to `ctry27cd`, and checks that it still resolves.
  - `test_resolve_columns_missing_raises` checks that a `ValueError` message contains `"lat"`.
  - `test_read_onspd_filters` uses fixture rows for: a live England postcode `CH1 1AA`; a terminated row (`doterm="202001"`); `BT1 1AA` (ctry `N92000002`); a Jersey row `JE2 3AB` (ctry `L93000001`); a row with `lat=99.999999` (no grid reference); live Scotland `EH1 1YZ`; live Wales `LL11 1AA`. It checks that exactly the three live GB postcodes are yielded, in file order, with their nations.
  - `test_area_code_for` checks: England with `cty="E10000003"` gives `"E10000003"`; England with `cty="E99999999"` and `lad="E06000050"` gives `"E06000050"`; Scotland with `lad="S12000036"` gives `"S12000036"`; Wales with `hlth="W11000023"` gives `"W11000023"`.
  - `test_read_area_names` checks that `{"E06000050": "Cheshire West and Chester", "W11000023": "Betsi Cadwaladr University Health Board"}` is a subset of the result.
- [ ] **Step 2:** Run `uv run pytest tests/test_onspd.py`. Expected: FAIL.
- [ ] **Step 3:** Implement with `csv.DictReader` streaming, which keeps memory flat for the 1.48 GB file, and `utf-8-sig` decoding. Normalise `pcds` with `normalise_postcode` and skip anything that returns `None`.
- [ ] **Step 4:** Run the tests and the checks. Expected: PASS.
- [ ] **Step 5: Commit** with message `pipeline: ONSPD reader and area assignment`.

### Task 3: Pharmacy sources and the merged directory

**Files:**
- Create: `pharmacies/__init__.py`, `pharmacies/hours.py`, `pharmacies/england.py`, `pharmacies/scotland.py`, `pharmacies/wales.py`
- Fixtures: `tests/fixtures/contractor_details_sample.csv` (the real header, with `DISTANCE_SELLING_CONTRACTOR` values `Y`, `N` and blank), `tests/fixtures/nhsbsa_sample.csv` (the real header plus about 8 rows covering `Community`, `DAC` and `LPS`, `CLOSED`, `Closed`, `"09:00-13:00,14:00-17:30"`, `09:00-13:30; 14:30-19:00`, and a garbage value `ASK`), `tests/fixtures/phs_sample.csv` (the real header, `NA` cells, and the double-spaced `G1  2GF`), `tests/fixtures/ods_list.json`, `tests/fixtures/ods_org_FWF56.json`
- Test: `tests/test_hours.py`, `tests/test_pharmacy_sources.py`, `tests/test_directory.py`

**Interfaces:**
- Consumes: `RawPharmacy`, `Pharmacy`, `Postcode`, `OpeningHours`, `Fetcher` (Task 1)
- Produces:
  - `parse_day_hours(value: str) -> tuple[tuple[str, str], ...] | None`. Returns `()` for `closed` in any case, a tuple of `(open, close)` pairs for valid `HH:MM-HH:MM` ranges separated by `,` or `;`, and `None` for anything else.
  - `read_nhsbsa(csv_path: Path) -> tuple[list[RawPharmacy], int]`. Returns the pharmacies and a count of hours warnings. Rows with `CONTRACT_TYPE == "DAC"` are excluded.
  - `read_distance_selling_codes(csv_path: Path) -> frozenset[str]` reads NHSBSA Contractor Details and returns every `CONTRACTOR_CODE` whose `DISTANCE_SELLING_CONTRACTOR` is `Y` (case-insensitive, trimmed). `N` and blank are not excluded.
  - `read_phs(csv_path: Path) -> list[RawPharmacy]`, with `hours=None`.
  - `fetch_ods_wales(fetcher: Fetcher, welsh_postcodes: set[str]) -> list[RawPharmacy]`. Pages through `https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations?PrimaryRoleId=RO182&Status=Active&Limit=1000&Offset=N` and keeps orgs whose normalised `PostCode` is in `welsh_postcodes`. For each one it fetches `OrgLink` to get the address lines (`AddrLn1`, `AddrLn2`, `AddrLn3`, `Town`). Hours are `None`.
  - `@dataclass DirectoryResult(pharmacies: list[Pharmacy], geocode_failures: list[RawPharmacy], hours_warnings: int, excluded_distance_selling: int)`
  - `build_directory(raw: Iterable[RawPharmacy], postcode_index: Mapping[str, Postcode], hours_warnings: int, distance_selling: frozenset[str]) -> DirectoryResult`. First drops English pharmacies whose code is in `distance_selling` and counts them. Then geocodes each pharmacy by its normalised postcode and sorts by `(nation, code)`. If the same `(nation, code)` appears twice, it keeps the first and logs a warning.

- [ ] **Step 1: Write failing tests.**
  - `test_parse_day_hours`:
    - `"CLOSED"` and `"Closed"` give `()`
    - `"09:00-17:00"` gives `(("09:00","17:00"),)`
    - `"09:00-13:00,14:00-17:30"` and `"09:00-13:00; 14:00-17:30"` both give two pairs
    - `"ASK"`, `""` and `"25:00-26:00"` give `None`
  - `test_read_nhsbsa`:
    - the `DAC` row is absent and `LPS` is present
    - the nation is `England` and the code comes from `PHARMACY_ODS_CODE_F_CODE`
    - empty address fields (`" "`) are dropped
    - the `ASK` day becomes `None` and the warnings count is `1`
  - `test_read_phs`: `"NA"` address parts are dropped, the postcode `G1  2GF` is normalised to `G1 2GF`, the code is the `DispCode` string, the nation is `Scotland` and `hours is None`.
  - `test_fetch_ods_wales`: a fake `Fetcher` serves two pages (the second one empty). Only the org whose postcode is in `welsh_postcodes` is returned, with the code `FWF56`, the nation `Wales`, and the address taken from the org JSON.
  - `test_read_distance_selling_codes`: with fixture rows `FAA01=Y`, `FAA02=N`, `FAA03=` (blank) and `FAA04= y `, the result is `frozenset({"FAA01", "FAA04"})`.
  - `test_build_directory_excludes_distance_selling`: England `FAA01` is in the set and absent from `pharmacies`, `excluded_distance_selling == 1`, and a Welsh pharmacy with the same code `FAA01` is kept, because the flag only applies to England.
  - `test_build_directory`: a pharmacy whose postcode is missing from the index goes to `geocode_failures` and isn't in `pharmacies`. The output is sorted with `("England","FA002")` before `("Scotland","1030")` before `("Wales","FWF56")`.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement as specified. For ODS, put 0.1 s between detail calls and use the fetcher's retry.
- [ ] **Step 4:** Run the tests and the checks. Expected: PASS.
- [ ] **Step 5: Commit** with message `pipeline: pharmacy sources mapped into one directory`.

### Task 4: Source discovery and the `fetch` command

**Files:**
- Create: `sources.py`, `cli.py`
- Modify: `__init__.py` (`main()` calls `cli.run(sys.argv[1:])`)
- Test: `tests/test_sources.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `Fetcher`, `PipelineConfig`
- Produces:
  - `@dataclass(frozen=True) SourceRelease(name: str, label: str, url: str)`
  - `latest_nhsbsa(fetcher) -> SourceRelease` uses CKAN `package_show?id=consolidated-pharmaceutical-list` and takes the CSV resource with the latest `created`, using its `name` as the label.
  - `latest_phs(fetcher) -> SourceRelease` uses CKAN `package_show?id=dispenser-location-contact-details`, the same way.
  - `latest_contractor_details(fetcher) -> SourceRelease` uses CKAN `package_show?id=contractor-details`, the same way (for example `CONTRACTOR_DETAILS_202610`).
  - `latest_onspd(fetcher) -> SourceRelease` uses the ArcGIS search `q=title:"ONS Postcode Directory" AND owner:ONSGeography_data AND type:"CSV Collection"`. It excludes titles containing `User Guide`, takes the newest `modified`, and the URL is `https://www.arcgis.com/sharing/rest/content/items/{id}/data`.
  - `OSM_UK_URL = "https://download.geofabrik.de/europe/united-kingdom-latest.osm.pbf"`
  - `cli.run(argv: list[str]) -> int` with these subcommands:
    - `fetch --cache DIR` downloads everything and writes `DIR/sources.json`, a list of `{name, label, url, sha256}`. After unzipping ONSPD, it also runs `fetch_ods_wales` once and saves `DIR/ods_wales.json` (sha256 recorded under `ods_wales`). Every build shard then reads the same Welsh list, so pharmacy indexes match across shards.
    - `build` (Task 8)
    - `check` (Task 9)

- [ ] **Step 1: Write failing tests.** These use recorded JSON fixtures trimmed from the live APIs.
  - `test_latest_nhsbsa` gives label `CONSOL_PHARMACY_LIST_202627Q2`.
  - `test_latest_phs` gives label `Dispenser Details - August 2026`.
  - `test_latest_contractor_details` gives label `CONTRACTOR_DETAILS_202610`.
  - `test_latest_onspd` gives the item `9e5a92a3cfb14dc7ad43d6ea7a7b8c7f` and the label `ONS Postcode Directory (August 2026)`.
  - `test_cli_fetch_writes_sources_json` uses a fake fetcher and checks the keys of `sources.json`, including the `ods_wales` entry, and that `ods_wales.json` exists.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement. `fetch` unzips ONSPD into `DIR/onspd/`, keeping only `Data/*_UK.csv` and `Documents/*.csv`.
- [ ] **Step 4:** Run the tests and the checks. Expected: PASS.
- [ ] **Step 5: Commit** with message `pipeline: source discovery and fetch command`.

### Task 5: Candidate selection

**Files:**
- Create: `candidates.py`
- Test: `tests/test_candidates.py`

**Interfaces:**
- Consumes: `Postcode`, `Pharmacy`, `PipelineConfig`
- Produces:
  - `@dataclass(frozen=True) Candidate(ph_idx: int, straight_m: int)`
  - `select_candidates(postcodes: Sequence[Postcode], pharmacies: Sequence[Pharmacy], radius_m: int, max_candidates: int, min_candidates: int) -> list[list[Candidate]]`. Returns one list per postcode, sorted by `(straight_m, nation, code)`. `ph_idx` is the index into `pharmacies`, which is already in `(nation, code)` order.

Rule: take every pharmacy within `radius_m`, capped at `max_candidates`. If that gives fewer than `min_candidates`, pad up to `min_candidates` with the nearest pharmacies at any distance. Distance is Euclidean on British National Grid metres (`east`, `north`), rounded to whole metres. Use `scipy.spatial.cKDTree.query(k=max_candidates, distance_upper_bound=radius_m)`, then `query(k=min_candidates)` for postcodes that come back short.

- [ ] **Step 1: Write failing tests.** Use synthetic coordinates.
  - `test_within_radius_sorted`: pharmacies at 100, 300 and 6000 m give `ph_idx` values in order 100, 300, then padding brings in the 6000 m one, because `min_candidates=3`.
  - `test_cap_at_max`: 50 pharmacies within radius give 40 results.
  - `test_remote_postcode_gets_min_five`: the nearest pharmacy is 30 km away, and the result has length 5 with every `straight_m > 5000`.
  - `test_tie_break_nation_then_code`: two pharmacies at an identical distance come out as `("England","FZZ99")` before `("Scotland","1001")`, and two English ones sort by code.
  - `test_fewer_pharmacies_than_min`: with only 2 pharmacies in total, the result has length 2 and doesn't crash.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement as specified above.
- [ ] **Step 4:** Run the tests and the checks. Expected: PASS.
- [ ] **Step 5: Commit** with message `pipeline: candidate selection with radius, cap and minimum`.

### Task 6: Routing interface, tiling, fake router

**Files:**
- Create: `routing/__init__.py`, `routing/fake.py`
- Test: `tests/test_routing.py`

**Interfaces:**
- Consumes: `Postcode`, `Pharmacy`, `Candidate`
- Produces:
  - `LatLon = tuple[float, float]`
  - `@dataclass(frozen=True) TableResult(distances_m: list[list[int | None]], durations_s: list[list[int | None]])`
  - `class Router(Protocol)`: `table(sources: Sequence[LatLon], destinations: Sequence[LatLon]) -> TableResult`
  - `@dataclass(frozen=True) TravelRow(pc_idx: int, ph_idx: int, straight_m: int, walk_m: int | None, walk_s: int | None, drive_s: int | None)`
  - `route_candidates(postcodes: Sequence[Postcode], pharmacies: Sequence[Pharmacy], candidates: Sequence[list[Candidate]], walk: Router, drive: Router, tile_m: int = 2000, max_sources: int = 250) -> list[TravelRow]`. Returns rows ordered by `pc_idx`, then candidate order.
  - `FakeRouter(speed_m_s: float, detour: float = 1.3, unreachable: set[LatLon] = set())`. Distance is straight-line × `detour`. Duration is distance ÷ speed. `None` for destinations in `unreachable`.

Tiling: group postcodes by `(east // tile_m, north // tile_m)` and split any group larger than `max_sources`. For each group, the destinations are the sorted union of its candidates' `ph_idx` values. Make one `table` call per router per group.

- [ ] **Step 1: Write failing tests.**
  - `test_route_candidates_uses_fake_values`: for straight 1000 m, walking at speed 1.4 gives `walk_m == 1300` and `walk_s == 929`, and driving at speed 13.4 gives `drive_s == 97`.
  - `test_unreachable_leaves_blanks`: the row exists, with `walk_m is None`, `walk_s is None` and `straight_m` set.
  - `test_tiling_calls_per_tile`: a counting router sees 3 postcodes in 2 tiles as 2 calls per router.
  - `test_order_preserved` checks the order is `pc_idx` ascending, then candidate order.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement. Rounding is half-up to an integer.
- [ ] **Step 4:** Run the tests and the checks. Expected: PASS.
- [ ] **Step 5: Commit** with message `pipeline: routing interface, tiling and fake router`.

### Task 7: OSRM router and extract clipping

**Files:**
- Create: `routing/osrm.py`
- Test: `tests/test_osrm.py` (marked `@pytest.mark.osrm`, skipped unless `RUN_OSRM=1`); `tests/test_osrm_unit.py` (pure)
- Modify: `pyproject.toml` (register the `osrm` marker)

**Interfaces:**
- Consumes: `Router`, `TableResult`, `LatLon`
- Produces:
  - `clip_extract(src_pbf: Path, bbox: tuple[float, float, float, float], dest: Path) -> Path` runs `osmium extract --strategy smart -b minlon,minlat,maxlon,maxlat src -o dest --overwrite`.
  - `area_bbox(points: Iterable[LatLon], margin_m: int = 3000) -> tuple[float, float, float, float]`
  - `osrm_server(pbf: Path, profile: Literal["foot", "car"], image: str, port: int) -> ContextManager[str]` runs `osrm-extract -p /opt/{profile}.lua`, then `osrm-partition` and `osrm-customize`, then `osrm-routed --algorithm mld --max-table-size 1000` in Docker. It yields the base URL and stops the container on exit.
  - `OsrmRouter(base_url: str, fetcher: Fetcher)` calls `GET /table/v1/{profile}/{lon,lat;...}?sources=..&destinations=..&annotations=distance,duration`. Null cells become `None`, and values are rounded to integers.

- [ ] **Step 1: Write failing tests.**
  - Unit test `test_osrm_url_format`: two sources and one destination give the path `/table/v1/foot/-2.89,53.19;-2.88,53.20;-3.0,53.05` with query `sources=0;1&destinations=2&annotations=distance,duration`.
  - Unit test `test_osrm_nulls_become_none`.
  - Unit test `test_area_bbox_margin`: a margin of 3000 m widens the latitude by about 0.027°.
  - Integration test `test_osrm_rutland_end_to_end`: Geofabrik `england/rutland-latest.osm.pbf`, the foot profile, from Oakham `LE15 6AA` to Uppingham `LE15 9TU` gives `walk_m` between 9,000 and 14,000.
- [ ] **Step 2:** Run the unit tests. Expected: FAIL.
- [ ] **Step 3:** Implement. Docker runs with `--rm`, the data directory mounted read-write, and a container name suffixed with the profile.
- [ ] **Step 4:** Run the unit tests and the checks. Expected: PASS. Then run `RUN_OSRM=1 uv run pytest -m osrm` locally (Docker must be running). Expected: PASS.
- [ ] **Step 5: Commit** with message `pipeline: OSRM router and extract clipping`.

### Task 8: Bundle writer and the `build` command

**Files:**
- Create: `bundle.py`, `docs/data-format.md` (the release layout above, written for readers)
- Modify: `cli.py` (`build`)
- Test: `tests/test_bundle.py`, `tests/test_build_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 1–7
- Produces:
  - `@dataclass(frozen=True) FileInfo(path: str, sha256: str, bytes: int)`
  - `write_directory(out: Path, pharmacies: Sequence[Pharmacy]) -> FileInfo`
  - `write_area(out: Path, area_code: str, postcodes: Sequence[Postcode], rows: Sequence[TravelRow]) -> tuple[FileInfo, FileInfo]`
  - `write_district_index(out: Path, postcodes: Iterable[Postcode]) -> FileInfo`
  - `write_manifest(out: Path, manifest: dict[str, Any]) -> FileInfo`
  - `cli build --cache DIR --release YYYY-MM --out DIR [--areas CODE ...] [--router osrm|fake]`. This builds the directory from all of GB (Welsh pharmacies come from `ods_wales.json`, never fetched live), then for each area: its postcodes, their candidates, then routing and writing. `--areas` limits which areas are built, and `--areas` with no codes writes only the directory, district index and manifest. The directory and district index always cover all of GB.
  - `merge_manifests(base: dict[str, Any], shards: Sequence[dict[str, Any]]) -> dict[str, Any]` concatenates `areas` sorted by code. It raises `ValueError` if any shard's `directory.sha256` differs from the base's.
  - `cli merge --out DIR SHARD_DIR ...` copies each shard's `areas/` into `DIR` and rewrites `DIR/manifest.json` using `merge_manifests`.

Gzip uses `mtime=0` and `compresslevel=9` so that rebuilding identical input gives byte-identical files (NFR-11). Paths in `FileInfo` are relative to `out`.

- [ ] **Step 1: Write failing tests.**
  - `test_write_area_roundtrip`: the gunzipped CSV headers are exactly `pc_idx,postcode,lat,lon` and `pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s`, and a `None` value is written as an empty cell.
  - `test_directory_hours_cells`: `None` hours give 7 empty cells; `()` gives `CLOSED`; two ranges give `09:00-13:00;14:00-17:30`.
  - `test_gzip_deterministic`: writing twice gives identical sha256.
  - `test_district_index`: `CH1 1AA` (`E06000050`) and `CH5 1AA` (`W11000023`) give the rows `CH1,E06000050` and `CH5,W11000023`.
  - `test_build_cli_fake_router`: a fixture cache with 6 postcodes in 2 areas and 4 pharmacies gives a manifest with 2 areas, every file's sha256 matching the file on disk, and `"OpenStreetMap"` in one of the attribution entries.
  - `test_merge_shards`: building each of the 2 areas as its own shard, then running `merge`, gives a manifest whose `areas` and `directory` equal the single-build manifest (ignoring `built_at`).
  - `test_merge_rejects_directory_mismatch`: a shard with a different `directory.sha256` raises `ValueError`.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement. Area names come from `read_area_names`, falling back to the code itself when a name is missing.
- [ ] **Step 4:** Run the tests and the checks. Expected: PASS.
- [ ] **Step 5: Commit** with message `pipeline: bundle writer and build command`.

### Task 9: Release checks and the `check` command (FR-04)

**Files:**
- Create: `checks.py`
- Modify: `cli.py` (`check --release-dir DIR [--previous-dir DIR] [--reference FILE]`, which exits 1 on any failure)
- Test: `tests/test_checks.py`

**Interfaces:**
- Consumes: the manifest and files from Task 8, `PipelineConfig`
- Produces:
  - `@dataclass(frozen=True) CheckFailure(check: str, detail: str)`
  - `run_checks(release_dir: Path, config: PipelineConfig, previous_dir: Path | None, reference: Path | None) -> list[CheckFailure]`

The checks:
- `checksums`: every manifest file exists, and its sha256 and size match.
- `size`: every file is at most `max_file_bytes`.
- `no_bt`: no postcode in any `postcodes.csv.gz`, `pharmacies.csv.gz` or `districts.csv.gz` starts with `BT`.
- `nations`: all three nations have pharmacies, and every area has more than 0 postcodes and more than 0 pairs.
- `min_candidates`: every postcode has at least `min(min_candidates, directory size)` travel rows.
- `geocode`: for each nation, failures ÷ (failures + pharmacies) is at most `geocode_failure_limit`.
- `distance_selling`: `excluded_distance_selling` is between 200 and 1,000. Last checked October 2026: 471 matched. A count outside that range means the Contractor Details format changed.
- `counts`: when a previous release exists, the count per nation and the total postcodes are within `count_tolerance`.
- `reference`: when `reference` is given, every case in `expectations.toml` passes (format in Task 10).

- [ ] **Step 1: Write failing tests.** Each test builds a valid release using the Task 8 fake-router fixture, then corrupts one thing:
  - `test_valid_release_passes` gives `[]`
  - `test_checksum_mismatch`
  - `test_bt_postcode_detected`
  - `test_oversize_file` (set `max_file_bytes` to 10)
  - `test_count_drop_over_tolerance` (the previous manifest has twice the England count)
  - `test_geocode_failures_over_limit`
  - `test_postcode_short_of_candidates`
  - `test_distance_selling_count_out_of_range` (set the manifest value to `0`)

  Each of these asserts exactly one failure, with the matching `check` name.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the tests and the checks. Expected: PASS.
- [ ] **Step 5: Commit** with message `pipeline: release checks (FR-04)`.

### Task 10: Reference area run and hand-checked expectations

**Files:**
- Create: `pipeline/reference/expectations.toml`, `pipeline/reference/README.md` (how each case was checked)
- Test: the `reference` check from Task 9, run on real output

**Interfaces:**
- Consumes: `cli fetch`, `cli build --router osrm`, `cli check --reference`
- Produces: `expectations.toml` cases in this format:
  `[[case]] postcode = "CH1 1AA"`, `nearest = ["England:FXX00", ...]` (the first N codes, in order), `walk_m_range = [min, max]` for the first.

The reference areas are Cheshire West and Chester (`E06000050`) and Betsi Cadwaladr (`W11000023`), which cover the England–Wales border (R14).

- [ ] **Step 1:** Run `uv run within-reach-pipeline fetch --cache .cache`. Expected: `sources.json` lists 6 sources (`onspd`, `nhsbsa`, `contractor_details`, `phs`, `osm`, `ods_wales`), and `ods_wales.json` holds several hundred Welsh pharmacies.
- [ ] **Step 2:** Run `uv run within-reach-pipeline build --cache .cache --release 2026-11 --out build/2026-11 --areas E06000050 W11000023 --router osrm`. Expected: both areas are written and every file is under 24 MiB.
- [ ] **Step 3:** Pick 10 postcodes: 4 in Chester, 2 near the border (for example `CH4`), 2 in Wrexham and 2 rural. For each, the user checks the top 3 pharmacies and the first walking distance on a map (OpenStreetMap routing), then records the results in `expectations.toml` with a ±15% walking range.
- [ ] **Step 4:** Run `uv run within-reach-pipeline check --release-dir build/2026-11 --reference reference/expectations.toml`. Expected: exit 0. Then test that the check can fail: deliberately edit one expected code. Expected: exit 1 with a `reference` failure. Revert the edit.
- [ ] **Step 5: Commit** with message `pipeline: reference expectations for Chester and North Wales`. Commit only `reference/`; `.cache/` and `build/` are git-ignored, so add `pipeline/.cache/` to `.gitignore`.

### Task 11: Monthly workflow, publishing and rollback (FR-01, FR-04, FR-05)

**Files:**
- Create: `.github/workflows/pipeline.yml`
- Modify: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: `cli fetch`, `cli build`, `cli check`
- Produces:
  - GitHub Releases tagged `data-YYYY-MM`, each with the asset `data-YYYY-MM.tar.gz`, which unpacks to `<release>/...`
  - `dist/data/latest.json` and `dist/data/<release>/`, plus the previous release, in every deploy

`pipeline.yml`:
- **Triggers:** `schedule: cron "0 3 2 * *"` (the 2nd of each month), and `workflow_dispatch` with inputs `areas` (space-separated; empty means all) and `release` (defaults to the current `YYYY-MM`).
- **`prepare` job:** runs `fetch` and caches `.cache/` (key: the source labels, read from `sources.json`). It outputs the area list as JSON shards of about 10 areas each.
- **`build` job:** a matrix over the shards. It installs `osmium-tool` with `apt` and needs Docker. It runs `build --areas <shard>` and uploads the shard as an artifact with `retention-days: 1`.
- **`assemble` job:**
  - runs `build --areas` with no codes (directory, district index and base manifest only), then `merge --out` over the downloaded shards
  - downloads the previous release with `gh release download`, then runs `check --previous-dir --reference`
  - on success, runs `gh release create data-YYYY-MM`
  - on failure, nothing is published (AC-14), and `gh issue create --title "Data pipeline failed: <release>" --label pipeline` opens an alert issue
- **Permissions:** `contents: write` only in `assemble`, and `issues: write` only in its failure step. Every other job gets `contents: read`.
- **Keep the schedule alive:** GitHub turns off scheduled workflows in public repos after 60 days with no repository activity. Add a step to `assemble` that, on success, commits the new release tag and date to `data/RELEASES.md` on `main` (with `contents: write`, which is already granted there). That counts as activity, and it also gives a readable history of releases.
- **Until the repo is public**, scheduled runs build only the reference areas (`E06000050 W11000023`), because private-repo Actions storage is limited to 500 MB. Flip the default when the repo goes public at the Phase 0 gate.

`deploy.yml`: before `pages deploy`, add a step that finds the two newest `data-*` releases with `gh release list`, downloads and unpacks them into `app/dist/data/`, and writes `latest.json`. Rolling back means re-running the deploy with the input `data_release=<older tag>` (add this `workflow_dispatch` input). If no data release exists yet, the step skips and the deploy continues.

- [ ] **Step 1:** Write both workflows. Run `uvx --from actionlint-py actionlint`. Expected: exit 0.
- [ ] **Step 2:** Push, then run `gh workflow run pipeline.yml -f areas="E06000050 W11000023"`. Expected: the run is green and the release `data-2026-11` exists (`gh release view data-2026-11`).
- [ ] **Step 3:** Check the failure path: dispatch with `areas="E06000050"` and a temporary `count_tolerance = 0.0` in `config.toml` on a branch. Expected: nothing is published and an alert issue is opened. Delete the branch, the issue and any partial release.
- [ ] **Step 4:** If `DEPLOY_ENABLED` is set, run the deploy and check `https://preview.within-reach.pages.dev/data/latest.json`. Otherwise run the merge step locally against `gh release download` and inspect `app/dist/data/`.
- [ ] **Step 5: Commit** with message `ci: monthly data pipeline, publishing and rollback`.

### Task 12: Show the data release date in the app (FR-05)

**Files:**
- Create: `app/src/lib/data/release.ts`, `app/src/lib/data/release.test.ts`
- Modify: `app/src/lib/ui/Placeholder.svelte`, `app/tests/e2e/placeholder.spec.ts`

**Interfaces:**
- Produces:
  - `type ReleaseInfo = { release: string; builtAt: string }`
  - `parseRelease(latest: unknown, manifest: unknown): ReleaseInfo | null` (pure; returns `null` on any malformed input)
  - `loadRelease(fetchFn: typeof fetch = fetch): Promise<ReleaseInfo | null>` fetches `/data/latest.json`, then `/data/<release>/manifest.json`, and returns `null` on 404 or any error.

- [ ] **Step 1: Write failing tests.**
  - Vitest:
    - `parseRelease({release:"2026-11"}, {release:"2026-11", built_at:"2026-11-02T03:00:00Z"})` gives `{release:"2026-11", builtAt:"2026-11-02T03:00:00Z"}`
    - a release name that doesn't match `^\d{4}-\d{2}$` gives `null`
    - a mismatch between `latest` and the manifest's `release` gives `null`
  - Playwright `data release date is shown`: use `page.route` to serve the two JSON files, then expect the text `Data release: November 2026` (formatted with `en-GB` month and year).
  - Playwright `no data release shows nothing`: when the files return 404, the text `Data release` is absent and the page still passes the privacy guard.
- [ ] **Step 2:** Run `npm test` and `npm run test:e2e`. Expected: FAIL.
- [ ] **Step 3:** Implement. The release name is only used in a same-origin path after passing the regex, so no user input reaches a URL.
- [ ] **Step 4:** Run `npm run lint && npm run check && npm test && npm run test:e2e`. Expected: PASS.
- [ ] **Step 5: Commit** with message `app: show data release date (FR-05)`.

---

## Spec coverage

| Requirement | Tasks |
|---|---|
| FR-01: scheduled and on-demand runs, sources, release dates, one directory format | 3, 4, 11 |
| FR-02: per-area walking and driving, catchment, border buffer | 2, 5, 6, 7, 8. The buffer comes from candidates being chosen from all GB pharmacies |
| FR-03: bundles, directory, manifest, size limit | 8 |
| FR-04: checks, stop on failure, alert | 9, 10, 11 |
| FR-05: rollback, show release date | 11, 12 |
| NFR-09: fits the free runner | 7, 11 (per-area clipped extracts, sharded matrix) |
| NFR-11: deterministic output | 5, 8 |
| NFR-16: attribution | 8 |
| D15: Welsh licence | 3. ODS (OGL) replaces NWSSP; record this in `docs/decisions.md` and spec 0.6 |

## Known limitations to record (spec issues section)

- **Online-only pharmacies:** English distance-selling pharmacies are excluded using NHSBSA Contractor Details (478 flagged and 471 matched in October 2026). Welsh rows in that file have a blank flag, so Welsh online pharmacies (very few) can't be identified, and services exclude them through their approved list. Scotland has no distance-selling contract type.
- **Pharmacy location precision:** pharmacy coordinates are their postcode's centroid, the same precision as client postcodes (A6).
- **Name lookups lag behind:** ONSPD's names files lag its codes by up to a year. An area with no name falls back to showing its code.

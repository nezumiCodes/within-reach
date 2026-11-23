# UK Walking Rules and Reachable Pharmacies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Walking routes may use unsigned cycle paths, bridleways and trunk roads with a pavement, and results say when a walk needs an unsigned cycle path. Postcodes whose nearest pharmacies can't be reached get further pharmacies that can.

**Architecture:**
- **Walking rules:** a Lua wrapper profile adds the UK rules on top of OSRM's stock walking rules, and puts unsigned cycle paths in an excludable OSRM class. Routing asks the walking graph twice per batch, the second time excluding that class, and sets a `walk_cycle` flag on each travel row.
- **Widening:** after the first routing pass, a new module adds and routes further candidates for postcodes with fewer than 5 reachable pharmacies, then drops unreachable rows.
- **Data and app:** the travel file gains a `walk_cycle` column. The app reads both the old and the new layout and shows the note.

**Tech Stack:** Python 3.12 (uv, ruff, mypy strict, pytest), OSRM v26.11.0 Lua profiles, Docker, Svelte 5 + TypeScript (Vitest, Playwright).

**Spec:** `docs/superpowers/specs/2026-11-22-walking-rules-and-reachable-pharmacies-design.md`

## Global Constraints

- Work on branch `walking-rules-and-reach`. Commit as `109743126+nezumiCodes@users.noreply.github.com`, with no AI attribution lines in commits or PR text.
- Stock profile used unchanged: `foot-gb.lua` loads `/opt/foot.lua` and must not copy it.
- Cycle path class: `highway=cycleway` with no `foot` of `yes`, `designated` or `permissive`. Class name `cycleway`.
- Trunk rule: `trunk` and `trunk_link` are walkable only if one of `sidewalk`, `sidewalk:both`, `sidewalk:left` or `sidewalk:right` is `both`, `left`, `right` or `yes`, or `foot` is `yes`, `designated` or `permissive`.
- The driving graph keeps `/opt/car.lua`.
- New config values (`pipeline/config.toml`, `[catchment]`):
  - `reach_cap_m = 25000`
  - `reach_max_rounds = 4`
  - `cycle_note_min_extra_m = 50`
- `walk_cycle` is true only when there is a walking route, and the route without unsigned cycle paths is missing or more than 50 m longer.
- Widening triggers when fewer than `min_candidates` (5) rows have a walking or a driving route. It only considers pharmacies inside the area's extract bounding box and within 25,000 m in a straight line. It runs at most 4 rounds. It never routes the same pair twice, and keeps at most `max_candidates` (40) rows.
- Final rows: if any row is reachable, drop the unreachable rows. If none is, keep the original first-pass rows. Sort by `(straight_m, ph_idx)`.
- Travel header: `pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s,walk_cycle`, where `walk_cycle` is `1` or blank.
- Manifest `config` gains:
  - `"walk_profile": "foot-gb"`
  - `"reach_cap_m": 25000`
  - `"reach_max_rounds": 4`
  - `"cycle_note_min_extra_m": 50`
- Each manifest area entry gains `"postcodes_without_route"` and `"postcodes_widened_to_cap"`.
- App wording, exactly: `1.4 km · 18 min walk, partly on a cycle path · 5 min drive`. The note goes after "walk" and before " · ".
- The app must read both the 6-column and the 7-column travel header, and reject any other header.
- Release order: v0.2.0 must be tagged before any data run, and before the scheduled run on 2 December.

## Review Focus

1. **The route without cycle paths is shorter than the normal route.** This can happen when the start point snaps to a different way. `walk_cycle` must be false, never negative or true. Test in Task 2.
2. **A pharmacy chosen in round 1 comes back in a later round.** It must never be duplicated or routed twice. Test in Task 3.
3. **Widening on a dense postcode already near 40 rows.** The final rows must never exceed `max_candidates`. Test in Task 3.
4. **Data from before this change (6 columns) after the new app deploys.** It must still load, with no notes. Test in Task 5.
5. **A trunk road with `sidewalk=no` but `foot=designated`.** It must be walkable, because the foot tag wins. Test in Task 1.

---

### Task 1: UK walking profile, mounted into OSRM, with exclude support

**Files:**
- Create: `pipeline/osrm/foot-gb.lua`
- Create: `pipeline/tests/fixtures/osm/walk_rules.osm`
- Modify: `pipeline/src/within_reach_pipeline/routing/osrm.py` (`osrm_server`, `OsrmRouter.table`)
- Modify: `pipeline/src/within_reach_pipeline/build.py` (manifest `config`)
- Test: `pipeline/tests/test_osrm_unit.py`, `pipeline/tests/test_osrm.py`, `pipeline/tests/test_build_cli.py`

**Interfaces:**
- Produces:
  - `PROFILE_DIR: Path` in `routing/osrm.py`, which is `Path(__file__).resolve().parents[3] / "osrm"`.
  - `WALK_PROFILE = "foot-gb"`.
  - `extract_command(workdir: Path, profile: Profile, image: str) -> list[str]`: the docker command for `osrm-extract`.
  - `OsrmRouter.table(sources, destinations, exclude: str | None = None) -> TableResult`.
  - The manifest `config["walk_profile"] == "foot-gb"`.

- [ ] **Step 1: Write the failing unit tests** in `test_osrm_unit.py`:

```python
def test_extract_command_mounts_profiles_and_uses_foot_gb(tmp_path: Path) -> None:
    cmd = extract_command(tmp_path, "foot", "img:1")
    assert f"{PROFILE_DIR}:/profiles:ro" in cmd
    assert cmd[-3:] == ["-p", "/profiles/foot-gb.lua", "/data/area.osm.pbf"]

def test_extract_command_car_keeps_stock_profile(tmp_path: Path) -> None:
    assert extract_command(tmp_path, "car", "img:1")[-3:] == ["-p", "/opt/car.lua", "/data/area.osm.pbf"]

def test_profile_file_exists() -> None:
    assert (PROFILE_DIR / "foot-gb.lua").is_file()

def test_table_exclude_in_url() -> None:
    # same stub fetcher as test_osrm_url_format
    router.table([(53.0, -2.9)], [(53.1, -2.9)], exclude="cycleway")
    assert fetcher.urls[-1].endswith("&annotations=distance,duration&exclude=cycleway")

def test_table_without_exclude_has_no_param() -> None:
    assert "exclude" not in fetcher.urls[-1]
```

In `test_build_cli.py`, in the existing fake-router build test, add `assert manifest["config"]["walk_profile"] == "foot-gb"`.

- [ ] **Step 2: Run them and watch them fail**

Run: `cd pipeline && uv run pytest tests/test_osrm_unit.py tests/test_build_cli.py -q`
Expected: FAIL (`extract_command`/`PROFILE_DIR` not defined, `exclude` unexpected keyword, missing `walk_profile`).

- [ ] **Step 3: Implement**
- Add `extract_command`. `osrm_server` uses it, and also mounts `PROFILE_DIR` read-only for `osrm-partition`, `osrm-customize` and `osrm-routed`. The profile path is `/profiles/foot-gb.lua` for `"foot"` and `/opt/car.lua` for `"car"`. `exclude` appends `&exclude=<value>`.
- `build.py` adds `"walk_profile": WALK_PROFILE` to the manifest `config`.
- Write `pipeline/osrm/foot-gb.lua` with this structure. The stock profile's `require('lib/...')` calls need `/opt` on the Lua path, because OSRM sets the path from the wrapper's own directory:

```lua
-- UK walking rules (docs/superpowers/specs/2026-11-22-walking-rules-and-reachable-pharmacies-design.md):
-- OSRM's stock foot.lua, unchanged, plus unsigned cycle paths (excludable class "cycleway"),
-- bridleways, and trunk roads only where a pavement or foot access is tagged.
api_version = 4
package.path = '/opt/?.lua;' .. package.path
local stock = dofile('/opt/foot.lua')

local FOOT_OK = Set { 'yes', 'designated', 'permissive' }
local PAVEMENT = Set { 'both', 'left', 'right', 'yes' }
local SIDEWALK_KEYS = { 'sidewalk', 'sidewalk:both', 'sidewalk:left', 'sidewalk:right' }

local function has_pavement(way) ... end   -- any SIDEWALK_KEYS value in PAVEMENT

function setup()
  local profile = stock.setup()
  for _, h in ipairs({ 'cycleway', 'bridleway', 'trunk', 'trunk_link' }) do
    profile.speeds.highway[h] = profile.default_speed
  end
  profile.classes = Sequence { 'cycleway' }
  profile.excludable = Sequence { Set { 'cycleway' } }
  return profile
end

function process_way(profile, way, result, relations)
  local highway, foot = way:get_value_by_key('highway'), way:get_value_by_key('foot')
  if (highway == 'trunk' or highway == 'trunk_link') and not FOOT_OK[foot] and not has_pavement(way) then
    return
  end
  stock.process_way(profile, way, result, relations)
  if highway == 'cycleway' and not FOOT_OK[foot] then
    result.forward_classes['cycleway'] = true
    result.backward_classes['cycleway'] = true
  end
end

return { setup = setup, process_way = process_way, process_node = stock.process_node,
         process_turn = stock.process_turn, process_relation = stock.process_relation }
```

If `profile.speeds.highway` isn't the speed table in this OSRM version (check `/opt/foot.lua`, line 105, `speeds = Sequence { highway = {...} }`), adapt the lookup and record a ruling.

- [ ] **Step 4: Unit tests pass**

Run: `cd pipeline && uv run pytest tests/test_osrm_unit.py tests/test_build_cli.py -q`
Expected: PASS

- [ ] **Step 5: Write the OSM fixture and the Docker integration test**

`tests/fixtures/osm/walk_rules.osm` is hand-written OSM XML near 53.0, -2.9. Keep the ways at least 500 m apart so snapping can't jump between them. Build separate pairs of points, A to B, each joined only by:
1. an untagged `highway=cycleway` (pair `cycle`);
2. `highway=cycleway` with `foot=no` (pair `cycle_no`);
3. `highway=cycleway` with `foot=designated` (pair `cycle_signed`);
4. `highway=bridleway` (pair `bridle`);
5. `highway=trunk` with no sidewalk tags (pair `trunk_bare`);
6. `highway=trunk` with `sidewalk=both` (pair `trunk_pavement`);
7. `highway=trunk` with `sidewalk=no`, `foot=designated` (pair `trunk_foot`);
8. `highway=residential` (pair `street`).

Each pair is about 400 m long, and the points sit on the way's end nodes.

Add a test to `tests/test_osrm.py` (it runs under the existing `RUN_OSRM=1` marker). It builds `osrm_server` from the fixture with a temporary profile switch: walking with `foot-gb`, plus a stock-foot server, via a test-only helper `osrm_server(..., profile_path=...)` or by calling `extract_command` with stock. Pick one and record a ruling. Assert:

```python
assert walk("cycle") is not None and stock("cycle") is None and walk("cycle", exclude="cycleway") is None
assert walk("cycle_no") is None
assert walk("cycle_signed") is not None and walk("cycle_signed", exclude="cycleway") is not None
assert walk("bridle") is not None
assert walk("trunk_bare") is None
assert walk("trunk_pavement") is not None
assert walk("trunk_foot") is not None
assert walk("street") == stock("street")
```

Here `walk(pair, exclude=None)` returns the table distance from A to B on the `foot-gb` server, and `stock(pair)` the same on the stock server.

- [ ] **Step 6: Run the integration test**

Run: `cd pipeline && RUN_OSRM=1 uv run pytest tests/test_osrm.py -q -k walk_rules`
Expected: PASS. (It fails first if run before Step 3's Lua exists; it was written after, so record in the ledger that its RED was the stock-profile half of each assertion.)

- [ ] **Step 7: Lint, type-check, commit**

Run: `cd pipeline && uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: clean.

```bash
git add pipeline/osrm pipeline/src/within_reach_pipeline/routing/osrm.py pipeline/src/within_reach_pipeline/build.py pipeline/tests
git commit -m "pipeline: UK walking profile (unsigned cycle paths, bridleways, trunk roads with a pavement)"
```

---

### Task 2: `walk_cycle` flag in routing

**Files:**
- Modify: `pipeline/src/within_reach_pipeline/routing/__init__.py` (`Router`, `TravelRow`, `route_candidates`)
- Modify: `pipeline/src/within_reach_pipeline/routing/fake.py` (`FakeRouter`)
- Modify: `pipeline/src/within_reach_pipeline/config.py`, `pipeline/config.toml`
- Test: `pipeline/tests/test_routing.py`, `pipeline/tests/test_config.py`

**Interfaces:**
- Consumes: `OsrmRouter.table(..., exclude=...)` from Task 1.
- Produces:
  - `Router.table(sources, destinations, exclude: str | None = None) -> TableResult`.
  - `TravelRow.walk_cycle: bool = False`, as the last field.
  - `route_candidates(postcodes, pharmacies, candidates, walk, drive, cycle_min_extra_m: int = 50, tile_m=2000, max_sources=250) -> list[TravelRow]`.
  - `FakeRouter(speed_m_s, detour=1.3, unreachable=None, cycle_only: set[LatLon] | None = None, cycle_extra_m: int = 0)`. With `exclude="cycleway"`, targets in `cycle_only` return `None`, and other targets return `distance + cycle_extra_m`.
  - `PipelineConfig.cycle_note_min_extra_m: int`, `reach_cap_m: int`, `reach_max_rounds: int`. All three are loaded here, so Task 3 needs no config change.

- [ ] **Step 1: Write the failing tests**

```python
def test_walk_cycle_set_when_only_cycle_path_reaches() -> None:
    target = (53.0 + ONE_KM_LAT, -2.89)
    walk = FakeRouter(1.4, cycle_only={target})
    [row] = route_candidates([_postcode("CH1 1AA", 53.0, 400000)], [_pharmacy("FA001", target[0])],
                             [[Candidate(0, 1000)]], walk, DRIVE)
    assert row.walk_m == 1300 and row.walk_cycle is True

def test_walk_cycle_needs_more_than_threshold() -> None:
    # cycle_extra_m=50: excluded route is exactly 50 m longer, so no note; 51 m: note
    assert _one_row(FakeRouter(1.4, cycle_extra_m=50)).walk_cycle is False
    assert _one_row(FakeRouter(1.4, cycle_extra_m=51)).walk_cycle is True

def test_walk_cycle_false_when_excluded_route_is_shorter() -> None:
    assert _one_row(FakeRouter(1.4, cycle_extra_m=-30)).walk_cycle is False   # Review Focus 1

def test_walk_cycle_false_without_walk_route() -> None:
    target = (53.0 + ONE_KM_LAT, -2.89)
    assert _one_row(FakeRouter(1.4, unreachable={target})).walk_cycle is False

def test_walk_router_called_twice_per_tile_drive_once() -> None:
    # counting wrapper around FakeRouter: walk sees exclude=None then "cycleway"; drive sees only None

def test_cycle_and_reach_settings_load() -> None:   # test_config.py
    config = load_config(CONFIG)
    assert (config.cycle_note_min_extra_m, config.reach_cap_m, config.reach_max_rounds) == (50, 25000, 4)
```

`_one_row(walk)` is a local helper: one postcode, one pharmacy 1 km north, `DRIVE`. The existing `test_route_candidates_uses_router_values` must still pass unchanged, because `walk_cycle` defaults to False.

- [ ] **Step 2: Run, watch them fail**

Run: `cd pipeline && uv run pytest tests/test_routing.py tests/test_config.py -q`
Expected: FAIL (unexpected keyword `cycle_only`, no attribute `walk_cycle`, missing config keys).

- [ ] **Step 3: Implement**
- `route_candidates` calls `walk.table(sources, targets)` and `walk.table(sources, targets, exclude="cycleway")`.
- `walk_cycle = walk_m is not None and (excluded is None or excluded - walk_m > cycle_min_extra_m)`.
- Add the three keys to `[catchment]` in `config.toml`, with one comment each citing the design doc.

- [ ] **Step 4: Pass**

Run: `cd pipeline && uv run pytest -q`
Expected: PASS (whole pipeline suite).

- [ ] **Step 5: Commit**

```bash
git commit -am "pipeline: flag walking routes that need an unsigned cycle path"
```

---

### Task 3: Widen candidates until pharmacies are reachable

**Files:**
- Modify: `pipeline/src/within_reach_pipeline/candidates.py` (add `next_candidates`)
- Create: `pipeline/src/within_reach_pipeline/reach.py`
- Modify: `pipeline/src/within_reach_pipeline/build.py` (use it, plus the new area fields and manifest config)
- Test: `pipeline/tests/test_candidates.py`, `pipeline/tests/test_reach.py` (new), `pipeline/tests/test_build_cli.py`

**Interfaces:**
- Consumes: `route_candidates` and `TravelRow.walk_cycle` from Task 2; the `PipelineConfig` fields from Task 2.
- Produces:
  - `next_candidates(postcode: Postcode, pharmacies: Sequence[Pharmacy], tree: cKDTree, tried: set[int], allowed: set[int], count: int, cap_m: int) -> list[Candidate]`. It returns the nearest `count` pharmacies by straight line that are in `allowed`, not in `tried`, and within `cap_m`, sorted by `(straight_m, ph_idx)`.
  - `@dataclass(frozen=True) ReachResult(rows: list[TravelRow], widened_to_cap: set[int])`. `widened_to_cap` holds the `pc_idx` values whose widening stopped because nothing more was available within the cap and the bounding box, or because the round limit was hit, while still short.
  - `route_reachable(postcodes, pharmacies, candidates, walk, drive, *, allowed: set[int], min_reachable: int, max_candidates: int, cap_m: int, max_rounds: int, cycle_min_extra_m: int) -> ReachResult`.
  - The manifest `config` gains `reach_cap_m`, `reach_max_rounds` and `cycle_note_min_extra_m`. Area entries gain `postcodes_without_route` and `postcodes_widened_to_cap`.

- [ ] **Step 1: Write the failing tests** (`test_reach.py` uses the `_postcode`/`_pharmacy` helpers from `test_routing.py`; move them to `tests/fakes.py` if they don't import cleanly):

```python
def test_unreachable_nearest_are_replaced_by_reachable_further_ones() -> None:
    # 5 pharmacies at 1-5 km all unreachable (walk+drive), 3 more at 8-10 km reachable
    result = route_reachable(..., min_reachable=5, cap_m=25000, max_rounds=4, ...)
    assert [r.ph_idx for r in result.rows] == [5, 6, 7]          # unreachable ones dropped
    assert result.widened_to_cap == {0}                             # still short: ran out inside cap

def test_cap_stops_widening() -> None:
    # reachable pharmacy at 30 km is never added; postcode keeps original 5 unreachable rows
    assert [r.ph_idx for r in result.rows] == [0, 1, 2, 3, 4] and all(r.walk_m is None for r in result.rows)

def test_outside_allowed_box_never_added() -> None:
    # reachable pharmacy at 8 km not in `allowed` -> not routed

def test_no_pair_routed_twice_or_duplicated() -> None:              # Review Focus 2
    # counting router records (source, target) pairs across rounds; all unique; rows unique by ph_idx

def test_round_limit() -> None:
    # max_rounds=1 with reachable pharmacies only in round 2 -> not reached; pc in widened_to_cap

def test_reachable_postcode_is_untouched() -> None:
    # 5 reachable first-pass rows -> rows equal route_candidates output, router called for one pass only

def test_rows_never_exceed_max_candidates() -> None:                # Review Focus 3
    # 38 first-pass rows, 2 reachable; widening offers 10 more reachable; max_candidates=40
    assert len([r for r in result.rows if r.pc_idx == 0]) <= 40

def test_next_candidates_skips_tried_and_respects_cap() -> None:     # test_candidates.py
```

In `test_build_cli.py` (fake router), assert that every area has integer `postcodes_without_route` and `postcodes_widened_to_cap`, and that `config["reach_cap_m"] == 25000`.

- [ ] **Step 2: Run, watch them fail**

Run: `cd pipeline && uv run pytest tests/test_reach.py tests/test_candidates.py tests/test_build_cli.py -q`
Expected: FAIL (`reach` module and `next_candidates` missing).

- [ ] **Step 3: Implement `next_candidates`, then `route_reachable`**

Algorithm (spec section 3):

```
rows = route_candidates(first-pass candidates)
tried[pc] = first-pass ph_idx set
for round in 1..max_rounds:
    short = postcodes with < min_reachable reachable rows (walk_m or drive_s not None)
    if not short: break
    extra = {pc: next_candidates(pc, ..., tried[pc], allowed, count=(shortfall + min_reachable), cap_m)}
    pcs with no extra -> mark exhausted (go to widened_to_cap if still short); drop from further rounds
    route only the extra pairs: route_candidates(postcodes, pharmacies, per-pc lists with only extras, ...)
    add rows; tried[pc] |= extra
after loop: still-short, non-exhausted pcs (round limit) -> widened_to_cap
final per pc: reachable = rows with walk or drive; keep reachable if any else first-pass rows;
              sort (straight_m, ph_idx); truncate to max_candidates
```

`route_candidates` routes every candidate it's given, so pass lists holding only the new pairs (empty lists for other postcodes). It already skips groups with no destinations. A postcode with no reachable row after the loop isn't in `widened_to_cap` if it kept its first-pass list. Make sure the tests show this.

`build.py`:
- `allowed = {i for i, p in enumerate(pharmacies) if inside(bbox, p)}`, where `bbox = area_bbox(points)`, the same box as the extract (expose the box from `_area_extract`, or compute it once and pass it in).
- Call `route_reachable` instead of `route_candidates`.
- `postcodes_without_route` counts postcodes whose final rows have no walk and no drive.
- `postcodes_widened_to_cap = len(result.widened_to_cap)`.
- The area map uses the final rows' pharmacies for its points; the extract stays sized from the first pass.

- [ ] **Step 4: Pass**

Run: `cd pipeline && uv run pytest -q && uv run mypy && uv run ruff check .`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git commit -am "pipeline: widen candidates until pharmacies can be reached, drop unreachable ones"
```

---

### Task 4: Travel file column, release checks, data format docs

**Files:**
- Modify: `pipeline/src/within_reach_pipeline/bundle.py` (`write_area`, and `merge_manifests` if config keys need carrying)
- Modify: `pipeline/src/within_reach_pipeline/checks.py` (`_check_min_candidates`, plus a new `_check_walk_cycle`)
- Modify: `docs/data-format.md`
- Test: `pipeline/tests/test_bundle.py`, `pipeline/tests/test_checks.py`

**Interfaces:**
- Consumes: `TravelRow.walk_cycle` (Task 2); the area fields (Task 3).
- Produces: travel files with the 7-column header; check names `"walk_cycle"` and `"min_candidates"` (the existing name, new rule).

- [ ] **Step 1: Write the failing tests**

```python
def test_travel_file_has_walk_cycle_column(tmp_path) -> None:      # test_bundle.py
    # rows with walk_cycle True/False -> header ends ",walk_cycle"; True -> "1", False -> ""

def test_walk_cycle_without_walk_fails(tmp_path) -> None:           # test_checks.py
    # a travel row with walk_m blank and walk_cycle "1" -> CheckFailure("walk_cycle", ...)

def test_min_candidates_passes_short_postcode_widened_to_cap() -> None:
    # 3 rows all reachable, area postcodes_widened_to_cap=1 -> no failure

def test_min_candidates_fails_short_postcode_with_unreachable_rows() -> None:
    # 3 rows, one with no walk and no drive -> failure

def test_min_candidates_fails_more_short_reachable_than_widened() -> None:
    # two short all-reachable postcodes, postcodes_widened_to_cap=1 -> failure

def test_min_candidates_full_lists_still_pass() -> None:
```

- [ ] **Step 2: Run, watch them fail**

Run: `cd pipeline && uv run pytest tests/test_bundle.py tests/test_checks.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**
- `write_area` writes `"1" if r.walk_cycle else ""`.
- `_check_min_candidates` passes a short postcode only if all its rows have a walk or a drive route. It fails the area if the number of such postcodes exceeds `area["postcodes_widened_to_cap"]`, and treats a missing key as 0, so older shards fail closed.
- `_check_walk_cycle` flags any row with `walk_cycle == "1"` and blank `walk_m`. Register it with the other per-release checks.
- `docs/data-format.md`:
  - the new column and its meaning ("needs a cycle path not signed for walkers, adding more than 50 m if avoided");
  - that walking uses UK rules (`foot-gb`);
  - the new manifest `config` and area fields;
  - that unreachable candidates are dropped when reachable ones exist.

- [ ] **Step 4: Pass the whole pipeline suite, lint, type-check**

Run: `cd pipeline && uv run pytest -q && uv run mypy && uv run ruff check . && uv run ruff format --check .`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git commit -am "pipeline: walk_cycle column in travel files; release checks for it and for widened postcodes"
```

---

### Task 5: App reads the new column and shows the note

**Files:**
- Modify: `app/src/lib/engine/csv.ts` (`parseTravel`), `app/src/lib/engine/types.ts` (`TravelRow`), `app/src/lib/engine/results.ts` (`Result`, `buildResults`), `app/src/lib/engine/format.ts` (`travelLine`)
- Modify: `scripts/make_fixture_release.py` (carry `walk_cycle` through), `scripts/test_make_fixture_release.py` (or wherever its test lives)
- Test: `app/src/lib/engine/csv.test.ts`, `app/src/lib/engine/format.test.ts`, `app/src/lib/engine/results.test.ts`

**Interfaces:**
- Consumes: the travel header from Task 4.
- Produces:
  - `TravelRow.walkCycle: boolean`
  - `Result.walkCycle: boolean`
  - `travelLine(r: Result): string`, with the note.

- [ ] **Step 1: Write the failing tests**

```ts
it('reads the 7-column travel file', () => {
  const rows = parseTravel('pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s,walk_cycle\n0,1,900,1400,1080,300,1\n0,2,950,1500,1150,310,\n')
  expect(rows.map((r) => r.walkCycle)).toEqual([true, false])
})
it('reads the older 6-column travel file with no notes', () => {          // Review Focus 4
  const rows = parseTravel('pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s\n0,1,900,1400,1080,300\n')
  expect(rows[0].walkCycle).toBe(false)
})
it('rejects any other travel header', () => {
  expect(() => parseTravel('pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s,extra\n')).toThrow()
})
it('travelLine notes a walk that needs a cycle path', () => {
  expect(travelLine({ ...base, walkM: 1400, walkS: 1080, driveS: 300, walkCycle: true }))
    .toBe('1.4 km · 18 min walk, partly on a cycle path · 5 min drive')
})
it('travelLine has no note otherwise', () => {
  expect(travelLine({ ...base, walkM: 1400, walkS: 1080, driveS: 300, walkCycle: false }))
    .toBe('1.4 km · 18 min walk · 5 min drive')
})
it('buildResults carries walkCycle through', () => { /* one row with walkCycle true -> result.walkCycle true */ })
```

For the fixture script, its test asserts that a source travel file with `walk_cycle` keeps the column and values after trimming, and that a 6-column source still produces a 6-column file.

- [ ] **Step 2: Run, watch them fail**

Run: `cd app && npx vitest run src/lib/engine` and `cd pipeline && uv run pytest ../scripts -q`
Expected: FAIL.

- [ ] **Step 3: Implement**
- `parseTravel` accepts either column list, by checking the header against both constants.
- `make_fixture_release.py` copies whichever header the source has.

- [ ] **Step 4: Pass the whole app suite plus checks**

Run: `cd app && npm test && npm run check && npm run lint`
Expected: PASS (coverage thresholds still met), 0 errors.

- [ ] **Step 5: Commit**

```bash
git commit -am "app: read walk_cycle and note walks that need a cycle path"
```

---

### Task 6: Real-data check, fixture with a note, docs

**Files:**
- Modify: `app/tests/fixtures/data/**` (regenerated)
- Modify: `app/tests/e2e/search.spec.ts` (add the note test)
- Modify: `docs/decisions.md`, `pipeline/README.md`, `pipeline/reference/expectations.toml` (only if a case legitimately changes, with a comment saying why)
- Modify (outside the repo, keep a backup first): `~/Downloads/Within Reach Tool.md` issue I5, `~/.claude/plans/i-am-working-on-indexed-fountain.md` section 7

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Baseline timing.** Note the existing data-2026-11 counts from the live manifest: E06000050 69, E06000035 49, W11000023 0 `postcodes_without_walk`. The `build` log of a local run on `main` gives the baseline time per area. If that's too slow, use the GitHub run's per-shard times for these areas instead, and record which source was used.

- [ ] **Step 2: Local OSRM build** of the three areas with maps, from `pipeline/`:

Run: `uv run within-reach-pipeline build --release 2026-11 --areas E06000050 W11000023 E06000035 --router osrm --maps tilemaker --out ../.local-release` (match the CLI's real flag names; check `--help`).
Expected: completes. Then `uv run within-reach-pipeline check ../.local-release --reference` passes.

- [ ] **Step 3: Verify the outcomes and record them.** From the manifest and travel files:
- E06000050 `postcodes_without_walk` is well below 69 (target 0). Every remaining postcode is listed with its sector.
- In E06000035, ME3 9EJ's rows include Knights Pharmacy (ME3 9DT) and no `SS8` pharmacy.
- At least one CH4 7 postcode has a row with `walk_cycle=1`. Record which postcode, for Step 5.
- Build time per area, compared with Step 1.

If Lache doesn't improve, stop and debug (superpowers:systematic-debugging) before going on.

- [ ] **Step 4: Regenerate the app fixture** from the local release with the documented command (`scripts/make_fixture_release.py ... --districts CH2 CH4 LL11 --split-area E06000050`). Keep the synthetic SY14 9ZZ case the existing script adds. If the Step 3 postcode isn't in those districts, add its district.

Run: `cd app && npm run test:e2e`
Expected: the existing e2e tests pass on the new fixture. If expected values shift because the data changed, update them only where the new routing explains it, and note each change in the commit message.

- [ ] **Step 5: e2e test for the note** in `search.spec.ts`:

```ts
test('a walk that needs an unsigned cycle path says so', async ({ page }) => {
  test.skip(!!process.env.LIVE_URL, 'depends on the fixture release')
  await search(page, PC.cycle)            // the postcode found in Task 6 Step 3
  await expect(results(page).filter({ hasText: 'partly on a cycle path' }).first()).toBeVisible()
})
```

Run: `cd app && npm run test:e2e`
Expected: PASS in all projects.

- [ ] **Step 6: Docs**
- `docs/decisions.md`: a new entry covering the walking rules and the widening, with the before and after counts and build times from Step 3, and the data-2026-11 baseline (Cheshire West and Chester 69, Argyll and Bute 60, Medway 49, Wokingham 5).
- `pipeline/README.md`: mention `pipeline/osrm/foot-gb.lua` and the new config keys.
- Spec I5: say the cause was the stock walking rules, fixed by `foot-gb`. Plan section 7: done, with a link to the design doc.
- Before editing the spec, copy it to `Within Reach Tool 0.7_22_11_2026.md` (the home-folder rule on versioned files).

- [ ] **Step 7: Commit**

```bash
git add app/tests docs pipeline/README.md pipeline/reference
git commit -m "test: fixture regenerated with UK walking rules; e2e test for the cycle path note; docs"
```

---

### Task 7: PR, release v0.2.0, data run

Each step marked **(ask)** needs the user's go-ahead: merges, tags and replacing a release all have effects outside this branch.

- [ ] **Step 1:** Final whole-branch review (per the execution skill), then fix pass.
- [ ] **Step 2:** Push the branch and open a PR. The body summarises what changed, with the Step 3 numbers from Task 6, and no AI attribution line. Wait for CI to pass.
- [ ] **Step 3 (ask):** Merge, then delete the branch locally and on the remote.
- [ ] **Step 4 (ask):** Tag `v0.2.0` on the merge commit (`git tag -a v0.2.0 -m "UK walking rules, cycle path note, reachable pharmacies"`) and push it. Confirm the deploy succeeds, and that the live site still searches correctly on data-2026-11 (the 6-column files), using the five-postcode smoke test.
- [ ] **Step 5 (ask):** Full data run. Either replace data-2026-11 (delete the release and its tag, then dispatch `pipeline.yml` with release 2026-11), or let the scheduled run on 2 December publish data-2026-12. The user decides. After it finishes, check the release assets, the follow-on deploy, and the live check. On the live site, a Lache postcode shows "partly on a cycle path", and ME3 9EJ lists Knights Pharmacy.
- [ ] **Step 6:** Record the new per-area no-walk and no-route counts in `docs/decisions.md` (in a small follow-up PR), and decide with the user whether Oban and Crowthorne still need investigating.

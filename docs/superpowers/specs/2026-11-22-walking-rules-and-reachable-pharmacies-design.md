# UK walking rules and reachable pharmacies: design

Date: 22 November 2026. Status: draft for approval. Reviewed by a builder check; questions answered by the user on 22 November 2026.
Builds on the Phase 1 pipeline and the Phase 2 public search. Replaces "Option 1" in section 7 of the master plan (`~/.claude/plans/i-am-working-on-indexed-fountain.md`) and settles spec issue I5.

## Why

The first full GB release (data-2026-11) has 183 postcodes with no walking route to any pharmacy. Someone searching from one of them gets a list with "No walking route found" on every entry, which is wrong and makes the tool look broken. There are two causes:

1. **The walking rules.** OSRM's stock walking profile (`/opt/foot.lua` in `osrm-backend:v26.11.0-debian`) leaves out `highway=cycleway`, `highway=bridleway` and `highway=trunk`. In the UK, shared-use cycle paths are normal and often the only footway: the Lache estate in Chester (69 postcodes, CH4 7 / CH4 9 / CH99 9) can only be left by the A483 trunk road, untagged cycle paths beside it (OSM ways 369715259 and 369715252), or a private road.
2. **The choice of candidate pharmacies.** Candidates are chosen by straight-line distance. Around Allhallows on the Hoo peninsula (Medway, 49 postcodes, ME3 9), the five nearest are on Canvey Island, across the Thames, with no crossing nearby. None can be reached, so the postcode gets five unreachable entries, while Knights Pharmacy (ME3 9DT), 8.1 km away on the same side, is never considered.

The user also wants walkers to know when a route relies on a cycle path, because someone on foot may not expect it or may not be comfortable using one.

## Goals

- Walking routes may use cycle paths, unless a path is tagged `foot=no`.
- When the best walking route to a pharmacy needs a cycle path that isn't marked as open to walkers, the result says so. Signed shared-use paths (`foot=yes`, `designated` or `permissive`) are already walkable with the stock rules and stay plain walking, with no note (user's decision).
- Walking routes may use bridleways, with no note, because pedestrians have a legal right of way.
- Walking routes may use trunk roads only where a pavement is mapped.
- Every postcode that can reach a pharmacy on the same side of the water gets reachable pharmacies, not just the nearest by straight line.
- Releases record which walking rules were used, so releases can be compared.
- One full data run covers all of this.

## Non-goals

- **Oban** (Argyll and Bute, 60 postcodes, PA34 5 / PA37 1) and **Crowthorne** (Wokingham, 5 postcodes, RG45 6 / RG40 3NQ). Their nearest pharmacies are 160 m to 1.4 km away and driving works, so cycle paths are an unlikely cause. A suspect is the stock profile blocking roads tagged `sidewalk=separate` when the separate pavements don't connect. This gets its own investigation once this change has run; the new release's counts will show whether these areas improve.
- Showing route lines on the map, or turn-by-turn directions.
- Editing OpenStreetMap. The user may tag the Lache paths themselves; that's separate from this work.
- Changing the 3 km clip margin (issue #13).

## Anti-goals

- Routing pedestrians along dual carriageways or trunk roads with no pavement.
- Walking along paths explicitly closed to pedestrians (`foot=no`, `access=no` without a foot exception, `access=private`).
- A copy of the stock profile we must keep in step by hand. Upgrading OSRM should still bring its fixes.
- Breaking the live site at the moment the new data deploys (see "Release order").
- Listing a pharmacy with no route when reachable pharmacies exist for that postcode.

## Approaches

### Detecting a cycle path in the best walking route

| Approach | Trade-off |
|---|---|
| **A. One walking graph, asked twice (chosen).** The walking profile puts cycle paths in an OSRM class `cycleway` and declares it excludable. For each routing batch the pipeline asks for walking distances once normally and once with `exclude=cycleway`. If the second answer is missing or longer, the best route uses a cycle path. | One extra walking table request per batch, about 10–20% more build time. No extra graph. |
| B. Two walking graphs (stock and UK rules), compared. | Same answer, but a second graph per area: more time and memory on the GitHub runners. |
| C. Ask for each route's full geometry and inspect it. | Millions of route requests per release. Ruled out. |

The user chose A.

### Making sure postcodes get reachable pharmacies

| Approach | Trade-off |
|---|---|
| **A. Widen the search when needed (chosen).** After routing, any postcode with fewer than `min_candidates` reachable pharmacies gets the next nearest added by straight line, and those are routed. This repeats until it has enough or the next candidate is beyond a 25 km cap. | Only affected postcodes are re-routed, so build time barely changes. |
| B. Choose candidates by road distance from the start. | More correct in principle, but a rewrite of candidate selection and much slower. |

The user chose A.

## Design

### 1. UK walking profile (`pipeline/osrm/foot-gb.lua`)

A thin wrapper around the stock `/opt/foot.lua`, not a copy. It loads the stock profile, adjusts its `setup()` result, and wraps `process_way`:

- **Speeds:** add `cycleway` and `bridleway` to the walking speed table at the stock walking speed. Add `trunk` and `trunk_link` too, but see the trunk rule below.
- **Access:** unchanged. The stock access handling already blocks `foot=no`, `access=no` and `access=private` (unless a foot tag allows them), so a cycle path tagged `foot=no` stays closed.
- **Trunk rule:** a `trunk` or `trunk_link` way is walkable only if `sidewalk`, `sidewalk:both`, `sidewalk:left` or `sidewalk:right` is `both`, `left`, `right` or `yes`, or `foot` is `yes`, `designated` or `permissive`. Otherwise the way is dropped before the stock handlers run.
- **Classes:** a `highway=cycleway` way with no `foot` tag of `yes`, `designated` or `permissive` gets the class `cycleway` in both directions. These are exactly the cycle paths the stock rules don't allow. Signed shared-use paths aren't classed, because the stock rules already treat them as ordinary walking. The profile declares `classes` containing `cycleway` and `excludable` containing `{cycleway}`. Nothing else is classed, so excluding `cycleway` only removes unsigned cycle paths.
- **Speeds and timing:** unchanged from stock for everything already walkable, so walking times outside cycle-path routes don't move.

The pipeline mounts `pipeline/osrm/` into the OSRM container read-only and runs `osrm-extract` with `foot-gb.lua` for the walking graph. The driving graph keeps `/opt/car.lua`.

### 2. Cycle-path flag in routing

- `OsrmRouter.table(...)` gains an optional `exclude: str | None` argument, added to the request as `&exclude=cycleway`.
- `route_candidates` asks the walking router twice per batch: normally, and with `exclude="cycleway"`.
- A new `TravelRow` field `walk_cycle: bool`. It's true when there's a normal walking route, and the route without unsigned cycle paths is either missing or more than 50 m longer. It's false when there's no walking route at all. The 50 m threshold is my call, so a few metres at a crossing, or a slightly different snap point, don't trigger the note. It goes in `config.toml` as `cycle_note_min_extra_m = 50`.
- `FakeRouter` accepts and ignores `exclude`, so fake builds produce `walk_cycle = false` everywhere.

### 3. Reachable candidates

After the first routing pass for an area:

1. A postcode is **reachable-short** if fewer than `min_candidates` (5) of its candidates have a walking or a driving route. Either kind of route counts (user's decision). A postcode whose nearby pharmacies can only be driven to doesn't widen to find walkable ones further away, because at that distance nobody walks anyway.
2. For each reachable-short postcode, take the next nearest pharmacies by straight line, excluding those already tried. Take enough to cover the shortfall, plus `min_candidates` more, so islands don't need many rounds. Only consider pharmacies inside the area's extract bounding box, because nothing outside it can be routed. Stop at pharmacies more than `reach_cap_m` (25,000 m) away in a straight line.
3. Route the new pairs (walking, walking without cycle paths, and driving) in the same batched way.
4. Repeat until no postcode is reachable-short, no new candidates remain inside the cap, or 4 rounds have run.
5. **Final list for each postcode:** if it has at least one reachable pharmacy, drop its unreachable ones. If it has none (a real island with no route), keep the original straight-line candidates unchanged, so the app still shows the nearest pharmacies with "No route found".

The final list is then sorted by the existing rule (straight-line metres, then directory order), so files stay deterministic. `max_candidates` (40) is still the most rows per postcode.

`config.toml` gains `reach_cap_m = 25000` and `reach_max_rounds = 4` under the existing candidate settings.

The candidate pharmacies used to size the area extract are still the first-pass candidates. Widening only uses pharmacies inside that extract.

### 4. Data format

- `travel.csv.gz` gains a seventh column: `pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s,walk_cycle`. `walk_cycle` is `1` or blank. Blank is used for false to keep files small, matching the blank-for-missing convention.
- The manifest's `config` gains `"walk_profile": "foot-gb"`, `"reach_cap_m": 25000` and `"reach_max_rounds": 4`.
- The manifest's area entries gain `"postcodes_without_route"`: postcodes with neither a walking nor a driving route to any candidate. `postcodes_without_walk` stays.
- `docs/data-format.md` documents all of the above, and that walking uses UK-adjusted rules.

### 5. App

- The travel parser in `app/src/lib/engine/csv.ts` accepts both the 6-column header (releases before this change) and the 7-column header. A missing `walk_cycle` means false. Any other header still fails loudly.
- `Result` gains `walkCycle: boolean`.
- `travelLine` shows the note right after the walking part when `walkCycle` is true: `1.4 km · 18 min walk, partly on a cycle path · 5 min drive`.
- Nothing else in the list or map changes. Sorting and filters are unaffected.

### 6. Release order (so the live site never breaks)

The current production app (v0.1.0) rejects a travel file with an unknown header. A monthly or manual data run redeploys the latest `v*` tag with the newest data. So:

1. Merge the pipeline and app changes in one PR.
2. Tag the app release (v0.2.0) **before** the next data run. It reads both old and new travel files, so it works with data-2026-11 straight away.
3. Then run the full data rebuild. The redeploy that follows serves v0.2.0 with the new data.

The scheduled run on 2 December would otherwise deploy new data with whatever tag is latest, so step 2 must happen before then.

### 7. Checks

- `checks.py` checks the new column, that `walk_cycle` is only set where `walk_m` is set, and the new manifest fields.
- **The minimum-candidates check changes** (my call), because dropping unreachable rows can leave a postcode with fewer than 5. A postcode passes if any of these is true; otherwise the release still fails:
  - it has at least `min(min_candidates, pharmacy count)` rows;
  - every row is reachable and widening stopped at the cap, or found nothing more inside the extract;
  - no row is reachable, and it kept its original straight-line list.

  To make this checkable, the build records the second case in the manifest as a per-area `postcodes_widened_to_cap` count. The checks then compare short postcodes against it.
- The release's reference check (`pipeline/reference/expectations.toml`, 10 cases around Chester and Wrexham) must still pass. Any case whose nearest three change is re-checked against the map, and the expectations are updated only with a note of why.

## Tests

- **Profile (real OSRM in Docker, `RUN_OSRM=1`):** a small hand-written `.osm` file run through `osrm-extract` with both profiles. Cases:
  - A and B joined only by an untagged cycle path: no route with the stock profile; a route with `foot-gb`. With `exclude=cycleway`, no route.
  - The same path tagged `foot=no`: no route with `foot-gb`.
  - The same path tagged `foot=designated`: a route with both profiles, and still a route with `exclude=cycleway` (it isn't classed).
  - A and B joined only by a bridleway: a route with `foot-gb`.
  - A and B joined only by a trunk road with no sidewalk tag: no route. With `sidewalk=both`: a route.
  - A residential street: the same distance with both profiles.
- **Unit tests:**
  - the extract command mounts the profile directory and uses `foot-gb.lua` for walking only;
  - the `exclude` parameter appears in the table URL;
  - `walk_cycle` logic, including the 50 m threshold;
  - widening: a fake router where the nearest candidates are unreachable, so further ones are added, unreachable ones are dropped, and the cap and round limit are respected; an island with no reachable pharmacy keeps its original list;
  - the travel file writes and reads the new column;
  - checks reject `walk_cycle` without `walk_m`;
  - the new minimum-candidates rule passes each of its three cases and still fails a short postcode that is none of them.
- **App (Vitest):** the parser reads both header versions and rejects others; `travelLine` shows the note. The fixture release is regenerated with the new column, including at least one `walk_cycle` row. A Playwright test searches a postcode with that row and sees the note.
- **Local real-data check:** build E06000050 (Cheshire West and Chester) and W11000023 (Betsi Cadwaladr) with OSRM, and also E06000035 (Medway). Record before and after:
  - Lache's `postcodes_without_walk`, expected to fall from 69 towards 0;
  - Allhallows (ME3 9EJ), which should list Knights Pharmacy (ME3 9DT) and no Canvey Island pharmacies;
  - the reference cases, which must pass;
  - build time per area, before and after.

## Done when

- The PR is merged with CI green, and v0.2.0 is tagged and live.
- A full data run has published a release with `walk_profile: foot-gb`. The live site shows "partly on a cycle path" for a Lache postcode, and Allhallows lists Knights Pharmacy.
- The release's no-walk and no-route counts per area are recorded in `docs/decisions.md`, next to the data-2026-11 baseline (Cheshire West and Chester 69, Argyll and Bute 60, Medway 49, Wokingham 5).
- Spec issue I5 and master plan section 7 are updated.

## Left to the builder

- How the wrapper loads the stock profile (`require` with the OSRM profile path, or `dofile('/opt/foot.lua')`), provided the stock file is used unchanged.
- How widening is structured in code, provided routing stays batched by tile and a postcode is never routed twice to the same pharmacy.
- Exact names for new config keys and functions, following the existing style.

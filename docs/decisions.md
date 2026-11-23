# Decision record

Decisions from spec section 15. Gate 0 requires D1–D5, D9, D11 and D13 to be settled.

| ID | Decision | Outcome | Date |
|---|---|---|---|
| D1 | Starting point | Start fresh; reuse the Part 2 script's logic in the pipeline | 17 Nov 2026 |
| D2 | Engine language in the browser | TypeScript | 17 Nov 2026 |
| D3 | Routing engine | OSRM for walking and driving | 17 Nov 2026 |
| D4 | Area unit and catchment radius | Councils in England and Scotland, health boards in Wales, plus a buffer. Catchment (Phase 1): every pharmacy within 5 km in a straight line, capped at the nearest 40, and always at least the nearest 5 (`pipeline/config.toml`) | 17 Nov 2026 |
| D5 | Project licence | AGPL-3.0-only | 17 Nov 2026 |
| D9 | Ownership and pilot data | Cleared: personal project, no employer claim | 17 Nov 2026 |
| D11 | App framework | Svelte 5 with Vite, bundled, no CDN | 17 Nov 2026 |
| D13 | Static host | Cloudflare Pages at withinreach.vasnik.net (DNS stays at GoDaddy) | 17 Nov 2026 |
| D14 | Pipeline schedule | Monthly, at 03:00 UTC on the 2nd of each month | 17 Nov 2026 |
| D15 | Welsh pharmacy list | Use NHS ODS (Open Government Licence) instead of the NWSSP list, so no NWSSP permission is needed | 17 Nov 2026 |
| D6, D7, D8, D10, D12 | | Open: due at later phases | |

## Other Phase 0 choices

- The repository stays private until the Phase 0 gate, then goes public.
- Folder names inside the repository are lowercase, which is the code convention.
- `'wasm-unsafe-eval'` is left out of the CSP until a WebAssembly dependency is added.
- Pushes to `main` deploy a preview. Tags `v*` deploy to production.

## Phase 1 choices

- Bundles are gzipped CSV files, published as GitHub Releases (`data-YYYY-MM`). See `docs/data-format.md`.
- Online-only (distance-selling) pharmacies are left out, using NHSBSA Contractor Details.
- The release check allows up to 2% of a nation's pharmacies to have a postcode ONSPD can't locate.
- While the repository is private, runs build only the reference areas and publish a `-partial` prerelease, which deploy never serves.

Spec draft 0.6 (18 Nov 2026) records these.

## Phase 2 choices

Design: `docs/superpowers/specs/2026-11-18-phase-2-public-search-design.md`. Spec draft 0.7 (20 Nov 2026) records these.

- Phase 2 is a public postcode search (map plus list). The service tool moves to Phase 3.
- The street map is built per area by the pipeline (tilemaker, OpenMapTiles schema, slimmed, zoom 13) and downloaded whole. The browser reads it from memory, so there are no tile or range requests. Maps over 20 MiB are split into plain byte chunks.
- Map library: MapLibre GL JS, loaded only after the first search. Its worker and the map fonts (Noto Sans, OFL) are served from the site, so the CSP is unchanged.
- Data files are served with `Cache-Control: no-store` and kept in memory only for the tab, so a shared device doesn't show which areas were looked up. Nothing is stored in the browser, so "Clear all data" waits for service mode.
- Filters: Open Saturday, Open Sunday, Open late (until 19:00 or later on a weekday). A pharmacy whose hours can't answer a filter is never hidden; it's listed under "Opening hours not known".
- The list shows 10 at a time. Pin numbers follow the list as currently shown.
- Maps are a separate release asset (`maps-YYYY-MM.tar.gz`); only the latest release's maps are deployed.
- The data files must be served as they are (`.csv.gz` as `application/gzip`, no `Content-Encoding`). A host that re-encodes them fails the app's checksum check, on purpose. Cloudflare Pages serves them correctly; the local preview server is configured to match.

## UK walking rules and reachable pharmacies (v0.2.0)

Design: `docs/superpowers/specs/2026-11-22-walking-rules-and-reachable-pharmacies-design.md`.

- **Walking uses UK rules** (`pipeline/osrm/foot-gb.lua`, recorded as `walk_profile: foot-gb` in each manifest). It's OSRM's stock foot profile, loaded unchanged, plus:
  - cycle paths, unless tagged `foot=no`;
  - bridleways;
  - trunk roads, only where a pavement or foot access is tagged.

  Driving is unchanged.
- **Results note "partly on a cycle path"** when the best walk needs a cycle path not signed for walkers (no `foot=yes`, `designated` or `permissive`), meaning that avoiding it is impossible or adds more than 50 m. Signed shared-use paths count as ordinary walking.
- **Reachable pharmacies.** If fewer than 5 of a postcode's pharmacies can be reached on foot or by car, the search widens:
  - the next nearest are added, up to 25 km in a straight line, within the area's map extract, for at most 4 rounds;
  - the unreachable ones are then dropped;
  - a postcode that can reach none keeps its original list.

**Effect, measured on 23 Nov 2026** (same November sources, before and after this change):

| Area | Postcodes without a walking route, before | After |
|---|---|---|
| Cheshire West and Chester (E06000050) | 69 (Lache, CH4 7 / CH4 9 / CH99 9) | 0 |
| Medway (E06000035) | 49 (Allhallows, ME3 9) | 0 |
| Betsi Cadwaladr (W11000023) | 0 | 0 |

- **Allhallows (ME3 9EJ)** now lists Knights Pharmacy and Hoo Pharmacy (about 9 km on foot, 13 minutes by car) instead of five Canvey Island pharmacies across the Thames.
- **Lache (CH4 7DJ)** now has walking routes, every one partly on a cycle path. The nearest, Westminster Park Pharmacy, is 3.9 km on foot.
- **How often the note appears:** on 10% of all rows in Cheshire West and Chester, 8% in Betsi Cadwaladr and 7% in Medway. Many UK cycle paths don't say whether walkers may use them.
- **Build time** for the three areas with maps: about 4½ minutes, the same before and after.
- **Two reference cases changed** their third-nearest pharmacy, because a walk got shorter through a newly allowed bridleway or trunk-road pavement: CH2 3JQ (Boots, Foregate Street) and LL21 0BB (Glyn Ceiriog Pharmacy). `pipeline/reference/expectations.toml` notes why.
- **The data-2026-11 baseline** for all of Great Britain was 183 postcodes without a walking route: Cheshire West and Chester 69, Argyll and Bute 60, Medway 49, Wokingham 5. Oban (Argyll and Bute) and Crowthorne (Wokingham) have a different cause, still to be investigated.
- **The app reads both travel-file layouts**, so v0.2.0 can go live before the first release built with these rules.

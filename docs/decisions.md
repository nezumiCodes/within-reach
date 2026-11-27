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
- **The app reads both travel-file layouts**, so v0.2.0 can go live before the first release built with these rules.

**All of Great Britain, data-2026-11 rebuilt on 23 Nov 2026** with these rules (pipeline run 45223162832, all release checks passed, including the Lache and Allhallows reference cases):

| Area | Postcodes without a walking route, first data-2026-11 (18 Nov) | Rebuilt (23 Nov) |
|---|---|---|
| Cheshire West and Chester (E06000050) | 69 | 0 |
| Argyll and Bute (S12000035) | 60 | 0 |
| Medway (E06000035) | 49 | 0 |
| Wokingham (E06000041) | 5 | 5 |
| **Great Britain** (1,748,230 postcodes) | **183** | **5** |

- **Oban** (Argyll and Bute) was fixed by the same rules, so it wasn't a separate cause after all. PA34 4AA now lists the two George Street pharmacies first.
- **Crowthorne** (Wokingham): 5 postcodes still have no walking route, but every one has pharmacies reachable by car, so no postcode is left without a route (`postcodes_without_route` is 0 in every area). The cause is still to be investigated.
- **No postcode needed the 25 km cap**: `postcodes_widened_to_cap` is 0 in every area.
- **Allhallows (ME3 9EJ)** on the live site: Knights Pharmacy and Hoo Pharmacy, then four Sheerness pharmacies (reachable by car over the Sheppey crossing, 45–47 minutes).
- **Run time:** 141 minutes, against 93–100 minutes for earlier full runs. The slowest shard took 53 minutes, and the Scottish shards took at most 26.

## Service filters: needle exchange (England)

Design: `docs/superpowers/specs/2026-11-24-needle-exchange-filter-design.md`.

**Research (24 Nov 2026).** Supervised consumption was the first goal, but no open source covers it in any nation.
- **Dispensing data can't show opioid substitution** in any nation:
  - NHSBSA's contractor dispensing file only counts services and items;
  - PHS's dispenser file leaves out Schedule 2 and 3 controlled drugs;
  - NWSSP's files count items by GP practice only.
- **DoHS v3 test environment:** supervised consumption (`SRV0258`) is listed by 1 of 11,227 pharmacies (an online pharmacy). Needle and syringe exchange (`SRV0274`) is listed by 1,583. So needle exchange was built first.
- **Scotland and Wales:** NHS inform / NHS 24 and NHS 111 Wales list services per pharmacy, but their terms don't allow reuse without permission. Permission has been requested.

**Decisions**
- **Source:** the NHS England Directory of Healthcare Services (DoHS) API, v3, for England. Content is under the Open Government Licence, with the attribution line in `docs/data-format.md`.
- **Services are data.** Each is declared in `pipeline/config.toml` (`key`, `name`, DoHS `code`, `nations`), so a new service or nation is added as data, not by redesign.
- **A `services` cell per pharmacy** (`key` listed, `key?` not known, absent not listed), not rules by nation. A later source may cover some English councils and not others, so "not known" can't be decided by nation. The app needs no nation rules.
- **Wording is always "not listed", never "doesn't offer".** Listings are what pharmacies publish on their NHS website profiles. Some pharmacies that offer needle exchange don't list it.
- **Scottish and Welsh pharmacies are "not known"** (`nsp?`), the same pattern as opening hours.
- **English pharmacies missing from DoHS are "not listed"** (empty cell). They are counted as `missing_dohs`, and the release check fails at 10% or more.
- **Routed service candidates.** Filtering only the existing candidates would find nothing in rural areas with 5 or 6 candidates, even with a needle exchange 8 km away, which would wrongly tell someone there is none near them. Instead each postcode is routed to its nearest `service_min` (5) pharmacies listing each service, up to `reach_cap_m` (25 km):
  - `service_min` is a total: service pharmacies already among the candidates count towards it;
  - these rows are exempt from the 40-candidate cap, and a pharmacy that is also nearby is stored once;
  - the map extract and bounding box are sized after they are chosen, so they can be routed and shown on the map;
  - they don't count towards the "at least 5 reachable" widening. Otherwise distant service rows could push out nearer pharmacies (the Allhallows case, ME3 9EJ);
  - each service widens with its own `reach_max_rounds` budget.
- **Straight-line fallback in the app was rejected.** It mixes routed and unrouted results and brings back straight-line distance across estuaries, which v0.2.0 removed.
- **The switch.** `[services] enabled = false` in `pipeline/config.toml` until production access to the DoHS API is approved by NHS England. While it is off, no run fetches services. After switch-on, branch runs will be configured to build with services off (plan Task 11). Integration (test) data is never published. With it off, releases and the app are unchanged: empty `services` cells, `config.services = []`, `services = {}`, and no Services group.
- **Order of release:** the app that reads both pharmacy layouts, then the production key, then the switch on.
- **Release order for this branch:** merging adds the `services` column to `pharmacies.csv.gz` even with the switch off, and the live app (v0.2.0) only accepts the exact old header. So after the merge, tag `v0.3.0` from `main` before any data run, and before the scheduled run on 2 December 2026 at 03:00 UTC (which builds from `main`, and `deploy.yml` then redeploys the latest tag with that data). If the tag can't follow the merge in time, hold the merge until after that run.
- **The key** comes from `NHS_DOHS_API_KEY`. It is never logged or written to the cache, the release or error messages. See `pipeline/README.md`.
- **Release checks:** at least 1,000 pharmacies listed, within ±20% of the previous release, `missing_dohs` under 10% of English pharmacies, and only configured keys in the `services` column.
- **Test fixture:** the app's e2e fixture uses made-up services (`fixtures/synthetic/fixture_services.csv`), not DoHS data.

**Effect, measured on 26 Nov 2026** (same November sources and maps, built locally with services off, then on, using a DoHS integration (test) snapshot; nothing from it was published):

| Area | Travel rows, before → after | Travel file | Map | Build time | Postcodes short of 5 |
|---|---|---|---|---|---|
| Medway (E06000035) | 184,110 → 194,264 (+5.5%) | 2.00 → 2.13 MB (+6.3%) | 1.73 → 1.77 MB (+2.4%) | 45 s → 49 s | 84 of 6,188 |
| Cheshire West and Chester (E06000050) | 117,623 → 160,420 (+36.4%) | 1.25 → 1.79 MB (+42.5%) | 6.45 → 8.80 MB (+36.4%) | 68 s → 97 s | 3 of 11,026 |
| Betsi Cadwaladr (W11000023) | 186,312 → 230,850 (+23.9%) | 2.11 → 2.69 MB (+27.3%) | 13.95 → 16.93 MB (+21.4%) | 130 s → 180 s | 17,182 of 24,940 |
| Highland (S12000017) | 54,025 → 54,025 (0%) | 0.62 MB (0%) | 28.83 → 28.84 MB (+0.0%) | 84 s → 101 s | 7,961 of 7,961 |

- **No map grew by more than half** (the limit in the design, section 3), so no cap on map growth is needed. The largest growth is Cheshire West and Chester, +36%.
- **The test snapshot:** 11,202 DoHS pharmacies, 1,567 listing `SRV0274`. The manifest counted `listed` 1,564, `missing_dohs` 72 and `unmatched_dohs` 1,372.
- **Build time** for the four areas: 345 s before, 447 s after (+30%). Times per area run from one area's start to the next. The timings are noisy: Highland does the same work in both builds but took 84 s and then 101 s, and an earlier services-on build took 387 s (+12%).
- **Postcodes short of 5** (`services.nsp.postcodes_short`) is expected in Scotland and Wales, where only English pharmacies list the service. Welsh postcodes near the border get rows for English pharmacies, which is why the Betsi Cadwaladr files grow. No Highland postcode has an English pharmacy within 25 km.
- **The nearest pharmacies are kept.** All 1,547 Medway postcodes with 40 candidates kept all 40. No Chester postcode has more than 20 candidates, so the cap never applies there.
- **Services don't change the general rows.** Compared row by row in all four areas, no postcode's set of general pharmacies differs with services on. 31 shared rows (in 27 postcodes) have different walk or drive values, because the larger extract gives OSRM a bigger road network to route over. A first build did change them: three Allhallows postcodes (ME3 9QE, ME3 9QQ, ME3 9QZ) lost a Sheerness pharmacy. The wider extract had brought Southend pharmacies, across the estuary, into the reach widening search. Now reach widening searches only the box the first-pass candidates give, as with services off. Service widening searches the whole extract.
- **Two reference cases added**, chosen from a test snapshot, so they must be rechecked on the first production run: SY14 8JA (Malpas, nearest needle exchange 16 km) and CH1 2DY (Chester centre, all 17 candidates kept plus 3 needle exchange rows beyond 5 km). Service cases are skipped while services are off.

**Open question: refresh.** DoHS terms ask for a 24-hour refresh of cached content. The pipeline is monthly, because routes depend on the service list. Whether monthly is acceptable is with NHS England. If not, the planned follow-up is a small daily job that publishes a service list, so the app can hide pharmacies that have dropped a service.

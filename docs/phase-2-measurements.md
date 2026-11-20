# Phase 2 measurements

Measured on 20 November 2026 on the `phase-2-public-search` branch. These are three very different areas, built from the November 2026 sources with the pinned tilemaker image and the sea areas included, as the monthly build will do.

## What a search downloads

| Area | Postcodes | Postcodes file | Travel file | Map | Map parts |
|---|---|---|---|---|---|
| Birmingham (E08000025), dense city | 21,556 | 0.2 MB | 7.4 MB | 3.8 MB | 1 |
| Kent (E10000016), largest English county | 46,148 | 0.5 MB | 4.8 MB | 8.7 MB | 1 |
| Highland (S12000017), huge and sparse | 7,961 | 0.1 MB | 0.6 MB | 27.5 MB | 2 |

Every search also downloads the GB-wide pharmacy directory (0.5 MB) and district index (9 KB), the same for every visitor. The map library loads only after the first search: MapLibre 296 KB and its worker 158 KB (gzipped), map fonts 0.5 MB. The first page is 24 KB of JavaScript.

## Build time

Each map took under a minute to build on a laptop (M-series Mac, Docker), including the osmium clip: Birmingham 47 s, Kent 45 s, Highland 58 s, each including about 30 s spent reading the postcode directory. This adds roughly 10–20 minutes to each 10-area shard in the monthly run.

## Time from pressing Search

Chromium, desktop window, `vite preview` on the same machine, with network throttling. Each run starts with an empty memory, as a first search would.

| Postcode (area) | Connection | List shown | Map ready |
|---|---|---|---|
| B1 1AY (Birmingham) | Broadband (70 Mbit/s, 20 ms) | 1.6 s | 3.1 s |
| BR6 7NZ (Kent) | Broadband | 1.3 s | 2.8 s |
| AB37 9HR (Highland) | Broadband | 0.4 s | 4.2 s |
| B1 1AY (Birmingham) | Fast 4G (9 Mbit/s, 60 ms) | 8.4 s | 13.7 s |
| BR6 7NZ (Kent) | Fast 4G | 6.1 s | 15.9 s |
| AB37 9HR (Highland) | Fast 4G | 1.8 s | 28.3 s |

**Against the design's targets** (average broadband: list within 3 s, map within 6 s): all three areas meet both.

**On mobile data the targets are missed.**
- The list waits for the whole travel file, and Birmingham's is 7.4 MB.
- Highland's map is 27.5 MB, so its map takes almost half a minute on 4G. The list still shows within 2 s and stays usable meanwhile, with a progress bar on the map.

Ways to improve this later, none needed for Phase 2:
- Split large areas' travel files.
- Drop a zoom level from very large rural maps.
- Show the list from a postcode's own rows before the whole file arrives (needs a different file layout).

A second search in the same area downloads nothing (tested in `app/tests/e2e/map.spec.ts`).

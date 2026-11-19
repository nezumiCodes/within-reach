# Phase 2 design: public pharmacy search with a private map

Status: draft for approval, 18 November 2026. Builder check done on 19 November 2026; its answers are folded in below.
Spec: `~/Downloads/Within Reach Tool.md` (draft 0.6). Master plan: `~/.claude/plans/i-am-working-on-indexed-fountain.md`.

## 1. Intent

Within Reach is changing what it builds first. The spec's Phase 2 is the service tool: approved lists, client files and shortlists. The owner wants a **public search first**:

> "Imagine someone that could send any client to any pharmacy that is close to their home or workplace knowing their postcode. There should be a map highlighting the nearest pharmacies as well as a list next to the map with the details of the pharmacies from closest to furthest."

**Who uses it:** anyone pointing a client to a pharmacy, such as a keyworker, support worker or GP receptionist, plus members of the public. They have no account and no approved list. They know one postcode, either the client's home or their workplace.

**Why the privacy design matters:** the postcode being searched is often a client's home, and in this context that's health data. The project promises that the host only ever learns which **area** (council or health board) was looked at, never the postcode. The map must keep that promise too, which is what drives most of this design.

The service tool (spec FR-09 to FR-12, FR-14, FR-18, FR-21, FR-23 and decisions D7, D8, D10, D12) moves to a later phase and will be added to the same app.

## 2. Goals, non-goals, anti-goals

**Goals**
- Type a postcode and see the nearest pharmacies on a street map and in a list, from closest to furthest, numbered to match.
- Each entry shows the name, address, walking distance and time, driving time, and weekly opening hours (or "No opening hours included").
- Sort by walking distance (the default) or by driving time.
- Filter: Open Saturday, Open Sunday, Open late.
- Everything works with only same-origin static-file GETs, under the existing CSP.
- The list alone is fully usable (WCAG 2.2 AA). The map is a visual extra.

**Non-goals for this phase**
- Service mode: approved lists, client files, shortlists, downloads, run records.
- Directions or links to outside map services. A link containing the client's postcode would leak it to a third party.
- Phone numbers, services offered and step-free access. These aren't in the data.
- Searching by address or place name. Postcode only.
- An offline version, or more map detail than zoom 13 (see section 10).

**Anti-goals: it's a failure even if it works when**
- any request contains the postcode, or reveals anything finer than the area (such as map tile requests, HTTP range requests on the map file, or the postcode in a URL or hash);
- any request goes to another domain (fonts, tiles, a script CDN or analytics);
- anything about a search stays on the device after the tab closes;
- a pharmacy is hidden by a filter when its hours aren't known;
- the list stops working because the map can't load.

## 3. Constraints

- **NFR-01 to NFR-04 are release blockers:** GET-only requests for static files on the site's own domain; no client data in any request; the strict CSP; no server-side code; nothing about a search written to browser storage.
- **The CSP in `app/public/_headers` stays as it is:** `script-src 'self'`, `worker-src 'self'`, `connect-src 'self'`, `font-src 'self'`, `img-src 'self' data:`, and no `'unsafe-inline'` or `'unsafe-eval'`. If MapLibre truly needs `blob:` in `img-src` or `worker-src`, the builder may add exactly that, with a comment and a test explaining why. No new origins are ever allowed.
- **Hosting is Cloudflare Pages:** each file must be under 25 MiB; the free plan allows 20,000 files per deployment; bandwidth is free.
- **NFR-08:** current Edge, Chrome, Firefox and Safari. Edge is the main target.
- **NFR-05:** every data and map file is checked against the manifest's SHA-256 before use.
- **NFR-10:** plain static files, with no host-specific features (the `_headers` file is already accepted).
- **NFR-15:** typed code, at least 85% engine test coverage, existing lint and type checks.
- **Licences:** the map shows "© OpenStreetMap contributors" visibly (ODbL). Map fonts must be OFL or similar.
- **Branch and PR rules from `~/.claude/CLAUDE.md`:** a branch per piece of work, merge only when CI is green, and no AI attribution in commits or PRs.

## 4. Approaches considered

### 4a. Where the map background comes from (owner picked A)
| | How | Privacy | Cost |
|---|---|---|---|
| **A. Whole-area map files** ✅ | The pipeline builds one vector map file per area. The browser downloads the whole file and reads it from memory | The host learns only the area, as now | Most work: a pipeline step, plus MapLibre in the app |
| B. Tiles from our own site | Normal tile-by-tile loading from withinreach.vasnik.net | Host logs show roughly which streets were viewed | Moderate |
| C. Public tile service | OpenStreetMap or MapTiler servers | A third party sees the location; breaks NFR-02 | Least |
| D. No street map | Pins and distance rings on a blank background | Fine | Least, but much less useful |

**Measured** (OpenMapTiles schema via tilemaker, roads, names, water, railways and places, no buildings or points of interest, maxzoom 13): Birmingham 3.0 MB, Kent 8.7 MB, Highland 26.8 MB. At full detail they were 21, 56 and 103 MB.

### 4b. Map library (owner picked A)
| | |
|---|---|
| **A. MapLibre GL JS** ✅ | WebGL, smooth, good label placement, actively maintained. About 250 KB, plus self-hosted glyphs. Its CSP build (`maplibre-gl-csp.js` plus a separate worker file) works without `blob:` workers. Needs WebGL; where WebGL is off, the map shows "Map not available on this device" and the list carries on |
| B. Leaflet with protomaps-leaflet | 2D canvas, about 60 KB, no WebGL and no fonts. Jumpier, cruder labels, less maintained |

### 4c. Splitting large map files (builder's call, recorded here)
Areas over the size limit are split as **plain byte chunks** of one PMTiles file (`map.pmtiles.000`, `.001`, …, each at most 20 MiB). The browser downloads every chunk, joins them and reads one file. This is simpler than splitting by geography: there's one file per area to build, check and render, and no tile seams.

## 5. What the user sees

### Layout
Desktop and tablet in landscape, with the map on the left and the list on the right:

```
┌──────────────────────────────────────────────────────────────────┐
│ Within Reach              Postcode [ CH2 3JQ      ] [ Search ]    │
│ Data from November 2026                                          │
├─────────────────────────────────┬────────────────────────────────┤
│                                 │ Sort: (•) Walking ( ) Driving  │
│         ③                       │ [ ] Open Saturday [ ] Open     │
│      ②      ★                   │ Sunday [ ] Open late           │
│          ①                      │────────────────────────────────│
│               ④                 │ 1 Boughton Pharmacy            │
│            MAP                  │   12 Christleton Rd, CH3 5UF   │
│                                 │   0.8 km · 11 min walk ·       │
│                                 │   3 min drive                  │
│                                 │   ▸ Opening hours              │
│                                 │ 2 …                            │
│ © OpenStreetMap contributors    │ [ Show 10 more ]               │
└─────────────────────────────────┴────────────────────────────────┘
```

On phones and narrow windows everything stacks in this order: postcode, then the map (about 40% of the screen height), then sort and filters, then the list.

### The postcode box
- The label is exactly **"Postcode"**. There's one box and no Home/Work choice.
- The search runs on Enter or the Search button. Input is normalised with the existing `normalisePostcode` (case and spaces don't matter).
- The postcode is never put in the URL, the hash, history or storage. The form doesn't submit (`preventDefault`); state is held only in memory.

### Messages (announced to screen readers through a live region)
| Case | Message |
|---|---|
| Not a valid postcode | "Enter a full UK postcode, for example CH2 3JQ." |
| Northern Ireland (BT) | "Northern Ireland isn't covered yet. Within Reach covers England, Scotland and Wales." |
| Valid but not in the data (terminated, or district unknown) | "We couldn't find CH2 9ZZ. Check it's correct and still in use." |
| Download failed | "Couldn't download the pharmacy data. Check your connection and try again." [Try again] |
| Checksum mismatch | "The downloaded data didn't pass its integrity check, so it hasn't been used." [Try again] (re-downloads with `cache: 'reload'`) |
| No WebGL / map failed | The map area shows "Map not available on this device. The list below has all the details." |

### List entries
- **Number:** matches the pin and follows the current displayed order (renumbered when the sort or filters change). *Builder's call.*
- **Name, then address and postcode.**
- **Distances:**
  - "0.8 km · 11 min walk · 3 min drive". Km to one decimal place, using metres below 1 km ("650 m"). Minutes are rounded up, with a minimum of 1.
  - A missing walk or drive value shows "No walking route found" or "No driving route found".
  - Pharmacies with no route in the current sort mode go to the end, ordered by straight-line distance.
- **Opening hours:**
  - A `<details>` element "Opening hours" holds a Mon–Sun table. `CLOSED` shows as "Closed"; ranges show as "9:00–13:00, 14:00–17:30".
  - If all seven days are blank: "No opening hours included", with no details element.
  - If some days are blank, those days show "Not known".
- **Paging:** 10 entries show at first, then [Show 10 more] until every pharmacy in the travel table for that postcode (at most 40) is shown. *Builder's call.*

### Sort
"Walking" (the default) orders by `walk_m`; "Driving" orders by `drive_s`. Ties are broken by `straight_m`, then nation, then code (NFR-11).

### Filters
Three checkboxes. When more than one is ticked, a pharmacy must match all of them.

| Filter | Matches | Unknown |
|---|---|---|
| Open Saturday | `sat` has at least one range | `sat` blank |
| Open Sunday | `sun` has at least one range | `sun` blank |
| Open late | Any Mon–Fri range ends at 19:00 or later. A range ending at or before its start (past midnight) counts as late | No weekday qualifies and at least one weekday is blank |

- Matching pharmacies keep their order.
- **Unknown pharmacies are never hidden** (FR-15). With any filter on, they're listed after the confirmed matches under the heading **"Opening hours not known"**, in the same order. One line explains: "Scottish and Welsh pharmacy lists don't include opening hours, so these pharmacies can't be filtered."
- Hidden pharmacies are summarised under the list, with the reasons for whichever filters excluded them, for example:
  - "4 closer pharmacies hidden: not open on Sundays."
  - "6 pharmacies hidden: not open on Saturdays or not open late."

  The word "closer" is used when at least one hidden pharmacy is closer, in the current sort, than the last one shown.
- If nothing matches and nothing is unknown: "No pharmacies nearby match these filters." The hidden summary still shows.
- The active filters and sort are always visible above the list (NFR-14).

### Map
- **Contents:** the area's map; a distinct marker for the searched postcode; numbered circle pins for the entries currently shown in the list.
- **Framing:** the view fits the postcode and the shown pins, with padding. It re-fits when the list changes.
- **Pins and list are linked:**
  - Clicking a pin highlights its list entry and scrolls it into view.
  - Hovering or focusing a list entry highlights its pin.
  - Choosing "Show on map" on an entry pans to it.
- **Drawn in the map:** the pins are a GeoJSON source with circle and symbol layers, using the self-hosted glyphs. There are no DOM markers and no sprite sheet.
- **For assistive technology:** the canvas container has `role="img"` and the label "Map of the postcode and the N pharmacies listed". Pins aren't separately keyboard-focusable, because the list carries all the same information. Map keyboard pan and zoom stay on.
- **Attribution:** "© OpenStreetMap contributors" is always visible.
- **Zooming in:** the map file stops at zoom 13. MapLibre's `maxZoom` is set to about 16, so users can still zoom in: zoom-13 tiles are enlarged ("overzoomed"), and lines and labels stay sharp because they're vectors. *Builder's call on the exact limit.*
- **Loading order:** the list doesn't wait for the map. While the map downloads, its panel shows "Loading map…" with a progress bar (bytes received out of the manifest size).

### Data release line
The header shows "Data from November 2026", using the existing `loadRelease`/`formatRelease`. A footer links to the attribution text from the manifest.

## 6. How a search works

1. **On page load:** fetch `/data/latest.json` and `/data/<release>/manifest.json` (existing code). These are the same for every visitor.
2. **On the first search:** fetch `districts.csv.gz` and `pharmacies.csv.gz` (both GB-wide, the same for everyone). Verify, decompress and keep them in memory for the session.
3. **Find the area:** take the outward code from the normalised postcode and look up its area code(s) in the districts file. If there isn't one, show "couldn't find".
4. **Download each area** for that district: `postcodes.csv.gz` and `travel.csv.gz`. A district can span two or more areas; download all of them, so the host learns the district's set of areas, which is still area level. Verify against the manifest, then decompress with the native `DecompressionStream('gzip')`. Checked on 19 Nov 2026: the live site serves `.csv.gz` files as `content-type: application/gzip` with no `Content-Encoding`, so `fetch` returns the raw gzip bytes and their SHA-256 matches the manifest. A test should pin this: if a host ever adds `Content-Encoding: gzip`, the check must fail loudly rather than unzip twice.
5. **Find the postcode** in the area that contains it (binary search; the file is sorted). If it's absent, show "couldn't find".
6. **Build the results** from that postcode's travel rows and the pharmacy directory, then render the list.
7. **In parallel with steps 5–6, load the map** for the area that contains the postcode. Fetch every chunk, check each chunk's SHA-256, join them into one `ArrayBuffer`, and give it to the PMTiles reader through a custom in-memory source. MapLibre reads tiles through a registered `pmtiles://` protocol. **There are no HTTP range requests and no per-tile requests.**
8. **Memory:** downloaded files are kept in a session-only in-memory map keyed by path, so searching another postcode in the same area downloads nothing.

**What is never stored:** the app writes nothing to localStorage, sessionStorage, IndexedDB, Cache Storage or cookies in this phase.
- `/data/*` responses are sent with `Cache-Control: no-store`, so a shared device's browser cache doesn't show which areas were looked at. Re-downloading costs nothing on Cloudflare. *Builder's call: a deliberate privacy-over-speed choice; see section 9.*
- App code, the style, fonts and the worker are cached normally, because they're the same for everyone.

**FR-26 ("Clear all data"):** the app stores nothing, so there's nothing to clear in this phase. The control arrives with service mode, which adds the stored service profile.

## 7. Pipeline changes (map files)

### New build step
After the travel tables for each area are built, the step builds `areas/<area>/map.pmtiles` (or its chunks).
- **Bounding box:** the bounding box of the area's postcodes **and** every pharmacy in its travel table, plus a 1 km margin, so pins in neighbouring areas and nations sit on the map.
- **Tool:** tilemaker (already measured) with a pinned version and a checked-in config and Lua process file (`pipeline/maps/`). It produces the OpenMapTiles schema, slimmed as measured:
  - **Included:** roads, road names, water, waterway names, railways, place names, and the coastline and land outline.
  - **Excluded:** buildings, land use, points of interest, boundaries.
  - **Zooms:** maxzoom 13, minzoom about 6 (the builder tunes this).
- **Input:** the same `uk.osm.pbf` and osmium extract the router uses. Coastline shapefiles (if used) are a pinned, checksummed input recorded in `sources`.
- **Splitting:** if the file is over 20 MiB, it's split into byte chunks `map.pmtiles.000`, `.001` and so on, each at most 20 MiB.

### Manifest
Each area entry gains:
```json
"map": {"size": 28102311, "sha256": "<whole file>",
        "parts": [{"path": "areas/S12000017/map.pmtiles.000", "size": 20971520, "sha256": "…"}, …]}
```
An unsplit file has one part, the file itself. The app verifies each part, then the joined whole.

### Checks (FR-04)
- Every built area has a map.
- Every part is under 25 MiB.
- The checksums match.
- The PMTiles header bounds cover the area's postcodes.

### Release packaging
- Maps are published as a **separate asset** on the same GitHub release, `maps-YYYY-MM.tar.gz`, so the data tarball stays as it is and neither file nears GitHub's 2 GB asset limit.
- `deploy.yml` downloads and verifies both assets.
- Only the **latest** release's maps are deployed: the previous release keeps its data (for rollback checks) but the app never reads old maps. *Builder's call, to keep each deployment's size and file count down; if a rollback is ever needed, the maps can be redeployed from that release's asset.*

### Docs
`docs/data-format.md` gains the map files, the manifest fields and the map licence line.

### CI time
Map building runs inside the existing per-shard build job. The builder measures its time on the reference areas and on Highland, and keeps shards within the 350-minute job timeout.

## 8. App structure

The existing folders are kept. *Builder's call on file names:*

- **`lib/engine/`** (pure, unit-tested, 85% coverage or more):
  - CSV parsing of the four file types;
  - postcode lookup;
  - result building and sorting;
  - opening-hours parsing and the three filters;
  - the hidden summary text;
  - distance and time formatting.
- **`lib/data/`:**
  - fetch, verify with `crypto.subtle`, decompress, and the session memory cache;
  - joining map chunks;
  - the PMTiles in-memory source.
- **`lib/ui/`:**
  - `SearchForm`, `ResultsList`, `ResultEntry`, `Filters`, `MapPanel` (MapLibre isolated here, lazily imported after the first search so the first page stays small) and `Messages`.
- **Map assets served from `app/public/map/`:**
  - `style.json`, a hand-written minimal style for the slimmed layers, with calm colours and enough contrast for the pins;
  - `glyphs/{fontstack}/{range}.pbf`: one Regular and one Bold font, OFL-licensed (for example Noto Sans), covering Latin, Latin-1 and General Punctuation only;
  - the MapLibre CSP worker file.
- **Dependencies:**
  - `maplibre-gl` (BSD-3);
  - `pmtiles` (BSD-3) for the reader only.
  - Both are pinned through the lockfile and covered by Dependabot.

## 9. Testing

- **Vitest (engine):**
  - every filter row in section 5, including partial hours, `CLOSED`, past-midnight ranges and multiple filters;
  - unknown pharmacies grouped and never hidden;
  - hidden summary wording, including "closer";
  - sort and tie-breaks (NFR-11);
  - missing routes;
  - postcodes found, absent, or in a district spanning two areas;
  - distance and time formatting;
  - checksum mismatches rejected;
  - chunk joining.
- **Fixture release:** a small checked-in `/data` release built from real public data for two neighbouring reference areas (or a trimmed copy), with a tiny map file. Searched postcodes in tests are treated like client data by the privacy guard. The files stay gzipped (`.csv.gz`), as in a real release. The client-data pre-commit check only looks at `.csv`, `.xlsx` and similar files, so it doesn't block them, and that's correct: they're public reference data, not client data. The e2e setup copies the fixture into the preview build's `/data/`.
- **Playwright** (Edge, Chrome, Firefox and WebKit, as now), using the existing privacy guard (`tests/e2e/fixtures.ts`). Every test fails on any non-GET request, any other host, or a postcode in a URL, header or body. Added tests:
  - a full search shows the list and the map, and pins match the list numbers;
  - **no request URL for the map contains a tile path or a `Range` header**, and the area's map parts are each fetched once, whole;
  - filters, sort and paging;
  - all the error messages;
  - after a search, `location.href`, history, localStorage, sessionStorage, IndexedDB, Cache Storage and cookies hold nothing about it;
  - responses under `/data/` carry `Cache-Control: no-store`;
  - with WebGL disabled (a Chromium launch flag), the map message shows and the list still works;
  - an axe scan on the results page, with filters on and with an error showing;
  - keyboard only: search, change the sort and filters, open the opening hours, page through.
- **Live-site check:** extended to fetch one area's map part and confirm the headers.
- **Pipeline (pytest):**
  - bounding box calculation (includes the pharmacies in neighbouring areas);
  - the splitting rule;
  - manifest map entries;
  - the new checks;
  - a tilemaker integration test on a tiny extract, skipped when tilemaker isn't installed, the same pattern as the OSRM tests.

**Performance targets** (desktop, average broadband): list on screen within 3 s of Search for a typical area, and the map within 6 s. The builder records the numbers for Birmingham, Kent and Highland.

## 10. Later (not in this phase)

These are recorded so this phase's choices don't block them:
- **Service mode** (spec FR-09 to FR-12, FR-14, FR-18, FR-21, FR-23, FR-26; decisions D7, D8, D10, D12) in the same app.
- **More map detail:** footpaths, buildings, shop names, zoom 14–15. Files grow roughly 3–5 times; move them to Cloudflare R2 (free downloads) if Pages limits bite.
- **Downloading neighbouring areas too,** so the host learns only a region.
- **An offline whole-GB version** for frequent users, about 1–1.5 GB (estimated): no search would reveal even the area.
- **Server-backed features** (live hours, address search). Only behind a privacy relay (Oblivious HTTP), a sealed enclave, or private information retrieval, and each needs a spec change to NFR-03.
- **UK walking profile** (master plan section 7) improves walking routes before Phase 4.
- **Privacy notice page and analytics** (master plan section 6).

## 11. Spec changes needed (draft 0.7)

- **Phases:** Phase 2 becomes public search with a map. Service-mode Musts move to Phase 3, together with D7, D8, D10 and D12.
- **FR-13:** describe the public search (map, list, sort, the three filters, the hours-unknown grouping).
- **A new FR for the area map:** whole-file download, no range or tile requests, attribution.
- **FR-08:** the area is chosen automatically from the postcode's district; the files are verified and held in memory, with `no-store` in this phase.
- **Data format and FR-01 to FR-05:** the map files, manifest fields and checks.
- **Acceptance tests:**
  - AC-18: a search makes no tile or range requests;
  - AC-19: the filters never hide pharmacies with unknown hours;
  - AC-20: the list works when WebGL is off.
- **Change log:** a new row.

## 12. Left to the builder

- tilemaker version, zoom range, the exact layer list and the style's colours, within the size targets above. Planetiler is acceptable if it's measurably better and still free of runtime dependencies in the app.
- Font choice (OFL) and glyph ranges.
- Component and file names, and state handling in Svelte 5.
- How the fixture release is produced (a script under `scripts/` is fine).
- Whether pins use circle and symbol layers or a small generated image, provided there's no DOM marker per pin and the CSP doesn't change.

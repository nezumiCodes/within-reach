# Pharmacy service filters, starting with needle and syringe exchange (England)

Status: draft for approval, 24 Nov 2026.

## Why

Within Reach is used by keyworkers in drug and alcohol services. They need to know which nearby pharmacies a client can actually reach, and, as importantly, which of those offer the service the client needs. The first service the user asked for was supervised consumption. The research on 24 Nov 2026 (below) found no usable open source for it in any nation. Needle and syringe exchange is the closest service that does have usable data for England, so it comes first. The design is built so that more services, and more nations, can be added without reworking it.

## What the research found (24 Nov 2026)

- **No dispensing data can show supervised consumption:**
  - NHSBSA's per-pharmacy file only counts services, forms and items;
  - the PHS per-dispenser file leaves out Schedule 2 and 3 drugs;
  - NWSSP only publishes item counts by GP practice.
- **NHS England's Directory of Healthcare Services (DoHS) API, v3**, has the most usable data. In the integration environment, out of 11,227 pharmacies:
  - **1,583 list "Needle and syringe exchange" (SRV0274);**
  - only 1 lists "Supervised consumption of medicines" (SRV0258), and that one is an online pharmacy.

  The content is OGL with attribution. Production access needs NHS approval.
- **Scotland and Wales:** the NHS inform and NHS 111 Wales directories have per-pharmacy services, but their terms don't allow reuse. Requests to NHS 24 and NWSSP were drafted on 24 Nov 2026 and are with the user to send.
- **Supervised consumption in England** is commissioned by councils. A separate plan covers collecting the councils' lists ("option 3", in the research notes). It is not part of this design, but the data model here must be able to take it.

## Goals

1. A **"Needle exchange"** filter in the public search. When it is on, English pharmacies that don't list the service are hidden, and the hidden summary says so.
2. Every postcode's results include **its nearest needle exchange pharmacies with real walking and driving times**, even when they are beyond the usual 5 km candidate list.
3. Scottish and Welsh pharmacies stay listed under **"not known"** when the filter is on, the same pattern as opening hours.
4. **A general model for services:**
   - each service declares its source and which nations it covers;
   - adding supervised consumption (from council lists) or Scottish and Welsh data later means adding data, not redesigning.

## Non-goals

- Supervised consumption, in any nation (no source yet).
- Scottish or Welsh service data (waiting on permission).
- Refreshing service data more often than the monthly release. See "Refresh" below for the open question with NHS England.
- Any other DoHS service in this phase. The model allows them, but each needs its own decision.

## Anti-goals (would make this a failure even if it works)

- **Telling someone there's no needle exchange near them when there is one.** This is why the pipeline routes the nearest service pharmacies instead of filtering only the existing candidates.
- **Implying a pharmacy doesn't offer a service.** The wording is always "not listed", never "doesn't offer". A note by the filter says listings come from pharmacies' NHS website profiles and may be incomplete.
- **The API key leaking** into the repo, logs, the release or the browser.
- **Any change to the privacy model.** The browser still only fetches static files from its own domain.

## Approaches considered

- **A. Filter only the existing candidates.** The smallest change, but in rural areas with 5–6 candidates it would often find nothing, even with a needle exchange 8 km away. Rejected: it breaks the first anti-goal.
- **B. Route each postcode to its nearest service pharmacies (chosen by the user).** The pipeline adds, for each postcode, its nearest pharmacies listing the service, up to 25 km, and routes them like the rest. Results stay real walking and driving times. This costs somewhat larger travel files and longer builds, and the data is fixed for the month.
- **C. Straight-line fallback in the app.** Avoids extra routing, but mixes routed and unrouted results, and brings back straight-line distance across estuaries, which v0.2.0 removed. Rejected.

## Design

### 1. Service data from the DoHS API (pipeline, `fetch`)

- **New source:** the DoHS API v3. Fetch all organisations with `OrganisationTypeId eq 'PHA'`, selecting `ODSCode`, `OrganisationSubType`, `Services` (and `LastUpdatedDates` if present).
  - Pages: `$top=1000`, paged with `$skip`. That's about 12 requests, at most 1 per second.
  - Production base URL: `https://api.service.nhs.uk/service-search-api/`, `api-version=3`, with the header `apikey`.
- **The key** comes from the environment variable `NHS_DOHS_API_KEY`. The pipeline must never log the key, the request headers or full URLs with headers. If the key is missing, `fetch` fails with a clear message. It doesn't skip services silently, unless services are switched off in config (§7).
- **Service codes come from config** (`[services]` in `pipeline/config.toml`), each with a short key, a display name and the DoHS code. For this phase, one entry:
  - key `nsp`
  - name "Needle exchange"
  - DoHS code `SRV0274`
  - nations `["England"]`
- **Matching:** DoHS `ODSCode` is matched to the NHSBSA pharmacy code the pipeline already uses for English pharmacies. The pipeline counts and records:
  - DoHS records with no NHSBSA match;
  - NHSBSA pharmacies with no DoHS record.

  NHSBSA pharmacies with no DoHS record are treated as "not listed" (the service is fixed for that nation), not as unknown. The counts go in the manifest.
- **The snapshot** is cached in `.cache` like the other sources (for example `dohs-services.csv`: `code,services`), with its fetch time. Shards read the cache, not the API: only `prepare` calls the API.

### 2. Pharmacies file

- `pharmacies.csv.gz` gains one column at the end, `services`. It records each configured service **per pharmacy**, separated by `;`:
  - `nsp`: listed;
  - `nsp?`: not known (no source covers this pharmacy);
  - absent: not listed.

  For example, an English pharmacy listing it has `nsp`, an English pharmacy not listing it has an empty cell, and every Scottish and Welsh pharmacy has `nsp?`.
- **Why per pharmacy** (decided by me): council supervised consumption lists will cover some English councils and not others, so "not known" can't be decided by nation. With coverage in the cell, the app needs no nation rules, and later sources (a council list, Scottish or Welsh data) only change what the pipeline writes. The manifest's `nations` field (§4) is just a description for people; the app doesn't use it.
- **Release order:** the current app (v0.2.0) only accepts the exact pharmacies header. So the app that reads both layouts ships first, and only then data with the new column. This is the same order v0.2.0 used for `walk_cycle`.

### 3. Service candidates and routing (option B)

For each postcode and each configured service:

1. **Select by straight line.** `service_min` (config, **5**) is a **total**: service pharmacies already among the postcode's candidates count towards it. (Decided by me: in towns that already have several, this avoids routing and storing pharmacies the postcode doesn't need.) Only if fewer than `service_min` are already there, add the nearest pharmacies listing the service that aren't yet candidates, within `reach_cap_m` (25 km), from all GB pharmacies the service covers, to make up the difference.
2. **Size the extract after selecting.** These service candidates are chosen before the area's map extract is sized, and their locations are added to the points the bounding box is built from. That way they can be routed. (Today the extract is sized from the first-pass candidates, so a pharmacy 20 km away would fall outside it.)
   - **The area map grows to match (decided by the user, 24 Nov 2026).** The map is built from the same extract, so every service pharmacy in the results shows on a detailed map.
   - **Measure first:** before building the full GB release, compare map file sizes before and after on the reference areas, plus Highland (S12000017, the largest map today, 26.8 MB). Record the results in `docs/decisions.md`.
   - **Limit:** maps are already split into 20 MiB parts (`[maps] chunk_bytes`), so file size isn't the constraint; download size is. If the measurement shows a large increase, for example any map growing by more than half, bring the numbers to the user before the full build. Options then include capping how far that area's map grows; far-off service pharmacies would still be listed and routed, but show no pin. No automatic cap is built until the numbers are in.
3. **Route them** in the same pass as the other candidates. Unreachable ones are dropped. If fewer than `service_min` are reachable, widen round by round like `route_reachable` (next nearest listing the service, within the cap and the extract, up to `reach_max_rounds`).
4. **The 40-candidate cap doesn't apply to service rows.** `route_reachable` currently sorts by straight line and keeps the first `max_candidates`, which would cut them. Mark service rows so that cap ignores them: a postcode keeps its 40 nearest plus up to 5 per service. A row can be both nearby and a service pharmacy, and it is stored once.
5. **The travel file layout doesn't change.** Service rows are ordinary rows.
6. Count postcodes that end with fewer than `service_min` reachable service pharmacies, per service and per area. These are expected in remote areas and on islands, not errors.

Edge cases:

- A postcode in Wales or Scotland near the English border still gets English service pharmacies, because selection uses all GB pharmacies the service covers.
- A postcode with no service pharmacy within 25 km gets none. The app then says so, using the wording in §5.

### 4. Manifest

New `config` fields:
- `services`: a list of `{key, name, nations, source, source_fetched_at}`;
- `service_min`.

`source` is the attribution text (§6).

New per-area fields:
- `services.<key>.postcodes_short`: postcodes with fewer than `service_min` reachable service pharmacies.

New top-level counts:
- `services.<key>.listed`: English pharmacies listing the service;
- `services.<key>.unmatched_dohs`: DoHS records with no NHSBSA match;
- `services.<key>.missing_dohs`: NHSBSA pharmacies with no DoHS record.

### 5. App

- **A new "Services" group** in the filter controls, with one checkbox, "Needle exchange". It sits next to the opening-hours checkboxes and is built from `manifest.config.services`, not hard-coded, so later services appear on their own.
- **Filter status for a service, read from the pharmacy's `services` cell (§2):**
  - **match:** `nsp`;
  - **unknown:** `nsp?`;
  - **hidden:** absent.

  It combines with the hours filters by the current rule: hidden if any active filter says hidden, otherwise unknown if any says unknown, otherwise match.
- **Hidden summary:** reason text "not listed for needle exchange", for example "3 closer pharmacies hidden: not listed for needle exchange." With hours filters too, the reasons are joined in the existing order, services after hours.
- **The "not known" group** gets a heading and explanation that name what isn't known:
  - only hours → as today;
  - only a service → heading "Needle exchange not known", text "Scottish and Welsh pharmacy lists don't include services, so these pharmacies can't be filtered.";
  - both → the builder writes one heading and line covering both, in the same style.
- **On each result**, a pharmacy that lists a service shows it (for example "Needle exchange"), whether or not the filter is on.
- **A note under the filter:** "From pharmacies' NHS website listings. Some pharmacies that offer it don't list it. Phone to check."
- **No results:** if the filter hides everything and nothing is unknown, the status message says "No pharmacies listing needle exchange were found within 25 km." The cap distance comes from the manifest.
- **Results order is unchanged:** sorted by walking or driving, as today. Service rows beyond 5 km simply appear further down when the filter is off.

### 6. Attribution and terms

- Footer, and the data notes on the page: "Contains information from NHS England, licensed under the current version of the Open Government Licence." This is the wording NHS England's terms ask for when content is modified.
- Don't use NHS branding, and don't suggest endorsement.

### 7. Rollout, keys and the switch

- **Switch:** `[services] enabled = false` in `pipeline/config.toml` until the production key exists.
  - With it off, the pipeline doesn't call the API, writes an empty `services` column, and writes `services: []` in the manifest. The app shows no Services group.
  - This lets the code merge, and the app ship, before production access.
- **Production key:**
  1. The user requests production access from the NHS website service desk (nhswebsite.servicedesk@nhs.net) and accepts the Online Connection Agreement.
  2. The same email asks whether a monthly refresh is acceptable (see "Refresh" below).
  3. The key is stored as a GitHub **environment** secret, `NHS_DOHS_API_KEY`, in a new environment restricted to `main`. Only the `prepare` job uses that environment.
  4. Creating the environment and secret is a security-settings change, so **ask the user first**.
- **Pipeline runs from other branches** (partial test releases, which are published as public prereleases) always run with services switched off. They never get the production key, and the integration key's data must never be published. (Decided by me.) The feature's pipeline code is tested with unit tests on fixture data, and locally against the integration API. Its first real run is on `main`, after the switch is turned on.
- **Local development** uses the integration key from Keychain (`within-reach-dohs-int`) and the integration base URL, chosen by config or flag. Integration data is never published.
- **Order:**
  1. App release that reads both pharmacy layouts, with services switched off.
  2. Production key.
  3. Switch on and run the pipeline.

### 8. Release checks

- `services.nsp.listed` is at least **1,000** (the test environment has 1,583). This catches an empty or broken API response.
- `services.nsp.listed` is within ±20% of the previous release, once there is one.
- `missing_dohs` is under 10% of English pharmacies.
- Every value in the `services` column is a configured key.
- **Reference cases:**
  - a rural English postcode whose nearest needle exchange is more than 5 km away gets at least one routed service row;
  - a town postcode gets service rows without losing any of its 40 nearest.
  - The builder picks the postcodes from real data.

### Refresh (open, to be settled with NHS England)

NHS England's website terms say cached content "should" be refreshed every 24 hours. This design refreshes monthly, because the routes depend on the service list. The production-access email asks whether monthly is acceptable. If NHS England says no, the planned follow-up is a small daily job that publishes a service list, with which the app hides pharmacies that have dropped a service. Pharmacies that have newly added it would wait for the monthly build.

## Measuring the change

On the three reference areas used for v0.2.0 (Cheshire West and Chester, Medway, Betsi Cadwaladr), before and after, using the integration snapshot locally:
- extra travel rows;
- travel file sizes;
- map file sizes (plus Highland, S12000017);
- build time;
- `postcodes_short`.

The results go in `docs/decisions.md`. A full GB run needs the production key.

## Left to the builder

- Module layout, names, and how service rows are marked inside routing.
- How the widening code is shared between reach and services.
- Exact wording of the combined "not known" heading.
- Placement and styling of the service tag on each result. It must pass the existing axe checks.
- Fixture changes, so the e2e tests can cover the filter (the fixture release must include some `nsp` pharmacies and one postcode whose nearest is more than 5 km away).

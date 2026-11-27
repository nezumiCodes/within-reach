# Within Reach data format

The monthly pipeline publishes a **data release**, served by the site under `/data/`. Everything here is built from public data and contains no client information.

Files are gzipped UTF-8 CSV with a header row. Rebuilding from the same inputs gives byte-identical files. A blank cell means *unknown*.

```
data/latest.json                               {"release": "2026-12", "previous": "2026-11" | null}
data/<release>/manifest.json                   what was built, from what, with checksums
data/<release>/pharmacies.csv.gz               the GB pharmacy directory
data/<release>/districts.csv.gz                postcode district -> area(s)
data/<release>/areas/<area>/postcodes.csv.gz   live postcodes in one area
data/<release>/areas/<area>/travel.csv.gz      nearby pharmacies for each of those postcodes
data/<release>/areas/<area>/map.pmtiles        the area's street map (or map.pmtiles.000, .001, …)
```

Everything under `/data/` is served with `Cache-Control: no-store`, so the browser never keeps it.

## pharmacies.csv.gz

`ph_idx,nation,code,name,address,postcode,lat,lon,mon,tue,wed,thu,fri,sat,sun,services`

- `ph_idx`: 0-based row number, used by `travel.csv.gz`. It's only stable within one release.
- `nation` + `code` identify a pharmacy. The code is the ODS code in England and Wales, and the PHS dispenser code in Scotland.
- `lat`/`lon`: the centre of the pharmacy's postcode (WGS84, 6 decimals).
- Day columns:
  - blank: unknown. The Scottish and Welsh lists have no hours, and some English values can't be read.
  - `CLOSED`: closed that day.
  - otherwise, opening ranges such as `09:00-13:00;14:00-17:30`.
- `services`: the pharmacy's status for each configured service (see below).
- Excluded: dispensing appliance contractors, and English online-only (distance-selling) pharmacies.

### The `services` column

Releases before the first with services have no `services` column. The app reads both layouts.

- Keys match `[a-z0-9_]+` and are unique. The pipeline's config loader rejects anything else, and the app's parser accepts only the same grammar.
- The cell is a list of keys joined by `;`:
  - `key`: the pharmacy lists the service;
  - `key?`: not known, because no source covers this pharmacy;
  - key absent: not listed.
- Example: `nsp` (listed), `nsp?` (not known), blank (not listed).
- Needle exchange has the key `nsp`. Its source is the NHS England Directory of Healthcare Services (DoHS) API, service code `SRV0274`, which covers England only.
  - An English pharmacy with no DoHS record gets an empty cell (not listed). It is counted in `missing_dohs` in the manifest.
  - Every Scottish and Welsh pharmacy gets `nsp?`.
- With services switched off (`[services] enabled = false` in `pipeline/config.toml`), every cell is empty.
- "Not listed" means only that the pharmacy's NHS website listing doesn't include the service. Some pharmacies that offer it don't list it.

## districts.csv.gz

`outward,area_codes`. For each postcode district (for example `CH1`), the space-separated area codes that contain its live postcodes. The app uses it to tell a user which area to load for a postcode that isn't loaded yet.

## areas/<area>/postcodes.csv.gz

`pc_idx,postcode,lat,lon`, sorted by postcode. `pc_idx` is the 0-based row number within this file.

Areas are upper-tier councils in England, councils in Scotland and health boards in Wales.

## areas/<area>/travel.csv.gz

`pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s,walk_cycle`

Releases before December 2026 have no `walk_cycle` column. The app reads both layouts.

Rows are grouped by `pc_idx`. Within a postcode they're ordered by `straight_m`, then nation, then code.

For each postcode, the file lists every pharmacy within 5 km in a straight line, up to the nearest 40. If that gives fewer than 5, it lists the nearest 5 at any distance instead. Pharmacies in neighbouring areas and nations are included.

Some of the nearest pharmacies can't be reached, for example across an estuary. If a postcode can reach fewer than 5 of its pharmacies on foot or by car, the next nearest are added and routed, up to 25 km in a straight line and within the area's map extract, for at most 4 rounds. The unreachable ones are then dropped. A postcode that can reach none keeps its original list, with blank routes.

Services add rows to this list. For each configured service, a postcode is also given its nearest `service_min` (5) pharmacies that list it, up to `reach_cap_m` (25 km) in a straight line. `service_min` is a total: pharmacies that list the service and are already among the candidates count towards it.

- Service rows are ordinary rows, so the layout doesn't change.
- They are exempt from the 40-candidate cap, so a postcode keeps its 40 nearest plus up to `service_min` per service. A pharmacy that is both nearby and a service pharmacy is stored once.
- They are chosen before the area's map extract is sized, so the extract (and the map) covers them.
- They don't count towards the "at least 5 reachable" widening above. Otherwise distant service rows could push out nearer pharmacies (the Allhallows case, ME3 9EJ).
- Each service widens on its own if fewer than `service_min` of its pharmacies can be reached: the next nearest listing it are added and routed, within the cap and the extract, for at most `reach_max_rounds` rounds.
- A postcode with fewer than `service_min` reachable pharmacies for a service is counted in `services.<key>.postcodes_short` (see the manifest).

- `straight_m`: straight-line metres
- `walk_m` and `walk_s`: walking metres and seconds. They use UK walking rules (`foot-gb`, in `pipeline/osrm/foot-gb.lua`): OSRM's foot profile, plus cycle paths (unless tagged `foot=no`), bridleways, and trunk roads where a pavement is mapped.
- `drive_s`: driving seconds (OSRM car profile)
- `walk_cycle`: `1` when the best walk needs a cycle path not signed for walkers (no `foot=yes`, `designated` or `permissive`), meaning that avoiding it is impossible or adds more than 50 m. Otherwise blank.
- A blank walk or drive cell means no route was found, for example to an island with no ferry in the map data.

## areas/<area>/map.pmtiles

The area's street map as a vector [PMTiles](https://github.com/protomaps/PMTiles) v3 file, built by tilemaker with the OpenMapTiles schema and slimmed to roads, road names, water, railways and place names, up to zoom 13. It covers the area's postcodes and every pharmacy listed for them, plus 1 km.

The app downloads the whole file and reads it from memory. It never asks for parts of it (no HTTP range requests or tiles), so the host learns only which area was looked at.

A map over 20 MiB is split into plain byte chunks, `map.pmtiles.000`, `.001` and so on. Joining them in order gives the original file.

## manifest.json

The manifest records:
- the release name and build time
- each source's label, URL and SHA-256
- the catchment settings and OSRM version, and in `config`: `walk_profile` (`foot-gb`), `reach_cap_m`, `reach_max_rounds` and `cycle_note_min_extra_m`
- in `config`, for services: `services` (a list of `{key, name, nations, source, source_fetched_at}`, where `source` is the attribution text and `source_fetched_at` is when the DoHS snapshot was taken) and `service_min`
- attribution text
- pharmacy counts per nation
- pharmacies that couldn't be geocoded
- the number of opening-hours values that couldn't be read
- the number of online-only pharmacies excluded
- `services`, top level: for each service key, `listed` (English pharmacies listing it), `unmatched_dohs` (DoHS records with no NHSBSA match) and `missing_dohs` (English pharmacies with no DoHS record)
- for each area: its code, name, nation, postcode count, pair count, and each file's path, SHA-256 and size
- for each area, three counts: `postcodes_without_walk` (no walking route to any listed pharmacy), `postcodes_without_route` (neither walking nor driving), and `postcodes_widened_to_cap` (postcodes that reach some pharmacies, but fewer than 5, after widening the search as far as it goes)
- for each area, `services.<key>.postcodes_short`: postcodes with fewer than `service_min` reachable pharmacies listing the service. These are expected in remote areas and on islands.
- for each area with a map, `map`: the whole map's `bytes` and `sha256`, and `parts`, each with `path`, `sha256` and `bytes`
- `config.maps`: `tilemaker` when maps were built, otherwise `none`
- `all_area_codes` (every area in Great Britain) and `complete`, which is true only when every one of them was built. Partial releases are published under a `data-YYYY-MM-partial` tag for testing and are never served by the site.

The app checks every file it downloads against these checksums.

With services switched off, the manifest has `config.services = []`, `config.service_min = 0` and `services = {}`, and each area's `services` is `{}`.

## Release assets

Each monthly GitHub release has two archives, each with a `.sha256` file:
- `data-YYYY-MM.tar.gz`: everything above except the map files;
- `maps-YYYY-MM.tar.gz`: only the map files.

The site serves the latest two data releases, and maps for the latest only.

## Licences

- Contains public sector information licensed under the Open Government Licence v3.0 (ONS Postcode Directory, NHSBSA, Public Health Scotland, NHS ODS).
- When services are on, the manifest's attribution adds: Contains information from NHS England, licensed under the current version of the Open Government Licence.
- Contains OS data © Crown copyright and database right.
- The travel tables are derived from © OpenStreetMap contributors data and are offered under the Open Database Licence (ODbL).
- Map files: © OpenStreetMap contributors (ODbL), including sea areas from osmdata.openstreetmap.de; schema OpenMapTiles (CC-BY 4.0).

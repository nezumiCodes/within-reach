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

`ph_idx,nation,code,name,address,postcode,lat,lon,mon,tue,wed,thu,fri,sat,sun`

- `ph_idx`: 0-based row number, used by `travel.csv.gz`. It's only stable within one release.
- `nation` + `code` identify a pharmacy. The code is the ODS code in England and Wales, and the PHS dispenser code in Scotland.
- `lat`/`lon`: the centre of the pharmacy's postcode (WGS84, 6 decimals).
- Day columns:
  - blank: unknown. The Scottish and Welsh lists have no hours, and some English values can't be read.
  - `CLOSED`: closed that day.
  - otherwise, opening ranges such as `09:00-13:00;14:00-17:30`.
- Excluded: dispensing appliance contractors, and English online-only (distance-selling) pharmacies.

## districts.csv.gz

`outward,area_codes`. For each postcode district (for example `CH1`), the space-separated area codes that contain its live postcodes. The app uses it to tell a user which area to load for a postcode that isn't loaded yet.

## areas/<area>/postcodes.csv.gz

`pc_idx,postcode,lat,lon`, sorted by postcode. `pc_idx` is the 0-based row number within this file.

Areas are upper-tier councils in England, councils in Scotland and health boards in Wales.

## areas/<area>/travel.csv.gz

`pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s`

Rows are grouped by `pc_idx`. Within a postcode they're ordered by `straight_m`, then nation, then code.

For each postcode, the file lists every pharmacy within 5 km in a straight line, up to the nearest 40. If that gives fewer than 5, it lists the nearest 5 at any distance instead. Pharmacies in neighbouring areas and nations are included.

- `straight_m`: straight-line metres
- `walk_m` and `walk_s`: walking metres and seconds (OSRM foot profile)
- `drive_s`: driving seconds (OSRM car profile)
- A blank walk or drive cell means no route was found, for example to an island with no ferry in the map data.

## areas/<area>/map.pmtiles

The area's street map as a vector [PMTiles](https://github.com/protomaps/PMTiles) v3 file, built by tilemaker with the OpenMapTiles schema and slimmed to roads, road names, water, railways and place names, up to zoom 13. It covers the area's postcodes and every pharmacy listed for them, plus 1 km.

The app downloads the whole file and reads it from memory. It never asks for parts of it (no HTTP range requests or tiles), so the host learns only which area was looked at.

A map over 20 MiB is split into plain byte chunks, `map.pmtiles.000`, `.001` and so on. Joining them in order gives the original file.

## manifest.json

The manifest records:
- the release name and build time
- each source's label, URL and SHA-256
- the catchment settings and OSRM version
- attribution text
- pharmacy counts per nation
- pharmacies that couldn't be geocoded
- the number of opening-hours values that couldn't be read
- the number of online-only pharmacies excluded
- for each area: its code, name, nation, postcode count, pair count, and each file's path, SHA-256 and size
- for each area with a map, `map`: the whole map's `bytes` and `sha256`, and `parts`, each with `path`, `sha256` and `bytes`
- `config.maps`: `tilemaker` when maps were built, otherwise `none`
- `all_area_codes` (every area in Great Britain) and `complete`, which is true only when every one of them was built. Partial releases are published under a `data-YYYY-MM-partial` tag for testing and are never served by the site.

The app checks every file it downloads against these checksums.

## Release assets

Each monthly GitHub release has two archives, each with a `.sha256` file:
- `data-YYYY-MM.tar.gz`: everything above except the map files;
- `maps-YYYY-MM.tar.gz`: only the map files.

The site serves the latest two data releases, and maps for the latest only.

## Licences

- Contains public sector information licensed under the Open Government Licence v3.0 (ONS Postcode Directory, NHSBSA, Public Health Scotland, NHS ODS).
- Contains OS data © Crown copyright and database right.
- The travel tables are derived from © OpenStreetMap contributors data and are offered under the Open Database Licence (ODbL).
- Map files: © OpenStreetMap contributors (ODbL), including sea areas from osmdata.openstreetmap.de; schema OpenMapTiles (CC-BY 4.0).

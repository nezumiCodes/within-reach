# Reference postcodes

`expectations.toml` holds 10 postcodes around Chester and Wrexham, chosen to cover a city centre, suburbs, both sides of the England–Wales border and two rural towns. Every monthly run checks them (`check --reference`), and the release is not published if any case fails.

For each postcode:

- `nearest`: the three nearest pharmacies on foot, as `Nation:code`. Order is not compared, because pharmacies a few tens of metres apart swap places when OpenStreetMap paths are edited.
- `walk_m_range`: the shortest walk in metres, ±15% of the value in the November 2026 build.

## How they were checked

The November 2026 results were checked by hand on 17 November 2026 using walking directions on openstreetmap.org, and on Google Maps for CH4 0QN, which OpenStreetMap's search doesn't find. The nearest pharmacy on foot matched for every postcode, including these near-ties:

- CH4 8PU (Saltney): Owen's CH4 8BJ (1,394 m) and Morrisons CH4 8RU across the border (1,413 m).
- LL11 2AW (Rhosddu): Superdrug LL11 1SA (1,086 m) and Rowlands LL11 2NS (1,135 m).

## When a case fails

1. Check the postcode on a map. A pharmacy may have opened, closed or moved, which is a real change.
2. If the data is right, update the case, record the date here and say why in the commit message.
3. If it's wrong, don't publish. Look at what changed in the source lists or the OSM extract.

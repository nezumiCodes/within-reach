# Within Reach pipeline

Turns public data (ONSPD, the three national pharmacy lists, OpenStreetMap) into per-area static bundles. It handles public data only.

The stages are built in Phase 1. Run the checks with `uv run pytest . ../scripts`, `uv run ruff check . ../scripts` and `uv run mypy`.

## Area maps

`build --maps tilemaker` also builds each area's street map (`areas/<code>/map.pmtiles`, see `docs/data-format.md`). It needs Docker, the water polygons that `fetch` downloads into `.cache/coastline/`, and the tilemaker image pinned in `config.toml`. The tilemaker settings are in `maps/config-openmaptiles.json`.

The test that runs real tilemaker is skipped unless you set `RUN_TILEMAKER=1`, in the same way as `RUN_OSRM=1` for the routing tests.

To regenerate the app's test data from a published release, see `scripts/make_fixture_release.py`.

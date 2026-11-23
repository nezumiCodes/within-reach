"""Real OSRM in Docker on Rutland's map. Run with RUN_OSRM=1 (needs Docker and network)."""

import os
from pathlib import Path

import pytest

from within_reach_pipeline.config import load_config
from within_reach_pipeline.http import HttpxFetcher
from within_reach_pipeline.routing import LatLon
from within_reach_pipeline.routing.osrm import OsrmRouter, osrm_server

pytestmark = [
    pytest.mark.osrm,
    pytest.mark.skipif(os.environ.get("RUN_OSRM") != "1", reason="set RUN_OSRM=1 to run"),
]
RUTLAND = "https://download.geofabrik.de/europe/united-kingdom/england/rutland-latest.osm.pbf"
OAKHAM, UPPINGHAM = (52.6699, -0.7280), (52.5870, -0.7230)


def test_osrm_rutland_end_to_end(tmp_path: Path) -> None:
    config = load_config()
    fetcher = HttpxFetcher(config.user_agent)
    pbf = tmp_path / "rutland.osm.pbf"
    fetcher.download(RUTLAND, pbf)
    with osrm_server(pbf, "foot", config.osrm_image, port=5091) as base_url:
        result = OsrmRouter(base_url, fetcher, profile="foot").table([OAKHAM], [UPPINGHAM])
    walk_m = result.distances_m[0][0]
    assert walk_m is not None and 9_000 <= walk_m <= 14_000


def test_osrm_accepts_large_tables(tmp_path: Path) -> None:
    """250 sources x 200 destinations (a ~10 KB URL), larger than any tile the pipeline sends."""
    import random

    config = load_config()
    fetcher = HttpxFetcher(config.user_agent)
    pbf = tmp_path / "rutland.osm.pbf"
    fetcher.download(RUTLAND, pbf)
    rng = random.Random(1)  # noqa: S311 - test coordinates, not security

    def points(n: int) -> list[tuple[float, float]]:
        return [(rng.uniform(52.56, 52.74), rng.uniform(-0.80, -0.50)) for _ in range(n)]

    with osrm_server(pbf, "foot", config.osrm_image, port=5092) as base_url:
        result = OsrmRouter(base_url, fetcher, profile="foot").table(points(250), points(200))
    assert len(result.distances_m) == 250 and len(result.distances_m[0]) == 200


# UK walking rules (pipeline/osrm/foot-gb.lua). Each scenario is its own little network: a
# residential stub at each end, joined only by the way under test, so a route exists exactly
# when that way is walkable. The points sit on the stubs' outer ends, so they always snap to a
# walkable street, whichever profile is loaded.
SCENARIOS: dict[str, dict[str, str]] = {
    "cycle": {"highway": "cycleway"},
    "cycle_no": {"highway": "cycleway", "foot": "no"},
    "cycle_signed": {"highway": "cycleway", "foot": "designated"},
    "bridle": {"highway": "bridleway"},
    "trunk_bare": {"highway": "trunk"},
    "trunk_pavement": {"highway": "trunk", "sidewalk": "both"},
    "trunk_foot": {"highway": "trunk", "sidewalk": "no", "foot": "designated"},
    "street": {"highway": "residential"},
    "detour": {"highway": "cycleway"},  # plus a residential way round, about three times longer
}
BASE_LAT, BASE_LON = 53.0, -2.9
STEP_LON = 0.02  # about 1.3 km between scenarios
STUB, LINK = 0.001, 0.0036  # degrees of latitude: about 110 m and 400 m


def _walk_rules_osm(path: Path) -> dict[str, tuple[LatLon, LatLon]]:
    nodes: list[str] = []
    ways: list[str] = []
    ends: dict[str, tuple[LatLon, LatLon]] = {}
    next_id = iter(range(1, 10_000))

    def node(lat: float, lon: float) -> int:
        i = next(next_id)
        nodes.append(f'<node id="{i}" version="1" lat="{lat:.7f}" lon="{lon:.7f}"/>')
        return i

    def way(refs: list[int], tags: dict[str, str]) -> None:
        nd = "".join(f'<nd ref="{r}"/>' for r in refs)
        tg = "".join(f'<tag k="{k}" v="{v}"/>' for k, v in tags.items())
        ways.append(f'<way id="{next(next_id)}" version="1">{nd}{tg}</way>')

    for n, (name, tags) in enumerate(SCENARIOS.items()):
        lon = BASE_LON + n * STEP_LON
        a_out, a_in = node(BASE_LAT, lon), node(BASE_LAT + STUB, lon)
        b_in = node(BASE_LAT + STUB + LINK, lon)
        b_out = node(BASE_LAT + 2 * STUB + LINK, lon)
        way([a_out, a_in], {"highway": "residential"})
        way([a_in, b_in], tags)
        way([b_in, b_out], {"highway": "residential"})
        if name == "detour":
            east = lon + 0.006  # about 400 m east, so the way round is about 1.2 km
            c1, c2 = node(BASE_LAT + STUB, east), node(BASE_LAT + STUB + LINK, east)
            way([a_in, c1, c2, b_in], {"highway": "residential"})
        ends[name] = ((BASE_LAT, lon), (BASE_LAT + 2 * STUB + LINK, lon))
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="test">'
    path.write_text(xml + "".join(nodes) + "".join(ways) + "</osm>\n", encoding="utf-8")
    return ends


def test_walk_rules_foot_gb_against_stock(tmp_path: Path) -> None:
    from within_reach_pipeline.routing.osrm import area_bbox, clip_extract

    config = load_config()
    fetcher = HttpxFetcher(config.user_agent)
    ends = _walk_rules_osm(tmp_path / "walk.osm")
    points = [p for pair in ends.values() for p in pair]
    gb_dir, stock_dir = tmp_path / "gb", tmp_path / "stock"
    gb_pbf = clip_extract(tmp_path / "walk.osm", area_bbox(points), gb_dir / "walk.osm.pbf")
    stock_dir.mkdir()
    stock_pbf = stock_dir / "walk.osm.pbf"
    stock_pbf.write_bytes(gb_pbf.read_bytes())

    with (
        osrm_server(gb_pbf, "foot", config.osrm_image, port=5093) as gb_url,
        osrm_server(
            stock_pbf, "foot", config.osrm_image, port=5094, profile_path="/opt/foot.lua"
        ) as stock_url,
    ):
        gb = OsrmRouter(gb_url, fetcher, profile="foot")
        stock_router = OsrmRouter(stock_url, fetcher, profile="foot")

        def walk(name: str, exclude: str | None = None) -> int | None:
            a, b = ends[name]
            return gb.table([a], [b], exclude=exclude).distances_m[0][0]

        def stock(name: str) -> int | None:
            a, b = ends[name]
            return stock_router.table([a], [b]).distances_m[0][0]

        assert walk("cycle") is not None and stock("cycle") is None
        assert walk("cycle", exclude="cycleway") is None
        assert walk("cycle_no") is None
        assert walk("cycle_signed") is not None
        assert walk("cycle_signed", exclude="cycleway") == walk("cycle_signed")  # not classed
        assert walk("bridle") is not None
        assert walk("trunk_bare") is None
        assert walk("trunk_pavement") is not None
        assert walk("trunk_foot") is not None  # the foot tag wins over sidewalk=no
        assert walk("street") == stock("street")
        direct, round_ = walk("detour"), walk("detour", exclude="cycleway")
        assert direct is not None and round_ is not None and round_ > direct + 500
        assert stock("detour") == round_

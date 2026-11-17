"""Real OSRM in Docker on Rutland's map. Run with RUN_OSRM=1 (needs Docker and network)."""

import os
from pathlib import Path

import pytest

from within_reach_pipeline.config import load_config
from within_reach_pipeline.http import HttpxFetcher
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

from pathlib import Path
from typing import Any

import pytest

from within_reach_pipeline.routing.osrm import OsrmRouter, area_bbox, osmium_extract_command


class RecordingFetcher:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.urls: list[str] = []

    def get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        self.urls.append(url)
        return self.response

    def get_text(self, url: str) -> str:
        raise NotImplementedError

    def download(self, url: str, dest: Path) -> str:
        raise NotImplementedError


def test_osrm_url_format() -> None:
    fetcher = RecordingFetcher(
        {"code": "Ok", "distances": [[1.0], [2.0]], "durations": [[3.0], [4.0]]}
    )
    router = OsrmRouter("http://localhost:5000", fetcher, profile="foot")
    router.table([(53.19, -2.89), (53.20, -2.88)], [(53.05, -3.0)])
    assert fetcher.urls == [
        "http://localhost:5000/table/v1/foot/-2.89,53.19;-2.88,53.2;-3.0,53.05"
        "?sources=0;1&destinations=2&annotations=distance,duration"
    ]


def test_osrm_values_rounded_and_nulls_become_none() -> None:
    fetcher = RecordingFetcher(
        {"code": "Ok", "distances": [[1234.5, None]], "durations": [[600.4, None]]}
    )
    result = OsrmRouter("http://x", fetcher, profile="car").table(
        [(53.0, -2.0)], [(53.1, -2.0), (53.2, -2.0)]
    )
    assert result.distances_m == [[1235, None]]
    assert result.durations_s == [[600, None]]


def test_osrm_error_code_raises() -> None:
    fetcher = RecordingFetcher({"code": "InvalidQuery", "message": "bad"})
    with pytest.raises(RuntimeError, match="InvalidQuery"):
        OsrmRouter("http://x", fetcher, profile="foot").table([(53.0, -2.0)], [(53.1, -2.0)])


def test_area_bbox_margin() -> None:
    min_lon, min_lat, max_lon, max_lat = area_bbox([(53.0, -2.0), (53.1, -1.9)], margin_m=3000)
    assert min_lat == pytest.approx(53.0 - 0.02698, abs=1e-4)
    assert max_lat == pytest.approx(53.1 + 0.02698, abs=1e-4)
    assert min_lon < -2.0 - 0.044 and max_lon > -1.9 + 0.044  # wider in degrees at 53°N


def test_osmium_extract_command() -> None:
    cmd = osmium_extract_command(
        Path("/in/uk.osm.pbf"), (-3.1, 52.9, -2.7, 53.3), Path("/out/area.osm.pbf")
    )
    assert cmd == [
        "osmium",
        "extract",
        "--strategy",
        "smart",
        "-b",
        "-3.1,52.9,-2.7,53.3",
        "/in/uk.osm.pbf",
        "-o",
        "/out/area.osm.pbf",
        "--overwrite",
    ]


def test_osmium_runs_in_docker_when_not_installed() -> None:
    from within_reach_pipeline.routing.osrm import OSMIUM_IMAGE, osmium_command

    cmd = osmium_command(
        Path("/in/uk.osm.pbf"), (-3.1, 52.9, -2.7, 53.3), Path("/out/area.osm.pbf"), native=False
    )
    assert cmd == [
        "docker",
        "run",
        "--rm",
        "-v",
        "/in:/in:ro",
        "-v",
        "/out:/out",
        OSMIUM_IMAGE,
        "osmium",
        "extract",
        "--strategy",
        "smart",
        "-b",
        "-3.1,52.9,-2.7,53.3",
        "/in/uk.osm.pbf",
        "-o",
        "/out/area.osm.pbf",
        "--overwrite",
    ]


def test_osmium_native_when_installed() -> None:
    from within_reach_pipeline.routing.osrm import osmium_command

    cmd = osmium_command(
        Path("/in/uk.osm.pbf"), (0.0, 1.0, 2.0, 3.0), Path("/o/a.pbf"), native=True
    )
    assert cmd[0] == "osmium"

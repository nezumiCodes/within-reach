from pathlib import Path
from typing import Any

import pytest

from within_reach_pipeline.routing.osrm import (
    PROFILE_DIR,
    OsrmRouter,
    area_bbox,
    extract_command,
    osmium_extract_command,
)


class RecordingFetcher:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.urls: list[str] = []

    def get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
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
        "http://localhost:5000/table/v1/foot/-2.890000,53.190000;-2.880000,53.200000;"
        "-3.000000,53.050000"
        "?sources=0;1&destinations=2&annotations=distance,duration"
    ]


def test_osrm_coordinates_near_greenwich_are_plain_decimals() -> None:
    # Python prints -0.000077 as "-7.7e-05", which OSRM rejects as InvalidQuery
    # (first full GB run, Lewisham, 18 Nov 2026).
    fetcher = RecordingFetcher({"code": "Ok", "distances": [[1.0]], "durations": [[1.0]]})
    OsrmRouter("http://x", fetcher, profile="foot").table([(51.421856, -0.000077)], [(51.4, 5e-05)])
    assert "/-0.000077,51.421856;0.000050,51.400000?" in fetcher.urls[0]
    assert "e-" not in fetcher.urls[0]


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
        "-3.100000,52.900000,-2.700000,53.300000",
        "/in/uk.osm.pbf",
        "-o",
        "/out/area.osm.pbf",
        "--overwrite",
    ]


def test_osmium_bbox_near_greenwich_is_plain_decimals() -> None:
    cmd = osmium_extract_command(Path("/in.pbf"), (-0.00004, 51.3, 0.2, 51.6), Path("/out.pbf"))
    assert cmd[cmd.index("-b") + 1] == "-0.000040,51.300000,0.200000,51.600000"


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
        "-3.100000,52.900000,-2.700000,53.300000",
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


def test_extract_command_mounts_profiles_and_uses_foot_gb(tmp_path: Path) -> None:
    cmd = extract_command(tmp_path, "foot", "img:1")
    assert f"{PROFILE_DIR}:/profiles:ro" in cmd
    assert cmd[-3:] == ["-p", "/profiles/foot-gb.lua", "/data/area.osm.pbf"]


def test_extract_command_car_keeps_stock_profile(tmp_path: Path) -> None:
    assert extract_command(tmp_path, "car", "img:1")[-3:] == [
        "-p",
        "/opt/car.lua",
        "/data/area.osm.pbf",
    ]


def test_profile_file_exists() -> None:
    assert (PROFILE_DIR / "foot-gb.lua").is_file()


def test_table_exclude_in_url() -> None:
    fetcher = RecordingFetcher({"code": "Ok", "distances": [[1.0]], "durations": [[1.0]]})
    OsrmRouter("http://x", fetcher, profile="foot").table(
        [(53.0, -2.9)], [(53.1, -2.9)], exclude="cycleway"
    )
    assert fetcher.urls[-1].endswith("&annotations=distance,duration&exclude=cycleway")


def test_table_without_exclude_has_no_param() -> None:
    fetcher = RecordingFetcher({"code": "Ok", "distances": [[1.0]], "durations": [[1.0]]})
    OsrmRouter("http://x", fetcher, profile="foot").table([(53.0, -2.9)], [(53.1, -2.9)])
    assert "exclude" not in fetcher.urls[-1]

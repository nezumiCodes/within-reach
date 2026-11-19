import hashlib
import os
import struct
from pathlib import Path

import pytest

from within_reach_pipeline.config import load_config
from within_reach_pipeline.http import HttpxFetcher
from within_reach_pipeline.maps import (
    MAP_CONFIG,
    build_area_map,
    map_bbox,
    pmtiles_bounds,
    tilemaker_command,
    write_map_entry,
)

RUTLAND = "https://download.geofabrik.de/europe/united-kingdom/england/rutland-latest.osm.pbf"


def test_map_bbox_has_1km_margin() -> None:
    box = map_bbox([(53.0, -3.0), (53.1, -2.9)])
    assert box[1] == pytest.approx(53.0 - 1000 / 111_195.0)
    assert box[3] == pytest.approx(53.1 + 1000 / 111_195.0)


def test_tilemaker_command_uses_plain_decimal_bbox(tmp_path: Path) -> None:
    cmd = tilemaker_command(
        "img@sha256:x",
        tmp_path / "a.osm.pbf",
        (-0.000077, 51.0, 0.1, 51.2),
        tmp_path / "c.json",
        tmp_path / "coastline",
        tmp_path / "out" / "map.pmtiles",
    )
    assert cmd[cmd.index("--bbox") + 1] == "-0.000077,51.000000,0.100000,51.200000"
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert "img@sha256:x" in cmd
    assert "resources/process-openmaptiles.lua" in cmd


def test_large_map_is_split_into_numbered_chunks(tmp_path: Path) -> None:
    built = tmp_path / "built.pmtiles"
    built.write_bytes(bytes(range(10)))
    entry = write_map_entry(tmp_path / "rel", "E06000050", built, chunk_bytes=4)
    assert [p["path"] for p in entry["parts"]] == [
        "areas/E06000050/map.pmtiles.000",
        "areas/E06000050/map.pmtiles.001",
        "areas/E06000050/map.pmtiles.002",
    ]
    assert [p["bytes"] for p in entry["parts"]] == [4, 4, 2]
    assert entry["bytes"] == 10
    assert entry["sha256"] == hashlib.sha256(bytes(range(10))).hexdigest()
    joined = b"".join((tmp_path / "rel" / p["path"]).read_bytes() for p in entry["parts"])
    assert joined == bytes(range(10))


def test_map_at_or_under_chunk_size_is_not_split(tmp_path: Path) -> None:
    built = tmp_path / "built.pmtiles"
    built.write_bytes(b"abcd")
    entry = write_map_entry(tmp_path / "rel", "E06000050", built, chunk_bytes=4)
    assert [p["path"] for p in entry["parts"]] == ["areas/E06000050/map.pmtiles"]
    assert entry["parts"][0]["sha256"] == entry["sha256"]
    assert (tmp_path / "rel" / "areas/E06000050/map.pmtiles").read_bytes() == b"abcd"


def test_pmtiles_bounds_reads_v3_header() -> None:
    header = bytearray(127)
    header[:7] = b"PMTiles"
    header[7] = 3
    struct.pack_into("<iiii", header, 102, -30_000_000, 530_000_000, -28_000_000, 532_000_000)
    assert pmtiles_bounds(bytes(header)) == (-3.0, 53.0, -2.8, 53.2)


def test_pmtiles_bounds_rejects_other_files() -> None:
    with pytest.raises(ValueError):
        pmtiles_bounds(b"not a pmtiles file".ljust(127, b"\0"))


def test_build_area_map_bbox_covers_neighbouring_pharmacies(tmp_path: Path) -> None:
    commands: list[list[str]] = []
    points = [(53.19, -2.89), (53.20, -2.88), (53.05, -3.0)]  # last: a pharmacy over the border
    build_area_map(
        "img",
        tmp_path / "a.osm.pbf",
        points,
        tmp_path / "c.json",
        tmp_path / "coastline",
        tmp_path / "out" / "map.pmtiles",
        run=commands.append,
    )
    box = [float(v) for v in commands[0][commands[0].index("--bbox") + 1].split(",")]
    assert box[0] < -3.0 < box[2] and box[1] < 53.05 < box[3]
    assert (tmp_path / "out").is_dir()


@pytest.mark.skipif(os.environ.get("RUN_TILEMAKER") != "1", reason="set RUN_TILEMAKER=1 to run")
def test_tilemaker_end_to_end(tmp_path: Path) -> None:
    """Real tilemaker in Docker on Rutland, with an empty coastline folder (Rutland is inland)."""
    config = load_config()
    pbf = tmp_path / "rutland.osm.pbf"
    HttpxFetcher(config.user_agent).download(RUTLAND, pbf)
    coastline = tmp_path / "coastline"
    coastline.mkdir()
    dest = tmp_path / "out" / "map.pmtiles"
    points = [(52.6699, -0.7280), (52.5870, -0.7230)]
    build_area_map(config.tilemaker_image, pbf, points, MAP_CONFIG, coastline, dest)
    header = dest.read_bytes()[:127]
    assert header.startswith(b"PMTiles")
    west, south, east, north = pmtiles_bounds(header)
    assert west <= -0.7280 <= east and south <= 52.5870 <= north

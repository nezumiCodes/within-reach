"""Whole-area map files (Phase 2 design, section 7).

Each area gets one slimmed vector map (PMTiles, OpenMapTiles schema, maxzoom 13) built by
tilemaker from the same osmium extract the router uses. The browser downloads the whole file,
so the host only learns which area was looked at. Files over the chunk size are split into
plain byte chunks that the browser joins back together.
"""

import hashlib
import struct
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from within_reach_pipeline.routing import LatLon
from within_reach_pipeline.routing.osrm import BBox, area_bbox, coord

MAP_MARGIN_M = 1000
PMTILES_HEADER_BYTES = 127
MAP_CONFIG = Path(__file__).resolve().parents[2] / "maps" / "config-openmaptiles.json"


def map_bbox(points: Sequence[LatLon]) -> BBox:
    """The area's postcodes and every pharmacy listed for them, plus a 1 km margin."""
    return area_bbox(points, margin_m=MAP_MARGIN_M)


def tilemaker_command(
    image: str, pbf: Path, bbox: BBox, config: Path, coastline: Path, dest: Path
) -> list[str]:
    mounts = [
        "-v",
        f"{pbf.parent}:/input:ro",
        "-v",
        f"{config.parent}:/config:ro",
        "-v",
        f"{coastline}:/coastline:ro",
        "-v",
        f"{dest.parent}:/output",
    ]
    return [
        "docker",
        "run",
        "--rm",
        *mounts,
        "-w",
        "/usr/src/app",
        image,
        "--input",
        f"/input/{pbf.name}",
        "--output",
        f"/output/{dest.name}",
        "--bbox",
        ",".join(coord(v) for v in bbox),
        "--config",
        f"/config/{config.name}",
        "--process",
        "resources/process-openmaptiles.lua",
    ]


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)  # noqa: S603


def build_area_map(
    image: str,
    pbf: Path,
    points: Sequence[LatLon],
    config_file: Path,
    coastline: Path,
    dest: Path,
    run: Callable[[list[str]], None] = _run,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(tilemaker_command(image, pbf, map_bbox(points), config_file, coastline, dest))


def _part(out: Path, relative: str, data: bytes) -> dict[str, Any]:
    path = out / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def write_map_entry(out: Path, area: str, built: Path, chunk_bytes: int) -> dict[str, Any]:
    """Copy a built map into the release, split into chunks if needed; return its manifest entry."""
    data = built.read_bytes()
    base = f"areas/{area}/map.pmtiles"
    if len(data) <= chunk_bytes:
        parts = [_part(out, base, data)]
    else:
        parts = [
            _part(out, f"{base}.{n:03d}", data[start : start + chunk_bytes])
            for n, start in enumerate(range(0, len(data), chunk_bytes))
        ]
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "parts": parts}


def pmtiles_bounds(header: bytes) -> BBox:
    """min_lon, min_lat, max_lon, max_lat from a PMTiles v3 header."""
    if len(header) < PMTILES_HEADER_BYTES or header[:7] != b"PMTiles" or header[7] != 3:
        raise ValueError("not a PMTiles v3 file")
    min_lon, min_lat, max_lon, max_lat = struct.unpack_from("<iiii", header, 102)
    return (min_lon / 1e7, min_lat / 1e7, max_lon / 1e7, max_lat / 1e7)

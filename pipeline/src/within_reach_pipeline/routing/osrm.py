"""OSRM routing in Docker, on a map extract clipped to one area (spec FR-02, NFR-09)."""

import logging
import math
import shutil
import subprocess
import time
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import httpx

from within_reach_pipeline.http import Fetcher
from within_reach_pipeline.routing import LatLon, TableResult, round_half_up

log = logging.getLogger(__name__)
Profile = Literal["foot", "car"]
METRES_PER_DEGREE_LAT = 111_195.0
BBox = tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat


def area_bbox(points: Iterable[LatLon], margin_m: int = 3000) -> BBox:
    lats, lons = zip(*points, strict=True)
    lat_margin = margin_m / METRES_PER_DEGREE_LAT
    widest = max(abs(min(lats)), abs(max(lats)))
    lon_margin = margin_m / (METRES_PER_DEGREE_LAT * math.cos(math.radians(widest)))
    return (
        min(lons) - lon_margin,
        min(lats) - lat_margin,
        max(lons) + lon_margin,
        max(lats) + lat_margin,
    )


def osmium_extract_command(src_pbf: Path, bbox: BBox, dest: Path) -> list[str]:
    box = ",".join(str(v) for v in bbox)
    return ["osmium", "extract", "--strategy", "smart", "-b", box, str(src_pbf),
            "-o", str(dest), "--overwrite"]  # fmt: skip


def clip_extract(src_pbf: Path, bbox: BBox, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(osmium_extract_command(src_pbf, bbox, dest))
    return dest


def _run(command: Sequence[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        tail = "\n".join(result.stderr.splitlines()[-20:])
        raise RuntimeError(f"{command[0]} failed ({result.returncode}):\n{tail}")


@contextmanager
def osrm_server(pbf: Path, profile: Profile, image: str, port: int) -> Iterator[str]:
    """Build an OSRM graph for pbf with the given profile and serve it on 127.0.0.1:port."""
    workdir = pbf.parent / f"osrm-{profile}"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    shutil.copyfile(pbf, workdir / "area.osm.pbf")
    mount = ["-v", f"{workdir.resolve()}:/data"]
    docker = ["docker", "run", "--rm", *mount, image]
    log.info("building OSRM %s graph for %s", profile, pbf.name)
    _run([*docker, "osrm-extract", "-p", f"/opt/{profile}.lua", "/data/area.osm.pbf"])
    _run([*docker, "osrm-partition", "/data/area.osrm"])
    _run([*docker, "osrm-customize", "/data/area.osrm"])

    name = f"within-reach-osrm-{profile}-{port}"
    _run(["docker", "run", "-d", "--rm", "--name", name, "-p", f"127.0.0.1:{port}:5000",
          *mount, image, "osrm-routed", "--algorithm", "mld", "--max-table-size", "1000",
          "/data/area.osrm"])  # fmt: skip
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                httpx.get(f"{base_url}/nearest/v1/{profile}/0,0", timeout=2)
                break
            except httpx.TransportError:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"OSRM {profile} server did not start") from None
                time.sleep(0.5)
        yield base_url
    finally:
        subprocess.run(["docker", "stop", name], capture_output=True, check=False)  # noqa: S603, S607


class OsrmRouter:
    def __init__(self, base_url: str, fetcher: Fetcher, profile: Profile) -> None:
        self.base_url = base_url.rstrip("/")
        self.fetcher = fetcher
        self.profile = profile

    def table(self, sources: Sequence[LatLon], destinations: Sequence[LatLon]) -> TableResult:
        coords = ";".join(f"{lon},{lat}" for lat, lon in [*sources, *destinations])
        source_ids = ";".join(str(i) for i in range(len(sources)))
        dest_ids = ";".join(str(len(sources) + i) for i in range(len(destinations)))
        url = (
            f"{self.base_url}/table/v1/{self.profile}/{coords}"
            f"?sources={source_ids}&destinations={dest_ids}&annotations=distance,duration"
        )
        data = self.fetcher.get_json(url)
        if data.get("code") != "Ok":
            raise RuntimeError(f"OSRM table failed: {data.get('code')} {data.get('message', '')}")

        def clean(matrix: list[list[float | None]]) -> list[list[int | None]]:
            return [[None if v is None else round_half_up(v) for v in row] for row in matrix]

        return TableResult(clean(data["distances"]), clean(data["durations"]))

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
from within_reach_pipeline.routing import WALK_PROFILE, LatLon, TableResult, round_half_up

log = logging.getLogger(__name__)
Profile = Literal["foot", "car"]
METRES_PER_DEGREE_LAT = 111_195.0
BBox = tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat
# UK walking rules: a wrapper around OSRM's stock foot.lua (pipeline/osrm/foot-gb.lua).
PROFILE_DIR = Path(__file__).resolve().parents[3] / "osrm"
_PROFILE_PATHS: dict[str, str] = {"foot": f"/profiles/{WALK_PROFILE}.lua", "car": "/opt/car.lua"}


def _docker(workdir: Path, image: str) -> list[str]:
    mounts = ["-v", f"{workdir.resolve()}:/data", "-v", f"{PROFILE_DIR}:/profiles:ro"]
    return ["docker", "run", "--rm", *mounts, image]


def extract_command(
    workdir: Path, profile: Profile, image: str, profile_path: str | None = None
) -> list[str]:
    """osrm-extract for one profile: UK walking rules for foot, stock rules for car.

    profile_path overrides the Lua file (the tests compare against the stock /opt/foot.lua).
    """
    lua = profile_path or _PROFILE_PATHS[profile]
    return [*_docker(workdir, image), "osrm-extract", "-p", lua, "/data/area.osm.pbf"]


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


OSMIUM_IMAGE = "within-reach-osmium:1"
OSMIUM_DOCKERFILE = Path(__file__).resolve().parents[3] / "docker" / "osmium.Dockerfile"


def coord(value: float) -> str:
    """A coordinate as a plain decimal, 6 places (about 10 cm).

    str() would give "-7.7e-05" near the Greenwich meridian, which OSRM and osmium reject.
    """
    return f"{value:.6f}"


def osmium_extract_command(src_pbf: Path, bbox: BBox, dest: Path) -> list[str]:
    box = ",".join(coord(v) for v in bbox)
    return [
        "osmium",
        "extract",
        "--strategy",
        "smart",
        "-b",
        box,
        str(src_pbf),
        "-o",
        str(dest),
        "--overwrite",
    ]


def osmium_command(src_pbf: Path, bbox: BBox, dest: Path, native: bool) -> list[str]:
    """Run osmium directly if installed, otherwise in the local Docker image."""
    command = osmium_extract_command(src_pbf, bbox, dest)
    if native:
        return command
    mounts = ["-v", f"{src_pbf.parent}:{src_pbf.parent}:ro", "-v", f"{dest.parent}:{dest.parent}"]
    return ["docker", "run", "--rm", *mounts, OSMIUM_IMAGE, *command]


def _ensure_osmium_image() -> None:
    present = subprocess.run(  # noqa: S603
        ["docker", "image", "inspect", OSMIUM_IMAGE],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if present.returncode != 0:
        log.info("building %s", OSMIUM_IMAGE)
        _run(
            [
                "docker",
                "build",
                "-t",
                OSMIUM_IMAGE,
                "-f",
                str(OSMIUM_DOCKERFILE),
                str(OSMIUM_DOCKERFILE.parent),
            ]
        )


def clip_extract(src_pbf: Path, bbox: BBox, dest: Path) -> Path:
    src_pbf, dest = src_pbf.resolve(), dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    native = shutil.which("osmium") is not None
    if not native:
        _ensure_osmium_image()
    _run(osmium_command(src_pbf, bbox, dest, native))
    return dest


def _run(command: Sequence[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        tail = "\n".join(result.stderr.splitlines()[-20:])
        raise RuntimeError(f"{command[0]} failed ({result.returncode}):\n{tail}")


@contextmanager
def osrm_server(
    pbf: Path, profile: Profile, image: str, port: int, profile_path: str | None = None
) -> Iterator[str]:
    """Build an OSRM graph for pbf with the given profile and serve it on 127.0.0.1:port."""
    workdir = pbf.parent / f"osrm-{profile}"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    shutil.copyfile(pbf, workdir / "area.osm.pbf")
    mount = ["-v", f"{workdir.resolve()}:/data", "-v", f"{PROFILE_DIR}:/profiles:ro"]
    docker = _docker(workdir, image)
    log.info("building OSRM %s graph for %s", profile, pbf.name)
    _run(extract_command(workdir, profile, image, profile_path))
    _run([*docker, "osrm-partition", "/data/area.osrm"])
    _run([*docker, "osrm-customize", "/data/area.osrm"])

    name = f"within-reach-osrm-{profile}-{port}"
    _run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{port}:5000",
            *mount,
            image,
            "osrm-routed",
            "--algorithm",
            "mld",
            "--max-table-size",
            "1000",
            "/data/area.osrm",
        ]
    )
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

    def table(
        self,
        sources: Sequence[LatLon],
        destinations: Sequence[LatLon],
        exclude: str | None = None,
    ) -> TableResult:
        coords = ";".join(f"{coord(lon)},{coord(lat)}" for lat, lon in [*sources, *destinations])
        source_ids = ";".join(str(i) for i in range(len(sources)))
        dest_ids = ";".join(str(len(sources) + i) for i in range(len(destinations)))
        url = (
            f"{self.base_url}/table/v1/{self.profile}/{coords}"
            f"?sources={source_ids}&destinations={dest_ids}&annotations=distance,duration"
        )
        if exclude is not None:
            url += f"&exclude={exclude}"
        data = self.fetcher.get_json(url)
        if data.get("code") != "Ok":
            raise RuntimeError(f"OSRM table failed: {data.get('code')} {data.get('message', '')}")

        def clean(matrix: list[list[float | None]]) -> list[list[int | None]]:
            return [[None if v is None else round_half_up(v) for v in row] for row in matrix]

        return TableResult(clean(data["distances"]), clean(data["durations"]))

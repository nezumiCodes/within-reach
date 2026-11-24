"""Command line: fetch | fetch-services | build | merge | areas | check."""

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import zipfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from within_reach_pipeline.bundle import merge_manifests, write_manifest
from within_reach_pipeline.config import PipelineConfig, load_config
from within_reach_pipeline.http import Fetcher, HttpxFetcher
from within_reach_pipeline.onspd import read_onspd
from within_reach_pipeline.pharmacies.england import read_nhsbsa
from within_reach_pipeline.pharmacies.wales import fetch_ods_wales, postcode_area, save_ods_wales
from within_reach_pipeline.services import fetch_snapshot, save_snapshot
from within_reach_pipeline.sources import (
    OSM_UK_URL,
    WATER_POLYGONS_URL,
    SourceRelease,
    latest_contractor_details,
    latest_nhsbsa,
    latest_onspd,
    latest_phs,
)

log = logging.getLogger("within_reach_pipeline")

# Fixed file names in the cache directory, shared by fetch and build.
NHSBSA_FILE = "nhsbsa.csv"
CONTRACTOR_DETAILS_FILE = "contractor_details.csv"
PHS_FILE = "phs.csv"
OSM_FILE = "uk.osm.pbf"
ODS_WALES_FILE = "ods_wales.json"
SERVICES_FILE = "dohs_services.json"
ONSPD_DIR = "onspd"
COASTLINE_DIR = "coastline"
SHAPEFILE_PARTS = (".shp", ".shx", ".dbf", ".prj", ".cpg")


def onspd_csv(cache: Path) -> Path:
    matches = sorted((cache / ONSPD_DIR / "Data").glob("*_UK.csv"))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected one ONSPD *_UK.csv in {cache / ONSPD_DIR / 'Data'}")
    return matches[0]


def _extract_onspd(zip_path: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            keep = (member.startswith("Data/") and member.endswith("_UK.csv")) or (
                member.startswith("Documents/") and member.endswith(".csv")
            )
            if keep and ".." not in Path(member).parts:
                archive.extract(member, dest)


def _extract_coastline(zip_path: Path, dest: Path) -> None:
    """Keep only the shapefile parts, flat in one folder (tilemaker reads water_polygons.shp)."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            name = Path(member).name
            if name.startswith("water_polygons") and Path(name).suffix in SHAPEFILE_PARTS:
                (dest / name).write_bytes(archive.read(member))


def fetch(cache: Path, fetcher: Fetcher) -> list[dict[str, str]]:
    cache.mkdir(parents=True, exist_ok=True)
    sources: list[dict[str, str]] = []

    def record(release: SourceRelease, filename: str) -> Path:
        path = cache / filename
        log.info("downloading %s (%s)", release.name, release.label)
        digest = fetcher.download(release.url, path)
        sources.append(
            {"name": release.name, "label": release.label, "url": release.url, "sha256": digest}
        )
        return path

    zip_path = record(latest_onspd(fetcher), "onspd.zip")
    _extract_onspd(zip_path, cache / ONSPD_DIR)
    zip_path.unlink()
    record(latest_nhsbsa(fetcher), NHSBSA_FILE)
    record(latest_contractor_details(fetcher), CONTRACTOR_DETAILS_FILE)
    record(latest_phs(fetcher), PHS_FILE)
    record(SourceRelease("osm", "Geofabrik united-kingdom-latest", OSM_UK_URL), OSM_FILE)
    water = SourceRelease("water_polygons", "OSM water polygons (split, WGS84)", WATER_POLYGONS_URL)
    water_zip = record(water, "water_polygons.zip")
    _extract_coastline(water_zip, cache / COASTLINE_DIR)
    water_zip.unlink()

    welsh_areas = {
        postcode_area(p.postcode) for p in read_onspd(onspd_csv(cache)) if p.nation == "Wales"
    }
    english, _ = read_nhsbsa(cache / NHSBSA_FILE)
    log.info("fetching Welsh pharmacies from NHS ODS (postcode areas %s)", sorted(welsh_areas))
    ods_path = cache / ODS_WALES_FILE
    welsh = fetch_ods_wales(fetcher, welsh_areas, frozenset(p.code for p in english))
    save_ods_wales(welsh, ods_path)
    fetched_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sources.append(
        {
            "name": "ods_wales",
            "label": f"NHS ODS ORD API, active pharmacies in Wales (RO182), fetched {fetched_at}",
            "url": "https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations",
            "sha256": hashlib.sha256(ods_path.read_bytes()).hexdigest(),
        }
    )
    (cache / "sources.json").write_text(json.dumps(sources, indent=1) + "\n", encoding="utf-8")
    return sources


def _release_name(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise argparse.ArgumentTypeError("release must look like YYYY-MM")
    return value


def merge(out: Path, shard_dirs: Sequence[Path]) -> dict[str, Any]:
    base = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    shards = [json.loads((d / "manifest.json").read_text(encoding="utf-8")) for d in shard_dirs]
    merged = merge_manifests(base, shards)
    for shard_dir in shard_dirs:
        if (shard_dir / "areas").exists():
            shutil.copytree(shard_dir / "areas", out / "areas", dirs_exist_ok=True)
    write_manifest(out, merged)
    return merged


def run(
    argv: Sequence[str],
    fetcher: Fetcher | None = None,
    env: Mapping[str, str] | None = None,
    config: PipelineConfig | None = None,
) -> int:
    env = os.environ if env is None else env
    if config is None:
        # An explicit config wins, then WITHIN_REACH_CONFIG (a path), then the repo default.
        config = (
            load_config(Path(env["WITHIN_REACH_CONFIG"]))
            if env.get("WITHIN_REACH_CONFIG")
            else load_config()
        )
    parser = argparse.ArgumentParser(prog="within-reach-pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch_cmd = commands.add_parser("fetch", help="download the latest public data")
    fetch_cmd.add_argument("--cache", type=Path, required=True)

    services_cmd = commands.add_parser(
        "fetch-services", help="download pharmacy services from the NHS England DoHS API"
    )
    services_cmd.add_argument("--cache", type=Path, required=True)

    build_cmd = commands.add_parser("build", help="build a release from a fetch cache")
    build_cmd.add_argument("--cache", type=Path, required=True)
    build_cmd.add_argument("--release", type=_release_name, required=True)
    build_cmd.add_argument("--out", type=Path, required=True)
    build_cmd.add_argument(
        "--areas",
        nargs="*",
        default=None,
        help="area codes to build; omit for all, give none for shared files only",
    )
    build_cmd.add_argument("--router", choices=["osrm", "fake"], default="osrm")
    build_cmd.add_argument(
        "--maps",
        choices=["tilemaker", "none"],
        default="none",
        help="also build a map file per area (needs Docker)",
    )
    build_cmd.add_argument("--built-at", default=None, help="ISO time (default: now, UTC)")

    merge_cmd = commands.add_parser("merge", help="merge area shards into a release")
    merge_cmd.add_argument("--out", type=Path, required=True)
    merge_cmd.add_argument("shards", type=Path, nargs="+")

    areas_cmd = commands.add_parser("areas", help="print area codes as JSON shards for CI")
    areas_cmd.add_argument("--cache", type=Path, required=True)
    areas_cmd.add_argument("--shard-size", type=int, default=10)
    areas_cmd.add_argument("--only", nargs="*", default=None, help="limit to these area codes")

    check_cmd = commands.add_parser("check", help="run the release checks (FR-04)")
    check_cmd.add_argument("--release-dir", type=Path, required=True)
    check_cmd.add_argument("--previous-dir", type=Path, default=None)
    check_cmd.add_argument("--reference", type=Path, default=None)
    check_cmd.add_argument(
        "--allow-partial", action="store_true", help="accept a release that skips areas"
    )

    args = parser.parse_args(list(argv))
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # httpx logs every request at INFO; a full build makes millions of OSRM requests.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.command == "fetch":
        fetch(args.cache, fetcher or HttpxFetcher(config.user_agent))
    elif args.command == "fetch-services":
        if not config.services_enabled:
            log.info("services disabled in config; no snapshot written")
            return 0
        api_key = env.get("NHS_DOHS_API_KEY")
        if not api_key:
            raise SystemExit("NHS_DOHS_API_KEY is not set")
        api_base = env.get("NHS_DOHS_API_BASE", config.services_api_base)
        args.cache.mkdir(parents=True, exist_ok=True)
        snapshot = fetch_snapshot(fetcher or HttpxFetcher(config.user_agent), api_base, api_key)
        save_snapshot(snapshot, args.cache / SERVICES_FILE)
    elif args.command == "build":
        from within_reach_pipeline.build import build_release

        built_at = args.built_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        build_release(
            args.cache,
            args.release,
            args.out,
            args.areas,
            args.router,
            config,
            built_at,
            maps=args.maps,
        )
    elif args.command == "merge":
        merge(args.out, args.shards)
    elif args.command == "areas":
        known = sorted({p.area_code for p in read_onspd(onspd_csv(args.cache))})
        wanted = known if not args.only else sorted(set(args.only))
        unknown = sorted(set(wanted) - set(known))
        if unknown:
            log.error("unknown area codes: %s", " ".join(unknown))
            return 2
        size = max(1, args.shard_size)
        shards = [" ".join(wanted[i : i + size]) for i in range(0, len(wanted), size)]
        print(json.dumps(shards))
    elif args.command == "check":
        from within_reach_pipeline.checks import run_checks

        failures = run_checks(
            args.release_dir, config, args.previous_dir, args.reference, args.allow_partial
        )
        for failure in failures:
            log.error("CHECK FAILED [%s] %s", failure.check, failure.detail)
        if failures:
            return 1
        log.info("all release checks passed")
    return 0

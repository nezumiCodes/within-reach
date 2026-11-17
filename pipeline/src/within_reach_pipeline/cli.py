"""Command line: fetch | build | merge | check."""

import argparse
import hashlib
import json
import logging
import re
import shutil
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from within_reach_pipeline.bundle import merge_manifests, write_manifest
from within_reach_pipeline.config import load_config
from within_reach_pipeline.http import Fetcher, HttpxFetcher
from within_reach_pipeline.onspd import read_onspd
from within_reach_pipeline.pharmacies.wales import fetch_ods_wales, save_ods_wales
from within_reach_pipeline.sources import (
    OSM_UK_URL,
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
ONSPD_DIR = "onspd"


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

    welsh_postcodes = {p.postcode for p in read_onspd(onspd_csv(cache)) if p.nation == "Wales"}
    log.info("fetching Welsh pharmacies from NHS ODS")
    ods_path = cache / ODS_WALES_FILE
    save_ods_wales(fetch_ods_wales(fetcher, welsh_postcodes), ods_path)
    sources.append(
        {
            "name": "ods_wales",
            "label": "NHS ODS ORD API, active pharmacies (RO182) with Welsh postcodes",
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


def run(argv: Sequence[str], fetcher: Fetcher | None = None) -> int:
    parser = argparse.ArgumentParser(prog="within-reach-pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch_cmd = commands.add_parser("fetch", help="download the latest public data")
    fetch_cmd.add_argument("--cache", type=Path, required=True)

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
    build_cmd.add_argument("--built-at", default=None, help="ISO time (default: now, UTC)")

    merge_cmd = commands.add_parser("merge", help="merge area shards into a release")
    merge_cmd.add_argument("--out", type=Path, required=True)
    merge_cmd.add_argument("shards", type=Path, nargs="+")

    check_cmd = commands.add_parser("check", help="run the release checks (FR-04)")
    check_cmd.add_argument("--release-dir", type=Path, required=True)
    check_cmd.add_argument("--previous-dir", type=Path, default=None)
    check_cmd.add_argument("--reference", type=Path, default=None)

    args = parser.parse_args(list(argv))
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.command == "fetch":
        fetch(args.cache, fetcher or HttpxFetcher(load_config().user_agent))
    elif args.command == "build":
        from within_reach_pipeline.build import build_release

        built_at = args.built_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        build_release(
            args.cache, args.release, args.out, args.areas, args.router, load_config(), built_at
        )
    elif args.command == "merge":
        merge(args.out, args.shards)
    elif args.command == "check":
        from within_reach_pipeline.checks import run_checks

        failures = run_checks(args.release_dir, load_config(), args.previous_dir, args.reference)
        for failure in failures:
            log.error("CHECK FAILED [%s] %s", failure.check, failure.detail)
        if failures:
            return 1
        log.info("all release checks passed")
    return 0

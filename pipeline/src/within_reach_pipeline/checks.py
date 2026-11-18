"""Release checks (spec FR-04). Any failure stops publishing; the previous release stays live."""

import csv
import gzip
import hashlib
import io
import json
import tomllib
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from within_reach_pipeline.config import PipelineConfig

NATIONS = ("England", "Scotland", "Wales")


@dataclass(frozen=True)
class CheckFailure:
    check: str
    detail: str


def _rows(path: Path) -> Iterator[dict[str, str]]:
    text = gzip.decompress(path.read_bytes()).decode("utf-8")
    yield from csv.DictReader(io.StringIO(text))


def _files(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    files = [manifest["directory"], manifest["districts"]]
    for area in manifest["areas"]:
        files.extend(area["files"].values())
    return files


def _check_files(release: Path, manifest: dict[str, Any], limit: int) -> list[CheckFailure]:
    failures: list[CheckFailure] = []
    for info in [*_files(manifest), {"path": "manifest.json"}]:
        path = release / info["path"]
        if not path.exists():
            failures.append(CheckFailure("checksums", f"{info['path']} is missing"))
            continue
        data = path.read_bytes()
        if "sha256" in info and (
            hashlib.sha256(data).hexdigest() != info["sha256"] or len(data) != info["bytes"]
        ):
            failures.append(CheckFailure("checksums", f"{info['path']} does not match manifest"))
        if len(data) > limit:
            failures.append(CheckFailure("size", f"{info['path']} is {len(data)} bytes"))
    return failures


def _check_no_bt(release: Path, manifest: dict[str, Any]) -> list[CheckFailure]:
    found: list[str] = []
    for row in _rows(release / manifest["directory"]["path"]):
        if row["postcode"].upper().startswith("BT"):
            found.append(f"pharmacy {row['nation']}:{row['code']}")
    for row in _rows(release / manifest["districts"]["path"]):
        if row["outward"].upper().startswith("BT"):
            found.append(f"district {row['outward']}")
    for area in manifest["areas"]:
        for row in _rows(release / area["files"]["postcodes"]["path"]):
            if row["postcode"].upper().startswith("BT"):
                found.append(f"{area['code']} {row['postcode']}")
    return [CheckFailure("no_bt", f"Northern Ireland postcode published: {f}") for f in found]


def _check_nations(manifest: dict[str, Any]) -> list[CheckFailure]:
    failures = [
        CheckFailure("nations", f"no pharmacies in {nation}")
        for nation in NATIONS
        if manifest["directory"]["count_by_nation"].get(nation, 0) == 0
    ]
    failures += [
        CheckFailure(
            "nations", f"area {a['code']} has {a['postcodes']} postcodes, {a['pairs']} pairs"
        )
        for a in manifest["areas"]
        if a["postcodes"] == 0 or a["pairs"] == 0
    ]
    return failures


def _check_min_candidates(
    release: Path, manifest: dict[str, Any], config: PipelineConfig
) -> list[CheckFailure]:
    directory_size = sum(manifest["directory"]["count_by_nation"].values())
    needed = min(config.min_candidates, directory_size)
    failures: list[CheckFailure] = []
    for area in manifest["areas"]:
        counts = Counter(row["pc_idx"] for row in _rows(release / area["files"]["travel"]["path"]))
        short = [i for i in range(area["postcodes"]) if counts.get(str(i), 0) < needed]
        if short:
            failures.append(
                CheckFailure("min_candidates", f"{area['code']}: {len(short)} postcodes short")
            )
    return failures


def _check_geocode(manifest: dict[str, Any], limit: float) -> list[CheckFailure]:
    failed = Counter(f["nation"] for f in manifest["geocode_failures"])
    failures: list[CheckFailure] = []
    for nation in NATIONS:
        ok = manifest["directory"]["count_by_nation"].get(nation, 0)
        total = ok + failed.get(nation, 0)
        if total and failed.get(nation, 0) / total > limit:
            failures.append(
                CheckFailure("geocode", f"{nation}: {failed[nation]} of {total} not geocoded")
            )
    return failures


def _check_distance_selling(manifest: dict[str, Any], config: PipelineConfig) -> list[CheckFailure]:
    excluded = int(manifest["excluded_distance_selling"])
    if config.distance_selling_min <= excluded <= config.distance_selling_max:
        return []
    return [CheckFailure("distance_selling", f"{excluded} online-only pharmacies excluded")]


def _within(current: int, previous: int, tolerance: float) -> bool:
    return previous == 0 or abs(current - previous) / previous <= tolerance


def _check_counts(
    manifest: dict[str, Any], previous: dict[str, Any], tolerance: float
) -> list[CheckFailure]:
    failures: list[CheckFailure] = []
    for nation in NATIONS:
        now = manifest["directory"]["count_by_nation"].get(nation, 0)
        before = previous["directory"]["count_by_nation"].get(nation, 0)
        if not _within(now, before, tolerance):
            failures.append(CheckFailure("counts", f"{nation} pharmacies {before} -> {now}"))
    before_areas = {a["code"]: a["postcodes"] for a in previous["areas"]}
    common = [a for a in manifest["areas"] if a["code"] in before_areas]
    now_total = sum(a["postcodes"] for a in common)
    before_total = sum(before_areas[a["code"]] for a in common)
    if not _within(now_total, before_total, tolerance):
        failures.append(CheckFailure("counts", f"postcodes {before_total} -> {now_total}"))
    return failures


def _check_reference(
    release: Path, manifest: dict[str, Any], reference: Path
) -> list[CheckFailure]:
    cases = tomllib.loads(reference.read_text(encoding="utf-8")).get("case", [])
    directory = {
        row["ph_idx"]: f"{row['nation']}:{row['code']}"
        for row in _rows(release / manifest["directory"]["path"])
    }
    failures: list[CheckFailure] = []
    for case in cases:
        postcode = case["postcode"]
        travel: list[dict[str, str]] | None = None
        for area in manifest["areas"]:
            for row in _rows(release / area["files"]["postcodes"]["path"]):
                if row["postcode"] == postcode:
                    pc_idx = row["pc_idx"]
                    travel = [
                        r
                        for r in _rows(release / area["files"]["travel"]["path"])
                        if r["pc_idx"] == pc_idx
                    ]
                    break
            if travel is not None:
                break
        if travel is None:
            failures.append(CheckFailure("reference", f"{postcode}: not in any built area"))
            continue
        # Travel rows are stored in straight-line order; the reference is about walking.
        # Rows without a walking route sort last. Order within the top N is not compared,
        # because near-ties (tens of metres) swap places as OSM paths are edited.
        travel.sort(key=lambda r: (not r["walk_m"], int(r["walk_m"] or 0), int(r["straight_m"])))
        expected = list(case["nearest"])
        actual = [directory[r["ph_idx"]] for r in travel[: len(expected)]]
        if sorted(actual) != sorted(expected):
            failures.append(
                CheckFailure("reference", f"{postcode}: nearest {actual} != {expected}")
            )
            continue
        low, high = case["walk_m_range"]
        walk = travel[0]["walk_m"]
        if not walk or not low <= int(walk) <= high:
            failures.append(
                CheckFailure(
                    "reference", f"{postcode}: walk {walk or 'none'} m not in {low}-{high}"
                )
            )
    return failures


def _check_complete(manifest: dict[str, Any]) -> list[CheckFailure]:
    built = {a["code"] for a in manifest["areas"]}
    missing = sorted(set(manifest.get("all_area_codes", [])) - built)
    if not missing:
        return []
    shown = " ".join(missing[:10]) + (" ..." if len(missing) > 10 else "")
    return [CheckFailure("complete", f"{len(missing)} areas not built: {shown}")]


def run_checks(
    release_dir: Path,
    config: PipelineConfig,
    previous_dir: Path | None,
    reference: Path | None,
    allow_partial: bool = False,
) -> list[CheckFailure]:
    """Run every release check. A partial release (not every area built) fails unless
    allow_partial is set; partial releases must never be served as production data."""
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    failures = _check_files(release_dir, manifest, config.max_file_bytes)
    if any(f.check == "checksums" and "missing" in f.detail for f in failures):
        return failures  # later checks would only fail on the same missing files
    failures += _check_no_bt(release_dir, manifest)
    failures += _check_nations(manifest)
    failures += _check_min_candidates(release_dir, manifest, config)
    failures += _check_geocode(manifest, config.geocode_failure_limit)
    failures += _check_distance_selling(manifest, config)
    if not allow_partial:
        failures += _check_complete(manifest)
    if previous_dir is not None:
        previous = json.loads((previous_dir / "manifest.json").read_text(encoding="utf-8"))
        failures += _check_counts(manifest, previous, config.count_tolerance)
    if reference is not None:
        failures += _check_reference(release_dir, manifest, reference)
    return failures

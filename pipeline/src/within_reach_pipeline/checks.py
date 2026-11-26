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

from within_reach_pipeline.bundle import TRAVEL_COLUMNS
from within_reach_pipeline.config import PipelineConfig
from within_reach_pipeline.maps import PMTILES_HEADER_BYTES, pmtiles_bounds

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
        files.extend(area.get("map", {}).get("parts", []))
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
    """Each postcode has min_candidates rows, unless widening ran out of reachable pharmacies.

    Unreachable rows are dropped when a postcode has reachable ones (reach.py), so a postcode
    may be short only if every row it kept is reachable, and no more postcodes may be short than
    the build reported as widened to the cap. A missing count (older shards) allows none.
    """
    directory_size = sum(manifest["directory"]["count_by_nation"].values())
    needed = min(config.min_candidates, directory_size)
    failures: list[CheckFailure] = []
    for area in manifest["areas"]:
        counts: Counter[str] = Counter()
        unreachable: set[str] = set()
        for row in _rows(release / area["files"]["travel"]["path"]):
            counts[row["pc_idx"]] += 1
            if not row["walk_m"] and not row["drive_s"]:
                unreachable.add(row["pc_idx"])
        short = [str(i) for i in range(area["postcodes"]) if counts.get(str(i), 0) < needed]
        bad = [i for i in short if i in unreachable]
        allowed = int(area.get("postcodes_widened_to_cap", 0))
        if bad or len(short) > allowed:
            failures.append(
                CheckFailure(
                    "min_candidates",
                    f"{area['code']}: {len(short)} postcodes short"
                    f" ({len(bad)} with unreachable rows, {allowed} widened to the cap)",
                )
            )
    return failures


def _check_travel_format(release: Path, manifest: dict[str, Any]) -> list[CheckFailure]:
    """Travel files use the current layout and walk_cycle is 1 or blank: the app rejects
    anything else, which would break every search in that area."""
    failures: list[CheckFailure] = []
    for area in manifest["areas"]:
        path = release / area["files"]["travel"]["path"]
        with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
            header = next(csv.reader(f), [])
        if header != TRAVEL_COLUMNS:
            failures.append(CheckFailure("travel_format", f"{area['code']}: header {header}"))
            continue
        bad = sum(1 for row in _rows(path) if row["walk_cycle"] not in ("", "1"))
        if bad:
            failures.append(
                CheckFailure("travel_format", f"{area['code']}: {bad} rows with a bad walk_cycle")
            )
    return failures


def _check_manifest_fields(manifest: dict[str, Any]) -> list[CheckFailure]:
    """The fields the walking rules and widening added (docs/data-format.md)."""
    failures: list[CheckFailure] = []
    if "walk_profile" not in manifest.get("config", {}):
        failures.append(CheckFailure("manifest_fields", "config has no walk_profile"))
    for area in manifest["areas"]:
        missing = [
            key
            for key in ("postcodes_without_route", "postcodes_widened_to_cap")
            if key not in area
        ]
        if missing:
            failures.append(CheckFailure("manifest_fields", f"{area['code']}: missing {missing}"))
    return failures


def _check_walk_cycle(release: Path, manifest: dict[str, Any]) -> list[CheckFailure]:
    """walk_cycle marks a walk that needs a cycle path, so it needs a walk."""
    failures: list[CheckFailure] = []
    for area in manifest["areas"]:
        rows = _rows(release / area["files"]["travel"]["path"])
        bad = sum(1 for row in rows if row.get("walk_cycle") == "1" and not row["walk_m"])
        if bad:
            failures.append(
                CheckFailure(
                    "walk_cycle", f"{area['code']}: {bad} rows note a cycle path but no walk"
                )
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


def _check_services(
    release: Path, manifest: dict[str, Any], config: PipelineConfig
) -> list[CheckFailure]:
    """Service data is plausible and every `services` cell holds only configured keys.

    With services off every cell is empty and the manifest has no service counts.
    """
    keys = {d.key for d in config.services} if config.services_enabled else set()
    failures: list[CheckFailure] = []
    bad_cells: set[str] = set()
    for row in _rows(release / manifest["directory"]["path"]):
        for value in filter(None, row["services"].split(";")):
            if value.removesuffix("?") not in keys:
                bad_cells.add(value)
    if bad_cells:
        failures.append(
            CheckFailure("services", f"unexpected services cell values: {sorted(bad_cells)}")
        )
    counts = manifest.get("services", {})
    if not keys:
        if counts:
            failures.append(CheckFailure("services", "service counts present with services off"))
        return failures
    england = manifest["directory"]["count_by_nation"].get("England", 0)
    for key in sorted(keys):
        entry = counts.get(key)
        if entry is None:
            failures.append(CheckFailure("services", f"{key}: no counts in the manifest"))
            continue
        if entry["listed"] < config.services_min_listed:
            failures.append(
                CheckFailure(
                    "services",
                    f"{key}: {entry['listed']} pharmacies listed,"
                    f" need {config.services_min_listed}",
                )
            )
        if entry["missing_dohs"] >= config.services_max_missing_share * england:
            failures.append(
                CheckFailure(
                    "services",
                    f"{key}: {entry['missing_dohs']} of {england} English pharmacies"
                    " have no DoHS record",
                )
            )
    return failures


def _check_service_counts(
    manifest: dict[str, Any], previous: dict[str, Any], tolerance: float
) -> list[CheckFailure]:
    """Listed counts stay within tolerance of the previous release, per service in both."""
    now, before = manifest.get("services", {}), previous.get("services", {})
    return [
        CheckFailure(
            "service_counts", f"{key} listed {before[key]['listed']} -> {now[key]['listed']}"
        )
        for key in sorted(now.keys() & before.keys())
        if not _within(now[key]["listed"], before[key]["listed"], tolerance)
    ]


def _check_reference(
    release: Path, manifest: dict[str, Any], reference: Path
) -> list[CheckFailure]:
    cases = tomllib.loads(reference.read_text(encoding="utf-8")).get("case", [])
    directory: dict[str, str] = {}
    listing: dict[str, set[str]] = {}  # service key -> ph_idx values that list it
    for row in _rows(release / manifest["directory"]["path"]):
        directory[row["ph_idx"]] = f"{row['nation']}:{row['code']}"
        for key in filter(None, row["services"].split(";")):
            if not key.endswith("?"):
                listing.setdefault(key, set()).add(row["ph_idx"])
    failures: list[CheckFailure] = []
    for case in cases:
        postcode = case["postcode"]
        if "nearest" not in case and "service" not in case:
            # Most likely a misspelt key: without this the case would silently check nothing.
            failures.append(
                CheckFailure("reference", f"{postcode}: case has neither nearest nor service")
            )
            continue
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
            # A partial release (reference areas only) can't answer cases elsewhere.
            if manifest.get("complete", True):
                failures.append(CheckFailure("reference", f"{postcode}: not in any built area"))
            continue
        if "service" in case:
            members = listing.get(case["service"], set())
            found = sum(
                1
                for r in travel
                if r["ph_idx"] in members
                and int(r["straight_m"]) > case["beyond_m"]
                and (r["walk_m"] or r["drive_s"])
            )
            if found < case["min_rows"]:
                failures.append(
                    CheckFailure(
                        "reference",
                        f"{postcode}: {found} routed {case['service']} rows beyond"
                        f" {case['beyond_m']} m, need {case['min_rows']}",
                    )
                )
        if "nearest" not in case:
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


def _check_maps(release: Path, manifest: dict[str, Any]) -> list[CheckFailure]:
    """Every area has a map whose joined parts match the manifest and cover its postcodes."""
    failures: list[CheckFailure] = []
    for area in manifest["areas"]:
        code, entry = area["code"], area.get("map")
        if entry is None:
            failures.append(CheckFailure("maps", f"{code} has no map"))
            continue
        data = b"".join((release / p["path"]).read_bytes() for p in entry["parts"])
        if hashlib.sha256(data).hexdigest() != entry["sha256"] or len(data) != entry["bytes"]:
            failures.append(CheckFailure("maps", f"{code} joined map does not match manifest"))
            continue
        try:
            west, south, east, north = pmtiles_bounds(data[:PMTILES_HEADER_BYTES])
        except ValueError:
            failures.append(CheckFailure("maps", f"{code} map is not a PMTiles v3 file"))
            continue
        outside = [
            row["postcode"]
            for row in _rows(release / area["files"]["postcodes"]["path"])
            if not (south <= float(row["lat"]) <= north and west <= float(row["lon"]) <= east)
        ]
        if outside:
            failures.append(
                CheckFailure("maps", f"{code} map does not cover {len(outside)} postcodes")
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
    failures += _check_walk_cycle(release_dir, manifest)
    failures += _check_travel_format(release_dir, manifest)
    failures += _check_manifest_fields(manifest)
    failures += _check_geocode(manifest, config.geocode_failure_limit)
    failures += _check_distance_selling(manifest, config)
    failures += _check_services(release_dir, manifest, config)
    if manifest["config"].get("maps") == "tilemaker":
        failures += _check_maps(release_dir, manifest)
    if not allow_partial:
        failures += _check_complete(manifest)
    if previous_dir is not None:
        previous = json.loads((previous_dir / "manifest.json").read_text(encoding="utf-8"))
        failures += _check_counts(manifest, previous, config.count_tolerance)
        failures += _check_service_counts(manifest, previous, config.services_listed_tolerance)
    if reference is not None:
        failures += _check_reference(release_dir, manifest, reference)
    return failures

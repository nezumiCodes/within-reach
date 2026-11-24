"""Build a release from a fetch cache: directory, district index, area bundles, manifest."""

import json
import logging
import tempfile
from collections import defaultdict
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Literal

from within_reach_pipeline.bundle import (
    ATTRIBUTION,
    SERVICES_ATTRIBUTION,
    write_area,
    write_directory,
    write_district_index,
    write_manifest,
)
from within_reach_pipeline.candidates import select_candidates
from within_reach_pipeline.config import PipelineConfig
from within_reach_pipeline.http import HttpxFetcher
from within_reach_pipeline.maps import MAP_CONFIG, build_area_map, write_map_entry
from within_reach_pipeline.models import Pharmacy, Postcode
from within_reach_pipeline.onspd import read_area_names, read_onspd
from within_reach_pipeline.pharmacies import build_directory
from within_reach_pipeline.pharmacies.england import read_distance_selling_codes, read_nhsbsa
from within_reach_pipeline.pharmacies.scotland import read_phs
from within_reach_pipeline.pharmacies.wales import load_ods_wales
from within_reach_pipeline.reach import route_reachable
from within_reach_pipeline.routing import WALK_PROFILE, Router, TravelRow
from within_reach_pipeline.routing.fake import FakeRouter
from within_reach_pipeline.routing.osrm import BBox, area_bbox
from within_reach_pipeline.services import assign_services, load_snapshot

log = logging.getLogger(__name__)
RouterKind = Literal["osrm", "fake"]
MapsKind = Literal["tilemaker", "none"]
WALK_SPEED_M_S, DRIVE_SPEED_M_S = 1.4, 13.4  # fake router only


def _area_extract(stack: ExitStack, cache: Path, bbox: BBox) -> Path:
    """The area's part of the GB map, used for routing and for the area map file."""
    from within_reach_pipeline.routing.osrm import clip_extract

    work = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="within-reach-")))
    return clip_extract(cache / "uk.osm.pbf", bbox, work / "area.osm.pbf")


def _inside(bbox: BBox, pharmacy: Pharmacy) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= pharmacy.lon <= max_lon and min_lat <= pharmacy.lat <= max_lat


def _routers(
    kind: RouterKind, stack: ExitStack, pbf: Path | None, config: PipelineConfig
) -> tuple[Router, Router]:
    if kind == "fake":
        return FakeRouter(WALK_SPEED_M_S), FakeRouter(DRIVE_SPEED_M_S)
    from within_reach_pipeline.routing.osrm import OsrmRouter, osrm_server

    if pbf is None:
        raise ValueError("the OSRM router needs an area extract")
    fetcher = HttpxFetcher(config.user_agent, timeout_s=300)
    walk_url = stack.enter_context(osrm_server(pbf, "foot", config.osrm_image, 5101))
    drive_url = stack.enter_context(osrm_server(pbf, "car", config.osrm_image, 5102))
    return OsrmRouter(walk_url, fetcher, "foot"), OsrmRouter(drive_url, fetcher, "car")


def postcodes_without_route(rows: Sequence[TravelRow]) -> int:
    """Postcodes with neither a walking nor a driving route to any of their pharmacies."""
    reachable: dict[int, bool] = {}
    for row in rows:
        ok = row.walk_m is not None or row.drive_s is not None
        reachable[row.pc_idx] = reachable.get(row.pc_idx, False) or ok
    return sum(1 for ok in reachable.values() if not ok)


def postcodes_without_walk(rows: Sequence[TravelRow]) -> int:
    """Postcodes with no walking route to any candidate: a sign of OSM footpath gaps (R6)."""
    walkable: dict[int, bool] = {}
    for row in rows:
        walkable[row.pc_idx] = walkable.get(row.pc_idx, False) or row.walk_m is not None
    return sum(1 for ok in walkable.values() if not ok)


def build_release(
    cache: Path,
    release: str,
    out: Path,
    areas: Sequence[str] | None,
    router: RouterKind,
    config: PipelineConfig,
    built_at: str,
    maps: MapsKind = "none",
) -> dict[str, Any]:
    from within_reach_pipeline.cli import (
        COASTLINE_DIR,
        CONTRACTOR_DETAILS_FILE,
        NHSBSA_FILE,
        ODS_WALES_FILE,
        ONSPD_DIR,
        PHS_FILE,
        SERVICES_FILE,
        onspd_csv,
    )

    log.info("reading ONSPD")
    postcodes = list(read_onspd(onspd_csv(cache)))
    index = {p.postcode: p for p in postcodes}
    by_area: dict[str, list[Postcode]] = defaultdict(list)
    for p in postcodes:
        by_area[p.area_code].append(p)

    england, hours_warnings = read_nhsbsa(cache / NHSBSA_FILE)
    raw = [*england, *read_phs(cache / PHS_FILE), *load_ods_wales(cache / ODS_WALES_FILE)]
    directory = build_directory(
        raw, index, hours_warnings, read_distance_selling_codes(cache / CONTRACTOR_DETAILS_FILE)
    )
    pharmacies = directory.pharmacies
    log.info(
        "directory: %d pharmacies, %d not geocoded",
        len(pharmacies),
        len(directory.geocode_failures),
    )

    out.mkdir(parents=True, exist_ok=True)
    snapshot = None
    if config.services_enabled:
        snapshot = load_snapshot(cache / SERVICES_FILE)
        if snapshot is None:
            raise FileNotFoundError(
                f"services are enabled but {cache / SERVICES_FILE} is missing: "
                "run fetch-services first"
            )
    assignment = assign_services(pharmacies, config.services, snapshot)
    directory_info = write_directory(out, pharmacies, assignment.cells)
    districts_info = write_district_index(out, postcodes)
    names = read_area_names(cache / ONSPD_DIR / "Documents")

    area_entries: list[dict[str, Any]] = []
    for code in sorted(by_area) if areas is None else sorted(set(areas)):
        area_postcodes = sorted(by_area.get(code, []), key=lambda p: p.postcode)
        if not area_postcodes:
            raise ValueError(f"area {code} has no live postcodes")
        log.info("area %s: %d postcodes", code, len(area_postcodes))
        candidates = select_candidates(
            area_postcodes,
            pharmacies,
            config.radius_m,
            config.max_candidates,
            config.min_candidates,
        )
        used = sorted({c.ph_idx for row in candidates for c in row})
        points = [(p.lat, p.lon) for p in area_postcodes]
        points += [(pharmacies[i].lat, pharmacies[i].lon) for i in used]
        # The extract is sized from the first-pass candidates; widening only adds pharmacies
        # inside it, because nothing outside can be routed.
        bbox = area_bbox(points)
        allowed = {i for i, p in enumerate(pharmacies) if _inside(bbox, p)}
        map_entry: dict[str, Any] | None = None
        with ExitStack() as stack:
            needs_extract = router == "osrm" or maps == "tilemaker"
            pbf = _area_extract(stack, cache, bbox) if needs_extract else None
            walk, drive = _routers(router, stack, pbf, config)
            reach = route_reachable(
                area_postcodes,
                pharmacies,
                candidates,
                walk,
                drive,
                allowed=allowed,
                min_reachable=config.min_candidates,
                max_candidates=config.max_candidates,
                cap_m=config.reach_cap_m,
                max_rounds=config.reach_max_rounds,
                cycle_min_extra_m=config.cycle_note_min_extra_m,
            )
            rows = reach.rows
            final_used = sorted({r.ph_idx for r in rows})
            points = [(p.lat, p.lon) for p in area_postcodes]
            points += [(pharmacies[i].lat, pharmacies[i].lon) for i in final_used]
            if maps == "tilemaker" and pbf is not None:
                built = pbf.parent / "map.pmtiles"
                log.info("area %s: building map", code)
                build_area_map(
                    config.tilemaker_image,
                    pbf,
                    points,
                    MAP_CONFIG,
                    cache / COASTLINE_DIR,
                    built,
                )
                map_entry = write_map_entry(out, code, built, config.map_chunk_bytes)
        postcode_info, travel_info = write_area(out, code, area_postcodes, rows)
        area_entries.append(
            {
                "code": code,
                "name": names.get(code, code),
                "nation": area_postcodes[0].nation,
                "postcodes": len(area_postcodes),
                "pairs": len(rows),
                "postcodes_without_walk": postcodes_without_walk(rows),
                "postcodes_without_route": postcodes_without_route(rows),
                "postcodes_widened_to_cap": len(reach.widened_to_cap),
                "files": {"postcodes": postcode_info.as_dict(), "travel": travel_info.as_dict()},
                **({"map": map_entry} if map_entry is not None else {}),
            }
        )

    sources = json.loads((cache / "sources.json").read_text(encoding="utf-8"))
    count_by_nation = {"England": 0, "Scotland": 0, "Wales": 0}
    for pharmacy in pharmacies:
        count_by_nation[pharmacy.raw.nation] += 1
    manifest: dict[str, Any] = {
        "release": release,
        "built_at": built_at,
        "sources": {s["name"]: {k: s[k] for k in ("label", "url", "sha256")} for s in sources},
        "config": {
            "radius_m": config.radius_m,
            "max_candidates": config.max_candidates,
            "min_candidates": config.min_candidates,
            "osrm_version": config.osrm_image.rsplit(":", 1)[-1],
            "walk_profile": WALK_PROFILE,
            "reach_cap_m": config.reach_cap_m,
            "reach_max_rounds": config.reach_max_rounds,
            "cycle_note_min_extra_m": config.cycle_note_min_extra_m,
            "router": router,
            "maps": maps,
            "services": [
                {
                    "key": d.key,
                    "name": d.name,
                    "nations": list(d.nations),
                    "source": SERVICES_ATTRIBUTION,
                    "source_fetched_at": snapshot.fetched_at,
                }
                for d in config.services
            ]
            if snapshot is not None
            else [],
            "service_min": config.service_min if snapshot is not None else 0,
        },
        "attribution": [*ATTRIBUTION, SERVICES_ATTRIBUTION]
        if snapshot is not None
        else ATTRIBUTION,
        "services": assignment.counts,
        "directory": {**directory_info.as_dict(), "count_by_nation": count_by_nation},
        "districts": districts_info.as_dict(),
        "geocode_failures": [
            {"nation": r.nation, "code": r.code, "postcode": r.postcode}
            for r in directory.geocode_failures
        ],
        "hours_warnings": directory.hours_warnings,
        "excluded_distance_selling": directory.excluded_distance_selling,
        "areas": area_entries,
        "all_area_codes": sorted(by_area),
        "complete": sorted(a["code"] for a in area_entries) == sorted(by_area),
    }
    write_manifest(out, manifest)
    return manifest

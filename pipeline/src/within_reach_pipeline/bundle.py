"""Write the published release files: gzipped CSV bundles and the manifest (spec FR-03).

Gzip uses mtime=0 and no embedded file name, so identical input gives byte-identical files
(NFR-11). The layout is documented in docs/data-format.md.
"""

import csv
import gzip
import hashlib
import io
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from within_reach_pipeline.models import WEEKDAYS, DayHours, Pharmacy, Postcode
from within_reach_pipeline.routing import TravelRow

ATTRIBUTION = [
    "Contains public sector information licensed under the Open Government Licence v3.0 "
    "(ONS Postcode Directory, NHSBSA, Public Health Scotland, NHS ODS).",
    "Contains OS data © Crown copyright and database right.",
    "Travel distances and times derived from map data © OpenStreetMap contributors, "
    "available under the Open Database Licence (ODbL).",
]


@dataclass(frozen=True)
class FileInfo:
    path: str
    sha256: str
    bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "bytes": self.bytes}


def _info(out: Path, relative: str) -> FileInfo:
    data = (out / relative).read_bytes()
    return FileInfo(relative, hashlib.sha256(data).hexdigest(), len(data))


def _write_gz_csv(
    out: Path, relative: str, header: Sequence[str], rows: Iterable[Sequence[Any]]
) -> FileInfo:
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    path = out / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as gz,
    ):
        gz.write(text.getvalue().encode("utf-8"))
    return _info(out, relative)


def _blank(value: int | None) -> str:
    return "" if value is None else str(value)


def _day_cell(day: DayHours) -> str:
    if day is None:
        return ""
    if day == ():
        return "CLOSED"
    return ";".join(f"{opens}-{closes}" for opens, closes in day)


def write_directory(out: Path, pharmacies: Sequence[Pharmacy]) -> FileInfo:
    header = ["ph_idx", "nation", "code", "name", "address", "postcode", "lat", "lon", *WEEKDAYS]
    rows = []
    for idx, p in enumerate(pharmacies):
        hours = p.raw.hours
        days = [_day_cell(hours.get(day)) if hours is not None else "" for day in WEEKDAYS]
        rows.append(
            [
                idx,
                p.raw.nation,
                p.raw.code,
                p.raw.name,
                ", ".join(p.raw.address),
                p.raw.postcode,
                f"{p.lat:.6f}",
                f"{p.lon:.6f}",
                *days,
            ]
        )
    return _write_gz_csv(out, "pharmacies.csv.gz", header, rows)


def write_area(
    out: Path, area_code: str, postcodes: Sequence[Postcode], rows: Sequence[TravelRow]
) -> tuple[FileInfo, FileInfo]:
    base = f"areas/{area_code}"
    postcode_info = _write_gz_csv(
        out,
        f"{base}/postcodes.csv.gz",
        ["pc_idx", "postcode", "lat", "lon"],
        ([i, p.postcode, f"{p.lat:.6f}", f"{p.lon:.6f}"] for i, p in enumerate(postcodes)),
    )
    travel_info = _write_gz_csv(
        out,
        f"{base}/travel.csv.gz",
        ["pc_idx", "ph_idx", "straight_m", "walk_m", "walk_s", "drive_s", "walk_cycle"],
        (
            [
                r.pc_idx,
                r.ph_idx,
                r.straight_m,
                _blank(r.walk_m),
                _blank(r.walk_s),
                _blank(r.drive_s),
                "1" if r.walk_cycle else "",
            ]
            for r in rows
        ),
    )
    return postcode_info, travel_info


def write_district_index(out: Path, postcodes: Iterable[Postcode]) -> FileInfo:
    """Outward code -> area codes, so the app can say which area to load (FR-12, AC-13)."""
    areas: dict[str, set[str]] = defaultdict(set)
    for p in postcodes:
        areas[p.postcode.split(" ")[0]].add(p.area_code)
    rows = ([outward, " ".join(sorted(areas[outward]))] for outward in sorted(areas))
    return _write_gz_csv(out, "districts.csv.gz", ["outward", "area_codes"], rows)


def write_manifest(out: Path, manifest: dict[str, Any]) -> FileInfo:
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    (out / "manifest.json").write_text(text, encoding="utf-8")
    return _info(out, "manifest.json")


def merge_manifests(base: dict[str, Any], shards: Sequence[dict[str, Any]]) -> dict[str, Any]:
    merged = dict(base)
    areas = list(base.get("areas", []))
    for shard in shards:
        if shard["directory"]["sha256"] != base["directory"]["sha256"]:
            raise ValueError("shard was built from a different pharmacy directory")
        areas.extend(shard["areas"])
    merged["areas"] = sorted(areas, key=lambda a: a["code"])
    # The base manifest is built without areas, so whether maps were built comes from the shards.
    maps = {shard.get("config", {}).get("maps") for shard in shards} - {None}
    if len(maps) > 1:
        raise ValueError(f"shards disagree on maps: {sorted(maps)}")
    if maps and "config" in base:
        merged["config"] = {**base["config"], "maps": maps.pop()}
    if "all_area_codes" in base:
        merged["complete"] = [a["code"] for a in merged["areas"]] == base["all_area_codes"]
    return merged

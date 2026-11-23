#!/usr/bin/env python3
"""Make the app's test data release: a real release trimmed to a few postcode districts.

The result is a small, valid release (manifest, checksums, renumbered indexes) plus a map per
area, used by the browser tests (Phase 2 plan, Task 8). It contains public data only.

Usage (from pipeline/, so the pipeline package is importable):
  uv run python ../scripts/make_fixture_release.py SRC_RELEASE_DIR DEST_DATA_DIR \\
      --districts CH2 CH4 LL11 --split-area E06000050 [--cache .cache]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import tempfile
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from within_reach_pipeline.maps import write_map_entry

LatLon = tuple[float, float]
MapBuilder = Callable[[str, list[LatLon], Path], None]
DEFAULT_CHUNK = 20 * 1024 * 1024


def _read(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(gzip.decompress(path.read_bytes()).decode("utf-8"))))


def _write(
    out: Path, relative: str, header: Sequence[str], rows: list[list[Any]]
) -> dict[str, Any]:
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    path = out / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(text.getvalue().encode("utf-8"))
    data = path.read_bytes()
    return {"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def trim_release(
    src: Path,
    dest: Path,
    districts: Sequence[str],
    chunk_bytes: int | None,
    build_map: MapBuilder | None,
    two_area: tuple[str, str] | None = None,
    split_area: str | None = None,
) -> dict[str, Any]:
    """Keep only postcodes in `districts`. two_area=(district, new_postcode) relabels that
    district's first Welsh postcode into a district mapped to two areas, so the app's
    two-area search path is tested. Writes dest/manifest.json and dest/../latest.json."""
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    wanted = set(districts)
    district_rows = _read(src / manifest["districts"]["path"])
    area_codes = sorted(
        {code for r in district_rows if r["outward"] in wanted for code in r["area_codes"].split()}
    )
    source_areas = {a["code"]: a for a in manifest["areas"]}
    pharmacies = _read(src / manifest["directory"]["path"])

    # First pass: kept postcodes and travel rows per area, with original indexes.
    kept: dict[str, tuple[list[dict[str, str]], list[dict[str, str]]]] = {}
    for code in area_codes:
        if code not in source_areas:
            continue
        files = source_areas[code]["files"]
        postcodes = [
            p for p in _read(src / files["postcodes"]["path"]) if p["postcode"].split()[0] in wanted
        ]
        if not postcodes:
            continue
        indexes = {p["pc_idx"] for p in postcodes}
        travel = [t for t in _read(src / files["travel"]["path"]) if t["pc_idx"] in indexes]
        kept[code] = (postcodes, travel)

    relabelled_area: str | None = None
    if two_area is not None:
        district, new_postcode = two_area
        for code in sorted(kept, reverse=True):  # Welsh codes sort last
            match = next((p for p in kept[code][0] if p["postcode"].split()[0] == district), None)
            if match is not None:
                match["postcode"] = new_postcode
                relabelled_area = code
                break
        if relabelled_area is None:
            raise ValueError(f"no postcode in {district} to relabel")

    used = sorted({int(t["ph_idx"]) for _, travel in kept.values() for t in travel})
    new_ph = {old: new for new, old in enumerate(used)}
    ph_header = list(pharmacies[0].keys())
    ph_rows = [
        [new_ph[int(p["ph_idx"])], *list(p.values())[1:]]
        for p in pharmacies
        if int(p["ph_idx"]) in new_ph
    ]
    directory_info = _write(dest, "pharmacies.csv.gz", ph_header, ph_rows)
    count_by_nation = {"England": 0, "Scotland": 0, "Wales": 0}
    for row in ph_rows:
        count_by_nation[str(row[1])] += 1

    districts_out: dict[str, set[str]] = {}
    areas_out: list[dict[str, Any]] = []
    for code, (postcodes, travel) in sorted(kept.items()):
        # Releases from December 2026 have a walk_cycle column; older ones don't.
        tr_header = ["pc_idx", "ph_idx", "straight_m", "walk_m", "walk_s", "drive_s"]
        if travel and "walk_cycle" in travel[0]:
            tr_header.append("walk_cycle")
        postcodes = sorted(postcodes, key=lambda p: p["postcode"])
        new_pc = {p["pc_idx"]: i for i, p in enumerate(postcodes)}
        for p in postcodes:
            districts_out.setdefault(p["postcode"].split()[0], set()).add(code)
        pc_rows = [[i, p["postcode"], p["lat"], p["lon"]] for i, p in enumerate(postcodes)]
        tr_rows: list[list[Any]] = sorted(
            (
                [
                    new_pc[t["pc_idx"]],
                    new_ph[int(t["ph_idx"])],
                    t["straight_m"],
                    t["walk_m"],
                    t["walk_s"],
                    t["drive_s"],
                    *([t["walk_cycle"]] if "walk_cycle" in tr_header else []),
                ]
                for t in travel
            ),
            key=lambda r: (int(r[0]), int(r[2]), int(r[1])),
        )
        base = f"areas/{code}"
        walkable = {int(r[0]) for r in tr_rows if r[3] != ""}
        routable = {int(r[0]) for r in tr_rows if r[3] != "" or r[5] != ""}
        entry: dict[str, Any] = {
            **{k: source_areas[code][k] for k in ("code", "name", "nation")},
            "postcodes": len(pc_rows),
            "pairs": len(tr_rows),
            "postcodes_without_walk": len(pc_rows) - len(walkable),
            "postcodes_without_route": len(pc_rows) - len(routable),
            # Trimming keeps whole postcode lists, so a short postcode stays short.
            "postcodes_widened_to_cap": source_areas[code].get("postcodes_widened_to_cap", 0),
            "files": {
                "postcodes": _write(
                    dest, f"{base}/postcodes.csv.gz", ["pc_idx", "postcode", "lat", "lon"], pc_rows
                ),
                "travel": _write(
                    dest,
                    f"{base}/travel.csv.gz",
                    tr_header,
                    tr_rows,
                ),
            },
        }
        if build_map is not None:
            points = [(float(p["lat"]), float(p["lon"])) for p in postcodes]
            points += [
                (float(pharmacies[old]["lat"]), float(pharmacies[old]["lon"]))
                for old in used
                if old in {int(t["ph_idx"]) for t in travel}
            ]
            with tempfile.TemporaryDirectory() as work:
                built = Path(work) / "map.pmtiles"
                build_map(code, points, built)
                size = built.stat().st_size
                chunk = chunk_bytes or DEFAULT_CHUNK
                if code == split_area:
                    chunk = min(chunk, max(1, -(-size // 2)))  # at least two parts
                entry["map"] = write_map_entry(dest, code, built, chunk)
        areas_out.append(entry)

    if two_area is not None and relabelled_area is not None:
        new_district = two_area[1].split()[0]
        districts_out[new_district] = set(sorted(kept))  # every kept area, postcode in the last
    districts_info = _write(
        dest,
        "districts.csv.gz",
        ["outward", "area_codes"],
        [[d, " ".join(sorted(codes))] for d, codes in sorted(districts_out.items())],
    )

    out = dict(manifest)
    out["directory"] = {**directory_info, "count_by_nation": count_by_nation}
    out["districts"] = districts_info
    out["areas"] = areas_out
    out["all_area_codes"] = [a["code"] for a in areas_out]
    out["complete"] = True
    out["geocode_failures"] = []
    out["config"] = {**manifest["config"], "maps": "tilemaker" if build_map else "none"}
    (dest / "manifest.json").write_text(
        json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (dest.parent / "latest.json").write_text(
        json.dumps({"release": manifest["release"], "previous": None}) + "\n", encoding="utf-8"
    )
    return out


def tilemaker_builder(cache: Path) -> MapBuilder:
    """Clip the cached GB extract to the points and build the map with the pinned tilemaker."""
    from within_reach_pipeline.config import load_config
    from within_reach_pipeline.maps import MAP_CONFIG, build_area_map
    from within_reach_pipeline.routing.osrm import area_bbox, clip_extract

    config = load_config()

    def build(area: str, points: list[LatLon], dest: Path) -> None:
        with ExitStack() as stack:
            work = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="fixture-")))
            pbf = clip_extract(cache / "uk.osm.pbf", area_bbox(points), work / "area.osm.pbf")
            coastline = cache / "coastline" if (cache / "coastline").exists() else work / "none"
            coastline.mkdir(exist_ok=True)
            build_area_map(config.tilemaker_image, pbf, points, MAP_CONFIG, coastline, dest)

    return build


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", type=Path, help="an extracted release, e.g. .../2026-11")
    parser.add_argument("dest", type=Path, help="the data folder, e.g. app/tests/fixtures/data")
    parser.add_argument("--districts", nargs="+", required=True)
    parser.add_argument("--split-area", default=None)
    parser.add_argument("--two-area", nargs=2, default=("LL11", "SY14 9ZZ"))
    parser.add_argument("--cache", type=Path, default=Path(".cache"))
    args = parser.parse_args(argv)
    release = json.loads((args.src / "manifest.json").read_text(encoding="utf-8"))["release"]
    manifest = trim_release(
        args.src,
        args.dest / release,
        args.districts,
        None,
        tilemaker_builder(args.cache),
        two_area=tuple(args.two_area),
        split_area=args.split_area,
    )
    for area in manifest["areas"]:
        print(
            f"{area['code']}: {area['postcodes']} postcodes, {len(area['map']['parts'])} map parts"
        )
    print(f"pharmacies: {manifest['directory']['count_by_nation']}")
    print(f"two-area test postcode: {args.two_area[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

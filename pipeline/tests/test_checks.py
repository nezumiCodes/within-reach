import dataclasses
import gzip
import hashlib
import json
import struct
from pathlib import Path

import pytest
from fakes import make_cache

from within_reach_pipeline import cli
from within_reach_pipeline.checks import CheckFailure, run_checks
from within_reach_pipeline.config import PipelineConfig, load_config
from within_reach_pipeline.maps import write_map_entry

# The fixture has 1 online-only pharmacy, not the 200+ a real release has.
CONFIG = dataclasses.replace(load_config(), distance_selling_min=1, distance_selling_max=10)


def _release(tmp_path: Path, name: str = "rel") -> Path:
    out = tmp_path / name
    cache = tmp_path / "cache" if (tmp_path / "cache").exists() else make_cache(tmp_path)
    argv = [
        "build",
        "--cache",
        str(cache),
        "--release",
        "2026-11",
        "--out",
        str(out),
        "--router",
        "fake",
        "--built-at",
        "2026-11-02T03:00:00Z",
    ]
    assert cli.run(argv) == 0
    return out


def _manifest(release: Path) -> dict:  # type: ignore[type-arg]
    return json.loads((release / "manifest.json").read_text())  # type: ignore[no-any-return]


def _save(release: Path, manifest: dict) -> None:  # type: ignore[type-arg]
    (release / "manifest.json").write_text(json.dumps(manifest))


def _only(failures: list[CheckFailure]) -> str:
    assert len(failures) == 1, failures
    return failures[0].check


def test_valid_release_passes(tmp_path: Path) -> None:
    release = _release(tmp_path)
    assert (
        run_checks(release, CONFIG, previous_dir=_release(tmp_path, "prev"), reference=None) == []
    )


def test_checksum_mismatch(tmp_path: Path) -> None:
    release = _release(tmp_path)
    manifest = _manifest(release)
    manifest["directory"]["sha256"] = "0" * 64
    _save(release, manifest)
    assert _only(run_checks(release, CONFIG, None, None)) == "checksums"


def test_bt_postcode_detected(tmp_path: Path) -> None:
    release = _release(tmp_path)
    path = release / "areas" / "E06000050" / "postcodes.csv.gz"
    text = gzip.decompress(path.read_bytes()).decode().replace("CH1 1AA", "BT1 1AA")
    path.write_bytes(gzip.compress(text.encode(), mtime=0))
    failures = run_checks(release, CONFIG, None, None)
    assert {f.check for f in failures} == {"no_bt", "checksums"}


def test_oversize_file(tmp_path: Path) -> None:
    release = _release(tmp_path)
    config = dataclasses.replace(CONFIG, max_file_bytes=10)
    assert {f.check for f in run_checks(release, config, None, None)} == {"size"}


def test_count_drop_over_tolerance(tmp_path: Path) -> None:
    release, previous = _release(tmp_path), _release(tmp_path, "prev")
    manifest = _manifest(previous)
    manifest["directory"]["count_by_nation"]["England"] = 4
    _save(previous, manifest)
    assert _only(run_checks(release, CONFIG, previous, None)) == "counts"


def test_postcode_total_drop_over_tolerance(tmp_path: Path) -> None:
    release, previous = _release(tmp_path), _release(tmp_path, "prev")
    manifest = _manifest(previous)
    manifest["areas"][0]["postcodes"] = 10
    _save(previous, manifest)
    assert _only(run_checks(release, CONFIG, previous, None)) == "counts"


def test_geocode_failures_over_limit(tmp_path: Path) -> None:
    release = _release(tmp_path)
    manifest = _manifest(release)
    manifest["geocode_failures"] = [{"nation": "Wales", "code": "FW9", "postcode": "LL1 1AA"}]
    _save(release, manifest)
    assert _only(run_checks(release, CONFIG, None, None)) == "geocode"


def test_postcode_short_of_candidates(tmp_path: Path) -> None:
    release = _release(tmp_path)
    config: PipelineConfig = dataclasses.replace(CONFIG, min_candidates=7)  # directory has 6
    failures = run_checks(release, config, None, None)
    assert {f.check for f in failures} == {"min_candidates"}
    assert len(failures) == 3  # one per area


def test_distance_selling_count_out_of_range(tmp_path: Path) -> None:
    release = _release(tmp_path)
    manifest = _manifest(release)
    manifest["excluded_distance_selling"] = 0
    _save(release, manifest)
    assert _only(run_checks(release, CONFIG, None, None)) == "distance_selling"


def test_missing_nation(tmp_path: Path) -> None:
    release = _release(tmp_path)
    manifest = _manifest(release)
    manifest["directory"]["count_by_nation"]["Scotland"] = 0
    _save(release, manifest)
    assert _only(run_checks(release, CONFIG, None, None)) == "nations"


def _reference(tmp_path: Path, nearest: str, walk_range: str) -> Path:
    path = tmp_path / "expectations.toml"
    path.write_text(
        f'[[case]]\npostcode = "CH1 1AA"\nnearest = [{nearest}]\nwalk_m_range = {walk_range}\n'
    )
    return path


def test_reference_passes_and_fails(tmp_path: Path) -> None:
    release = _release(tmp_path)
    good = _reference(tmp_path, '"England:FA001", "England:FA002"', "[600, 900]")
    assert run_checks(release, CONFIG, None, good) == []
    bad = _reference(tmp_path, '"England:FA001", "Wales:FW002"', "[600, 900]")
    assert _only(run_checks(release, CONFIG, None, bad)) == "reference"
    far = _reference(tmp_path, '"England:FA001"', "[1, 2]")
    assert _only(run_checks(release, CONFIG, None, far)) == "reference"


def test_reference_ignores_order_within_the_nearest(tmp_path: Path) -> None:
    # Near-ties (tens of metres) swap places when OSM paths change; the set is what matters.
    release = _release(tmp_path)
    swapped = _reference(tmp_path, '"England:FA002", "England:FA001"', "[600, 900]")
    assert run_checks(release, CONFIG, None, swapped) == []


def _set_walk(release: Path, row_prefix: str, walk_m: int) -> None:
    """Change one travel row's walking distance and keep the manifest checksums valid."""
    path = release / "areas" / "E06000050" / "travel.csv.gz"
    lines = gzip.decompress(path.read_bytes()).decode().splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith(row_prefix):
            cells = line.split(",")
            cells[3] = str(walk_m)
            lines[i] = ",".join(cells)
    data = gzip.compress("".join(lines).encode(), mtime=0)
    path.write_bytes(data)
    manifest = _manifest(release)
    entry = manifest["areas"][0]["files"]["travel"]
    entry["sha256"], entry["bytes"] = hashlib.sha256(data).hexdigest(), len(data)
    _save(release, manifest)


def test_reference_ranks_by_walking_distance(tmp_path: Path) -> None:
    # The travel file is in straight-line order; "nearest" means nearest on foot.
    release = _release(tmp_path)
    _set_walk(release, "0,0,", 99_999)  # CH1 1AA -> FA001 is closest in a line, far on foot
    walking = _reference(tmp_path, '"England:FA002", "Wales:FW002"', "[2400, 2600]")
    assert run_checks(release, CONFIG, None, walking) == []
    straight = _reference(tmp_path, '"England:FA001", "England:FA002"', "[600, 900]")
    assert _only(run_checks(release, CONFIG, None, straight)) == "reference"


def test_cli_check_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    release = _release(tmp_path)
    monkeypatch.setattr(cli, "load_config", lambda: CONFIG)
    assert cli.run(["check", "--release-dir", str(release)]) == 0
    manifest = _manifest(release)
    manifest["directory"]["sha256"] = "0" * 64
    _save(release, manifest)
    assert cli.run(["check", "--release-dir", str(release)]) == 1


def _partial_release(tmp_path: Path) -> Path:
    out = tmp_path / "partial"
    cache = make_cache(tmp_path)
    argv = [
        "build",
        "--cache",
        str(cache),
        "--release",
        "2026-11",
        "--out",
        str(out),
        "--router",
        "fake",
        "--built-at",
        "2026-11-02T03:00:00Z",
        "--areas",
        "E06000050",
    ]
    assert cli.run(argv) == 0
    return out


def test_partial_release_fails_completeness(tmp_path: Path) -> None:
    release = _partial_release(tmp_path)
    failures = run_checks(release, CONFIG, None, None)
    assert _only(failures) == "complete"
    assert "S12000049" in failures[0].detail and "W11000023" in failures[0].detail


def test_partial_release_allowed_explicitly(tmp_path: Path) -> None:
    release = _partial_release(tmp_path)
    assert run_checks(release, CONFIG, None, None, allow_partial=True) == []


def test_manifest_lists_all_areas(tmp_path: Path) -> None:
    manifest = _manifest(_partial_release(tmp_path))
    assert manifest["all_area_codes"] == ["E06000050", "S12000049", "W11000023"]
    assert manifest["complete"] is False


def _postcode_points(release: Path, code: str) -> list[tuple[float, float]]:
    path = release / "areas" / code / "postcodes.csv.gz"
    rows = gzip.decompress(path.read_bytes()).decode().splitlines()[1:]
    return [(float(r.split(",")[2]), float(r.split(",")[3])) for r in rows]


def _fake_pmtiles(bounds: tuple[float, float, float, float], size: int = 400) -> bytes:
    header = bytearray(size)
    header[:7] = b"PMTiles"
    header[7] = 3
    struct.pack_into("<iiii", header, 102, *(round(v * 1e7) for v in bounds))
    return bytes(header)


def _add_maps(release: Path, tmp_path: Path, chunk_bytes: int = 1000, shrink: bool = False) -> None:
    """Give every area a map covering its postcodes (or, with shrink, missing some)."""
    manifest = _manifest(release)
    manifest["config"]["maps"] = "tilemaker"
    for area in manifest["areas"]:
        lats, lons = zip(*_postcode_points(release, area["code"]), strict=True)
        west, south, east, north = (
            min(lons) - 0.01,
            min(lats) - 0.01,
            max(lons) + 0.01,
            max(lats) + 0.01,
        )
        if shrink:
            north = max(lats) - 0.0001
        built = tmp_path / f"{area['code']}.pmtiles"
        built.write_bytes(_fake_pmtiles((west, south, east, north)))
        area["map"] = write_map_entry(release, area["code"], built, chunk_bytes)
    _save(release, manifest)


def test_valid_release_with_maps_passes(tmp_path: Path) -> None:
    release = _release(tmp_path)
    _add_maps(release, tmp_path, chunk_bytes=150)
    assert run_checks(release, CONFIG, None, None) == []


def test_map_part_checksum_mismatch_fails(tmp_path: Path) -> None:
    release = _release(tmp_path)
    _add_maps(release, tmp_path, chunk_bytes=150)
    part = _manifest(release)["areas"][0]["map"]["parts"][1]["path"]
    data = bytearray((release / part).read_bytes())
    data[0] ^= 1
    (release / part).write_bytes(bytes(data))
    failures = run_checks(release, CONFIG, None, None)
    assert any(f.check == "checksums" and part in f.detail for f in failures)


def test_map_part_over_limit_fails(tmp_path: Path) -> None:
    release = _release(tmp_path)
    _add_maps(release, tmp_path)
    config = dataclasses.replace(CONFIG, max_file_bytes=300)
    failures = run_checks(release, config, None, None)
    assert any(f.check == "size" and "map.pmtiles" in f.detail for f in failures)


def test_area_without_map_fails_when_maps_built(tmp_path: Path) -> None:
    release = _release(tmp_path)
    _add_maps(release, tmp_path)
    manifest = _manifest(release)
    del manifest["areas"][0]["map"]
    _save(release, manifest)
    failures = run_checks(release, CONFIG, None, None)
    assert [f.detail for f in failures] == [f"{manifest['areas'][0]['code']} has no map"]
    assert failures[0].check == "maps"


def test_joined_map_hash_must_match(tmp_path: Path) -> None:
    release = _release(tmp_path)
    _add_maps(release, tmp_path, chunk_bytes=150)
    manifest = _manifest(release)
    manifest["areas"][0]["map"]["sha256"] = "0" * 64
    _save(release, manifest)
    assert _only(run_checks(release, CONFIG, None, None)) == "maps"


def test_map_bounds_must_cover_area_postcodes(tmp_path: Path) -> None:
    release = _release(tmp_path)
    _add_maps(release, tmp_path, shrink=True)
    failures = run_checks(release, CONFIG, None, None)
    assert {f.check for f in failures} == {"maps"}
    assert all("does not cover" in f.detail for f in failures)


def test_maps_none_skips_map_checks(tmp_path: Path) -> None:
    release = _release(tmp_path)
    assert _manifest(release)["config"]["maps"] == "none"
    assert run_checks(release, CONFIG, None, None) == []


def _edit_travel(release: Path, area: int, edit) -> None:  # type: ignore[no-untyped-def]
    """Rewrite one area's travel rows (header kept) and keep the manifest checksums valid."""
    manifest = _manifest(release)
    entry = manifest["areas"][area]["files"]["travel"]
    path = release / entry["path"]
    header, *rows = gzip.decompress(path.read_bytes()).decode().splitlines()
    rows = edit([r.split(",") for r in rows])
    data = gzip.compress(
        ("\n".join([header, *(",".join(r) for r in rows)]) + "\n").encode(), mtime=0
    )
    path.write_bytes(data)
    entry["sha256"], entry["bytes"] = hashlib.sha256(data).hexdigest(), len(data)
    manifest["areas"][area]["pairs"] = len(rows)
    _save(release, manifest)


def _keep_first(n: int, *pcs: str):  # type: ignore[no-untyped-def]
    """Keep only the first n rows of the given postcodes (pc_idx strings)."""

    def edit(rows: list[list[str]]) -> list[list[str]]:
        seen: dict[str, int] = {}
        kept = []
        for r in rows:
            seen[r[0]] = seen.get(r[0], 0) + 1
            if r[0] not in pcs or seen[r[0]] <= n:
                kept.append(r)
        return kept

    return edit


def _set_widened(release: Path, area: int, count: int) -> None:
    manifest = _manifest(release)
    manifest["areas"][area]["postcodes_widened_to_cap"] = count
    _save(release, manifest)


def test_walk_cycle_without_walk_fails(tmp_path: Path) -> None:
    release = _release(tmp_path)

    def edit(rows: list[list[str]]) -> list[list[str]]:
        rows[0][3], rows[0][4], rows[0][6] = "", "", "1"
        return rows

    _edit_travel(release, 0, edit)
    assert _only(run_checks(release, CONFIG, None, None)) == "walk_cycle"


def test_min_candidates_passes_short_postcode_widened_to_cap(tmp_path: Path) -> None:
    release = _release(tmp_path)
    _edit_travel(release, 0, _keep_first(3, "0"))
    _set_widened(release, 0, 1)
    assert run_checks(release, CONFIG, None, None) == []


def test_min_candidates_fails_short_postcode_with_unreachable_rows(tmp_path: Path) -> None:
    release = _release(tmp_path)

    def edit(rows: list[list[str]]) -> list[list[str]]:
        rows = _keep_first(3, "0")(rows)
        rows[0][3] = rows[0][4] = rows[0][5] = ""  # first row of postcode 0: no route at all
        return rows

    _edit_travel(release, 0, edit)
    _set_widened(release, 0, 1)
    assert _only(run_checks(release, CONFIG, None, None)) == "min_candidates"


def test_min_candidates_fails_more_short_reachable_than_widened(tmp_path: Path) -> None:
    release = _release(tmp_path)
    _edit_travel(release, 0, _keep_first(3, "0", "1"))
    _set_widened(release, 0, 1)
    assert _only(run_checks(release, CONFIG, None, None)) == "min_candidates"


def test_min_candidates_full_lists_still_pass(tmp_path: Path) -> None:
    release = _release(tmp_path)
    assert all(a["postcodes_widened_to_cap"] == 0 for a in _manifest(release)["areas"])
    assert run_checks(release, CONFIG, None, None) == []


def _edit_header(release: Path, area: int, header: str) -> None:
    manifest = _manifest(release)
    entry = manifest["areas"][area]["files"]["travel"]
    path = release / entry["path"]
    _, *rows = gzip.decompress(path.read_bytes()).decode().splitlines()
    data = gzip.compress(("\n".join([header, *rows]) + "\n").encode(), mtime=0)
    path.write_bytes(data)
    entry["sha256"], entry["bytes"] = hashlib.sha256(data).hexdigest(), len(data)
    _save(release, manifest)


def test_travel_header_must_be_the_current_layout(tmp_path: Path) -> None:
    # The app reads only the 6- and 7-column layouts; a new release must be 7 columns.
    release = _release(tmp_path)
    _edit_header(release, 0, "pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s,cycle")
    assert _only(run_checks(release, CONFIG, None, None)) == "travel_format"


def test_walk_cycle_must_be_one_or_blank(tmp_path: Path) -> None:
    release = _release(tmp_path)

    def edit(rows: list[list[str]]) -> list[list[str]]:
        rows[0][6] = "yes"
        return rows

    _edit_travel(release, 0, edit)
    assert _only(run_checks(release, CONFIG, None, None)) == "travel_format"


def test_manifest_needs_the_new_fields(tmp_path: Path) -> None:
    release = _release(tmp_path)
    manifest = _manifest(release)
    del manifest["config"]["walk_profile"]
    del manifest["areas"][1]["postcodes_without_route"]
    _save(release, manifest)
    failures = run_checks(release, CONFIG, None, None)
    assert {f.check for f in failures} == {"manifest_fields"}
    assert len(failures) == 2


def _reference_for(tmp_path: Path, postcode: str) -> Path:
    path = tmp_path / "expectations.toml"
    path.write_text(
        f'[[case]]\npostcode = "{postcode}"\nnearest = ["England:FA001"]\nwalk_m_range = [0, 1]\n'
    )
    return path


def test_reference_case_outside_a_partial_release_is_skipped(tmp_path: Path) -> None:
    # Partial runs build only the Chester and Wrexham areas; a Medway case can't apply.
    release = _partial_release(tmp_path)
    reference = _reference_for(tmp_path, "ZZ9 9ZZ")
    assert run_checks(release, CONFIG, None, reference, allow_partial=True) == []


def test_reference_case_missing_from_a_complete_release_fails(tmp_path: Path) -> None:
    release = _release(tmp_path)
    reference = _reference_for(tmp_path, "ZZ9 9ZZ")
    assert _only(run_checks(release, CONFIG, None, reference)) == "reference"

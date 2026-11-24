import csv
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fakes import make_cache

from within_reach_pipeline import cli
from within_reach_pipeline.bundle import SERVICES_ATTRIBUTION, merge_manifests
from within_reach_pipeline.config import PipelineConfig, load_config
from within_reach_pipeline.services import Snapshot, save_snapshot

BUILT_AT = "2026-11-02T03:00:00Z"


def _build(cache: Path, out: Path, *areas: str) -> dict:  # type: ignore[type-arg]
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
        BUILT_AT,
    ]
    if areas != ("ALL",):
        argv += ["--areas", *areas]
    assert cli.run(argv) == 0
    return json.loads((out / "manifest.json").read_text())  # type: ignore[no-any-return]


def test_build_cli_fake_router(tmp_path: Path) -> None:
    cache = make_cache(tmp_path)
    manifest = _build(cache, tmp_path / "out", "ALL")
    assert manifest["release"] == "2026-11"
    assert manifest["built_at"] == BUILT_AT
    assert [a["code"] for a in manifest["areas"]] == ["E06000050", "S12000049", "W11000023"]
    chester = manifest["areas"][0]
    assert chester["name"] == "Cheshire West and Chester"
    assert chester["nation"] == "England"
    assert chester["postcodes"] == 3
    assert chester["pairs"] == 3 * 5  # 2 within 5 km, so padded to the nearest 5
    assert manifest["directory"]["count_by_nation"] == {"England": 2, "Scotland": 2, "Wales": 2}
    assert manifest["excluded_distance_selling"] == 1
    assert manifest["geocode_failures"] == []
    assert any("OpenStreetMap" in line for line in manifest["attribution"])
    assert manifest["config"]["radius_m"] == 5000
    assert manifest["config"]["walk_profile"] == "foot-gb"
    assert manifest["config"]["reach_cap_m"] == 25000
    assert manifest["config"]["reach_max_rounds"] == 4
    assert manifest["config"]["cycle_note_min_extra_m"] == 50
    assert all(a["postcodes_without_route"] == 0 for a in manifest["areas"])
    assert all(a["postcodes_widened_to_cap"] == 0 for a in manifest["areas"])
    assert set(manifest["sources"]) == {
        "onspd",
        "nhsbsa",
        "contractor_details",
        "phs",
        "osm",
        "ods_wales",
    }
    files = [manifest["directory"], manifest["districts"]]
    files += [f for a in manifest["areas"] for f in a["files"].values()]
    for info in files:
        data = (tmp_path / "out" / info["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == info["sha256"]


def test_build_no_areas_writes_shared_files_only(tmp_path: Path) -> None:
    manifest = _build(make_cache(tmp_path), tmp_path / "out")
    assert manifest["areas"] == []
    assert (tmp_path / "out" / "pharmacies.csv.gz").exists()
    assert not (tmp_path / "out" / "areas").exists()


def test_merge_shards(tmp_path: Path) -> None:
    cache = make_cache(tmp_path)
    single = _build(cache, tmp_path / "single", "ALL")
    _build(cache, tmp_path / "s1", "E06000050")
    _build(cache, tmp_path / "s2", "S12000049", "W11000023")
    _build(cache, tmp_path / "merged")
    shards = [str(tmp_path / "s1"), str(tmp_path / "s2")]
    assert cli.run(["merge", "--out", str(tmp_path / "merged"), *shards]) == 0
    merged = json.loads((tmp_path / "merged" / "manifest.json").read_text())
    assert merged == single
    assert (tmp_path / "merged" / "areas" / "W11000023" / "travel.csv.gz").exists()


def test_merge_rejects_directory_mismatch() -> None:
    base = {"directory": {"sha256": "a"}, "areas": []}
    with pytest.raises(ValueError, match="directory"):
        merge_manifests(base, [{"directory": {"sha256": "b"}, "areas": []}])


def test_build_rejects_bad_release(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.run(
            ["build", "--cache", str(tmp_path), "--release", "../x", "--out", str(tmp_path / "o")]
        )


def test_areas_command_prints_shards(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cache = make_cache(tmp_path)
    assert cli.run(["areas", "--cache", str(cache), "--shard-size", "2"]) == 0
    assert json.loads(capsys.readouterr().out) == ["E06000050 S12000049", "W11000023"]


def test_areas_command_honours_explicit_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = make_cache(tmp_path)
    assert cli.run(["areas", "--cache", str(cache), "--only", "W11000023", "E06000050"]) == 0
    assert json.loads(capsys.readouterr().out) == ["E06000050 W11000023"]


def test_manifest_counts_postcodes_without_walking_route(tmp_path: Path) -> None:
    from within_reach_pipeline.build import postcodes_without_walk
    from within_reach_pipeline.routing import TravelRow

    rows = [
        TravelRow(0, 1, 100, None, None, 60),
        TravelRow(0, 2, 200, None, None, 90),
        TravelRow(1, 1, 150, 190, 140, 70),
        TravelRow(1, 2, 300, None, None, 99),
    ]
    assert postcodes_without_walk(rows) == 1  # postcode 0 has no walking route at all


def test_area_entry_has_no_walk_count(tmp_path: Path) -> None:
    manifest = _build(make_cache(tmp_path), tmp_path / "out", "ALL")
    assert all(a["postcodes_without_walk"] == 0 for a in manifest["areas"])


def test_build_without_maps_has_no_map_entries(tmp_path: Path) -> None:
    manifest = _build(make_cache(tmp_path), tmp_path / "out", "ALL")
    assert manifest["config"]["maps"] == "none"
    assert all("map" not in area for area in manifest["areas"])


def test_build_with_maps_records_map_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from within_reach_pipeline import build

    calls: list[Path] = []

    def fake_extract(stack: object, cache: Path, points: object) -> Path:
        return tmp_path / "area.osm.pbf"

    def fake_map(
        image: str, pbf: Path, points: object, config_file: Path, coastline: Path, dest: Path
    ) -> None:
        calls.append(pbf)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"PMTiles\x03" + b"\0" * 2)

    monkeypatch.setattr(build, "_area_extract", fake_extract)
    monkeypatch.setattr(build, "build_area_map", fake_map)
    cache = make_cache(tmp_path)
    out = tmp_path / "out"
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
        BUILT_AT,
        "--maps",
        "tilemaker",
    ]
    assert cli.run(argv) == 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["config"]["maps"] == "tilemaker"
    assert calls == [tmp_path / "area.osm.pbf"] * len(manifest["areas"])
    for area in manifest["areas"]:
        part = area["map"]["parts"][0]
        assert part["path"] == f"areas/{area['code']}/map.pmtiles"
        assert (out / part["path"]).read_bytes().startswith(b"PMTiles")
        assert area["map"]["bytes"] == 10


def test_merge_takes_maps_setting_from_shards() -> None:
    base: dict[str, Any] = {"directory": {"sha256": "a"}, "areas": [], "config": {"maps": "none"}}
    shard = {"directory": {"sha256": "a"}, "areas": [], "config": {"maps": "tilemaker"}}
    merged = merge_manifests(base, [shard, shard])
    assert merged["config"]["maps"] == "tilemaker"
    assert base["config"]["maps"] == "none"  # input untouched


def test_merge_rejects_shards_that_disagree_on_maps() -> None:
    base = {"directory": {"sha256": "a"}, "areas": [], "config": {"maps": "none"}}
    with_maps = {"directory": {"sha256": "a"}, "areas": [], "config": {"maps": "tilemaker"}}
    without = {"directory": {"sha256": "a"}, "areas": [], "config": {"maps": "none"}}
    with pytest.raises(ValueError, match="maps"):
        merge_manifests(base, [with_maps, without])


def _services_config() -> PipelineConfig:
    return replace(load_config(), services_enabled=True)


def _build_with(cache: Path, out: Path, *areas: str) -> dict:  # type: ignore[type-arg]
    argv = ["build", "--cache", str(cache), "--release", "2026-11", "--out", str(out)]
    argv += ["--router", "fake", "--built-at", BUILT_AT]
    if areas:
        argv += ["--areas", *areas]
    assert cli.run(argv, config=_services_config()) == 0
    return json.loads((out / "manifest.json").read_text())  # type: ignore[no-any-return]


def _save_snapshot(cache: Path) -> None:
    listed = {"FA002": frozenset({"SRV0274"}), "FZZZZ": frozenset()}  # FA001 has no DoHS record
    save_snapshot(
        Snapshot("2026-11-01T00:00:00Z", "https://api.service.nhs.uk/service-search-api/", listed),
        cache / cli.SERVICES_FILE,
    )


def test_build_with_snapshot_writes_services(tmp_path: Path) -> None:
    cache = make_cache(tmp_path)
    _save_snapshot(cache)
    manifest = _build_with(cache, tmp_path / "out", "E06000050")
    assert manifest["config"]["services"] == [
        {
            "key": "nsp",
            "name": "Needle exchange",
            "nations": ["England"],
            "source": SERVICES_ATTRIBUTION,
            "source_fetched_at": "2026-11-01T00:00:00Z",
        }
    ]
    assert manifest["config"]["service_min"] == 5
    assert manifest["services"] == {"nsp": {"listed": 1, "unmatched_dohs": 1, "missing_dohs": 1}}
    assert SERVICES_ATTRIBUTION in manifest["attribution"]
    with gzip.open(tmp_path / "out" / "pharmacies.csv.gz", "rt") as f:
        rows = list(csv.reader(f))
    assert rows[0][-1] == "services"
    cells = {r[2]: r[-1] for r in rows[1:]}
    assert cells["FA002"] == "nsp" and cells["FA001"] == ""
    assert all(v == "nsp?" for k, v in cells.items() if k not in ("FA002", "FA001"))


def test_build_without_snapshot_has_empty_services(tmp_path: Path) -> None:
    manifest = _build(make_cache(tmp_path), tmp_path / "out")
    assert manifest["config"]["services"] == [] and manifest["services"] == {}
    assert SERVICES_ATTRIBUTION not in manifest["attribution"]
    with gzip.open(tmp_path / "out" / "pharmacies.csv.gz", "rt") as f:
        assert {r[-1] for r in list(csv.reader(f))[1:]} == {""}


def test_build_enabled_without_snapshot_fails(tmp_path: Path) -> None:
    cache = make_cache(tmp_path)
    with pytest.raises(FileNotFoundError, match="fetch-services"):
        _build_with(cache, tmp_path / "out")


def test_merge_keeps_services_fields(tmp_path: Path) -> None:
    cache = make_cache(tmp_path)
    _save_snapshot(cache)
    _build_with(cache, tmp_path / "s1", "E06000050")
    _build_with(cache, tmp_path / "s2", "S12000049", "W11000023")
    base = _build_with(cache, tmp_path / "merged")
    assert (
        cli.run(
            ["merge", "--out", str(tmp_path / "merged"), str(tmp_path / "s1"), str(tmp_path / "s2")]
        )
        == 0
    )
    merged = json.loads((tmp_path / "merged" / "manifest.json").read_text())
    for key in ("services", "attribution"):
        assert merged[key] == base[key]
    assert merged["config"]["services"] == base["config"]["services"]
    assert merged["config"]["service_min"] == base["config"]["service_min"]


def test_area_entry_counts_service_shortfall(tmp_path: Path) -> None:
    cache = make_cache(tmp_path)
    off = _build(cache, tmp_path / "off", "E06000050")
    assert off["areas"][0]["services"] == {}
    _save_snapshot(cache)
    on = _build_with(cache, tmp_path / "on", "E06000050")
    # Only FA002 lists the service, so every Chester postcode is short of 5.
    assert on["areas"][0]["services"] == {"nsp": {"postcodes_short": 3}}


def test_build_extract_includes_service_pharmacies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pharmacy listing the service 15 km away, not a first-pass candidate, lies inside the
    extract, and is routed."""
    from within_reach_pipeline import build
    from within_reach_pipeline.config import ServiceDef

    boxes: list[tuple[float, float, float, float]] = []

    def fake_extract(stack: object, cache: Path, bbox: tuple[float, float, float, float]) -> Path:
        boxes.append(bbox)
        return tmp_path / "area.osm.pbf"

    def fake_map(
        image: str, pbf: Path, points: object, config_file: Path, coastline: Path, dest: Path
    ) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"PMTiles\x03" + b"\0" * 2)

    monkeypatch.setattr(build, "_area_extract", fake_extract)
    monkeypatch.setattr(build, "build_area_map", fake_map)
    cache = make_cache(tmp_path)
    save_snapshot(
        Snapshot(
            "2026-11-01T00:00:00Z",
            "https://api.service.nhs.uk/service-search-api/",
            {"FW002": frozenset({"SRV0274"})},
        ),
        cache / cli.SERVICES_FILE,
    )
    # Two first-pass candidates (the Chester pharmacies); the service also covers Wales here,
    # so FW002 in Wrexham (LL12 7AA, about 15 km from Chester) lists it.
    config = replace(
        load_config(),
        services_enabled=True,
        min_candidates=2,
        radius_m=2500,
        services=(ServiceDef("nsp", "Needle exchange", "SRV0274", ("England", "Wales")),),
    )
    out = tmp_path / "out"
    argv = ["build", "--cache", str(cache), "--release", "2026-11", "--out", str(out)]
    argv += ["--router", "fake", "--built-at", BUILT_AT, "--maps", "tilemaker"]
    argv += ["--areas", "E06000050"]
    assert cli.run(argv, config=config) == 0
    [(min_lon, min_lat, max_lon, max_lat)] = boxes
    fw002_lat, fw002_lon = 53.0606, -2.9779
    assert min_lat <= fw002_lat <= max_lat and min_lon <= fw002_lon <= max_lon
    with gzip.open(out / "pharmacies.csv.gz", "rt") as f:
        codes = [r[2] for r in list(csv.reader(f))[1:]]
    fw002 = codes.index("FW002")
    with gzip.open(out / "areas" / "E06000050" / "travel.csv.gz", "rt") as f:
        travel = list(csv.DictReader(f))
    for pc_idx in ("0", "1", "2"):
        rows = [r for r in travel if r["pc_idx"] == pc_idx]
        assert str(fw002) in {r["ph_idx"] for r in rows}
        assert len(rows) == 3  # FA001, FA002 and the service row FW002

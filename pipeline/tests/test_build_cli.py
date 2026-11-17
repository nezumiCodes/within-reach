import hashlib
import json
from pathlib import Path

import pytest
from fakes import make_cache

from within_reach_pipeline import cli
from within_reach_pipeline.bundle import merge_manifests

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

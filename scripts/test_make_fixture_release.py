import csv
import gzip
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline" / "tests"))
from fakes import make_cache  # type: ignore[import-not-found]

from within_reach_pipeline import cli
from within_reach_pipeline.checks import run_checks
from within_reach_pipeline.config import load_config

_spec = importlib.util.spec_from_file_location(
    "make_fixture_release", Path(__file__).with_name("make_fixture_release.py")
)
assert _spec is not None and _spec.loader is not None
mfr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mfr)


def _rows(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(gzip.decompress(path.read_bytes()).decode())))


@pytest.fixture
def source(tmp_path: Path) -> Path:
    out = tmp_path / "src" / "2026-11"
    argv = ["build", "--cache", str(make_cache(tmp_path)), "--release", "2026-11"]
    argv += ["--out", str(out), "--router", "fake", "--built-at", "2026-11-02T03:00:00Z"]
    assert cli.run(argv) == 0
    return out


def test_trimmed_release_passes_release_checks(source: Path, tmp_path: Path) -> None:
    districts = sorted(r["outward"] for r in _rows(source / "districts.csv.gz"))
    dest = tmp_path / "fixture"
    mfr.trim_release(source, dest / "2026-11", districts, chunk_bytes=None, build_map=None)
    config = load_config()
    config = type(config)(**{**config.__dict__, "distance_selling_min": 1})
    failures = run_checks(dest / "2026-11", config, None, None, allow_partial=True)
    assert failures == []
    assert json.loads((dest / "latest.json").read_text()) == {
        "release": "2026-11",
        "previous": None,
    }


def test_trimmed_release_renumbers_and_links(source: Path, tmp_path: Path) -> None:
    dest = tmp_path / "fixture" / "2026-11"
    manifest = mfr.trim_release(source, dest, ["CH1"], chunk_bytes=None, build_map=None)
    pharmacies = _rows(dest / "pharmacies.csv.gz")
    assert [int(p["ph_idx"]) for p in pharmacies] == list(range(len(pharmacies)))
    [area] = manifest["areas"]
    postcodes = _rows(dest / area["files"]["postcodes"]["path"])
    assert [p["postcode"] for p in postcodes] == sorted(p["postcode"] for p in postcodes)
    assert all(p["postcode"].startswith("CH1 ") for p in postcodes)
    assert [int(p["pc_idx"]) for p in postcodes] == list(range(len(postcodes)))
    travel = _rows(dest / area["files"]["travel"]["path"])
    assert {int(t["ph_idx"]) for t in travel} == set(range(len(pharmacies)))
    assert {int(t["pc_idx"]) for t in travel} == set(range(len(postcodes)))


def test_relabelled_postcode_lands_in_a_two_area_district(source: Path, tmp_path: Path) -> None:
    dest = tmp_path / "fixture" / "2026-11"
    manifest = mfr.trim_release(
        source,
        dest,
        ["CH1", "LL11"],
        chunk_bytes=None,
        build_map=None,
        two_area=("LL11", "SY14 9ZZ"),
    )
    districts = {r["outward"]: r["area_codes"] for r in _rows(dest / "districts.csv.gz")}
    assert districts["SY14"] == "E06000050 W11000023"
    welsh = next(a for a in manifest["areas"] if a["code"] == "W11000023")
    postcodes = [p["postcode"] for p in _rows(dest / welsh["files"]["postcodes"]["path"])]
    assert "SY14 9ZZ" in postcodes and postcodes == sorted(postcodes)


def test_maps_are_built_and_split(source: Path, tmp_path: Path) -> None:
    def fake_map(area: str, points: list[tuple[float, float]], dest: Path) -> None:
        dest.write_bytes(b"PMTiles\x03" + bytes(300))

    dest = tmp_path / "fixture" / "2026-11"
    manifest = mfr.trim_release(
        source, dest, ["CH1", "LL11"], chunk_bytes=None, build_map=fake_map, split_area="E06000050"
    )
    maps = {a["code"]: a["map"] for a in manifest["areas"]}
    assert len(maps["E06000050"]["parts"]) == 2
    assert len(maps["W11000023"]["parts"]) == 1
    assert manifest["config"]["maps"] == "tilemaker"


def _rewrite_travel(source: Path, edit) -> None:  # type: ignore[no-untyped-def]
    manifest = json.loads((source / "manifest.json").read_text())
    path = source / manifest["areas"][0]["files"]["travel"]["path"]
    header, *rows = gzip.decompress(path.read_bytes()).decode().splitlines()
    header, rows = edit(header, rows)
    path.write_bytes(gzip.compress(("\n".join([header, *rows]) + "\n").encode(), mtime=0))


def test_walk_cycle_column_is_carried_through(source: Path, tmp_path: Path) -> None:
    def mark_all(header: str, rows: list[str]) -> tuple[str, list[str]]:
        return header, [r + "1" for r in rows]  # each row ends with an empty walk_cycle

    _rewrite_travel(source, mark_all)
    dest = tmp_path / "fixture" / "2026-11"
    manifest = mfr.trim_release(source, dest, ["CH1"], chunk_bytes=None, build_map=None)
    travel = _rows(dest / manifest["areas"][0]["files"]["travel"]["path"])
    assert "walk_cycle" in travel[0]
    assert travel and all(t["walk_cycle"] == "1" for t in travel)
    assert manifest["areas"][0]["postcodes_without_route"] == 0
    assert manifest["areas"][0]["postcodes_widened_to_cap"] == 0


def test_services_file_fills_the_services_column_and_config(source: Path, tmp_path: Path) -> None:
    pharmacies = _rows(source / "pharmacies.csv.gz")
    english = next(p for p in pharmacies if p["nation"] == "England")
    welsh = next(p for p in pharmacies if p["nation"] == "Wales")
    services = tmp_path / "services.csv"
    services.write_text(
        f"nation,code,services\nEngland,{english['code']},nsp\nWales,{welsh['code']},nsp?\n"
    )
    districts = sorted(r["outward"] for r in _rows(source / "districts.csv.gz"))
    dest = tmp_path / "fixture" / "2026-11"
    manifest = mfr.trim_release(
        source, dest, districts, chunk_bytes=None, build_map=None, services=services
    )
    cells = {(p["nation"], p["code"]): p["services"] for p in _rows(dest / "pharmacies.csv.gz")}
    assert cells.pop(("England", english["code"])) == "nsp"
    assert cells.pop(("Wales", welsh["code"])) == "nsp?"
    assert set(cells.values()) == {""}
    assert manifest["config"]["services"] == [
        {
            "key": "nsp",
            "name": "Needle exchange",
            "nations": ["England"],
            "source": mfr.SERVICES_ATTRIBUTION,
            "source_fetched_at": "2026-11-24T00:00:00Z",
        }
    ]
    saved = json.loads((dest / "manifest.json").read_text())
    assert saved["config"]["services"] == manifest["config"]["services"]


def test_services_column_is_added_to_an_older_source(source: Path, tmp_path: Path) -> None:
    path = source / "pharmacies.csv.gz"
    header, *rows = gzip.decompress(path.read_bytes()).decode().splitlines()
    assert header.endswith(",services")
    old = [header.removesuffix(",services"), *(r.rsplit(",", 1)[0] for r in rows)]
    path.write_bytes(gzip.compress(("\n".join(old) + "\n").encode(), mtime=0))
    services = tmp_path / "services.csv"
    services.write_text("nation,code,services\n")
    dest = tmp_path / "fixture" / "2026-11"
    mfr.trim_release(source, dest, ["CH1"], chunk_bytes=None, build_map=None, services=services)
    assert list(_rows(dest / "pharmacies.csv.gz")[0])[-1] == "services"


def test_without_services_file_output_is_unchanged(source: Path, tmp_path: Path) -> None:
    dest = tmp_path / "fixture" / "2026-11"
    manifest = mfr.trim_release(source, dest, ["CH1"], chunk_bytes=None, build_map=None)
    source_manifest = json.loads((source / "manifest.json").read_text())
    assert manifest["config"]["services"] == source_manifest["config"]["services"]
    assert list(_rows(dest / "pharmacies.csv.gz")[0]) == list(
        _rows(source / "pharmacies.csv.gz")[0]
    )


def test_older_six_column_source_stays_six_columns(source: Path, tmp_path: Path) -> None:
    def drop_column(header: str, rows: list[str]) -> tuple[str, list[str]]:
        return header.rsplit(",", 1)[0], [r.rsplit(",", 1)[0] for r in rows]

    _rewrite_travel(source, drop_column)
    dest = tmp_path / "fixture" / "2026-11"
    manifest = mfr.trim_release(source, dest, ["CH1"], chunk_bytes=None, build_map=None)
    travel = _rows(dest / manifest["areas"][0]["files"]["travel"]["path"])
    assert list(travel[0]) == ["pc_idx", "ph_idx", "straight_m", "walk_m", "walk_s", "drive_s"]

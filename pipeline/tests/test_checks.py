import dataclasses
import gzip
import json
from pathlib import Path

import pytest
from fakes import make_cache

from within_reach_pipeline import cli
from within_reach_pipeline.checks import CheckFailure, run_checks
from within_reach_pipeline.config import PipelineConfig, load_config

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
    bad = _reference(tmp_path, '"England:FA002", "England:FA001"', "[600, 900]")
    assert _only(run_checks(release, CONFIG, None, bad)) == "reference"
    far = _reference(tmp_path, '"England:FA001"', "[1, 2]")
    assert _only(run_checks(release, CONFIG, None, far)) == "reference"


def test_cli_check_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    release = _release(tmp_path)
    monkeypatch.setattr(cli, "load_config", lambda: CONFIG)
    assert cli.run(["check", "--release-dir", str(release)]) == 0
    manifest = _manifest(release)
    manifest["directory"]["sha256"] = "0" * 64
    _save(release, manifest)
    assert cli.run(["check", "--release-dir", str(release)]) == 1

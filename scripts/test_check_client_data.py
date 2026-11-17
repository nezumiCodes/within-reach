import importlib.util
from pathlib import Path, PurePosixPath

import pytest

_spec = importlib.util.spec_from_file_location(
    "check_client_data", Path(__file__).with_name("check_client_data.py")
)
assert _spec is not None and _spec.loader is not None
ccd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ccd)


def _write(tmp_path: Path, rel: str, content: str) -> tuple[Path, PurePosixPath]:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path, PurePosixPath(rel)


def test_csv_outside_synthetic_is_blocked(tmp_path: Path) -> None:
    path, rel = _write(tmp_path, "clients.csv", "client_ref,home_postcode\nSYN-1,CH1 1AA\n")
    assert ccd.problems_for(path, rel)


def test_synthetic_csv_passes(tmp_path: Path) -> None:
    path, rel = _write(
        tmp_path, "fixtures/synthetic/ok.csv", "client_ref,home_postcode\nSYN-1,CH1 1AA\n"
    )
    assert ccd.problems_for(path, rel) == []


@pytest.mark.parametrize("column", ["name", "Surname", "NHS Number", "nhs_no", "dob"])
def test_forbidden_columns(tmp_path: Path, column: str) -> None:
    path, rel = _write(tmp_path, "fixtures/synthetic/bad.csv", f"client_ref,{column}\nSYN-1,x\n")
    assert any("forbidden column" in p for p in ccd.problems_for(path, rel))


def test_non_synthetic_ref(tmp_path: Path) -> None:
    path, rel = _write(tmp_path, "fixtures/synthetic/bad.csv", "client_ref\nAB123\n")
    assert any("must start with SYN-" in p for p in ccd.problems_for(path, rel))


def test_valid_nhs_number_detected(tmp_path: Path) -> None:
    # 943 476 5919 is the NHS's published example of a valid number.
    path, rel = _write(tmp_path, "fixtures/synthetic/bad.csv", "client_ref,x\nSYN-1,9434765919\n")
    assert any("NHS number" in p for p in ccd.problems_for(path, rel))


def test_xlsx_outside_synthetic_blocked(tmp_path: Path) -> None:
    path, rel = _write(tmp_path, "Downloads/caseload.xlsx", "binary")
    assert ccd.problems_for(path, rel)


def test_other_files_ignored(tmp_path: Path) -> None:
    path, rel = _write(tmp_path, "README.md", "9434765919")
    assert ccd.problems_for(path, rel) == []


def test_pipeline_public_fixtures_allowed(tmp_path: Path) -> None:
    path, rel = _write(
        tmp_path, "pipeline/tests/fixtures/phs_sample.csv", "DispCode,DispLocationName\n1030,X\n"
    )
    assert ccd.problems_for(path, rel) == []


def test_pipeline_fixtures_still_scanned(tmp_path: Path) -> None:
    path, rel = _write(tmp_path, "pipeline/tests/fixtures/bad.csv", "client_ref,name\nAB1,x\n")
    assert ccd.problems_for(path, rel)

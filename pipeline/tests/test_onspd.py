from pathlib import Path

import pytest

from within_reach_pipeline.onspd import (
    area_code_for,
    read_area_names,
    read_onspd,
    resolve_columns,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "onspd_sample.csv"


def _header() -> list[str]:
    return SAMPLE.read_text(encoding="utf-8").splitlines()[0].split(",")


def test_resolve_columns_real_header() -> None:
    columns = resolve_columns(_header())
    assert columns.lad == "lad26cd"
    assert columns.hlth == "hlth19cd"
    assert columns.ctry == "ctry26cd"
    assert columns.lon == "long"


def test_resolve_columns_future_suffixes() -> None:
    header = [{"lad26cd": "lad27cd", "ctry26cd": "ctry27cd"}.get(h, h) for h in _header()]
    columns = resolve_columns(header)
    assert columns.lad == "lad27cd"
    assert columns.ctry == "ctry27cd"


def test_resolve_columns_missing_raises() -> None:
    header = [h for h in _header() if h != "lat"]
    with pytest.raises(ValueError, match="lat"):
        resolve_columns(header)


def test_read_onspd_filters() -> None:
    postcodes = list(read_onspd(SAMPLE))
    assert [(p.postcode, p.nation) for p in postcodes] == [
        ("CH1 1AA", "England"),
        ("EH1 1YZ", "Scotland"),
        ("LL11 1AA", "Wales"),
        ("CB2 1TN", "England"),
    ]
    chester = postcodes[0]
    assert (chester.east, chester.north) == (340500, 366300)
    assert (chester.lat, chester.lon) == (53.19, -2.89)
    assert chester.area_code == "E06000050"
    assert postcodes[3].area_code == "E10000003"


def test_area_code_for() -> None:
    assert area_code_for("England", "E10000003", "E07000008", "E18000007") == "E10000003"
    assert area_code_for("England", "E99999999", "E06000050", "E18000008") == "E06000050"
    assert area_code_for("Scotland", "S99999999", "S12000036", "S08000024") == "S12000036"
    assert area_code_for("Wales", "W99999999", "W06000006", "W11000023") == "W11000023"


def test_read_area_names() -> None:
    names = read_area_names(FIXTURES / "onspd_names")
    assert names["E06000050"] == "Cheshire West and Chester"
    assert names["W11000023"] == "Betsi Cadwaladr University Health Board"
    assert names["E10000003"] == "Cambridgeshire"

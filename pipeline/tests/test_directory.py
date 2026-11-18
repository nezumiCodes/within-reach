from within_reach_pipeline.models import Postcode, RawPharmacy
from within_reach_pipeline.pharmacies import build_directory


def _raw(nation: str, code: str, postcode: str) -> RawPharmacy:
    return RawPharmacy(nation, code, f"{code} PHARMACY", ("1 HIGH ST",), postcode, None)  # type: ignore[arg-type]


INDEX = {
    "SK7 5LD": Postcode("SK7 5LD", 53.37, -2.12, 392000, 385000, "England", "E08000007"),
    "G22 5ER": Postcode("G22 5ER", 55.88, -4.24, 259000, 668000, "Scotland", "S12000049"),
    "LL11 4UF": Postcode("LL11 4UF", 53.06, -3.00, 333000, 351000, "Wales", "W11000023"),
}


def test_build_directory_sorted_and_geocoded() -> None:
    raw = [
        _raw("Wales", "FWF56", "LL11 4UF"),
        _raw("Scotland", "1030", "G22 5ER"),
        _raw("England", "FA002", "SK7 5LD"),
    ]
    result = build_directory(raw, INDEX, hours_warnings=2, distance_selling=frozenset())
    assert [p.key for p in result.pharmacies] == [
        ("England", "FA002"),
        ("Scotland", "1030"),
        ("Wales", "FWF56"),
    ]
    assert (result.pharmacies[0].east, result.pharmacies[0].north) == (392000, 385000)
    assert result.hours_warnings == 2


def test_build_directory_geocode_failure() -> None:
    raw = [_raw("England", "FA002", "SK7 5LD"), _raw("England", "FZZ99", "ZZ9 9ZZ")]
    result = build_directory(raw, INDEX, hours_warnings=0, distance_selling=frozenset())
    assert [p.key for p in result.pharmacies] == [("England", "FA002")]
    assert [r.code for r in result.geocode_failures] == ["FZZ99"]


def test_build_directory_excludes_distance_selling() -> None:
    raw = [_raw("England", "FAA01", "SK7 5LD"), _raw("Wales", "FAA01", "LL11 4UF")]
    result = build_directory(raw, INDEX, hours_warnings=0, distance_selling=frozenset({"FAA01"}))
    assert [p.key for p in result.pharmacies] == [("Wales", "FAA01")]
    assert result.excluded_distance_selling == 1


def test_build_directory_duplicate_key_keeps_first() -> None:
    raw = [_raw("England", "FA002", "SK7 5LD"), _raw("England", "FA002", "SK7 5LD")]
    result = build_directory(raw, INDEX, hours_warnings=0, distance_selling=frozenset())
    assert len(result.pharmacies) == 1

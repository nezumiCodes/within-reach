from within_reach_pipeline.candidates import Candidate, select_candidates
from within_reach_pipeline.models import Pharmacy, Postcode, RawPharmacy

ORIGIN = Postcode("CH1 1AA", 53.19, -2.89, 400000, 400000, "England", "E06000050")


def _pharmacy(nation: str, code: str, east: int, north: int) -> Pharmacy:
    raw = RawPharmacy(nation, code, code, (), "CH1 1AA", None)  # type: ignore[arg-type]
    return Pharmacy(raw, 0.0, 0.0, east, north)


def _sorted(pharmacies: list[Pharmacy]) -> list[Pharmacy]:
    return sorted(pharmacies, key=lambda p: p.key)


def test_within_radius_sorted_then_padded() -> None:
    pharmacies = _sorted(
        [
            _pharmacy("England", "FA003", 406000, 400000),
            _pharmacy("England", "FA001", 400100, 400000),
            _pharmacy("England", "FA002", 400000, 400300),
        ]
    )
    [result] = select_candidates([ORIGIN], pharmacies, 5000, 40, 3)
    assert result == [Candidate(0, 100), Candidate(1, 300), Candidate(2, 6000)]


def test_cap_at_max() -> None:
    pharmacies = _sorted(
        [_pharmacy("England", f"F{i:04d}", 400000 + i * 10, 400000) for i in range(1, 51)]
    )
    [result] = select_candidates([ORIGIN], pharmacies, 5000, 40, 5)
    assert len(result) == 40
    assert result[0].straight_m == 10
    assert result[-1].straight_m == 400


def test_remote_postcode_gets_min_five() -> None:
    pharmacies = _sorted(
        [_pharmacy("Scotland", f"{1000 + i}", 430000 + i * 1000, 400000) for i in range(8)]
    )
    [result] = select_candidates([ORIGIN], pharmacies, 5000, 40, 5)
    assert len(result) == 5
    assert all(c.straight_m > 5000 for c in result)
    assert [c.straight_m for c in result] == [30000, 31000, 32000, 33000, 34000]


def test_tie_break_nation_then_code() -> None:
    pharmacies = _sorted(
        [
            _pharmacy("Scotland", "1001", 401000, 400000),
            _pharmacy("England", "FZZ99", 399000, 400000),
            _pharmacy("England", "FAA00", 400000, 401000),
        ]
    )
    [result] = select_candidates([ORIGIN], pharmacies, 5000, 40, 1)
    keys = [pharmacies[c.ph_idx].key for c in result]
    assert keys == [("England", "FAA00"), ("England", "FZZ99"), ("Scotland", "1001")]


def test_fewer_pharmacies_than_min() -> None:
    pharmacies = _sorted(
        [_pharmacy("Wales", "FW001", 450000, 400000), _pharmacy("Wales", "FW002", 460000, 400000)]
    )
    [result] = select_candidates([ORIGIN], pharmacies, 5000, 40, 5)
    assert [c.ph_idx for c in result] == [0, 1]


def test_no_pharmacies() -> None:
    assert select_candidates([ORIGIN], [], 5000, 40, 5) == [[]]

import math
from collections.abc import Sequence

from within_reach_pipeline.candidates import Candidate
from within_reach_pipeline.models import Pharmacy, Postcode, RawPharmacy
from within_reach_pipeline.routing import LatLon, TableResult, TravelRow, route_candidates
from within_reach_pipeline.routing.fake import EARTH_RADIUS_M, FakeRouter

ONE_KM_LAT = 1000 / (EARTH_RADIUS_M * math.pi / 180)


def _postcode(name: str, lat: float, east: int) -> Postcode:
    return Postcode(name, lat, -2.89, east, 400000, "England", "E06000050")


def _pharmacy(code: str, lat: float) -> Pharmacy:
    raw = RawPharmacy("England", code, code, (), "CH1 1AA", None)
    return Pharmacy(raw, lat, -2.89, 400000, 401000)


WALK = FakeRouter(speed_m_s=1.4)
DRIVE = FakeRouter(speed_m_s=13.4)


def test_route_candidates_uses_router_values() -> None:
    postcodes = [_postcode("CH1 1AA", 53.0, 400000)]
    pharmacies = [_pharmacy("FA001", 53.0 + ONE_KM_LAT)]
    [row] = route_candidates(postcodes, pharmacies, [[Candidate(0, 1000)]], WALK, DRIVE)
    assert row == TravelRow(
        pc_idx=0, ph_idx=0, straight_m=1000, walk_m=1300, walk_s=929, drive_s=97
    )


def test_unreachable_leaves_blanks() -> None:
    target = 53.0 + ONE_KM_LAT
    walk = FakeRouter(speed_m_s=1.4, unreachable={(target, -2.89)})
    postcodes = [_postcode("CH1 1AA", 53.0, 400000)]
    [row] = route_candidates(
        postcodes, [_pharmacy("FA001", target)], [[Candidate(0, 1000)]], walk, DRIVE
    )
    assert row.walk_m is None and row.walk_s is None
    assert row.straight_m == 1000
    assert row.drive_s == 97


class CountingRouter:
    def __init__(self) -> None:
        self.calls = 0

    def table(self, sources: Sequence[LatLon], destinations: Sequence[LatLon]) -> TableResult:
        self.calls += 1
        return WALK.table(sources, destinations)


def test_tiling_calls_once_per_tile() -> None:
    postcodes = [
        _postcode("A1 1AA", 53.0, 400000),
        _postcode("A1 1AB", 53.0, 400500),
        _postcode("A1 1AD", 53.0, 405000),
    ]
    pharmacies = [_pharmacy("FA001", 53.01)]
    candidates = [[Candidate(0, 1000)] for _ in postcodes]
    walk, drive = CountingRouter(), CountingRouter()
    route_candidates(postcodes, pharmacies, candidates, walk, drive, tile_m=2000)
    assert (walk.calls, drive.calls) == (2, 2)


def test_large_tile_split_by_max_sources() -> None:
    postcodes = [_postcode(f"A1 {i}AA", 53.0, 400000 + i) for i in range(5)]
    candidates = [[Candidate(0, 1000)] for _ in postcodes]
    walk, drive = CountingRouter(), CountingRouter()
    route_candidates(postcodes, [_pharmacy("FA001", 53.01)], candidates, walk, drive, max_sources=2)
    assert walk.calls == 3


def test_order_preserved() -> None:
    postcodes = [_postcode("A1 1AD", 53.0, 405000), _postcode("A1 1AA", 53.0, 400000)]
    pharmacies = [_pharmacy("FA001", 53.01), _pharmacy("FA002", 53.02)]
    candidates = [[Candidate(1, 500), Candidate(0, 900)], [Candidate(0, 100)]]
    rows = route_candidates(postcodes, pharmacies, candidates, WALK, DRIVE)
    assert [(r.pc_idx, r.ph_idx) for r in rows] == [(0, 1), (0, 0), (1, 0)]

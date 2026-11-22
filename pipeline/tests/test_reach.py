"""Widening the candidate search until pharmacies can be reached (reach design, section 3)."""

import math
from collections.abc import Sequence

import numpy as np
from scipy.spatial import cKDTree

from within_reach_pipeline.candidates import Candidate, next_candidates, select_candidates
from within_reach_pipeline.models import Pharmacy, Postcode, RawPharmacy
from within_reach_pipeline.reach import ReachResult, route_reachable
from within_reach_pipeline.routing import LatLon, Router, TableResult
from within_reach_pipeline.routing.fake import EARTH_RADIUS_M, FakeRouter

ONE_KM_LAT = 1000 / (EARTH_RADIUS_M * math.pi / 180)
LON = -2.89
HOME = Postcode("ME3 9EJ", 53.0, LON, 400000, 400000, "England", "E06000035")


def _pharmacy(code: str, km: float) -> Pharmacy:
    """A pharmacy km kilometres north of HOME (lat/lon and grid metres agree)."""
    raw = RawPharmacy("England", code, code, (), "ME3 9DT", None)
    return Pharmacy(raw, 53.0 + km * ONE_KM_LAT, LON, 400000, 400000 + round(km * 1000))


def _routers(unreachable: Sequence[Pharmacy]) -> tuple[FakeRouter, FakeRouter]:
    blocked = {(p.lat, p.lon) for p in unreachable}
    return FakeRouter(1.4, unreachable=blocked), FakeRouter(13.4, unreachable=blocked)


class Recorder:
    """Wraps a router and records every (source, target, exclude) it is asked about."""

    def __init__(self, inner: FakeRouter) -> None:
        self.inner = inner
        self.pairs: list[tuple[LatLon, LatLon, str | None]] = []
        self.calls = 0

    def table(
        self,
        sources: Sequence[LatLon],
        destinations: Sequence[LatLon],
        exclude: str | None = None,
    ) -> TableResult:
        self.calls += 1
        self.pairs += [(s, d, exclude) for s in sources for d in destinations]
        return self.inner.table(sources, destinations, exclude)


def _run(
    pharmacies: list[Pharmacy],
    unreachable: Sequence[Pharmacy],
    *,
    allowed: set[int] | None = None,
    max_rounds: int = 4,
    max_candidates: int = 40,
    walk: Router | None = None,
    drive: Router | None = None,
) -> ReachResult:
    w, d = _routers(unreachable)
    candidates = select_candidates([HOME], pharmacies, 5000, max_candidates, 5)
    return route_reachable(
        [HOME],
        pharmacies,
        candidates,
        walk or w,
        drive or d,
        allowed=set(range(len(pharmacies))) if allowed is None else allowed,
        min_reachable=5,
        max_candidates=max_candidates,
        cap_m=25000,
        max_rounds=max_rounds,
        cycle_min_extra_m=50,
    )


def test_unreachable_nearest_are_replaced_by_reachable_further_ones() -> None:
    near = [_pharmacy(f"SS{i}", i) for i in range(1, 6)]  # across the water: no route
    far = [_pharmacy(f"ME{i}", km) for i, km in enumerate((8, 9, 10))]
    result = _run(near + far, near)
    assert [r.ph_idx for r in result.rows] == [5, 6, 7]  # unreachable ones dropped
    assert result.widened_to_cap == {0}  # still short of 5: ran out inside the cap


def test_cap_stops_widening() -> None:
    near = [_pharmacy(f"SS{i}", i) for i in range(1, 6)]
    result = _run([*near, _pharmacy("ME1", 30)], near)
    assert [r.ph_idx for r in result.rows] == [0, 1, 2, 3, 4]  # nothing reachable: original list
    assert all(r.walk_m is None and r.drive_s is None for r in result.rows)
    assert result.widened_to_cap == set()


def test_outside_allowed_box_never_added() -> None:
    near = [_pharmacy(f"SS{i}", i) for i in range(1, 6)]
    outside = _pharmacy("ME1", 8)
    walk = Recorder(_routers(near)[0])
    result = _run([*near, outside], near, allowed={0, 1, 2, 3, 4}, walk=walk)
    assert (outside.lat, outside.lon) not in {d for _, d, _ in walk.pairs}
    assert [r.ph_idx for r in result.rows] == [0, 1, 2, 3, 4]


def test_no_pair_routed_twice_or_duplicated() -> None:
    blocked = [_pharmacy(f"SS{i}", i) for i in range(1, 16)]  # 15 unreachable: 1-15 km
    reachable = [_pharmacy(f"ME{i}", 15 + i) for i in range(1, 6)]  # 16-20 km
    w, d = _routers(blocked)
    walk, drive = Recorder(w), Recorder(d)
    result = _run(blocked + reachable, blocked, walk=walk, drive=drive)
    for recorder in (walk, drive):
        assert len(recorder.pairs) == len(set(recorder.pairs))
    assert [r.ph_idx for r in result.rows] == [15, 16, 17, 18, 19]
    assert result.widened_to_cap == set()


def test_round_limit_leaves_postcode_short() -> None:
    blocked = [_pharmacy(f"SS{i}", i) for i in range(1, 6)]
    round_one = [_pharmacy("ME1", 6), _pharmacy("ME2", 7)]  # 2 reachable
    blocked_more = [_pharmacy(f"SX{i}", 7 + i) for i in range(1, 9)]  # fill round 1 (10 wanted)
    later = [_pharmacy(f"MZ{i}", 20 + i) for i in range(1, 4)]  # reachable, only in round 2
    result = _run(blocked + round_one + blocked_more + later, blocked + blocked_more, max_rounds=1)
    assert [r.ph_idx for r in result.rows] == [5, 6]
    assert result.widened_to_cap == {0}


def test_reachable_postcode_is_untouched() -> None:
    pharmacies = [_pharmacy(f"ME{i}", i) for i in range(1, 7)]
    walk = Recorder(FakeRouter(1.4))
    result = _run(pharmacies, [], walk=walk)
    assert walk.calls == 2  # one pass: normal and without cycle paths
    assert [r.ph_idx for r in result.rows] == [0, 1, 2, 3, 4]
    assert result.widened_to_cap == set()


def test_rows_never_exceed_max_candidates() -> None:
    blocked = [_pharmacy(f"SS{i}", i) for i in range(1, 6)]
    reachable = [_pharmacy(f"ME{i}", 5 + i) for i in range(1, 11)]  # 10 reachable added
    result = _run(blocked + reachable, blocked, max_candidates=6)
    assert [r.ph_idx for r in result.rows] == [5, 6, 7, 8, 9, 10]  # the nearest 6 reachable


def test_next_candidates_skips_tried_and_respects_cap() -> None:
    pharmacies = [_pharmacy(f"P{i}", km) for i, km in enumerate((1, 2, 3, 26))]
    tree = cKDTree(np.array([(p.east, p.north) for p in pharmacies], dtype=float))
    found = next_candidates(HOME, pharmacies, tree, {0}, {0, 1, 2, 3}, count=5, cap_m=25000)
    assert found == [Candidate(1, 2000), Candidate(2, 3000)]
    assert next_candidates(HOME, pharmacies, tree, set(), {2}, count=1, cap_m=25000) == [
        Candidate(2, 3000)
    ]

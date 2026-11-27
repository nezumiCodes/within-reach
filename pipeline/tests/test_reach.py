"""Widening the candidate search until pharmacies can be reached (reach design, section 3)."""

import math
from collections.abc import Sequence

import numpy as np
from scipy.spatial import cKDTree

from within_reach_pipeline.candidates import (
    Candidate,
    next_candidates,
    select_candidates,
    select_service_candidates,
)
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


def _run_services(
    pharmacies: list[Pharmacy],
    unreachable: Sequence[Pharmacy],
    listed: frozenset[int],
    *,
    allowed: set[int] | None = None,
    service_allowed: set[int] | None = None,
    max_candidates: int = 40,
    walk: Router | None = None,
    drive: Router | None = None,
) -> ReachResult:
    """As _run, with the build's service step: extras chosen, then routed with services on."""
    w, d = _routers(unreachable)
    candidates = select_candidates([HOME], pharmacies, 5000, max_candidates, 5)
    extras = select_service_candidates([HOME], pharmacies, candidates, listed, 5, 25000)
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
        max_rounds=4,
        cycle_min_extra_m=50,
        service_extras=extras,
        services={"nsp": listed},
        service_min=5,
        service_allowed=service_allowed,
    )


def test_service_rows_survive_the_40_cap() -> None:
    nearby = [_pharmacy(f"ME{i:02d}", 0.1 * (i + 1)) for i in range(45)]  # 0.1-4.5 km
    far = [_pharmacy(f"NS{i}", km) for i, km in enumerate((8, 9, 10, 11, 12))]
    listed = frozenset(range(45, 50))
    rows = _run_services(nearby + far, [], listed).rows
    assert len(rows) == 45 and {r.ph_idx for r in rows} >= listed
    assert [r.ph_idx for r in rows] == [*range(40), *range(45, 50)]  # nearest 40 + service rows


def test_listed_pharmacy_among_nearest_is_stored_once() -> None:
    pharmacies = [_pharmacy(f"ME{i}", i + 1) for i in range(10)]  # 1-10 km
    listed = frozenset({0, 6, 7, 8, 9})  # 0 is among the nearest 5: 4 more needed
    rows = _run_services(pharmacies, [], listed).rows
    assert len({r.ph_idx for r in rows}) == len(rows)
    assert [r.ph_idx for r in rows] == [0, 1, 2, 3, 4, 6, 7, 8, 9]


def test_unreachable_service_rows_widen_then_short() -> None:
    general = [_pharmacy(f"ME{i}", i + 1) for i in range(5)]  # 1-5 km, not listed
    services = [_pharmacy(f"NS{i}", km) for i, km in enumerate((8, 9, 10, 11, 12, 13))]
    listed_a, listed_last = services[0], services[5]
    pharmacies = general + services
    listed = frozenset(range(5, 11))
    w, _ = _routers([listed_a, listed_last])
    walk = Recorder(w)
    result = _run_services(pharmacies, [listed_a, listed_last], listed, walk=walk)
    routed = {dest for _, dest, _ in walk.pairs}
    assert (listed_last.lat, listed_last.lon) in routed  # added by service widening
    assert [r.ph_idx for r in result.rows] == [0, 1, 2, 3, 4, 6, 7, 8, 9]
    assert result.service_short == {"nsp": {0}}
    assert result.widened_to_cap == set()
    assert len(walk.pairs) == len(set(walk.pairs))  # nothing routed twice

    # The same, but the 13 km pharmacy can be reached: the postcode is no longer short.
    result = _run_services(pharmacies, [listed_a], listed)
    assert [r.ph_idx for r in result.rows] == [0, 1, 2, 3, 4, 6, 7, 8, 9, 10]
    assert result.service_short == {"nsp": set()}


def test_service_widening_stays_inside_allowed() -> None:
    general = [_pharmacy(f"ME{i}", i + 1) for i in range(5)]
    services = [_pharmacy(f"NS{i}", km) for i, km in enumerate((8, 9, 10, 11, 12, 13))]
    pharmacies = general + services
    listed = frozenset(range(5, 11))
    walk = Recorder(_routers([services[0]])[0])
    outside = services[5]
    result = _run_services(pharmacies, [services[0]], listed, allowed=set(range(10)), walk=walk)
    assert (outside.lat, outside.lon) not in {d for _, d, _ in walk.pairs}
    assert result.service_short == {"nsp": {0}}


def test_service_widening_searches_service_allowed() -> None:
    """The service extras widen the extract beyond the general box: service widening may
    search all of it, general widening only its own box."""
    general = [_pharmacy(f"ME{i}", i + 1) for i in range(5)]
    services = [_pharmacy(f"NS{i}", km) for i, km in enumerate((8, 9, 10, 11, 12, 13))]
    pharmacies = general + services
    listed = frozenset(range(5, 11))
    result = _run_services(
        pharmacies,
        [services[0]],
        listed,
        allowed=set(range(10)),
        service_allowed=set(range(11)),
    )
    assert 10 in {r.ph_idx for r in result.rows}
    assert result.service_short == {"nsp": set()}


def test_reach_widening_ignores_reachable_service_extras() -> None:
    """Allhallows: the nearest 5 are across the water, and the only pharmacies listing the
    service are further off but reachable. Reach widening must still find the nearer ones."""
    blocked = [_pharmacy(f"SS{i}", i) for i in range(1, 6)]  # 1-5 km, unreachable
    nearer = [_pharmacy(f"ME{i}", 5 + i) for i in range(1, 6)]  # 6-10 km, reachable
    listed_far = [_pharmacy(f"NS{i}", 11 + i) for i in range(1, 6)]  # 12-16 km, reachable
    pharmacies = blocked + nearer + listed_far
    listed = frozenset(range(10, 15))
    off = _run(pharmacies, blocked)
    w, d = _routers(blocked)
    walk, drive = Recorder(w), Recorder(d)
    on = _run_services(pharmacies, blocked, listed, walk=walk, drive=drive)
    general = {r.ph_idx for r in off.rows}
    service = {r.ph_idx for r in on.rows if r.ph_idx in listed}
    assert {5, 6, 7, 8, 9} <= general
    assert on.rows == sorted(
        {r.ph_idx: r for r in [*off.rows, *(r for r in on.rows if r.ph_idx in service)]}.values(),
        key=lambda r: (r.straight_m, r.ph_idx),
    )
    assert on.widened_to_cap == off.widened_to_cap
    assert on.service_short == {"nsp": set()}
    for recorder in (walk, drive):  # extras reached by widening are reused, not re-routed
        assert len(recorder.pairs) == len(set(recorder.pairs))


def test_reach_widening_with_extras_matches_services_off_when_short() -> None:
    """Some extras reachable, general search still short: general rows match services off."""
    blocked = [_pharmacy(f"SS{i}", i) for i in range(1, 6)]
    nearer = [_pharmacy(f"ME{i}", 8 + i) for i in range(1, 3)]  # 9, 10 km
    listed_far = [_pharmacy(f"NS{i}", 10.5 + i) for i in range(1, 4)]  # 11.5-13.5 km
    beyond = [_pharmacy(f"MZ{i}", 14 + i) for i in range(1, 6)]  # 15-19 km
    pharmacies = blocked + nearer + listed_far + beyond
    listed = frozenset(range(7, 10))
    off = _run(pharmacies, blocked)
    on = _run_services(pharmacies, blocked, listed)
    assert [r.ph_idx for r in on.rows] == [r.ph_idx for r in off.rows]
    assert on.rows == off.rows
    assert on.widened_to_cap == off.widened_to_cap


def test_no_services_matches_previous_rows() -> None:
    scenarios = [
        (
            [_pharmacy(f"SS{i}", i) for i in range(1, 6)],
            [_pharmacy(f"ME{i}", 8 + i) for i in range(3)],
        ),
        (
            [_pharmacy(f"SS{i}", i) for i in range(1, 16)],
            [_pharmacy(f"ME{i}", 15 + i) for i in range(1, 6)],
        ),
    ]
    for blocked, reachable in scenarios:
        pharmacies = blocked + reachable
        before = _run(pharmacies, blocked)
        w, d = _routers(blocked)
        candidates = select_candidates([HOME], pharmacies, 5000, 40, 5)
        after = route_reachable(
            [HOME],
            pharmacies,
            candidates,
            w,
            d,
            allowed=set(range(len(pharmacies))),
            min_reachable=5,
            max_candidates=40,
            cap_m=25000,
            max_rounds=4,
            cycle_min_extra_m=50,
            service_extras=None,
            services={},
            service_min=5,
        )
        assert after.rows == before.rows
        assert after.widened_to_cap == before.widened_to_cap
        assert after.service_short == {} == before.service_short

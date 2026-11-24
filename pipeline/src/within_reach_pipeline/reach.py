"""Make sure each postcode gets pharmacies it can reach (walking rules and reach design, section 3).

Candidates are first chosen by straight-line distance (candidates.py). Across an estuary the
nearest pharmacies can be unreachable: Allhallows' nearest five are on Canvey Island, across the
Thames. After the first routing pass, any postcode with fewer than min_reachable pharmacies it
can reach on foot or by car gets the next nearest added and routed, round by round, up to cap_m
and max_rounds. Unreachable rows are then dropped, unless nothing at all can be reached, in
which case the postcode keeps its first-pass list (a real island with no route).

Services (needle exchange design, section 3): service_extras are pharmacies listing a service
that the build added beyond the general candidates. They are routed in the first pass, but reach
widening ignores them: it counts and searches over the general rows exactly as it would without
services, reusing an extra's row (not routing it again) when the search reaches it. Then, per
service, postcodes with fewer than service_min reachable rows listing it get the next nearest
listing it, round by round, inside allowed and cap_m. Each postcode keeps its nearest
max_candidates general rows plus its nearest service_min reachable rows per service.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from within_reach_pipeline.candidates import Candidate, next_candidates
from within_reach_pipeline.models import Pharmacy, Postcode
from within_reach_pipeline.routing import Router, TravelRow, route_candidates


@dataclass(frozen=True)
class ReachResult:
    rows: list[TravelRow]
    # Postcodes that ended with some reachable pharmacies but fewer than min_reachable, because
    # the search ran out (cap, area box) or hit the round limit. The release checks allow
    # exactly these to be short.
    widened_to_cap: set[int]
    # Per service key: postcodes ending with fewer than service_min reachable rows listing it.
    service_short: dict[str, set[int]] = field(default_factory=dict)


def _reachable(row: TravelRow) -> bool:
    return row.walk_m is not None or row.drive_s is not None


def _by_distance(row: TravelRow) -> tuple[int, int]:
    return (row.straight_m, row.ph_idx)


def route_reachable(
    postcodes: Sequence[Postcode],
    pharmacies: Sequence[Pharmacy],
    candidates: Sequence[list[Candidate]],
    walk: Router,
    drive: Router,
    *,
    allowed: set[int],
    min_reachable: int,
    max_candidates: int,
    cap_m: int,
    max_rounds: int,
    cycle_min_extra_m: int,
    service_extras: Sequence[list[Candidate]] | None = None,
    services: Mapping[str, frozenset[int]] | None = None,
    service_min: int = 0,
) -> ReachResult:
    services = services or {}
    count = len(postcodes)

    # routed[i]: every row routed for postcode i, by pharmacy. general[i]: the pharmacies reach
    # widening knows about (first-pass candidates and what it added), in the order found.
    routed: list[dict[int, TravelRow]] = [{} for _ in range(count)]
    first_candidates = [list(c) for c in candidates]
    if service_extras is not None:
        for i, extras in enumerate(service_extras):
            have = {c.ph_idx for c in first_candidates[i]}
            first_candidates[i] += [c for c in extras if c.ph_idx not in have]
    for row in route_candidates(
        postcodes, pharmacies, first_candidates, walk, drive, cycle_min_extra_m
    ):
        routed[row.pc_idx][row.ph_idx] = row
    general: list[list[int]] = [[c.ph_idx for c in candidates[i]] for i in range(count)]
    first_pass = [[routed[i][ph] for ph in general[i] if ph in routed[i]] for i in range(count)]
    tried = [set(general[i]) for i in range(count)]
    needed = min(min_reachable, len(pharmacies))

    def short(i: int) -> int:
        return needed - sum(1 for ph in general[i] if _reachable(routed[i][ph]))

    tree: cKDTree | None = None

    def kdtree() -> cKDTree:
        nonlocal tree
        if tree is None:
            tree = cKDTree(np.array([(p.east, p.north) for p in pharmacies], dtype=float))
        return tree

    def route_new(new: list[list[Candidate]]) -> None:
        for row in route_candidates(postcodes, pharmacies, new, walk, drive, cycle_min_extra_m):
            routed[row.pc_idx][row.ph_idx] = row

    # Reach widening: over the general rows only, exactly as without services.
    searching = {i for i in range(count) if short(i) > 0}
    for _ in range(max_rounds):
        if not searching:
            break
        extra: list[list[Candidate]] = [[] for _ in postcodes]
        new: list[list[Candidate]] = [[] for _ in postcodes]
        for i in sorted(searching):
            extra[i] = next_candidates(
                postcodes[i],
                pharmacies,
                kdtree(),
                tried[i],
                allowed,
                short(i) + min_reachable,
                cap_m,
            )
            tried[i] |= {c.ph_idx for c in extra[i]}
            new[i] = [c for c in extra[i] if c.ph_idx not in routed[i]]  # extras: reuse rows
        searching -= {i for i in searching if not extra[i]}  # nothing more to try
        route_new(new)
        for i in range(count):
            general[i] += [c.ph_idx for c in extra[i]]
        searching = {i for i in searching if short(i) > 0}

    # Service widening: per service, the next nearest listing it, inside allowed and the cap.
    def listed_reachable(i: int, members: frozenset[int]) -> int:
        return sum(1 for ph, r in routed[i].items() if ph in members and _reachable(r))

    for members in services.values():
        inside = allowed & members
        searching = {i for i in range(count) if listed_reachable(i, members) < service_min}
        for _ in range(max_rounds):
            if not searching:
                break
            new = [[] for _ in postcodes]
            for i in sorted(searching):
                new[i] = next_candidates(
                    postcodes[i],
                    pharmacies,
                    kdtree(),
                    set(routed[i]),
                    inside,
                    service_min - listed_reachable(i, members),
                    cap_m,
                )
            searching -= {i for i in searching if not new[i]}
            route_new(new)
            searching = {i for i in searching if listed_reachable(i, members) < service_min}

    final: list[TravelRow] = []
    widened_to_cap: set[int] = set()
    service_short: dict[str, set[int]] = {key: set() for key in services}
    for i in range(count):
        reachable = [routed[i][ph] for ph in general[i] if _reachable(routed[i][ph])]
        keep = reachable if reachable else list(first_pass[i])
        if reachable and short(i) > 0:
            widened_to_cap.add(i)
        keep.sort(key=_by_distance)
        chosen = {r.ph_idx: r for r in keep[:max_candidates]}
        for key, members in services.items():
            listing = sorted(
                (r for ph, r in routed[i].items() if ph in members and _reachable(r)),
                key=_by_distance,
            )
            if len(listing) < service_min:
                service_short[key].add(i)
            chosen.update((r.ph_idx, r) for r in listing[:service_min])
        final.extend(sorted(chosen.values(), key=_by_distance))
    return ReachResult(final, widened_to_cap, service_short)

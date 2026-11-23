"""Make sure each postcode gets pharmacies it can reach (walking rules and reach design, section 3).

Candidates are first chosen by straight-line distance (candidates.py). Across an estuary the
nearest pharmacies can be unreachable: Allhallows' nearest five are on Canvey Island, across the
Thames. After the first routing pass, any postcode with fewer than min_reachable pharmacies it
can reach on foot or by car gets the next nearest added and routed, round by round, up to cap_m
and max_rounds. Unreachable rows are then dropped, unless nothing at all can be reached, in
which case the postcode keeps its first-pass list (a real island with no route).
"""

from collections.abc import Sequence
from dataclasses import dataclass

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


def _reachable(row: TravelRow) -> bool:
    return row.walk_m is not None or row.drive_s is not None


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
) -> ReachResult:
    first = route_candidates(postcodes, pharmacies, candidates, walk, drive, cycle_min_extra_m)
    rows: dict[int, list[TravelRow]] = {i: [] for i in range(len(postcodes))}
    for row in first:
        rows[row.pc_idx].append(row)
    first_pass = {i: list(r) for i, r in rows.items()}
    tried = {i: {c.ph_idx for c in candidates[i]} for i in range(len(postcodes))}
    needed = min(min_reachable, len(pharmacies))

    def short(i: int) -> int:
        return needed - sum(1 for r in rows[i] if _reachable(r))

    tree: cKDTree | None = None
    searching = {i for i in rows if short(i) > 0}
    for _ in range(max_rounds):
        if not searching:
            break
        if tree is None:
            tree = cKDTree(np.array([(p.east, p.north) for p in pharmacies], dtype=float))
        extra: list[list[Candidate]] = [[] for _ in postcodes]
        for i in sorted(searching):
            extra[i] = next_candidates(
                postcodes[i], pharmacies, tree, tried[i], allowed, short(i) + min_reachable, cap_m
            )
            tried[i] |= {c.ph_idx for c in extra[i]}
        searching -= {i for i in searching if not extra[i]}  # nothing more to try
        for row in route_candidates(postcodes, pharmacies, extra, walk, drive, cycle_min_extra_m):
            rows[row.pc_idx].append(row)
        searching = {i for i in searching if short(i) > 0}

    final: list[TravelRow] = []
    widened_to_cap: set[int] = set()
    for i in range(len(postcodes)):
        reachable = [r for r in rows[i] if _reachable(r)]
        keep = reachable if reachable else first_pass[i]
        if reachable and short(i) > 0:
            widened_to_cap.add(i)
        keep.sort(key=lambda r: (r.straight_m, r.ph_idx))
        final.extend(keep[:max_candidates])
    return ReachResult(final, widened_to_cap)

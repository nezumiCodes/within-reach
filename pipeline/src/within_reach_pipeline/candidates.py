"""Choose which pharmacies to route to from each postcode (spec FR-02).

Every pharmacy within radius_m (straight line), capped at max_candidates; if that gives fewer
than min_candidates, the nearest min_candidates at any distance instead, so remote postcodes
still get results. Candidates are chosen from all GB pharmacies, which also covers pharmacies
across area and national borders. Ordering follows NFR-11: straight-line metres, then nation,
then code (the directory is already sorted by nation and code, so its index breaks ties).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from within_reach_pipeline.models import Pharmacy, Postcode


@dataclass(frozen=True)
class Candidate:
    ph_idx: int
    straight_m: int


def _query(
    tree: cKDTree, points: np.ndarray, k: int, bound: float
) -> tuple[np.ndarray, np.ndarray]:
    distances, indexes = tree.query(points, k=k, distance_upper_bound=bound)
    if k == 1:  # scipy drops the k axis when k == 1
        distances, indexes = distances[:, None], indexes[:, None]
    return distances, indexes


def select_candidates(
    postcodes: Sequence[Postcode],
    pharmacies: Sequence[Pharmacy],
    radius_m: int,
    max_candidates: int,
    min_candidates: int,
) -> list[list[Candidate]]:
    if not pharmacies:
        return [[] for _ in postcodes]
    if not postcodes:
        return []
    tree = cKDTree(np.array([(p.east, p.north) for p in pharmacies], dtype=float))
    points = np.array([(p.east, p.north) for p in postcodes], dtype=float)
    total = len(pharmacies)

    k_max = min(max_candidates, total)
    near_d, near_i = _query(tree, points, k_max, float(radius_m))
    needed_min = min(min_candidates, total)
    fallback_d, fallback_i = _query(tree, points, needed_min, np.inf)

    results: list[list[Candidate]] = []
    for row in range(len(postcodes)):
        found = [
            (int(i), float(d)) for d, i in zip(near_d[row], near_i[row], strict=True) if i < total
        ]
        if len(found) < needed_min:
            found = [
                (int(i), float(d)) for d, i in zip(fallback_d[row], fallback_i[row], strict=True)
            ]
        candidates = [Candidate(idx, round(distance)) for idx, distance in found]
        candidates.sort(key=lambda c: (c.straight_m, c.ph_idx))
        results.append(candidates)
    return results


def next_candidates(
    postcode: Postcode,
    pharmacies: Sequence[Pharmacy],
    tree: cKDTree,
    tried: set[int],
    allowed: set[int],
    count: int,
    cap_m: int,
) -> list[Candidate]:
    """The nearest count pharmacies not yet tried, inside allowed and within cap_m (straight
    line), used to widen the search when the first candidates can't be reached."""
    found = [
        Candidate(int(i), round(math.dist((postcode.east, postcode.north), (p.east, p.north))))
        for i in tree.query_ball_point((postcode.east, postcode.north), float(cap_m))
        if int(i) in allowed and int(i) not in tried
        for p in (pharmacies[int(i)],)
    ]
    found.sort(key=lambda c: (c.straight_m, c.ph_idx))
    return found[:count]

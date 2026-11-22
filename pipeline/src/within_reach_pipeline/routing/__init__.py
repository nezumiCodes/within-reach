"""Routing interface and batching of postcode-to-pharmacy pairs (spec FR-02)."""

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from within_reach_pipeline.candidates import Candidate
from within_reach_pipeline.models import Pharmacy, Postcode

LatLon = tuple[float, float]
# Name of the UK walking rules (pipeline/osrm/foot-gb.lua), recorded in each release manifest.
WALK_PROFILE = "foot-gb"


@dataclass(frozen=True)
class TableResult:
    distances_m: list[list[int | None]]
    durations_s: list[list[int | None]]


class Router(Protocol):
    def table(self, sources: Sequence[LatLon], destinations: Sequence[LatLon]) -> TableResult: ...


@dataclass(frozen=True)
class TravelRow:
    pc_idx: int
    ph_idx: int
    straight_m: int
    walk_m: int | None
    walk_s: int | None
    drive_s: int | None


def round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def _groups(postcodes: Sequence[Postcode], tile_m: int, max_sources: int) -> list[list[int]]:
    tiles: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, postcode in enumerate(postcodes):
        tiles[(postcode.east // tile_m, postcode.north // tile_m)].append(idx)
    groups: list[list[int]] = []
    for key in sorted(tiles):
        members = tiles[key]
        groups.extend(members[i : i + max_sources] for i in range(0, len(members), max_sources))
    return groups


def route_candidates(
    postcodes: Sequence[Postcode],
    pharmacies: Sequence[Pharmacy],
    candidates: Sequence[list[Candidate]],
    walk: Router,
    drive: Router,
    tile_m: int = 2000,
    max_sources: int = 250,
) -> list[TravelRow]:
    rows_by_postcode: dict[int, list[TravelRow]] = {}
    for group in _groups(postcodes, tile_m, max_sources):
        destinations = sorted({c.ph_idx for idx in group for c in candidates[idx]})
        if not destinations:
            continue
        column = {ph_idx: col for col, ph_idx in enumerate(destinations)}
        sources = [(postcodes[idx].lat, postcodes[idx].lon) for idx in group]
        targets = [(pharmacies[ph].lat, pharmacies[ph].lon) for ph in destinations]
        walked = walk.table(sources, targets)
        driven = drive.table(sources, targets)
        for row, pc_idx in enumerate(group):
            rows_by_postcode[pc_idx] = [
                TravelRow(
                    pc_idx=pc_idx,
                    ph_idx=c.ph_idx,
                    straight_m=c.straight_m,
                    walk_m=walked.distances_m[row][column[c.ph_idx]],
                    walk_s=walked.durations_s[row][column[c.ph_idx]],
                    drive_s=driven.durations_s[row][column[c.ph_idx]],
                )
                for c in candidates[pc_idx]
            ]
    return [row for pc_idx in sorted(rows_by_postcode) for row in rows_by_postcode[pc_idx]]

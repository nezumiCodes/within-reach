"""A deterministic stand-in router for tests: straight line times a detour factor."""

import math
from collections.abc import Sequence

from within_reach_pipeline.routing import LatLon, TableResult, round_half_up

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(a: LatLon, b: LatLon) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


class FakeRouter:
    def __init__(
        self, speed_m_s: float, detour: float = 1.3, unreachable: set[LatLon] | None = None
    ) -> None:
        self.speed_m_s = speed_m_s
        self.detour = detour
        self.unreachable = unreachable or set()

    def table(self, sources: Sequence[LatLon], destinations: Sequence[LatLon]) -> TableResult:
        distances: list[list[int | None]] = []
        durations: list[list[int | None]] = []
        for source in sources:
            d_row: list[int | None] = []
            t_row: list[int | None] = []
            for target in destinations:
                if target in self.unreachable:
                    d_row.append(None)
                    t_row.append(None)
                    continue
                metres = haversine_m(source, target) * self.detour
                d_row.append(round_half_up(metres))
                t_row.append(round_half_up(metres / self.speed_m_s))
            distances.append(d_row)
            durations.append(t_row)
        return TableResult(distances, durations)

"""The merged GB pharmacy directory: three national lists, one format, keyed by (nation, code)."""

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from within_reach_pipeline.models import Pharmacy, Postcode, RawPharmacy
from within_reach_pipeline.postcodes import normalise_postcode

log = logging.getLogger(__name__)


@dataclass
class DirectoryResult:
    pharmacies: list[Pharmacy]
    geocode_failures: list[RawPharmacy]
    hours_warnings: int
    excluded_distance_selling: int


def build_directory(
    raw: Iterable[RawPharmacy],
    postcode_index: Mapping[str, Postcode],
    hours_warnings: int,
    distance_selling: frozenset[str],
) -> DirectoryResult:
    seen: set[tuple[str, str]] = set()
    pharmacies: list[Pharmacy] = []
    failures: list[RawPharmacy] = []
    excluded = 0
    for item in raw:
        if item.nation == "England" and item.code in distance_selling:
            excluded += 1
            continue
        key = (item.nation, item.code)
        if key in seen:
            log.warning("duplicate pharmacy %s:%s; keeping the first", *key)
            continue
        seen.add(key)
        normalised = normalise_postcode(item.postcode)
        location = postcode_index.get(normalised) if normalised else None
        if location is None:
            failures.append(item)
            continue
        pharmacies.append(
            Pharmacy(
                raw=item,
                lat=location.lat,
                lon=location.lon,
                east=location.east,
                north=location.north,
            )
        )
    pharmacies.sort(key=lambda p: p.key)
    return DirectoryResult(pharmacies, failures, hours_warnings, excluded)

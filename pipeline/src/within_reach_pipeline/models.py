"""Shared data types. Pharmacies are always identified by (nation, code)."""

from dataclasses import dataclass
from typing import Literal

Nation = Literal["England", "Scotland", "Wales"]
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS: tuple[Weekday, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Per day: () means closed, a tuple of (open, close) pairs means open, None means unknown.
DayHours = tuple[tuple[str, str], ...] | None
OpeningHours = dict[Weekday, DayHours]


@dataclass(frozen=True)
class Postcode:
    postcode: str
    lat: float
    lon: float
    east: int
    north: int
    nation: Nation
    area_code: str


@dataclass(frozen=True)
class RawPharmacy:
    nation: Nation
    code: str
    name: str
    address: tuple[str, ...]
    postcode: str
    hours: OpeningHours | None  # None: the source list has no opening hours at all


@dataclass(frozen=True)
class Pharmacy:
    raw: RawPharmacy
    lat: float
    lon: float
    east: int
    north: int

    @property
    def key(self) -> tuple[str, str]:
        return (self.raw.nation, self.raw.code)

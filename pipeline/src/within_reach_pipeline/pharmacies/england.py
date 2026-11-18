"""England: NHSBSA Consolidated Pharmaceutical List and Contractor Details (both OGL)."""

import csv
from collections.abc import Sequence
from pathlib import Path

from within_reach_pipeline.models import WEEKDAYS, OpeningHours, RawPharmacy
from within_reach_pipeline.pharmacies.hours import parse_day_hours
from within_reach_pipeline.postcodes import normalise_postcode

_DAY_COLUMNS = {
    "mon": "PHARMACY_OPENING_HOURS_MONDAY",
    "tue": "PHARMACY_OPENING_HOURS_TUESDAY",
    "wed": "PHARMACY_OPENING_HOURS_WEDNESDAY",
    "thu": "PHARMACY_OPENING_HOURS_THURSDAY",
    "fri": "PHARMACY_OPENING_HOURS_FRIDAY",
    "sat": "PHARMACY_OPENING_HOURS_SATURDAY",
    "sun": "PHARMACY_OPENING_HOURS_SUNDAY",
}
# Dispensing appliance contractors supply appliances only; they are not pharmacies.
_EXCLUDED_CONTRACTS = {"DAC"}
_REQUIRED = [
    "PHARMACY_ODS_CODE_F_CODE",
    "PHARMACY_TRADING_NAME",
    "POST_CODE",
    "CONTRACT_TYPE",
    *_DAY_COLUMNS.values(),
]


def _require(fieldnames: Sequence[str] | None, required: list[str], source: str) -> None:
    missing = [c for c in required if c not in (fieldnames or [])]
    if missing:
        raise ValueError(f"{source} is missing columns: {', '.join(missing)}")


def _cell(row: dict[str, str | None], key: str) -> str:
    return (row.get(key) or "").strip()


def read_nhsbsa(csv_path: Path) -> tuple[list[RawPharmacy], int]:
    pharmacies: list[RawPharmacy] = []
    warnings = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require(reader.fieldnames, _REQUIRED, "NHSBSA pharmacy list")
        for row in reader:
            if _cell(row, "CONTRACT_TYPE").upper() in _EXCLUDED_CONTRACTS:
                continue
            hours: OpeningHours = {}
            for day in WEEKDAYS:
                raw_value = _cell(row, _DAY_COLUMNS[day])
                parsed = parse_day_hours(raw_value)
                if parsed is None and raw_value:
                    warnings += 1
                hours[day] = parsed
            address = tuple(part for i in range(1, 5) if (part := _cell(row, f"ADDRESS_FIELD_{i}")))
            postcode = _cell(row, "POST_CODE")
            pharmacies.append(
                RawPharmacy(
                    nation="England",
                    code=_cell(row, "PHARMACY_ODS_CODE_F_CODE"),
                    name=_cell(row, "PHARMACY_TRADING_NAME"),
                    address=address,
                    postcode=normalise_postcode(postcode) or postcode,
                    hours=hours,
                )
            )
    return pharmacies, warnings


def read_distance_selling_codes(csv_path: Path) -> frozenset[str]:
    """Codes of online-only (distance-selling) pharmacies, which can't supervise doses."""
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require(
            reader.fieldnames,
            ["CONTRACTOR_CODE", "DISTANCE_SELLING_CONTRACTOR"],
            "NHSBSA Contractor Details",
        )
        return frozenset(
            _cell(row, "CONTRACTOR_CODE")
            for row in reader
            if _cell(row, "DISTANCE_SELLING_CONTRACTOR").upper() == "Y"
        )

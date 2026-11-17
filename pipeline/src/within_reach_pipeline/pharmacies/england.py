"""England: NHSBSA Consolidated Pharmaceutical List and Contractor Details (both OGL)."""

import csv
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


def read_nhsbsa(csv_path: Path) -> tuple[list[RawPharmacy], int]:
    pharmacies: list[RawPharmacy] = []
    warnings = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["CONTRACT_TYPE"].strip().upper() in _EXCLUDED_CONTRACTS:
                continue
            hours: OpeningHours = {}
            for day in WEEKDAYS:
                raw_value = row.get(_DAY_COLUMNS[day], "")
                parsed = parse_day_hours(raw_value)
                if parsed is None and raw_value.strip():
                    warnings += 1
                hours[day] = parsed
            address = tuple(
                part for i in range(1, 5) if (part := row.get(f"ADDRESS_FIELD_{i}", "").strip())
            )
            pharmacies.append(
                RawPharmacy(
                    nation="England",
                    code=row["PHARMACY_ODS_CODE_F_CODE"].strip(),
                    name=row["PHARMACY_TRADING_NAME"].strip(),
                    address=address,
                    postcode=normalise_postcode(row["POST_CODE"]) or row["POST_CODE"].strip(),
                    hours=hours,
                )
            )
    return pharmacies, warnings


def read_distance_selling_codes(csv_path: Path) -> frozenset[str]:
    """Codes of online-only (distance-selling) pharmacies, which can't supervise doses."""
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        return frozenset(
            row["CONTRACTOR_CODE"].strip()
            for row in csv.DictReader(handle)
            if row.get("DISTANCE_SELLING_CONTRACTOR", "").strip().upper() == "Y"
        )

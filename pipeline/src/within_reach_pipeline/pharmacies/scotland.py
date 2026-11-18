"""Scotland: Public Health Scotland, Dispenser Location Contact Details (OGL). No hours."""

import csv
from pathlib import Path

from within_reach_pipeline.models import RawPharmacy
from within_reach_pipeline.postcodes import normalise_postcode


def _clean(value: str) -> str:
    text = value.strip()
    return "" if text.upper() == "NA" else text


def read_phs(csv_path: Path) -> list[RawPharmacy]:
    pharmacies: list[RawPharmacy] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw_postcode = _clean(row["DispLocationPostcode"])
            pharmacies.append(
                RawPharmacy(
                    nation="Scotland",
                    code=row["DispCode"].strip(),
                    name=_clean(row["DispLocationName"]),
                    address=tuple(
                        part
                        for i in range(1, 5)
                        if (part := _clean(row.get(f"DispLocationAddress{i}", "")))
                    ),
                    postcode=normalise_postcode(raw_postcode) or raw_postcode,
                    hours=None,
                )
            )
    return pharmacies

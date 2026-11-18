"""Wales: active pharmacies from the NHS ODS ORD API (OGL), resolving decision D15. No hours."""

import json
import re
import time
from pathlib import Path
from typing import Any

from within_reach_pipeline.http import Fetcher
from within_reach_pipeline.models import RawPharmacy
from within_reach_pipeline.postcodes import normalise_postcode

ORD_ORGANISATIONS = "https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations"
PHARMACY_ROLE = "RO182"
PAGE_SIZE = 1000


def postcode_area(postcode: str) -> str:
    """The leading letters of a postcode: LL11 4UF -> LL."""
    return re.match(r"[A-Z]*", postcode.strip().upper()).group(0)  # type: ignore[union-attr]


def fetch_ods_wales(
    fetcher: Fetcher,
    welsh_areas: set[str],
    english_codes: frozenset[str],
    pause_s: float = 0.1,
) -> list[RawPharmacy]:
    """Active pharmacies whose ODS record places them in Wales.

    Only organisations in postcode areas that contain Welsh postcodes are looked up (CH, SY and
    others straddle the border), and codes already in the NHSBSA list are skipped, so no
    pharmacy appears twice. The ODS postcode is kept as given even if ONSPD doesn't know it, so
    the directory step can count geocode failures for Wales.
    """
    pharmacies: list[RawPharmacy] = []
    offset = 0
    while True:
        params = {"PrimaryRoleId": PHARMACY_ROLE, "Status": "Active", "Limit": str(PAGE_SIZE)}
        if offset:  # Offset = records to skip; the API rejects Offset=0, so omit it at first
            params["Offset"] = str(offset)
        page: dict[str, Any] = fetcher.get_json(ORD_ORGANISATIONS, params=params)
        organisations = page.get("Organisations", [])
        for summary in organisations:
            code = str(summary.get("OrgId", "")).strip()
            raw_postcode = str(summary.get("PostCode", ""))
            if not code or code in english_codes or postcode_area(raw_postcode) not in welsh_areas:
                continue
            detail = fetcher.get_json(summary["OrgLink"])["Organisation"]
            if pause_s:
                time.sleep(pause_s)
            location = detail.get("GeoLoc", {}).get("Location", {})
            if str(location.get("Country", "")).strip().upper() != "WALES":
                continue
            address = tuple(
                str(location[key]).strip()
                for key in ("AddrLn1", "AddrLn2", "AddrLn3", "Town")
                if str(location.get(key, "")).strip()
            )
            postcode = str(location.get("PostCode") or raw_postcode)
            pharmacies.append(
                RawPharmacy(
                    nation="Wales",
                    code=code,
                    name=str(detail.get("Name", summary.get("Name", ""))).strip(),
                    address=address,
                    postcode=normalise_postcode(postcode) or postcode.strip(),
                    hours=None,
                )
            )
        if len(organisations) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return pharmacies


def save_ods_wales(pharmacies: list[RawPharmacy], path: Path) -> None:
    rows = [
        {"code": p.code, "name": p.name, "address": list(p.address), "postcode": p.postcode}
        for p in pharmacies
    ]
    path.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def load_ods_wales(path: Path) -> list[RawPharmacy]:
    return [
        RawPharmacy("Wales", r["code"], r["name"], tuple(r["address"]), r["postcode"], None)
        for r in json.loads(path.read_text(encoding="utf-8"))
    ]

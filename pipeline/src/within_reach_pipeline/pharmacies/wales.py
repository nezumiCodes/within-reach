"""Wales: active pharmacies from the NHS ODS ORD API (OGL), resolving decision D15. No hours."""

import json
import time
from pathlib import Path
from typing import Any

from within_reach_pipeline.http import Fetcher
from within_reach_pipeline.models import RawPharmacy
from within_reach_pipeline.postcodes import normalise_postcode

ORD_ORGANISATIONS = "https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations"
PHARMACY_ROLE = "RO182"
PAGE_SIZE = 1000


def fetch_ods_wales(
    fetcher: Fetcher, welsh_postcodes: set[str], pause_s: float = 0.1
) -> list[RawPharmacy]:
    pharmacies: list[RawPharmacy] = []
    offset = 0
    while True:
        params = {"PrimaryRoleId": PHARMACY_ROLE, "Status": "Active", "Limit": str(PAGE_SIZE)}
        if offset:  # Offset = records to skip; the API rejects Offset=0, so omit it at first
            params["Offset"] = str(offset)
        page: dict[str, Any] = fetcher.get_json(ORD_ORGANISATIONS, params=params)
        organisations = page.get("Organisations", [])
        for summary in organisations:
            postcode = normalise_postcode(summary.get("PostCode", ""))
            if postcode is None or postcode not in welsh_postcodes:
                continue
            detail = fetcher.get_json(summary["OrgLink"])["Organisation"]
            location = detail.get("GeoLoc", {}).get("Location", {})
            address = tuple(
                str(location[key]).strip()
                for key in ("AddrLn1", "AddrLn2", "AddrLn3", "Town")
                if str(location.get(key, "")).strip()
            )
            pharmacies.append(
                RawPharmacy(
                    nation="Wales",
                    code=summary["OrgId"],
                    name=str(detail.get("Name", summary.get("Name", ""))).strip(),
                    address=address,
                    postcode=postcode,
                    hours=None,
                )
            )
            if pause_s:
                time.sleep(pause_s)
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

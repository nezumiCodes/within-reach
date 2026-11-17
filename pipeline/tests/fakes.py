"""Test doubles shared by several test modules."""

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def onspd_zip_bytes(tmp: Path) -> bytes:
    """A tiny ONSPD-shaped zip: Data/*_UK.csv plus the Documents name files."""
    target = tmp / "onspd_fixture.zip"
    with zipfile.ZipFile(target, "w") as z:
        z.write(FIXTURES / "onspd_sample.csv", "Data/ONSPD_TEST_2026_UK.csv")
        for names in sorted((FIXTURES / "onspd_names").glob("*.csv")):
            z.write(names, f"Documents/{names.name}")
        z.writestr("User Guide/readme.txt", "ignored")
    return target.read_bytes()


class FakeFetcher:
    """Serves recorded API fixtures and fixed download bodies."""

    def __init__(self, downloads: dict[str, bytes]) -> None:
        self.downloads = downloads
        self.json_calls: list[tuple[str, dict[str, str] | None]] = []

    def get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        self.json_calls.append((url, params))
        if "package_show" in url:
            assert params is not None
            name = {
                "consolidated-pharmaceutical-list": "ckan_nhsbsa.json",
                "dispenser-location-contact-details": "ckan_phs.json",
                "contractor-details": "ckan_contractor_details.json",
            }[params["id"]]
            return json.loads((FIXTURES / name).read_text())
        if "arcgis.com/sharing/rest/search" in url:
            return json.loads((FIXTURES / "arcgis_onspd_search.json").read_text())
        if url.endswith("/organisations"):
            assert params is not None
            if params["Offset"] == "0":
                return json.loads((FIXTURES / "ods_list.json").read_text())
            return {"Organisations": []}
        if "/organisations/" in url:
            return json.loads((FIXTURES / "ods_org_FWF56.json").read_text())
        raise AssertionError(f"unexpected JSON request {url}")

    def get_text(self, url: str) -> str:
        raise AssertionError(f"unexpected text request {url}")

    def download(self, url: str, dest: Path) -> str:
        body = next(v for k, v in self.downloads.items() if k in url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return hashlib.sha256(body).hexdigest()

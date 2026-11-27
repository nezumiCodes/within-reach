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


def water_zip_bytes(tmp: Path) -> bytes:
    """A water-polygons-shaped zip: one folder holding the shapefile parts, plus a readme."""
    target = tmp / "water_fixture.zip"
    with zipfile.ZipFile(target, "w") as z:
        for ext in ("shp", "shx", "dbf", "prj", "cpg"):
            z.writestr(f"water-polygons-split-4326/water_polygons.{ext}", ext)
        z.writestr("water-polygons-split-4326/README.txt", "ignored")
    return target.read_bytes()


class FakeFetcher:
    """Serves recorded API fixtures and fixed download bodies."""

    def __init__(self, downloads: dict[str, bytes]) -> None:
        self.downloads = downloads
        # (url, params, header names). Names only: header values may be secrets (the API key).
        self.json_calls: list[tuple[str, dict[str, str] | None, list[str]]] = []

    def get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        self.json_calls.append((url, params, sorted(headers or {})))
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
            assert params.get("Offset") != "0", "ORD rejects Offset=0"
            if "Offset" not in params:
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


ONSPD_HEADER = (FIXTURES / "onspd_sample.csv").read_text(encoding="utf-8").splitlines()[0]

# postcode, ctry, cty, lad, hlth, east, north, lat, lon
CACHE_POSTCODES = [
    (
        "CH1 1AA",
        "E92000001",
        "E99999999",
        "E06000050",
        "E18000008",
        340500,
        366300,
        53.1900,
        -2.8900,
    ),
    (
        "CH1 2AA",
        "E92000001",
        "E99999999",
        "E06000050",
        "E18000008",
        341000,
        366500,
        53.1918,
        -2.8826,
    ),
    (
        "CH2 1AA",
        "E92000001",
        "E99999999",
        "E06000050",
        "E18000008",
        342000,
        367500,
        53.2009,
        -2.8678,
    ),
    (
        "LL11 1AA",
        "W92000004",
        "W99999999",
        "W06000006",
        "W11000023",
        333000,
        350500,
        53.0470,
        -3.0000,
    ),
    (
        "LL11 4UF",
        "W92000004",
        "W99999999",
        "W06000006",
        "W11000023",
        332000,
        351500,
        53.0559,
        -3.0151,
    ),
    (
        "G22 5ER",
        "S92000003",
        "S99999999",
        "S12000049",
        "S08000031",
        259000,
        668000,
        55.8800,
        -4.2400,
    ),
    (
        "G1 2GF",
        "S92000003",
        "S99999999",
        "S12000049",
        "S08000031",
        259500,
        665500,
        55.8620,
        -4.2520,
    ),
    (
        "LL12 7AA",
        "W92000004",
        "W99999999",
        "W06000006",
        "W11000023",
        334500,
        352000,
        53.0606,
        -2.9779,
    ),
]


def make_cache(root: Path) -> Path:
    """A complete fetch cache in miniature: 8 postcodes in 3 areas, 6 usable pharmacies."""
    import csv

    cache = root / "cache"
    data = cache / "onspd" / "Data"
    data.mkdir(parents=True)
    header = ONSPD_HEADER.split(",")
    with (data / "ONSPD_TEST_2026_UK.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for pc, ctry, cty, lad, hlth, east, north, lat, lon in CACHE_POSTCODES:
            row = dict.fromkeys(header, "")
            row.update(
                pcds=pc,
                ctry26cd=ctry,
                cty26cd=cty,
                lad26cd=lad,
                hlth19cd=hlth,
                east1m=str(east),
                north1m=str(north),
                lat=f"{lat:.6f}",
                long=f"{lon:.6f}",
            )
            writer.writerow(row)
    docs = cache / "onspd" / "Documents"
    docs.mkdir()
    for names in (FIXTURES / "onspd_names").glob("*.csv"):
        (docs / names.name).write_bytes(names.read_bytes())

    nhsbsa_rows = list(csv.DictReader((FIXTURES / "nhsbsa_sample.csv").open(encoding="utf-8-sig")))
    template = next(r for r in nhsbsa_rows if r["PHARMACY_ODS_CODE_F_CODE"] == "FA002")
    with (cache / "nhsbsa.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(template))
        writer.writeheader()
        for code, postcode in [("FA001", "CH1 2AA"), ("FA002", "CH2 1AA"), ("FAA01", "CH1 1AA")]:
            writer.writerow({**template, "PHARMACY_ODS_CODE_F_CODE": code, "POST_CODE": postcode})
    (cache / "contractor_details.csv").write_bytes(
        (FIXTURES / "contractor_details_sample.csv").read_bytes()
    )  # FAA01 is flagged as distance selling
    (cache / "phs.csv").write_bytes((FIXTURES / "phs_sample.csv").read_bytes())
    (cache / "ods_wales.json").write_text(
        json.dumps(
            [
                {
                    "code": "FWF56",
                    "name": "ROWLANDS PHARMACY",
                    "address": ["BEECH STREET", "WREXHAM"],
                    "postcode": "LL11 4UF",
                },
                {
                    "code": "FW002",
                    "name": "WREXHAM PHARMACY",
                    "address": ["HIGH STREET", "WREXHAM"],
                    "postcode": "LL12 7AA",
                },
            ]
        )
    )
    (cache / "uk.osm.pbf").write_bytes(b"not used by the fake router")
    sources = [
        {"name": n, "label": f"{n} test", "url": f"https://example.test/{n}", "sha256": "0" * 64}
        for n in ["onspd", "nhsbsa", "contractor_details", "phs", "osm", "ods_wales"]
    ]
    (cache / "sources.json").write_text(json.dumps(sources))
    return cache

"""Find the latest release of each public data source."""

from dataclasses import dataclass
from typing import Any

from within_reach_pipeline.http import Fetcher

NHSBSA_CKAN = "https://opendata.nhsbsa.net/api/3/action/package_show"
PHS_CKAN = "https://www.opendata.nhs.scot/api/3/action/package_show"
ARCGIS_SEARCH = "https://www.arcgis.com/sharing/rest/search"
ARCGIS_ITEM_DATA = "https://www.arcgis.com/sharing/rest/content/items/{id}/data"
OSM_UK_URL = "https://download.geofabrik.de/europe/united-kingdom-latest.osm.pbf"
# Sea areas for the map files (OSM coastline processed by osmdata.openstreetmap.de, ODbL).
WATER_POLYGONS_URL = "https://osmdata.openstreetmap.de/download/water-polygons-split-4326.zip"


@dataclass(frozen=True)
class SourceRelease:
    name: str
    label: str
    url: str


def _latest_ckan_csv(fetcher: Fetcher, api: str, package: str, name: str) -> SourceRelease:
    result: dict[str, Any] = fetcher.get_json(api, params={"id": package})["result"]
    csvs = [r for r in result["resources"] if str(r.get("format", "")).upper() == "CSV"]
    if not csvs:
        raise ValueError(f"{package}: no CSV resources")
    newest = max(csvs, key=lambda r: str(r.get("created") or ""))
    return SourceRelease(name=name, label=str(newest["name"]).strip(), url=str(newest["url"]))


def latest_nhsbsa(fetcher: Fetcher) -> SourceRelease:
    return _latest_ckan_csv(fetcher, NHSBSA_CKAN, "consolidated-pharmaceutical-list", "nhsbsa")


def latest_contractor_details(fetcher: Fetcher) -> SourceRelease:
    return _latest_ckan_csv(fetcher, NHSBSA_CKAN, "contractor-details", "contractor_details")


def latest_phs(fetcher: Fetcher) -> SourceRelease:
    return _latest_ckan_csv(fetcher, PHS_CKAN, "dispenser-location-contact-details", "phs")


def latest_onspd(fetcher: Fetcher) -> SourceRelease:
    data = fetcher.get_json(
        ARCGIS_SEARCH,
        params={
            "f": "json",
            "num": "20",
            "sortField": "modified",
            "sortOrder": "desc",
            "q": 'title:"ONS Postcode Directory" AND owner:ONSGeography_data '
            'AND type:"CSV Collection"',
        },
    )
    items = [
        r
        for r in data["results"]
        if r.get("type") == "CSV Collection" and "user guide" not in str(r["title"]).lower()
    ]
    if not items:
        raise ValueError("ONSPD: no CSV Collection found")
    newest = max(items, key=lambda r: int(r["modified"]))
    return SourceRelease("onspd", str(newest["title"]), ARCGIS_ITEM_DATA.format(id=newest["id"]))

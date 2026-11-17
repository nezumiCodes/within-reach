from fakes import FakeFetcher

from within_reach_pipeline.sources import (
    latest_contractor_details,
    latest_nhsbsa,
    latest_onspd,
    latest_phs,
)


def _fetcher() -> FakeFetcher:
    return FakeFetcher(downloads={})


def test_latest_nhsbsa() -> None:
    release = latest_nhsbsa(_fetcher())
    assert release.name == "nhsbsa"
    assert release.label == "CONSOL_PHARMACY_LIST_202627Q2"
    assert release.url.endswith("consol_pharmacy_list_202627q2.csv")


def test_latest_phs() -> None:
    assert latest_phs(_fetcher()).label == "Dispenser Details - August 2026"


def test_latest_contractor_details() -> None:
    assert latest_contractor_details(_fetcher()).label == "CONTRACTOR_DETAILS_202610"


def test_latest_onspd() -> None:
    release = latest_onspd(_fetcher())
    assert release.label == "ONS Postcode Directory (August 2026)"
    assert release.url == (
        "https://www.arcgis.com/sharing/rest/content/items/9e5a92a3cfb14dc7ad43d6ea7a7b8c7f/data"
    )

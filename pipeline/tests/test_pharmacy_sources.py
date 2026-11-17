import json
from pathlib import Path
from typing import Any

from within_reach_pipeline.pharmacies.england import read_distance_selling_codes, read_nhsbsa
from within_reach_pipeline.pharmacies.scotland import read_phs
from within_reach_pipeline.pharmacies.wales import fetch_ods_wales

FIXTURES = Path(__file__).parent / "fixtures"


def test_read_nhsbsa() -> None:
    pharmacies, warnings = read_nhsbsa(FIXTURES / "nhsbsa_sample.csv")
    codes = [p.code for p in pharmacies]
    assert "FA696" not in codes  # DAC: appliance contractor, not a pharmacy
    assert "FC380" in codes  # LPS is kept
    fa002 = next(p for p in pharmacies if p.code == "FA002")
    assert fa002.nation == "England"
    assert fa002.name == "ROWLANDS PHARMACY"
    assert fa002.address == ("61 ARUNDEL AVENUE", "HAZEL GROVE", "STOCKPORT")
    assert fa002.postcode == "SK7 5LD"
    assert fa002.hours is not None
    assert fa002.hours["mon"] == (("09:00", "13:00"), ("14:00", "17:30"))
    assert fa002.hours["sun"] == ()
    odd = next(p for p in pharmacies if p.code == "FAA01")
    assert odd.hours is not None
    assert odd.hours["sat"] == ()
    assert odd.hours["sun"] is None
    assert warnings == 1


def test_read_distance_selling_codes() -> None:
    codes = read_distance_selling_codes(FIXTURES / "contractor_details_sample.csv")
    assert codes == frozenset({"FAA01", "FAA04"})


def test_read_phs() -> None:
    pharmacies = read_phs(FIXTURES / "phs_sample.csv")
    first = pharmacies[0]
    assert (first.nation, first.code, first.name) == ("Scotland", "1030", "A G BANNERMAN LTD")
    assert first.address == ("220/222 SARACEN STREET", "GLASGOW")
    assert first.hours is None
    assert pharmacies[1].postcode == "G1 2GF"


class FakeFetcher:
    def __init__(self) -> None:
        self.pages = [json.loads((FIXTURES / "ods_list.json").read_text()), {"Organisations": []}]
        self.org = json.loads((FIXTURES / "ods_org_FWF56.json").read_text())
        self.detail_calls: list[str] = []

    def get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        if url.endswith("/organisations"):
            assert params is not None
            assert params["PrimaryRoleId"] == "RO182"
            assert params["Status"] == "Active"
            # Like the real ORD API: Offset is "records to skip" and 0 is rejected (406).
            assert params.get("Offset") != "0", "ORD rejects Offset=0"
            return self.pages[int(params.get("Offset", "0")) // 1000]
        self.detail_calls.append(url)
        return self.org

    def get_text(self, url: str) -> str:
        raise NotImplementedError

    def download(self, url: str, dest: Path) -> str:
        raise NotImplementedError


def test_fetch_ods_wales() -> None:
    fetcher = FakeFetcher()
    pharmacies = fetch_ods_wales(fetcher, welsh_postcodes={"LL11 4UF"}, pause_s=0)
    assert len(pharmacies) == 1
    wales = pharmacies[0]
    assert (wales.nation, wales.code, wales.name) == ("Wales", "FWF56", "ROWLANDS PHARMACY")
    assert wales.address == ("PEN Y MAES HEALTH CENTRE", "BEECH STREET", "SUMMERHILL", "WREXHAM")
    assert wales.postcode == "LL11 4UF"
    assert wales.hours is None
    assert len(fetcher.detail_calls) == 1  # the English org is never looked up

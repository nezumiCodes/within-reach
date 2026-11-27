import json
from pathlib import Path
from typing import Any

import pytest

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


def _summary(code: str, postcode: str) -> dict[str, str]:
    return {
        "OrgId": code,
        "PostCode": postcode,
        "Name": f"{code} PHARMACY",
        "OrgLink": f"https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations/{code}",
    }


def _detail(code: str, postcode: str, country: str) -> dict[str, Any]:
    location = {
        "AddrLn1": "1 HIGH STREET",
        "Town": "TOWN",
        "PostCode": postcode,
        "Country": country,
    }
    return {"Organisation": {"Name": f"{code} PHARMACY", "GeoLoc": {"Location": location}}}


class FakeFetcher:
    def __init__(self) -> None:
        listing = json.loads((FIXTURES / "ods_list.json").read_text())["Organisations"]
        listing += [
            _summary("FWZ01", "LL99 9ZZ"),  # Welsh, postcode not (yet) in ONSPD
            _summary("FHX01", "CH1 1AA"),  # English, in a Welsh-border area
            _summary("FA0E2", "CH1 2AA"),
        ]  # already in the NHSBSA list
        self.pages = [{"Organisations": listing}, {"Organisations": []}]
        self.details = {
            "FWF56": json.loads((FIXTURES / "ods_org_FWF56.json").read_text()),
            "FWZ01": _detail("FWZ01", "LL99 9ZZ", "WALES"),
            "FHX01": _detail("FHX01", "CH1 1AA", "ENGLAND"),
        }
        self.detail_calls: list[str] = []

    def get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if url.endswith("/organisations"):
            assert params is not None
            assert params["PrimaryRoleId"] == "RO182"
            assert params["Status"] == "Active"
            # Like the real ORD API: Offset is "records to skip" and 0 is rejected (406).
            assert params.get("Offset") != "0", "ORD rejects Offset=0"
            return self.pages[int(params.get("Offset", "0")) // 1000]
        code = url.rsplit("/", 1)[-1]
        self.detail_calls.append(code)
        return self.details[code]

    def get_text(self, url: str) -> str:
        raise NotImplementedError

    def download(self, url: str, dest: Path) -> str:
        raise NotImplementedError


def test_fetch_ods_wales() -> None:
    fetcher = FakeFetcher()
    pharmacies = fetch_ods_wales(
        fetcher, welsh_areas={"LL", "CH"}, english_codes=frozenset({"FA0E2"}), pause_s=0
    )
    assert [p.code for p in pharmacies] == ["FWF56", "FWZ01"]
    wales = pharmacies[0]
    assert (wales.nation, wales.name) == ("Wales", "ROWLANDS PHARMACY")
    assert wales.address == ("PEN Y MAES HEALTH CENTRE", "BEECH STREET", "SUMMERHILL", "WREXHAM")
    assert wales.postcode == "LL11 4UF"
    assert wales.hours is None
    # The postcode is kept even though ONSPD doesn't know it, so geocoding can count the failure.
    assert pharmacies[1].postcode == "LL99 9ZZ"
    # FA002 (SK area) and FA0E2 (already English) are never looked up.
    assert sorted(fetcher.detail_calls) == ["FHX01", "FWF56", "FWZ01"]


def test_postcode_area() -> None:
    from within_reach_pipeline.pharmacies.wales import postcode_area

    assert [postcode_area(p) for p in ["LL11 4UF", "CH5 1AA", "M1 1AE"]] == ["LL", "CH", "M"]


def test_read_nhsbsa_missing_hours_column_raises(tmp_path: Path) -> None:
    text = (FIXTURES / "nhsbsa_sample.csv").read_text(encoding="utf-8-sig")
    renamed = tmp_path / "renamed.csv"
    renamed.write_text(text.replace("PHARMACY_OPENING_HOURS_MONDAY", "OPENING_MONDAY", 1))
    with pytest.raises(ValueError, match="PHARMACY_OPENING_HOURS_MONDAY"):
        read_nhsbsa(renamed)


def test_read_nhsbsa_short_row_does_not_crash(tmp_path: Path) -> None:
    lines = (FIXTURES / "nhsbsa_sample.csv").read_text(encoding="utf-8-sig").splitlines()
    short = tmp_path / "short.csv"
    short.write_text("\n".join([lines[0], "FZZ01,STOCKPORT,SHORT PHARMACY,ORG,1 HIGH ST"]) + "\n")
    pharmacies, _ = read_nhsbsa(short)
    assert pharmacies[0].code == "FZZ01"
    assert pharmacies[0].hours is not None and pharmacies[0].hours["mon"] is None

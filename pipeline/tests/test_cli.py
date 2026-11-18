import contextlib
import json
import logging
from pathlib import Path

from fakes import FIXTURES, FakeFetcher, onspd_zip_bytes

from within_reach_pipeline import cli
from within_reach_pipeline.pharmacies.wales import load_ods_wales


def test_cli_fetch_writes_cache(tmp_path: Path) -> None:
    fetcher = FakeFetcher(
        downloads={
            "arcgis.com/sharing/rest/content/items": onspd_zip_bytes(tmp_path),
            "consol_pharmacy_list": (FIXTURES / "nhsbsa_sample.csv").read_bytes(),
            "contractor_details": b"contractor",
            "dispenser_contactdetails": b"phs",
            "geofabrik": b"pbf",
        }
    )
    cache = tmp_path / "cache"
    assert cli.run(["fetch", "--cache", str(cache)], fetcher=fetcher) == 0

    sources = json.loads((cache / "sources.json").read_text())
    names = [s["name"] for s in sources]
    assert names == ["onspd", "nhsbsa", "contractor_details", "phs", "osm", "ods_wales"]
    assert all(set(s) == {"name", "label", "url", "sha256"} for s in sources)
    for filename in ["nhsbsa.csv", "contractor_details.csv", "phs.csv", "uk.osm.pbf"]:
        assert (cache / filename).exists()
    assert (cache / "onspd" / "Data" / "ONSPD_TEST_2026_UK.csv").exists()
    assert len(list((cache / "onspd" / "Documents").glob("*.csv"))) == 3
    assert not (cache / "onspd" / "User Guide").exists()

    # LL11 1AA makes "LL" a Welsh postcode area, so FWF56 (LL11 4UF) is looked up in ODS and
    # kept because its ODS record says WALES. FA002 (SK7) is never considered.
    welsh = load_ods_wales(cache / "ods_wales.json")
    assert [p.code for p in welsh] == ["FWF56"]


def test_ods_wales_roundtrip(tmp_path: Path) -> None:
    from within_reach_pipeline.models import RawPharmacy
    from within_reach_pipeline.pharmacies.wales import save_ods_wales

    items = [RawPharmacy("Wales", "FWF56", "ROWLANDS", ("A", "B"), "LL11 4UF", None)]
    save_ods_wales(items, tmp_path / "w.json")
    assert load_ods_wales(tmp_path / "w.json") == items


def test_http_request_logging_is_quiet(tmp_path: Path) -> None:
    # A full build makes millions of OSRM requests; logging each one floods the Actions log.
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    with contextlib.suppress(FileNotFoundError):  # only the logging setup matters here
        cli.run(["check", "--release-dir", str(tmp_path / "missing")])
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING

import gzip
import hashlib
from pathlib import Path

from within_reach_pipeline.bundle import (
    write_area,
    write_directory,
    write_district_index,
)
from within_reach_pipeline.models import Pharmacy, Postcode, RawPharmacy
from within_reach_pipeline.routing import TravelRow


def _lines(path: Path) -> list[str]:
    return gzip.decompress(path.read_bytes()).decode("utf-8").splitlines()


PC = [
    Postcode("CH1 1AA", 53.19, -2.89, 340500, 366300, "England", "E06000050"),
    Postcode("CH5 1AA", 53.2, -3.0, 333000, 367000, "Wales", "W11000023"),
]


def _pharmacy(hours: dict | None) -> Pharmacy:  # type: ignore[type-arg]
    raw = RawPharmacy(
        "England", "FA002", "ROWLANDS", ("61 ARUNDEL AVENUE", "STOCKPORT"), "SK7 5LD", hours
    )
    return Pharmacy(raw, 53.37, -2.12, 392000, 385000)


def test_write_area_roundtrip(tmp_path: Path) -> None:
    rows = [TravelRow(0, 3, 120, 150, 107, None)]
    postcodes_info, travel_info = write_area(tmp_path, "E06000050", PC[:1], rows)
    assert postcodes_info.path == "areas/E06000050/postcodes.csv.gz"
    assert _lines(tmp_path / postcodes_info.path) == [
        "pc_idx,postcode,lat,lon",
        "0,CH1 1AA,53.190000,-2.890000",
    ]
    assert _lines(tmp_path / travel_info.path) == [
        "pc_idx,ph_idx,straight_m,walk_m,walk_s,drive_s,walk_cycle",
        "0,3,120,150,107,,",
    ]
    data = (tmp_path / travel_info.path).read_bytes()
    assert travel_info.sha256 == hashlib.sha256(data).hexdigest()
    assert travel_info.bytes == len(data)


def test_travel_file_has_walk_cycle_column(tmp_path: Path) -> None:
    rows = [TravelRow(0, 3, 120, 150, 107, 30, walk_cycle=True), TravelRow(0, 4, 130, 160, 115, 31)]
    _, travel_info = write_area(tmp_path, "E06000050", PC[:1], rows)
    assert _lines(tmp_path / travel_info.path)[1:] == [
        "0,3,120,150,107,30,1",
        "0,4,130,160,115,31,",
    ]


def test_directory_hours_cells(tmp_path: Path) -> None:
    hours = {
        "mon": (("09:00", "13:00"), ("14:00", "17:30")),
        "tue": (),
        "wed": None,
        "thu": (),
        "fri": (),
        "sat": (),
        "sun": (),
    }
    write_directory(tmp_path / "a", [_pharmacy(hours)])
    lines = _lines(tmp_path / "a" / "pharmacies.csv.gz")
    assert lines[0] == (
        "ph_idx,nation,code,name,address,postcode,lat,lon,mon,tue,wed,thu,fri,sat,sun"
    )
    assert lines[1] == (
        '0,England,FA002,ROWLANDS,"61 ARUNDEL AVENUE, STOCKPORT",SK7 5LD,'
        "53.370000,-2.120000,09:00-13:00;14:00-17:30,CLOSED,,CLOSED,CLOSED,"
        "CLOSED,CLOSED"
    )
    write_directory(tmp_path / "b", [_pharmacy(None)])
    assert _lines(tmp_path / "b" / "pharmacies.csv.gz")[1].endswith(",,,,,,,")


def test_gzip_deterministic(tmp_path: Path) -> None:
    first = write_directory(tmp_path / "a", [_pharmacy(None)])
    second = write_directory(tmp_path / "b", [_pharmacy(None)])
    assert first.sha256 == second.sha256


def test_district_index(tmp_path: Path) -> None:
    info = write_district_index(tmp_path, PC)
    assert info.path == "districts.csv.gz"
    assert _lines(tmp_path / info.path) == ["outward,area_codes", "CH1,E06000050", "CH5,W11000023"]


def test_district_spanning_two_areas(tmp_path: Path) -> None:
    extra = Postcode("CH1 9ZZ", 53.1, -3.0, 333000, 367000, "Wales", "W11000023")
    write_district_index(tmp_path, [*PC, extra])
    assert _lines(tmp_path / "districts.csv.gz")[1] == "CH1,E06000050 W11000023"

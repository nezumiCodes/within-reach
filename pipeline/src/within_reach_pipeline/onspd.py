"""ONS Postcode Directory (ONSPD) reading and area assignment.

Only live postcodes in England, Scotland and Wales are kept. Northern Ireland (BT) rows are
licensed for internal use only and are never read past this module (spec C3, FR-04).
Column names carry year suffixes that change between releases (lad26cd -> lad27cd), so columns
are found by pattern.
"""

import csv
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from within_reach_pipeline.models import Nation, Postcode
from within_reach_pipeline.postcodes import is_northern_ireland, normalise_postcode

ONSPD_COUNTRIES: dict[str, Nation] = {
    "E92000001": "England",
    "S92000003": "Scotland",
    "W92000004": "Wales",
}
NO_GRID_LAT = 99.999999
ENGLAND_NO_COUNTY = "E99999999"


@dataclass(frozen=True)
class OnspdColumns:
    pcds: str
    doterm: str
    ctry: str
    cty: str
    lad: str
    hlth: str
    east: str
    north: str
    lat: str
    lon: str


_PATTERNS: dict[str, str] = {
    "pcds": r"pcds",
    "doterm": r"doterm",
    "ctry": r"ctry\d{2}cd",
    "cty": r"cty\d{2}cd",
    "lad": r"lad\d{2}cd",
    "hlth": r"hlth\d{2}cd",
    "east": r"east1m",
    "north": r"north1m",
    "lat": r"lat",
    "lon": r"long",
}


def resolve_columns(header: Sequence[str]) -> OnspdColumns:
    found: dict[str, str] = {}
    missing: list[str] = []
    for field, pattern in _PATTERNS.items():
        matches = [h for h in header if re.fullmatch(pattern, h.strip().lower())]
        if matches:
            found[field] = matches[0]
        else:
            missing.append(pattern.replace(r"\d{2}", "NN"))
    if missing:
        raise ValueError(f"ONSPD header is missing columns: {', '.join(missing)}")
    return OnspdColumns(**found)


def area_code_for(nation: Nation, cty: str, lad: str, hlth: str) -> str:
    """Councils in England (upper tier) and Scotland, health boards in Wales (decision D4)."""
    if nation == "England":
        return lad if cty in ("", ENGLAND_NO_COUNTY) else cty
    if nation == "Scotland":
        return lad
    return hlth


def read_onspd(csv_path: Path) -> Iterator[Postcode]:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = resolve_columns(reader.fieldnames or [])
        for row in reader:
            nation = ONSPD_COUNTRIES.get(row[columns.ctry])
            if nation is None or row[columns.doterm].strip():
                continue
            postcode = normalise_postcode(row[columns.pcds])
            if postcode is None or is_northern_ireland(postcode):
                continue
            try:
                lat, lon = float(row[columns.lat]), float(row[columns.lon])
                east, north = int(row[columns.east]), int(row[columns.north])
            except ValueError:
                continue
            if lat == NO_GRID_LAT:
                continue
            yield Postcode(
                postcode=postcode,
                lat=lat,
                lon=lon,
                east=east,
                north=north,
                nation=nation,
                area_code=area_code_for(
                    nation, row[columns.cty], row[columns.lad], row[columns.hlth]
                ),
            )


_NAME_FILES = (
    "LAD Local Authority District names*.csv",
    "CTY County names*.csv",
    "HLTH health authority names*.csv",
)


def read_area_names(documents_dir: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    for pattern in _NAME_FILES:
        for path in sorted(documents_dir.glob(pattern)):
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                header = [h.strip().upper() for h in next(reader, [])]
                code_col = next(i for i, h in enumerate(header) if h.endswith("CD"))
                name_col = next(i for i, h in enumerate(header) if h.endswith("NM"))
                for row in reader:
                    if len(row) > max(code_col, name_col) and row[code_col].strip():
                        names[row[code_col].strip()] = row[name_col].strip()
    return names

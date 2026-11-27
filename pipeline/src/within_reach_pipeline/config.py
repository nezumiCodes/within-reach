"""Pipeline settings, loaded from pipeline/config.toml."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

# The app's pharmacy parser accepts only this grammar for the keys in the services cell.
SERVICE_KEY = re.compile(r"[a-z0-9_]+")

# The production DoHS host. A full release's services must come from here (checks.py).
DOHS_PRODUCTION_HOST = "api.service.nhs.uk"

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config.toml"


@dataclass(frozen=True)
class ServiceDef:
    key: str
    name: str
    code: str
    nations: tuple[str, ...]


@dataclass(frozen=True)
class PipelineConfig:
    radius_m: int
    max_candidates: int
    min_candidates: int
    reach_cap_m: int
    reach_max_rounds: int
    cycle_note_min_extra_m: int
    max_file_bytes: int
    count_tolerance: float
    geocode_failure_limit: float
    osrm_image: str
    user_agent: str
    distance_selling_min: int
    distance_selling_max: int
    tilemaker_image: str
    map_chunk_bytes: int
    services_enabled: bool
    services: tuple[ServiceDef, ...]
    service_min: int
    services_api_base: str
    services_min_listed: int
    services_listed_tolerance: float
    services_max_missing_share: float


def _check_service_keys(services: tuple[ServiceDef, ...]) -> None:
    seen: set[str] = set()
    for service in services:
        if not SERVICE_KEY.fullmatch(service.key):
            raise ValueError(f"service key must match [a-z0-9_]+: {service.key!r}")
        if service.key in seen:
            raise ValueError(f"duplicate service key: {service.key}")
        seen.add(service.key)


def load_config(path: Path = DEFAULT_CONFIG) -> PipelineConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    catchment, release, services = data["catchment"], data["release"], data["services"]
    catalogue = tuple(
        ServiceDef(
            key=str(entry["key"]),
            name=str(entry["name"]),
            code=str(entry["code"]),
            nations=tuple(str(n) for n in entry["nations"]),
        )
        for entry in services["catalogue"]
    )
    _check_service_keys(catalogue)
    return PipelineConfig(
        radius_m=int(catchment["radius_m"]),
        max_candidates=int(catchment["max_candidates"]),
        min_candidates=int(catchment["min_candidates"]),
        reach_cap_m=int(catchment["reach_cap_m"]),
        reach_max_rounds=int(catchment["reach_max_rounds"]),
        cycle_note_min_extra_m=int(catchment["cycle_note_min_extra_m"]),
        max_file_bytes=int(release["max_file_bytes"]),
        count_tolerance=float(release["count_tolerance"]),
        geocode_failure_limit=float(release["geocode_failure_limit"]),
        osrm_image=str(data["routing"]["osrm_image"]),
        user_agent=str(data["http"]["user_agent"]),
        distance_selling_min=int(release["distance_selling_min"]),
        distance_selling_max=int(release["distance_selling_max"]),
        tilemaker_image=str(data["maps"]["tilemaker_image"]),
        map_chunk_bytes=int(data["maps"]["chunk_bytes"]),
        services_enabled=bool(services["enabled"]),
        services=catalogue,
        service_min=int(services["service_min"]),
        services_api_base=str(services["api_base"]),
        services_min_listed=int(services["min_listed"]),
        services_listed_tolerance=float(services["listed_tolerance"]),
        services_max_missing_share=float(services["max_missing_share"]),
    )

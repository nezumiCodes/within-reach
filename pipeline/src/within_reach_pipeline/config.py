"""Pipeline settings, loaded from pipeline/config.toml."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config.toml"


@dataclass(frozen=True)
class PipelineConfig:
    radius_m: int
    max_candidates: int
    min_candidates: int
    max_file_bytes: int
    count_tolerance: float
    geocode_failure_limit: float
    osrm_image: str
    user_agent: str


def load_config(path: Path = DEFAULT_CONFIG) -> PipelineConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    catchment, release = data["catchment"], data["release"]
    return PipelineConfig(
        radius_m=int(catchment["radius_m"]),
        max_candidates=int(catchment["max_candidates"]),
        min_candidates=int(catchment["min_candidates"]),
        max_file_bytes=int(release["max_file_bytes"]),
        count_tolerance=float(release["count_tolerance"]),
        geocode_failure_limit=float(release["geocode_failure_limit"]),
        osrm_image=str(data["routing"]["osrm_image"]),
        user_agent=str(data["http"]["user_agent"]),
    )

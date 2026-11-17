from pathlib import Path

from within_reach_pipeline.config import load_config

CONFIG = Path(__file__).resolve().parents[1] / "config.toml"


def test_load_config_defaults() -> None:
    config = load_config(CONFIG)
    assert config.radius_m == 5000
    assert config.max_candidates == 40
    assert config.min_candidates == 5
    assert config.max_file_bytes == 25_165_824
    assert config.count_tolerance == 0.10
    assert config.geocode_failure_limit == 0.01
    assert config.osrm_image.endswith(":v26.11.0-debian")

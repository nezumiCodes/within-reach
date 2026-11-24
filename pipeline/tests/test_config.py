from pathlib import Path

import pytest

from within_reach_pipeline.config import ServiceDef, load_config

CONFIG = Path(__file__).resolve().parents[1] / "config.toml"


def test_load_config_defaults() -> None:
    config = load_config(CONFIG)
    assert config.radius_m == 5000
    assert config.max_candidates == 40
    assert config.min_candidates == 5
    assert config.max_file_bytes == 25_165_824
    assert config.count_tolerance == 0.10
    assert config.geocode_failure_limit == 0.02
    assert config.osrm_image.endswith(":v26.11.0-debian")
    assert (config.distance_selling_min, config.distance_selling_max) == (200, 1000)


def test_maps_settings_load() -> None:
    config = load_config(CONFIG)
    assert config.map_chunk_bytes == 20 * 1024 * 1024
    assert "@sha256:" in config.tilemaker_image


def test_cycle_and_reach_settings_load() -> None:
    config = load_config(CONFIG)
    assert (config.cycle_note_min_extra_m, config.reach_cap_m, config.reach_max_rounds) == (
        50,
        25000,
        4,
    )


def test_services_config_loads() -> None:
    config = load_config(CONFIG)
    assert config.services_enabled is False
    assert config.service_min == 5
    assert config.services == (ServiceDef("nsp", "Needle exchange", "SRV0274", ("England",)),)
    assert config.services_api_base == "https://api.service.nhs.uk/service-search-api/"
    assert (
        config.services_min_listed,
        config.services_listed_tolerance,
        config.services_max_missing_share,
    ) == (1000, 0.20, 0.10)


def _with_keys(tmp_path: Path, *keys: str) -> Path:
    text = CONFIG.read_text(encoding="utf-8")
    start = text.index("[[services.catalogue]]")
    entries = "".join(
        f'[[services.catalogue]]\nkey = "{k}"\nname = "N"\ncode = "C"\nnations = ["England"]\n\n'
        for k in keys
    )
    path = tmp_path / "config.toml"
    end = text.index("[routing]")
    path.write_text(text[:start] + entries + text[end:], encoding="utf-8")
    return path


def test_service_key_grammar_accepts_nsp(tmp_path: Path) -> None:
    assert [s.key for s in load_config(_with_keys(tmp_path, "nsp")).services] == ["nsp"]


@pytest.mark.parametrize("key", ["needle-exchange", "NSP", "", "a;b", "nsp?"])
def test_service_key_grammar_rejects_bad_keys(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError, match="service key"):
        load_config(_with_keys(tmp_path, key))


def test_service_keys_must_be_unique(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate service key"):
        load_config(_with_keys(tmp_path, "nsp", "nsp"))

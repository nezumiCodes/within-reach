import json
import logging
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import FIXTURES

from within_reach_pipeline.cli import SERVICES_FILE, run
from within_reach_pipeline.config import DEFAULT_CONFIG, load_config
from within_reach_pipeline.services import (
    ServicesFetchError,
    Snapshot,
    fetch_snapshot,
    load_snapshot,
    save_snapshot,
)

BASE = "https://dohs.example.test/service-search-api/"
KEY = "secret-key"
KEYED = {"NHS_DOHS_API_KEY": KEY, "NHS_DOHS_API_BASE": BASE}
ENABLED = replace(load_config(), services_enabled=True)


def _pages() -> list[dict[str, Any]]:
    made_up = json.loads((FIXTURES / "dohs_page.json").read_text())["value"]
    first = [{"ODSCode": f"ZZ{n:04d}", "Services": []} for n in range(997)] + made_up
    second = [{"ODSCode": f"YY{n:04d}", "Services": []} for n in range(2)]
    return [{"value": first}, {"value": second}]


class DohsFake:
    def __init__(self, pages: list[dict[str, Any]], fail_at: int | None = None) -> None:
        self.pages = pages
        self.fail_at = fail_at
        self.calls: list[tuple[str, dict[str, str], dict[str, str]]] = []

    def get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        assert params is not None and headers is not None
        self.calls.append((url, params, headers))
        index = len(self.calls) - 1
        if index == self.fail_at:
            request = httpx.Request("GET", url, headers=headers)
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("429 Too Many Requests", request=request, response=response)
        return self.pages[index]

    def get_text(self, url: str) -> str:
        raise AssertionError("unexpected")

    def download(self, url: str, dest: Path) -> str:
        raise AssertionError("unexpected")


def test_fetch_snapshot_pages_and_normalises() -> None:
    fake = DohsFake(_pages())
    snap = fetch_snapshot(fake, BASE, KEY, sleep=lambda s: None)
    assert len(snap.listed) == 1002
    assert snap.listed["FA002"] == frozenset()  # lower-case code normalised
    assert "SRV0274" in snap.listed["FE412"]
    assert snap.api_base == BASE
    assert all(c[0] == BASE for c in fake.calls)
    assert all(c[1]["search"] == "*" and c[1]["searchMode"] == "all" for c in fake.calls)
    assert all(c[1]["api-version"] == "3" for c in fake.calls)
    assert [c[1]["$skip"] for c in fake.calls] == ["0", "1000"]
    assert all(c[1]["$top"] == "1000" for c in fake.calls)
    assert all(c[1]["$filter"] == "OrganisationTypeId eq 'PHA'" for c in fake.calls)
    assert all(set(c[2]) == {"apikey"} for c in fake.calls)
    # The key is only ever in a header.
    assert all(KEY not in c[0] and KEY not in c[1].values() for c in fake.calls)


def test_fetch_snapshot_pauses_between_pages_only() -> None:
    pauses: list[float] = []
    fetch_snapshot(DohsFake(_pages()), BASE, KEY, sleep=pauses.append)
    assert pauses == [1.1]


def test_failed_page_leaves_no_snapshot(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    failing = DohsFake(_pages(), fail_at=1)
    with caplog.at_level(logging.DEBUG), pytest.raises(ServicesFetchError) as err:
        run(
            ["fetch-services", "--cache", str(tmp_path)], fetcher=failing, env=KEYED, config=ENABLED
        )
    assert not (tmp_path / SERVICES_FILE).exists()
    assert not (tmp_path / (SERVICES_FILE + ".tmp")).exists()
    assert "$skip=1000" in str(err.value) and "429" in str(err.value)
    assert err.value.__cause__ is None and err.value.__suppress_context__
    assert KEY not in str(err.value) and KEY not in caplog.text
    assert BASE not in str(err.value)


def test_fetch_services_enabled_writes_snapshot(tmp_path: Path) -> None:
    fake = DohsFake(_pages())
    assert (
        run(["fetch-services", "--cache", str(tmp_path)], fetcher=fake, env=KEYED, config=ENABLED)
        == 0
    )
    snap = load_snapshot(tmp_path / SERVICES_FILE)
    assert snap is not None and len(snap.listed) == 1002
    assert snap.api_base == BASE
    assert KEY not in (tmp_path / SERVICES_FILE).read_text()


def test_fetch_services_disabled_writes_nothing(tmp_path: Path) -> None:
    assert run(["fetch-services", "--cache", str(tmp_path)], env={}) == 0
    assert not (tmp_path / SERVICES_FILE).exists()


def test_fetch_services_enabled_without_key_fails(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="NHS_DOHS_API_KEY"):
        run(["fetch-services", "--cache", str(tmp_path)], env={}, config=ENABLED)


def test_snapshot_round_trip(tmp_path: Path) -> None:
    snap = Snapshot(
        "2026-11-24T00:00:00Z", BASE, {"FA001": frozenset({"SRV0274"}), "FA002": frozenset()}
    )
    path = tmp_path / SERVICES_FILE
    assert load_snapshot(path) is None
    save_snapshot(snap, path)
    assert load_snapshot(path) == snap
    assert not path.with_name(path.name + ".tmp").exists()


def test_config_env_var_applies_to_every_command(tmp_path: Path) -> None:
    enabled_toml = DEFAULT_CONFIG.read_text().replace("enabled = false", "enabled = true")
    config_path = tmp_path / "config.toml"
    config_path.write_text(enabled_toml)
    env = {**KEYED, "WITHIN_REACH_CONFIG": str(config_path)}
    cache = tmp_path / "cache"
    cache.mkdir()
    fake = DohsFake(_pages())
    assert run(["fetch-services", "--cache", str(cache)], fetcher=fake, env=env) == 0
    assert (cache / SERVICES_FILE).exists()


def test_explicit_config_beats_env_var(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(DEFAULT_CONFIG.read_text().replace("enabled = false", "enabled = true"))
    disabled = replace(load_config(), services_enabled=False)
    env: Mapping[str, str] = {"WITHIN_REACH_CONFIG": str(config_path)}
    assert run(["fetch-services", "--cache", str(tmp_path)], env=env, config=disabled) == 0
    assert not (tmp_path / SERVICES_FILE).exists()

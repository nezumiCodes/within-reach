import json
import logging
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import httpx
import pytest
from fakes import FIXTURES

from within_reach_pipeline.cli import SERVICES_FILE, run
from within_reach_pipeline.config import DEFAULT_CONFIG, ServiceDef, load_config
from within_reach_pipeline.models import Pharmacy, RawPharmacy
from within_reach_pipeline.services import (
    ServicesFetchError,
    Snapshot,
    assign_services,
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
    return [{"@odata.count": 1002, "value": first}, {"@odata.count": 1002, "value": second}]


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
    # A stable order, so records can't shift between pages, and a total to check against.
    assert all(c[1]["$orderby"] == "ODSCode" for c in fake.calls)
    assert all(c[1]["$count"] == "true" for c in fake.calls)
    assert all(set(c[2]) == {"apikey"} for c in fake.calls)
    # The key is only ever in a header.
    assert all(KEY not in c[0] and KEY not in c[1].values() for c in fake.calls)


@pytest.mark.parametrize("count", [1003, 1001])
def test_record_total_must_match_count(count: int) -> None:
    pages = _pages()
    for page in pages:
        page["@odata.count"] = count
    with pytest.raises(ServicesFetchError, match=rf"1002 records but @odata\.count is {count}"):
        fetch_snapshot(DohsFake(pages), BASE, KEY, sleep=lambda s: None)


def test_count_changing_between_pages_fails() -> None:
    pages = _pages()
    pages[1]["@odata.count"] = 1003
    with pytest.raises(ServicesFetchError, match=r"@odata\.count changed"):
        fetch_snapshot(DohsFake(pages), BASE, KEY, sleep=lambda s: None)


def test_missing_count_fails() -> None:
    pages = _pages()
    del pages[0]["@odata.count"]
    with pytest.raises(ServicesFetchError, match=r"no @odata\.count"):
        fetch_snapshot(DohsFake(pages), BASE, KEY, sleep=lambda s: None)


def test_short_count_writes_no_snapshot(tmp_path: Path) -> None:
    pages = _pages()
    for page in pages:
        page["@odata.count"] = 1500
    with pytest.raises(ServicesFetchError):
        run(
            ["fetch-services", "--cache", str(tmp_path)],
            fetcher=DohsFake(pages),
            env=KEYED,
            config=ENABLED,
        )
    assert not (tmp_path / SERVICES_FILE).exists()


def test_duplicate_ods_codes_take_the_union_of_services() -> None:
    page = {
        "@odata.count": 3,
        "value": [
            {"ODSCode": "FX001", "Services": [{"ServiceCode": "SRV0274"}]},
            {"ODSCode": "fx001", "Services": [{"ServiceCode": "SRV0001"}]},
            {"ODSCode": "FX001", "Services": None},
        ],
    }
    snap = fetch_snapshot(DohsFake([page]), BASE, KEY, sleep=lambda s: None)
    assert snap.listed == {"FX001": frozenset({"SRV0274", "SRV0001"})}


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


NSP = ServiceDef("nsp", "Needle exchange", "SRV0274", ("England",))


def _ph(nation: Literal["England", "Scotland", "Wales"], code: str) -> Pharmacy:
    return Pharmacy(RawPharmacy(nation, code, "N", ("A",), "AB1 1AA", None), 53.0, -2.0, 1, 1)


def _assignment_inputs() -> tuple[list[Pharmacy], Snapshot]:
    pharmacies = [
        _ph("England", "FA001"),  # listed
        _ph("England", "fa002"),  # in DoHS, not listed (code case differs)
        _ph("England", "FA003"),  # no DoHS record: treated as not listed
        _ph("Scotland", "S1"),
        _ph("Wales", "W1"),
    ]
    snapshot = Snapshot(
        "2026-11-01T00:00:00Z",
        "https://x/",
        {
            "FA001": frozenset({"SRV0274", "SRV1"}),
            "FA002": frozenset({"SRV1"}),
            "FZZZZ": frozenset({"SRV0274"}),  # no NHSBSA match
        },
    )
    return pharmacies, snapshot


def test_assign_services_cells() -> None:
    pharmacies, snapshot = _assignment_inputs()
    a = assign_services(pharmacies, [NSP], snapshot)
    assert a.cells == ["nsp", "", "", "nsp?", "nsp?"]
    assert a.listed == {"nsp": frozenset({0})}
    assert a.counts == {"nsp": {"listed": 1, "unmatched_dohs": 1, "missing_dohs": 1}}


def test_assign_services_joins_several_keys() -> None:
    pharmacies, snapshot = _assignment_inputs()
    other = ServiceDef("oth", "Other", "SRV1", ("England",))
    a = assign_services(pharmacies, [NSP, other], snapshot)
    assert a.cells[:2] == ["nsp;oth", "oth"]


def test_assign_services_off() -> None:
    pharmacies, snapshot = _assignment_inputs()
    for a in (
        assign_services(pharmacies, [NSP], None),
        assign_services(pharmacies, [], snapshot),
    ):
        assert a.cells == [""] * 5
        assert a.listed == {} and a.counts == {}

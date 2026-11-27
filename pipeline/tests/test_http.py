from pathlib import Path

import httpx
import pytest

from within_reach_pipeline.http import HttpxFetcher

UA = "within-reach-pipeline (+https://withinreach.vasnik.net)"


def test_download_writes_file_and_returns_sha256(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"abc"))
    fetcher = HttpxFetcher(UA, transport=transport)
    dest = tmp_path / "out.bin"
    digest = fetcher.download("https://example.test/file", dest)
    assert digest == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert dest.read_bytes() == b"abc"
    assert not dest.with_suffix(".bin.part").exists()


def test_fetcher_sends_user_agent() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers["User-Agent"]
        return httpx.Response(200, json={"ok": True})

    fetcher = HttpxFetcher(UA, transport=httpx.MockTransport(handler))
    assert fetcher.get_json("https://example.test/api") == {"ok": True}
    assert seen["ua"] == UA


def test_get_json_retries_on_server_error() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=[1])

    fetcher = HttpxFetcher(UA, transport=httpx.MockTransport(handler), backoff_s=0)
    assert fetcher.get_json("https://example.test/api") == [1]
    assert calls["n"] == 3


def test_get_json_asks_for_json() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["accept"] = request.headers.get("Accept", "")
        return httpx.Response(200, json={})

    HttpxFetcher(UA, transport=httpx.MockTransport(handler)).get_json("https://example.test")
    assert seen["accept"] == "application/json"


def test_dropped_connections_retried_five_times() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 5:
            raise httpx.RemoteProtocolError("Server disconnected", request=request)
        return httpx.Response(200, json={"ok": 1})

    fetcher = HttpxFetcher(UA, transport=httpx.MockTransport(handler), backoff_s=0)
    assert fetcher.get_json("https://example.test/api") == {"ok": 1}
    assert calls["n"] == 5


def test_default_client_connects_over_ipv4_only() -> None:
    # GitHub's runners have no IPv6 route. Hosts with AAAA records (Geofabrik) failed with
    # "[Errno 101] Network is unreachable" on every retry (pipeline run 44350937497).
    from within_reach_pipeline.http import HttpxFetcher

    transport = HttpxFetcher("test-agent")._client._transport
    assert transport._pool._local_address == "0.0.0.0"  # type: ignore[attr-defined]  # noqa: S104


def test_get_json_sends_extra_headers() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["apikey"] = request.headers.get("apikey", "")
        seen["ua"] = request.headers["User-Agent"]
        seen["accept"] = request.headers["Accept"]
        return httpx.Response(200, json={})

    fetcher = HttpxFetcher(UA, transport=httpx.MockTransport(handler))
    fetcher.get_json("https://example.test", headers={"apikey": "k"})
    assert seen == {"apikey": "k", "ua": UA, "accept": "application/json"}


def _redirecting(seen: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.url.host} {request.headers.get('apikey', '-')}")
        if request.url.host == "api.example.test":
            return httpx.Response(302, headers={"Location": "https://elsewhere.test/x"})
        return httpx.Response(200, json={"ok": True}, content=None)

    return httpx.MockTransport(handler)


def test_get_json_does_not_follow_redirects() -> None:
    # The DoHS apikey header would be sent on to the redirect target.
    seen: list[str] = []
    fetcher = HttpxFetcher(UA, transport=_redirecting(seen), backoff_s=0)
    with pytest.raises(httpx.HTTPStatusError) as err:
        fetcher.get_json("https://api.example.test/search", headers={"apikey": "secret-key"})
    assert seen == ["api.example.test secret-key"]  # one request, never retried or followed
    assert err.value.response.status_code == 302
    assert "302" in str(err.value) and "redirect" in str(err.value).lower()
    assert "secret-key" not in str(err.value) and "apikey" not in str(err.value)


def test_plain_get_json_follows_redirects() -> None:
    # CKAN, ORD (OrgLink) and OSRM carry no credentials; a host move mustn't break the build.
    seen: list[str] = []
    fetcher = HttpxFetcher(UA, transport=_redirecting(seen), backoff_s=0)
    assert fetcher.get_json("https://api.example.test/search", params={"q": "x"}) == {"ok": True}
    assert seen == ["api.example.test -", "elsewhere.test -"]


def test_get_text_and_download_still_follow_redirects(tmp_path: Path) -> None:
    seen: list[str] = []
    fetcher = HttpxFetcher(UA, transport=_redirecting(seen), backoff_s=0)
    assert fetcher.get_text("https://api.example.test/page") == '{"ok":true}'
    fetcher.download("https://api.example.test/file", tmp_path / "f.json")
    assert (tmp_path / "f.json").read_text() == '{"ok":true}'
    assert [s.split()[0] for s in seen] == ["api.example.test", "elsewhere.test"] * 2


def _throttled(retry_after: list[str | None]) -> tuple[httpx.MockTransport, dict[str, int]]:
    """429 for each entry (with that Retry-After, if any), then 200."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= len(retry_after):
            value = retry_after[calls["n"] - 1]
            return httpx.Response(429, headers={"Retry-After": value} if value else {})
        return httpx.Response(200, json={"ok": True})

    return httpx.MockTransport(handler), calls


@pytest.mark.parametrize(
    ("retry_after", "waits"),
    [
        (["7"], [7.0]),
        (["0"], [0.0]),
        (["600"], [60.0]),  # capped
        ([None], [2.0]),  # absent: the usual backoff
        (["soon", "Wed, 21 Oct 2026 07:28:00 GMT"], [2.0, 4.0]),  # unparseable: backoff
        (["-5"], [2.0]),
    ],
)
def test_get_json_retries_429_honouring_retry_after(
    retry_after: list[str | None], waits: list[float]
) -> None:
    transport, calls = _throttled(retry_after)
    slept: list[float] = []
    fetcher = HttpxFetcher(UA, transport=transport, backoff_s=2.0, sleep=slept.append)
    assert fetcher.get_json("https://example.test/api") == {"ok": True}
    assert slept == waits
    assert calls["n"] == len(retry_after) + 1


def test_429_within_the_retry_budget() -> None:
    transport, calls = _throttled(["1"] * 10)
    slept: list[float] = []
    fetcher = HttpxFetcher(UA, transport=transport, retries=3, sleep=slept.append)
    with pytest.raises(httpx.HTTPStatusError) as err:
        fetcher.get_json("https://example.test/api")
    assert err.value.response.status_code == 429
    assert calls["n"] == 3 and slept == [1.0, 1.0]


def test_other_4xx_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403)

    slept: list[float] = []
    fetcher = HttpxFetcher(UA, transport=httpx.MockTransport(handler), sleep=slept.append)
    with pytest.raises(httpx.HTTPStatusError):
        fetcher.get_json("https://example.test/api")
    assert calls["n"] == 1 and slept == []

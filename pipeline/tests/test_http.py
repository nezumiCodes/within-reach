from pathlib import Path

import httpx

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

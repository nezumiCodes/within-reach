"""HTTP access behind a small protocol, so tests can substitute fakes."""

import hashlib
import time
from pathlib import Path
from typing import Any, Protocol

import httpx


class Fetcher(Protocol):
    def get_json(self, url: str, params: dict[str, str] | None = None) -> Any: ...

    def get_text(self, url: str) -> str: ...

    def download(self, url: str, dest: Path) -> str:
        """Download to dest and return the file's hex SHA-256."""
        ...


class HttpxFetcher:
    def __init__(
        self,
        user_agent: str,
        transport: httpx.BaseTransport | None = None,
        retries: int = 3,
        backoff_s: float = 2.0,
        timeout_s: float = 60.0,
    ) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            transport=transport,
            timeout=timeout_s,
            follow_redirects=True,
        )
        self._retries = retries
        self._backoff_s = backoff_s

    def _get(
        self, url: str, params: dict[str, str] | None = None, accept: str | None = None
    ) -> httpx.Response:
        headers = {"Accept": accept} if accept else None
        for attempt in range(1, self._retries + 1):
            try:
                response = self._client.get(url, params=params, headers=headers)
                if response.status_code < 500:
                    response.raise_for_status()
                    return response
            except httpx.TransportError:
                if attempt == self._retries:
                    raise
            if attempt == self._retries:
                response.raise_for_status()
            time.sleep(self._backoff_s * attempt)
        raise RuntimeError("unreachable")

    def get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        # Some APIs (NHS ODS) answer 406 unless JSON is requested explicitly.
        return self._get(url, params, accept="application/json").json()

    def get_text(self, url: str) -> str:
        return self._get(url).text

    def download(self, url: str, dest: Path) -> str:
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")
        digest = hashlib.sha256()
        for attempt in range(1, self._retries + 1):
            try:
                with self._client.stream("GET", url) as response:
                    response.raise_for_status()
                    digest = hashlib.sha256()
                    with part.open("wb") as out:
                        for chunk in response.iter_bytes(1 << 20):
                            digest.update(chunk)
                            out.write(chunk)
                break
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == self._retries:
                    raise
                time.sleep(self._backoff_s * attempt)
        part.replace(dest)
        return digest.hexdigest()

"""HTTP access behind a small protocol, so tests can substitute fakes."""

import hashlib
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import httpx

RETRY_AFTER_MAX_S = 60.0  # the longest a Retry-After header can make a 429 retry wait


class Fetcher(Protocol):
    def get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any: ...

    def get_text(self, url: str) -> str: ...

    def download(self, url: str, dest: Path) -> str:
        """Download to dest and return the file's hex SHA-256."""
        ...


class HttpxFetcher:
    def __init__(
        self,
        user_agent: str,
        transport: httpx.BaseTransport | None = None,
        retries: int = 5,
        backoff_s: float = 2.0,
        timeout_s: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            # IPv4 only: GitHub's runners have no IPv6 route, and httpx doesn't fall back to
            # IPv4 when a host (Geofabrik, for one) also publishes IPv6 addresses.
            transport=transport or httpx.HTTPTransport(local_address="0.0.0.0"),  # noqa: S104
            timeout=timeout_s,
            follow_redirects=True,
        )
        self._retries = retries
        self._backoff_s = backoff_s
        self._sleep = sleep

    def _backoff(self, attempt: int) -> float:
        return self._backoff_s * 2.0 ** (attempt - 1)

    def _retry_after(self, response: httpx.Response, attempt: int) -> float:
        """Seconds to wait after a 429: Retry-After (seconds, capped), else the backoff.
        An HTTP-date Retry-After is treated as unparseable."""
        try:
            seconds = float(response.headers.get("Retry-After", ""))
        except ValueError:
            return self._backoff(attempt)
        if not 0 <= seconds < float("inf"):
            return self._backoff(attempt)
        return min(seconds, RETRY_AFTER_MAX_S)

    def _get(
        self,
        url: str,
        params: dict[str, str] | None = None,
        accept: str | None = None,
        extra_headers: dict[str, str] | None = None,
        follow_redirects: bool = True,
    ) -> httpx.Response:
        headers = {**({"Accept": accept} if accept else {}), **(extra_headers or {})} or None
        for attempt in range(1, self._retries + 1):
            wait = self._backoff(attempt)
            try:
                response = self._client.get(
                    url, params=params, headers=headers, follow_redirects=follow_redirects
                )
                if response.is_redirect:
                    # Only reached with follow_redirects off. Never retried; the message names
                    # the status only, not the URL or headers.
                    raise httpx.HTTPStatusError(
                        f"redirect not followed: HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                if response.status_code == 429:
                    wait = self._retry_after(response, attempt)
                elif response.status_code < 500:
                    response.raise_for_status()
                    return response
            except httpx.TransportError:
                if attempt == self._retries:
                    raise
            if attempt == self._retries:
                response.raise_for_status()
            self._sleep(wait)
        raise RuntimeError("unreachable")

    def get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        # Some APIs (NHS ODS) answer 406 unless JSON is requested explicitly. A request with
        # extra headers may carry a credential (the DoHS apikey), which httpx would send on to
        # a redirect's new host, so it doesn't follow redirects; plain requests still do.
        return self._get(
            url,
            params,
            accept="application/json",
            extra_headers=headers,
            follow_redirects=not headers,
        ).json()

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
                self._sleep(self._backoff(attempt))
        part.replace(dest)
        return digest.hexdigest()

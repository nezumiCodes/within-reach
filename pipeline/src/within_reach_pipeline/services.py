"""Pharmacy services from NHS England's Directory of Healthcare Services (DoHS) API, v3."""

import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from within_reach_pipeline.config import ServiceDef
from within_reach_pipeline.http import Fetcher
from within_reach_pipeline.models import Pharmacy

log = logging.getLogger("within_reach_pipeline")

PAGE_SIZE = 1000
PAGE_PAUSE_S = 1.1  # the API allows one request a second


class ServicesFetchError(RuntimeError):
    """A DoHS request failed. The message never carries the URL, headers or key."""


@dataclass(frozen=True)
class Snapshot:
    fetched_at: str
    api_base: str
    # Upper-cased ODS code -> the service codes it lists. Every DoHS pharmacy has an entry.
    listed: dict[str, frozenset[str]]


def _service_code(entry: Any) -> str:
    return str(entry["ServiceCode"] if isinstance(entry, dict) else entry)


def fetch_snapshot(
    fetcher: Fetcher,
    api_base: str,
    api_key: str,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], str] = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
) -> Snapshot:
    """Page through every DoHS pharmacy, in ODS code order so records can't shift between pages.

    Fails, so no snapshot is written, unless the records received add up to `@odata.count`.
    """
    listed: dict[str, frozenset[str]] = {}
    skip = 0
    received = 0
    total: int | None = None
    while True:
        params = {
            "api-version": "3",
            "search": "*",
            "searchMode": "all",
            "$select": "ODSCode,Services",
            "$filter": "OrganisationTypeId eq 'PHA'",
            "$top": str(PAGE_SIZE),
            "$skip": str(skip),
            "$orderby": "ODSCode",
            "$count": "true",
        }
        try:
            page = fetcher.get_json(api_base, params=params, headers={"apikey": api_key})
        except httpx.HTTPError as err:
            # Not chained (from None): the original request carries the apikey header.
            status = err.response.status_code if isinstance(err, httpx.HTTPStatusError) else "n/a"
            raise ServicesFetchError(
                f"DoHS request failed at $skip={skip}: HTTP {status}"
            ) from None
        count = page.get("@odata.count")
        if not isinstance(count, int):
            raise ServicesFetchError(f"DoHS page at $skip={skip} has no @odata.count")
        if total is not None and count != total:
            raise ServicesFetchError(
                f"DoHS @odata.count changed from {total} to {count} at $skip={skip}"
            )
        total = count
        records = page["value"]
        received += len(records)
        for record in records:
            code = str(record["ODSCode"]).strip().upper()
            listed[code] = frozenset(_service_code(s) for s in record.get("Services") or [])
        if len(records) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
        sleep(PAGE_PAUSE_S)
    if received != total:
        raise ServicesFetchError(f"DoHS returned {received} records but @odata.count is {total}")
    log.info("DoHS: %d pharmacies", len(listed))
    return Snapshot(fetched_at=now(), api_base=api_base, listed=listed)


def save_snapshot(snapshot: Snapshot, path: Path) -> None:
    body = {
        "fetched_at": snapshot.fetched_at,
        "api_base": snapshot.api_base,
        "listed": {code: sorted(codes) for code, codes in sorted(snapshot.listed.items())},
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_snapshot(path: Path) -> Snapshot | None:
    if not path.exists():
        return None
    body = json.loads(path.read_text(encoding="utf-8"))
    return Snapshot(
        fetched_at=body["fetched_at"],
        api_base=body["api_base"],
        listed={code: frozenset(codes) for code, codes in body["listed"].items()},
    )


@dataclass(frozen=True)
class ServiceAssignment:
    cells: list[str]  # indexed by ph_idx
    listed: dict[str, frozenset[int]]  # service key -> ph_idx values that list it
    counts: dict[str, dict[str, int]]  # service key -> listed / unmatched_dohs / missing_dohs


def assign_services(
    pharmacies: Sequence[Pharmacy], defs: Sequence[ServiceDef], snapshot: Snapshot | None
) -> ServiceAssignment:
    """The `services` cell of every pharmacy: `key` listed, `key?` not known, absent not listed.

    Pharmacies in a nation the service does not cover are unknown. English pharmacies with no
    DoHS record are not listed (empty cell), but are counted in `missing_dohs`.
    """
    if snapshot is None or not defs:
        return ServiceAssignment([""] * len(pharmacies), {}, {})
    cells: list[list[str]] = [[] for _ in pharmacies]
    listed: dict[str, frozenset[int]] = {}
    counts: dict[str, dict[str, int]] = {}
    for d in defs:
        in_nations = {i for i, p in enumerate(pharmacies) if p.raw.nation in d.nations}
        matched: set[str] = set()
        hits: set[int] = set()
        missing = 0
        for i, p in enumerate(pharmacies):
            if i not in in_nations:
                cells[i].append(f"{d.key}?")
                continue
            code = p.raw.code.upper()
            codes = snapshot.listed.get(code)
            if codes is None:
                missing += 1  # no DoHS record: counted, and treated as not listed
                continue
            matched.add(code)
            if d.code in codes:
                cells[i].append(d.key)
                hits.add(i)
        listed[d.key] = frozenset(hits)
        counts[d.key] = {
            "listed": len(hits),
            "unmatched_dohs": len(set(snapshot.listed) - matched),
            "missing_dohs": missing,
        }
    return ServiceAssignment([";".join(c) for c in cells], listed, counts)

"""Major-board search links and optional Adzuna collection, without AI."""
from __future__ import annotations

from typing import Any, Mapping
from urllib.request import urlopen

from applicant.models import BOARD_DOMAINS
from applicant.providers import (
    adzuna_jobs as _adzuna_jobs,
    adzuna_listing,
    parse_listings,
    search_links,
    write_search_page,
)


def adzuna_jobs(
    settings: Mapping[str, Any],
    *,
    errors: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    return _adzuna_jobs(settings, errors=errors, urlopen_fn=urlopen)


__all__ = [
    "BOARD_DOMAINS",
    "adzuna_jobs",
    "adzuna_listing",
    "parse_listings",
    "search_links",
    "write_search_page",
]

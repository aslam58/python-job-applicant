"""India location spelling variants and a configurable public-employer preset."""
from __future__ import annotations

from applicant.matching import (
    CITY_GROUPS,
    INDIA_BOARDS,
    INDIA_PLACES,
    effective_boards,
    india_search,
    normalize_location,
)

__all__ = [
    "CITY_GROUPS",
    "INDIA_BOARDS",
    "INDIA_PLACES",
    "effective_boards",
    "india_search",
    "normalize_location",
]

"""Local document reading and deterministic, explainable job ranking."""
from __future__ import annotations

from applicant.matching import (
    STOP,
    SYNONYMS,
    TOKEN,
    rank,
    read_resume,
    tokens,
)

__all__ = [
    "STOP",
    "SYNONYMS",
    "TOKEN",
    "rank",
    "read_resume",
    "tokens",
]

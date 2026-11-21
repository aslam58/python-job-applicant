#!/usr/bin/env python3
"""Deterministic job discovery and assisted application filling. No AI services."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from applicant.autofill import (
    ALIASES,
    BLOCKED_TYPES,
    FIELD_INFO,
    KNOWN_ATS_HOSTS,
    SENSITIVE,
    apply as _apply,
    autofill as _autofill,
    confirm_receipt,
    detect_verification,
    evidence,
    form_scopes,
    inspect_form,
    is_resume_input,
    load_application_statuses,
    log_result,
    norm,
    preview_autofill as _preview_autofill,
    profile_value,
)
from applicant.cli import (
    ask_keywords,
    build_parser,
    guided_search as _guided_search,
    init_directory,
    main as _main,
    search as _search,
    show_status,
)
from applicant.http_client import get_json, plain_text
from applicant.matching import (
    contains_phrase,
    effective_boards,
    india_search,
    matches,
    normalize_location,
    rank,
    read_resume,
)
from applicant.models import (
    BOARD_DOMAINS,
    PROFILE,
    SOURCES,
    canonical_url,
    load_json,
    merge_defaults,
    sanitize_csv_cell,
    save_json,
    validate_profile,
    validate_sources,
    validate_url,
)
from applicant.providers import (
    adzuna_jobs,
    collect_public_jobs as _collect_public_jobs,
    fetch_board as _fetch_board,
    parse_listings,
    public_job_page,
    public_jobs as _public_jobs,
    write_search_page,
)


def fetch_board(
    board: Mapping[str, Any],
    fetch: Callable[[str], Any] | None = None,
    *,
    errors: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    return _fetch_board(board, fetch=get_json if fetch is None else fetch, errors=errors)


def public_jobs(
    provider: str,
    role: str = "",
    fetch: Callable[[str], Any] | None = None,
    *,
    country: str = "",
    page: int = 1,
) -> list[dict[str, Any]]:
    return _public_jobs(provider, role, fetch=get_json if fetch is None else fetch, country=country, page=page)


def collect_public_jobs(
    settings: Mapping[str, Any],
    failures: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _collect_public_jobs(settings, failures, fetch=get_json)


def search(
    sources_path: str | Path | None,
    output_path: str | Path,
    *,
    settings: Mapping[str, Any] | None = None,
    resume: str | None = None,
    profile_path: str | Path | None = None,
    hide_applied: bool = False,
) -> dict[str, Any]:
    return _search(
        sources_path,
        output_path,
        settings=settings,
        resume=resume,
        fetch=get_json,
        profile_path=profile_path,
        hide_applied=hide_applied,
    )


def preview_autofill(
    page: Any,
    profile: Mapping[str, Any],
    resume: Path | None,
    scope: str | None = None,
) -> dict[str, Any]:
    return _preview_autofill(page, profile, resume, scope, form_scopes_fn=form_scopes)


def autofill(
    page: Any,
    profile: Mapping[str, Any],
    resume: Path | None,
    scope: str | None = None,
) -> dict[str, int]:
    return _autofill(page, profile, resume, scope, form_scopes_fn=form_scopes)


def apply(args: Any) -> None:
    return _apply(args, autofill_fn=autofill, preview_fn=preview_autofill)


def guided_search(args: Any) -> int:
    return _guided_search(args, search_fn=search)


def main(argv: list[str] | None = None) -> int:
    return _main(argv, guided_search_fn=guided_search, apply_fn=apply, status_fn=show_status)


__all__ = [
    "ALIASES",
    "BLOCKED_TYPES",
    "BOARD_DOMAINS",
    "FIELD_INFO",
    "KNOWN_ATS_HOSTS",
    "PROFILE",
    "SENSITIVE",
    "SOURCES",
    "adzuna_jobs",
    "apply",
    "ask_keywords",
    "autofill",
    "build_parser",
    "canonical_url",
    "collect_public_jobs",
    "confirm_receipt",
    "contains_phrase",
    "detect_verification",
    "effective_boards",
    "evidence",
    "fetch_board",
    "form_scopes",
    "get_json",
    "guided_search",
    "india_search",
    "init_directory",
    "inspect_form",
    "is_resume_input",
    "load_application_statuses",
    "load_json",
    "log_result",
    "main",
    "matches",
    "merge_defaults",
    "norm",
    "normalize_location",
    "parse_listings",
    "plain_text",
    "preview_autofill",
    "profile_value",
    "public_job_page",
    "public_jobs",
    "rank",
    "read_resume",
    "sanitize_csv_cell",
    "save_json",
    "search",
    "show_status",
    "validate_profile",
    "validate_sources",
    "validate_url",
    "write_search_page",
]


if __name__ == "__main__":
    raise SystemExit(main())

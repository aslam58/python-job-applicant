"""Data models, defaults, config validation, URL normalization, and CSV safety."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping, TypedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class SearchError(TypedDict):
    board: str
    error: str


class JobListing(TypedDict, total=False):
    id: str
    company: str
    title: str
    location: str
    url: str
    detail_url: str
    source_url: str
    description: str
    source: str
    status: str
    resume_score: float
    matched_terms: list[str]
    missing_terms: list[str]
    application_status: str


# Service addresses are configuration defaults, independent of applicant identity.
BOARD_DOMAINS: dict[str, str] = {
    "LinkedIn": "linkedin.com/jobs",
    "Indeed": "indeed.com",
    "Naukri": "naukri.com",
    "Foundit": "foundit.in",
    "Glassdoor": "glassdoor.com",
    "Shine": "shine.com",
    "TimesJobs": "timesjobs.com",
    "Instahyre": "instahyre.com",
    "Wellfound": "wellfound.com",
    "Cutshort": "cutshort.io",
    "ZipRecruiter": "ziprecruiter.com",
    "Dice": "dice.com",
    "Reed": "reed.co.uk",
    "Totaljobs": "totaljobs.com",
    "Greenhouse": "greenhouse.io",
    "Lever": "jobs.lever.co",
    "Workday": "myworkdayjobs.com",
    "Ashby": "jobs.ashbyhq.com",
    "SmartRecruiters": "jobs.smartrecruiters.com",
}

PROFILE: dict[str, Any] = {
    "first_name": "",
    "last_name": "",
    "full_name": "",
    "email": "",
    "phone": "",
    "linkedin_url": "",
    "github_url": "",
    "portfolio_url": "",
    "city": "",
    "state": "",
    "country": "",
    "address_line_1": "",
    "postal_code": "",
    "current_company": "",
    "current_title": "",
    "notice_period": "",
    "resume_file": "",
    "questions": {},
}

SOURCES: dict[str, Any] = {
    "title_keywords": [],
    "location_keywords": [],
    "exclude_title_keywords": [],
    "description_keywords": [],
    "public_sources": ["arbeitnow", "himalayas"],
    "arbeitnow_pages": 1,
    "himalayas_pages": 3,
    "browser_boards": dict(BOARD_DOMAINS),
    "adzuna": {"enabled": False, "country": "", "pages": 1},
    "india": {"enabled": False},
    "boards": [],
    "direct_jobs": [],
}

_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def merge_defaults(data: Mapping[str, Any], defaults: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of data with any missing keys filled in from defaults."""
    merged: dict[str, Any] = copy.deepcopy(dict(defaults))
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict) and key != "browser_boards":
            nested = copy.deepcopy(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def validate_profile(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise ValueError("profile.json must contain a JSON object.")
    questions = profile.get("questions")
    if questions is not None and not isinstance(questions, dict):
        raise ValueError("profile.json 'questions' must be a JSON object.")
    return profile


def validate_sources(settings: Any) -> dict[str, Any]:
    if not isinstance(settings, dict):
        raise ValueError("sources.json must contain a JSON object.")
    for key in ("title_keywords", "location_keywords", "exclude_title_keywords",
                "description_keywords", "public_sources"):
        value = settings.get(key)
        if value is not None:
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"sources.json '{key}' must be a list of strings.")
    for key in ("boards", "direct_jobs"):
        value = settings.get(key)
        if value is not None and not isinstance(value, list):
            raise ValueError(f"sources.json '{key}' must be a list.")
    for key in ("adzuna", "india", "browser_boards"):
        value = settings.get(key)
        if value is not None and not isinstance(value, dict):
            raise ValueError(f"sources.json '{key}' must be a JSON object.")
    return settings


def validate_url(url: Any) -> str:
    if not isinstance(url, str) or not url or any(c.isspace() or ord(c) < 32 for c in url):
        raise ValueError("Expected a nonempty job URL without whitespace.")
    parts = urlsplit(url)
    # Accessing port also validates its syntax and range.
    _ = parts.port
    if parts.scheme != "https" or not parts.hostname or parts.username is not None or parts.password is not None:
        raise ValueError("Job URLs must be HTTPS and contain no embedded credentials.")
    return url


def canonical_url(url: str) -> str:
    p = urlsplit(url)
    tracking = {"source", "ref", "gh_src"}
    params = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in tracking
    ]
    fragment = p.fragment if p.fragment.startswith(("/", "!/")) else ""
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), urlencode(params), fragment))


def sanitize_csv_cell(value: Any) -> str:
    """Neutralize spreadsheet formula injection for untrusted text fields."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


def resolve_resume_path(raw_path: str, base_dir: Path) -> Path:
    """Resolve user-supplied resume paths, stripping surrounding quotes and handling drag-and-drop escapes."""
    cleaned = raw_path.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    candidate = Path(cleaned).expanduser()
    resolved = candidate if candidate.is_absolute() else (base_dir / candidate)
    if not resolved.exists() and r"\ " in cleaned:
        unescaped = Path(cleaned.replace(r"\ ", " ")).expanduser()
        alt = unescaped if unescaped.is_absolute() else (base_dir / unescaped)
        if alt.exists():
            return alt
    return resolved


def format_stored_resume_path(raw_path: str, resolved_path: Path, base_dir: Path) -> str:
    """Keep relative resume paths portable when inside base_dir; otherwise store resolved absolute path."""
    cleaned = raw_path.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    if not Path(cleaned).expanduser().is_absolute():
        try:
            rel = resolved_path.resolve().relative_to(base_dir.resolve())
            return rel.as_posix()
        except ValueError:
            pass
    return str(resolved_path.resolve())

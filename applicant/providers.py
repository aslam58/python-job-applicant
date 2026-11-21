"""Job board APIs, public feeds, Adzuna integration, and browser search-link generation."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Iterator, Mapping
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from applicant.http_client import get_json, plain_text
from applicant.matching import india_search
from applicant.models import BOARD_DOMAINS, SOURCES, validate_url

MAX_WORKERS = 6


def search_links(settings: Mapping[str, Any]) -> list[dict[str, str]]:
    domains = settings.get("browser_boards", BOARD_DOMAINS)
    rows: list[dict[str, str]] = []
    for name, domain in domains.items():
        if not re.fullmatch(r"[A-Za-z0-9./_-]+", domain):
            raise ValueError("Invalid board domain for " + name)
        for role in settings.get("title_keywords") or ["jobs"]:
            for place in settings.get("location_keywords") or [""]:
                query = " ".join(x for x in ("site:" + domain, role, place) if x)
                rows.append({
                    "board": name,
                    "role": role,
                    "location": place,
                    "url": "https://www.google.com/search?" + urlencode({"q": query}),
                })
    return rows


def write_search_page(settings: Mapping[str, Any], output: str | Path) -> tuple[list[dict[str, str]], Path]:
    links = search_links(settings)
    target = Path(output).with_suffix(".searches.html")
    rows: list[str] = []
    for link in links:
        label = " | ".join(x for x in (link["board"], link["role"], link["location"]) if x)
        rows.append(
            '<li><a target="_blank" rel="noopener" href="'
            + html.escape(link["url"], quote=True)
            + '">'
            + html.escape(label)
            + "</a></li>"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        "<title>Job board searches</title><body><h1>Search job boards</h1>"
        "<p>Open a search below. These are indexed web searches. Check the employer page "
        "for current availability. These links are separate from the collected and "
        "resume-ranked jobs in the JSON/CSV files.</p><ul>"
        + "".join(rows)
        + "</ul></body></html>",
        encoding="utf-8",
    )
    return links, target


def parse_listings(
    rows: Any,
    parse: Callable[[dict[str, Any]], dict[str, Any] | None],
    source: str,
    errors: list[dict[str, str]] | None,
) -> Iterator[dict[str, Any]]:
    """Keep sibling listings when an individual provider record is malformed."""
    if not isinstance(rows, list):
        raise ValueError(f"{source} did not return a list of jobs")
    for index, row in enumerate(rows, 1):
        try:
            if not isinstance(row, dict):
                raise ValueError("expected a job object")
            job = parse(row)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            if errors is None:
                raise
            errors.append({"board": source, "error": f"Skipped listing {index}: {exc}"})
            continue
        if job is not None:
            yield job


def fetch_board(
    board: Mapping[str, Any],
    fetch: Callable[[str], Any] = get_json,
    *,
    errors: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Read published jobs only; never use submission APIs or employer API keys."""
    kind, token = board["type"], board["token"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", token) or ".." in token:
        raise ValueError("Invalid board token")
    company = board.get("company", token)

    if kind == "greenhouse":
        payload = fetch(f"https://boards-api.greenhouse.io/v1/boards/{quote(token)}/jobs?content=true")

        def greenhouse_listing(j: dict[str, Any]) -> dict[str, Any]:
            return {
                "id": str(j["id"]),
                "company": company,
                "title": j["title"],
                "location": j.get("location", {}).get("name", ""),
                "url": j["absolute_url"],
                "description": plain_text(j.get("content", "")),
                "source": kind,
                "status": "published_on_board",
            }

        return list(parse_listings(payload["jobs"], greenhouse_listing, company, errors))

    if kind == "lever":
        region = board.get("region", "global")
        if region not in {"global", "eu"}:
            raise ValueError("Lever region must be global or eu")
        host = "api.eu.lever.co" if region == "eu" else "api.lever.co"
        jobs = fetch(f"https://{host}/v0/postings/{quote(token)}?mode=json")

        def lever_listing(j: dict[str, Any]) -> dict[str, Any]:
            return {
                "id": j["id"],
                "company": company,
                "title": j["text"],
                "location": j.get("categories", {}).get("location", ""),
                "url": j.get("applyUrl") or j["hostedUrl"],
                "description": " ".join([
                    j.get("descriptionPlain") or plain_text(j.get("description", "")),
                    *(plain_text(item.get("content")) for item in j.get("lists", []) if isinstance(item, dict)),
                    j.get("additionalPlain") or "",
                ]),
                "source": kind,
                "status": "published_on_board",
            }

        return list(parse_listings(jobs, lever_listing, company, errors))

    if kind == "ashby":
        payload = fetch(f"https://api.ashbyhq.com/posting-api/job-board/{quote(token)}?includeCompensation=true")

        def ashby_listing(j: dict[str, Any]) -> dict[str, Any] | None:
            if j.get("isListed") is False:
                return None
            locations: list[str] = []
            if j.get("location"):
                locations.append(str(j["location"]))
            for sec in j.get("secondaryLocations") or []:
                if isinstance(sec, dict) and sec.get("location"):
                    locations.append(str(sec["location"]))
            location_str = ", ".join(dict.fromkeys(locations))
            if j.get("isRemote"):
                location_str = (location_str + " | Remote").lstrip(" |")
            return {
                "id": str(j.get("id") or j.get("jobUrl") or j["title"]),
                "company": company,
                "title": j["title"],
                "location": location_str,
                "url": j.get("applyUrl") or j["jobUrl"],
                "source_url": j.get("jobUrl", ""),
                "description": j.get("descriptionPlain") or plain_text(j.get("descriptionHtml", "")),
                "source": kind,
                "status": "published_on_board",
            }

        return list(parse_listings(payload["jobs"], ashby_listing, company, errors))

    if kind == "smartrecruiters":
        jobs: list[dict[str, Any]] = []
        pages = int(board.get("pages", 10))
        if not 1 <= pages <= 20:
            raise ValueError("SmartRecruiters pages must be between 1 and 20")

        def smartrecruiters_listing(job: dict[str, Any]) -> dict[str, Any] | None:
            if job.get("visibility", "PUBLIC") != "PUBLIC":
                return None
            loc = job.get("location", {})
            location = loc.get("fullLocation") or ", ".join(
                str(loc.get(k) or "") for k in ("city", "region", "country") if loc.get(k)
            )
            if loc.get("country", "").casefold() == "in":
                location += " | India"
            if loc.get("remote"):
                location += " | Remote"
            return {
                "id": str(job["id"]),
                "title": job["name"],
                "company": company,
                "location": location,
                "description": "",
                "source": kind,
                "url": f"https://jobs.smartrecruiters.com/{quote(token)}/{quote(str(job['id']))}",
                "detail_url": f"https://api.smartrecruiters.com/v1/companies/{quote(token)}/postings/{quote(str(job['id']))}",
                "status": "published_on_board",
            }

        for page in range(pages):
            params: dict[str, Any] = {"limit": 100, "offset": page * 100}
            if board.get("country"):
                params["country"] = board["country"]
            data = fetch(f"https://api.smartrecruiters.com/v1/companies/{quote(token)}/postings?" + urlencode(params))
            rows = data.get("content", [])
            jobs.extend(parse_listings(rows, smartrecruiters_listing, company, errors))
            if len(rows) < 100 or (page + 1) * 100 >= data.get("totalFound", (page + 2) * 100):
                return jobs
        message = f"SmartRecruiters page limit ({pages}) reached. More listings may exist."
        if errors is None:
            raise ValueError(message)
        errors.append({"board": company, "error": message})
        return jobs

    raise ValueError(f"Unsupported board type: {kind}; use direct_jobs for other platforms")


def public_job_page(
    provider: str,
    role: str,
    fetch: Callable[[str], Any],
    country: str,
    page: int,
    errors: list[dict[str, str]] | None,
) -> tuple[list[dict[str, Any]], int]:
    """Return parsed jobs and the raw count before skipping expired or invalid rows."""
    if provider == "arbeitnow":
        url = "https://www.arbeitnow.com/api/job-board-api"
        if page > 1:
            url += "?" + urlencode({"page": page})
        data = fetch(url)

        def arbeitnow_listing(j: dict[str, Any]) -> dict[str, Any]:
            return {
                "title": j["title"],
                "company": j["company_name"],
                "url": j["url"],
                "location": j["location"] + (" | Remote" if j.get("remote") else ""),
                "description": plain_text(j["description"]),
                "source": provider,
                "status": "listed_on_feed",
            }

        rows = data["data"]
        return list(parse_listings(rows, arbeitnow_listing, provider, errors)), len(rows)

    if provider != "himalayas":
        raise ValueError("Unknown public source: " + provider)

    params: dict[str, Any] = {"q": role, "page": page}
    if country:
        params["country"] = country
    query = urlencode(params)
    data = fetch("https://himalayas.app/jobs/api/search?" + query)
    now = datetime.now(timezone.utc).timestamp()

    def himalayas_listing(j: dict[str, Any]) -> dict[str, Any] | None:
        if j.get("expiryDate") and float(j["expiryDate"]) <= now:
            return None
        places = ", ".join(j.get("locationRestrictions") or ["Worldwide"])
        return {
            "title": j["title"],
            "company": j["companyName"],
            "url": j["applicationLink"],
            "source_url": j["guid"],
            "location": "Remote | " + places,
            "description": plain_text(j["description"]),
            "source": provider,
            "status": "listed_on_feed",
        }

    rows = data["jobs"]
    return list(parse_listings(rows, himalayas_listing, provider, errors)), len(rows)


def public_jobs(
    provider: str,
    role: str = "",
    fetch: Callable[[str], Any] = get_json,
    *,
    country: str = "",
    page: int = 1,
) -> list[dict[str, Any]]:
    jobs, _ = public_job_page(provider, role, fetch, country, page, None)
    return jobs


def collect_public_jobs(
    settings: Mapping[str, Any],
    failures: list[dict[str, str]],
    *,
    fetch: Callable[[str], Any] = get_json,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tasks: list[tuple[str, str, int, str]] = []
    for provider in settings.get("public_sources", []):
        if provider == "himalayas":
            queries = settings.get("title_keywords") or [""]
            country = "IN" if india_search(settings) else ""
            limit = settings.get("himalayas_pages", SOURCES["himalayas_pages"])
            if type(limit) is not int or not 1 <= limit <= 10:
                failures.append({"board": provider, "error": "himalayas_pages must be an integer from 1 to 10"})
                continue
            for query in queries:
                tasks.append((provider, query, limit, country))
        elif provider == "arbeitnow":
            limit = settings.get("arbeitnow_pages", SOURCES["arbeitnow_pages"])
            if type(limit) is not int or not 1 <= limit <= 10:
                failures.append({"board": provider, "error": "arbeitnow_pages must be an integer from 1 to 10"})
                continue
            tasks.append((provider, "", limit, ""))
        else:
            tasks.append((provider, "", 1, ""))

    def run_task(task: tuple[str, str, int, str]) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any] | None]:
        provider, query, limit, country = task
        local_jobs: list[dict[str, Any]] = []
        local_errors: list[dict[str, str]] = []
        pages_read = 0
        capped = False
        for page in range(1, limit + 1):
            try:
                listings, raw_count = public_job_page(provider, query, fetch, country, page, local_errors)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                local_errors.append({"board": provider, "error": f"Query {query!r}, page {page}: {exc}"})
                break
            local_jobs.extend(listings)
            pages_read += 1
            if provider == "himalayas":
                if raw_count < 20:
                    break
                capped = page == limit
            elif provider == "arbeitnow":
                if raw_count == 0:
                    break
            else:
                break
        report = (
            {"query": query, "pages_read": pages_read, "limit_reached": capped}
            if provider == "himalayas"
            else None
        )
        return local_jobs, local_errors, report

    jobs: list[dict[str, Any]] = []
    page_reports: list[dict[str, Any]] = []
    if len(tasks) <= 1:
        results = [run_task(t) for t in tasks]
    else:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(tasks))) as pool:
            results = list(pool.map(run_task, tasks))

    for local_jobs, local_errors, report in results:
        jobs.extend(local_jobs)
        failures.extend(local_errors)
        if report is not None:
            page_reports.append(report)
            suffix = " (page limit reached)" if report["limit_reached"] else ""
            print(f"Himalayas query {report['query']!r}: read {report['pages_read']} page(s){suffix}.")
    return jobs, page_reports


def collect_board_jobs(
    boards: Iterable[Mapping[str, Any]],
    failures: list[dict[str, str]],
    *,
    fetch: Callable[[str], Any] = get_json,
) -> list[dict[str, Any]]:
    board_list = list(boards)
    if not board_list:
        return []

    def run_board(board: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        local_errors: list[dict[str, str]] = []
        try:
            listings = fetch_board(board, fetch=fetch, errors=local_errors)
            return listings, local_errors
        except Exception as exc:
            local_errors.append({"board": str(board.get("company", board.get("token", ""))), "error": str(exc)})
            return [], local_errors

    if len(board_list) == 1:
        results = [run_board(board_list[0])]
    else:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(board_list))) as pool:
            results = list(pool.map(run_board, board_list))

    jobs: list[dict[str, Any]] = []
    for listings, local_errors in results:
        jobs.extend(listings)
        failures.extend(local_errors)
    return jobs


def fetch_smartrecruiters_details(
    selected: list[dict[str, Any]],
    failures: list[dict[str, str]],
    *,
    fetch: Callable[[str], Any] = get_json,
) -> None:
    targets = [job for job in selected if job.get("detail_url")]
    if not targets:
        return

    def enrich(job: dict[str, Any]) -> dict[str, str] | None:
        detail_url = job.pop("detail_url", None)
        if not detail_url:
            return None
        try:
            detail = fetch(detail_url)
            sections = detail.get("jobAd", {}).get("sections", {})
            job["description"] = " ".join(
                plain_text(section.get("text", ""))
                for section in sections.values()
                if isinstance(section, dict)
            )
            if detail.get("applyUrl"):
                job["url"] = validate_url(detail["applyUrl"])
            return None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {"board": job["company"], "error": "Job detail unavailable: " + str(exc)}

    if len(targets) == 1:
        err = enrich(targets[0])
        if err:
            failures.append(err)
    else:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(targets))) as pool:
            for err in pool.map(enrich, targets):
                if err:
                    failures.append(err)


def adzuna_listing(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": row["title"],
        "company": row.get("company", {}).get("display_name", ""),
        "location": row.get("location", {}).get("display_name", ""),
        "url": row["redirect_url"],
        "description": row.get("description", ""),
        "source": "Adzuna",
        "source_url": "https://www.adzuna.com",
        "status": "listed_on_feed",
    }


def adzuna_jobs(
    settings: Mapping[str, Any],
    *,
    errors: list[dict[str, str]] | None = None,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> list[dict[str, Any]]:
    config = settings.get("adzuna", {})
    country = config.get("country", "")
    if not re.fullmatch("[a-z]{2}", country):
        raise ValueError("Set adzuna.country to your two-letter supported country code.")
    app_id, key = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
    if not app_id or not key:
        raise ValueError("Set ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables.")
    pages = int(config.get("pages", 1))
    if not 1 <= pages <= 10:
        raise ValueError("adzuna.pages must be between 1 and 10.")

    raw_places = settings.get("location_keywords") or [""]
    effective_places = list(dict.fromkeys(
        "" if place.strip().casefold() in {"remote", "worldwide", "anywhere"} else place
        for place in raw_places
    ))

    jobs: list[dict[str, Any]] = []
    for role in settings.get("title_keywords") or [""]:
        for place in effective_places:
            for page in range(1, pages + 1):
                query_params: dict[str, Any] = {
                    "app_id": app_id,
                    "app_key": key,
                    "what": role,
                    "results_per_page": 50,
                }
                if place:
                    query_params["where"] = place
                url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}?{urlencode(query_params)}"
                try:
                    with urlopen_fn(Request(url, headers={"Accept": "application/json"}), timeout=30) as response:
                        data = json.load(response)
                except Exception:
                    # Request errors may include API credentials in their URL.
                    message = "Adzuna request failed. Check country, credentials, quota and connection."
                    if errors is None:
                        raise ValueError(message) from None
                    errors.append({"board": "Adzuna", "error": f"Query {role!r} ({place or 'any'}), page {page}: {message}"})
                    break
                results = data.get("results", [])
                jobs.extend(parse_listings(results, adzuna_listing, "Adzuna", errors))
                if len(results) < 50:
                    break
    return jobs

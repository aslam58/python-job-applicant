"""Search orchestration, status reporting, guided prompts, and CLI entry point."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable, Mapping
import webbrowser

from applicant.autofill import apply as run_apply, load_application_statuses
from applicant.http_client import get_json
from applicant.matching import effective_boards, india_search, matches, rank, read_resume
from applicant.models import (
    PROFILE,
    SOURCES,
    canonical_url,
    format_stored_resume_path,
    load_json,
    merge_defaults,
    resolve_resume_path,
    sanitize_csv_cell,
    save_json,
    validate_profile,
    validate_sources,
    validate_url,
)
from applicant.providers import (
    adzuna_jobs,
    collect_board_jobs,
    collect_public_jobs,
    fetch_smartrecruiters_details,
    parse_listings,
    write_search_page,
)

CSV_FIELDS: list[str] = [
    "company",
    "title",
    "location",
    "url",
    "status",
    "application_status",
    "source",
    "source_url",
    "resume_score",
    "matched_terms",
    "missing_terms",
]


def _deduplicate_listings(
    jobs: list[dict[str, Any]],
    failures: list[dict[str, str]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for job in jobs:
        try:
            key = canonical_url(validate_url(job.get("url")))
            job.setdefault("location", "")
            job.setdefault("description", "")
            for field in ("company", "title", "location", "description"):
                if not isinstance(job.get(field), str):
                    raise ValueError(f"Expected text for {field}")
        except ValueError as exc:
            failures.append({"board": job.get("source", "unknown"), "error": f"Skipped listing {job.get('title', '')!r}: {exc}"})
            continue
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def search(
    sources_path: str | Path | None,
    output_path: str | Path,
    *,
    settings: Mapping[str, Any] | None = None,
    resume: str | None = None,
    fetch: Callable[[str], Any] = get_json,
    profile_path: str | Path | None = None,
    hide_applied: bool = False,
) -> dict[str, Any]:
    raw_settings = load_json(sources_path) if settings is None else dict(settings)
    validated = validate_sources(raw_settings)
    # Preserve explicit minimal dicts (e.g. omitting public_sources in tests), while filling nested defaults.
    cfg: dict[str, Any] = dict(validated)
    failures: list[dict[str, str]] = []

    if india_search(cfg):
        print("India coverage enabled: public employer preset and India-targeted Himalayas queries.")

    jobs, page_reports = collect_public_jobs(cfg, failures, fetch=fetch)
    if cfg.get("adzuna", {}).get("enabled"):
        try:
            jobs.extend(adzuna_jobs(cfg, errors=failures))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            failures.append({"board": "Adzuna", "error": str(exc)})

    boards = effective_boards(cfg, errors=failures)
    jobs.extend(collect_board_jobs(boards, failures, fetch=fetch))

    def direct_listing(row: dict[str, Any]) -> dict[str, Any]:
        return {
            **row,
            "id": row.get("id", ""),
            "source": "direct",
            "status": "not_verified",
            "description": row.get("description", ""),
        }

    jobs.extend(parse_listings(cfg.get("direct_jobs", []), direct_listing, "direct", failures))
    unique = _deduplicate_listings(jobs, failures)

    title_settings = {**cfg, "location_keywords": [], "exclude_title_keywords": [], "description_keywords": []}
    title_matches = [job for job in unique if matches(job, title_settings)]
    location_settings = {**cfg, "exclude_title_keywords": [], "description_keywords": []}
    location_matches = [job for job in title_matches if matches(job, location_settings)]
    exclusion_settings = {**cfg, "description_keywords": []}
    exclusion_matches = [job for job in location_matches if matches(job, exclusion_settings)]

    fetch_smartrecruiters_details(exclusion_matches, failures, fetch=fetch)
    # Re-deduplicate in case SmartRecruiters detail applyUrl collided with another listing.
    deduped_after_detail: list[dict[str, Any]] = []
    seen_after_detail: set[str] = set()
    for job in exclusion_matches:
        key = canonical_url(job["url"])
        if key not in seen_after_detail:
            seen_after_detail.add(key)
            deduped_after_detail.append(job)

    if cfg.get("description_keywords"):
        selected = [job for job in deduped_after_detail if matches(job, cfg)]
    else:
        selected = deduped_after_detail

    log_base = Path(profile_path).resolve().parent if profile_path else Path(output_path).resolve().parent
    app_statuses = load_application_statuses(log_base / "application-log.json")
    hidden_count = 0
    filtered_selected: list[dict[str, Any]] = []
    for job in selected:
        app_status = app_statuses.get(canonical_url(job["url"]), "")
        if app_status:
            job["application_status"] = app_status
        if hide_applied and app_status in {"submitted_by_user", "skipped_by_user"}:
            hidden_count += 1
            continue
        filtered_selected.append(job)
    selected = filtered_selected

    diagnostics: dict[str, Any] = {
        "himalayas_pages": page_reports,
        "collected_unique": len(unique),
        "by_source": dict(Counter(job["source"] for job in unique)),
        "after_title_filter": len(title_matches),
        "after_location_filter": len(location_matches),
        "after_exclusions": len(deduped_after_detail),
        "after_description_filter": len(selected) + hidden_count,
        "hidden_already_processed": hidden_count,
        "filters": {
            key: cfg.get(key, [])
            for key in ("title_keywords", "location_keywords", "exclude_title_keywords", "description_keywords")
        },
    }

    if resume is not None:
        rank(selected, resume)

    links, search_page = write_search_page(cfg, output_path)
    payload = {
        "diagnostics": diagnostics,
        "board_searches": links,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "jobs": selected,
        "errors": failures,
    }
    save_json(output_path, payload)

    csv_path = Path(output_path).with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for job in selected:
            row = {
                "company": sanitize_csv_cell(job.get("company", "")),
                "title": sanitize_csv_cell(job.get("title", "")),
                "location": sanitize_csv_cell(job.get("location", "")),
                "url": sanitize_csv_cell(job.get("url", "")),
                "status": sanitize_csv_cell(job.get("status", "")),
                "application_status": sanitize_csv_cell(job.get("application_status", "")),
                "source": sanitize_csv_cell(job.get("source", "")),
                "source_url": sanitize_csv_cell(job.get("source_url", "")),
                "resume_score": job.get("resume_score", ""),
                "matched_terms": sanitize_csv_cell(", ".join(job.get("matched_terms", []))),
                "missing_terms": sanitize_csv_cell(", ".join(job.get("missing_terms", []))),
            }
            writer.writerow(row)

    for i, job in enumerate(selected, 1):
        status_tag = f" [{job['application_status']}]" if job.get("application_status") else ""
        print(f"{i:3}. {job['company']} | {job['title']} | {job.get('location', '')}{status_tag}")
        if resume is not None:
            print("     Resume overlap: " + (", ".join(job["matched_terms"]) or "no shared keywords"))
            if job.get("missing_terms"):
                print("     Missing terms:  " + ", ".join(job["missing_terms"]))
        if job.get("source_url"):
            print(f"     Source: {job['source_url']}")
    for failure in failures:
        print(f"Source issue: {failure['board']}: {failure['error']}", file=sys.stderr)
    print(f"Collected {len(unique)} unique listings from automatic sources.")
    for source, count in diagnostics["by_source"].items():
        print(f"  {source}: {count}")
    summary = (
        f"After title filter: {len(title_matches)}; after location filter: {len(location_matches)}; "
        f"after exclusions: {len(deduped_after_detail)}"
    )
    if cfg.get("description_keywords"):
        summary += f"; after description filter: {len(selected) + hidden_count}"
    if hidden_count:
        summary += f"; hidden applied/skipped: {hidden_count}"
    print(summary + ".")

    if not selected:
        if not unique:
            print("Automatic sources returned no usable listings. Check source errors and configuration.")
        elif not title_matches:
            print("No collected titles matched your title phrases. Try separate shorter phrases or spelling variants.")
        elif not location_matches:
            print("Titles matched, but none matched the listed location text. Check city/country wording.")
        elif not deduped_after_detail:
            print("All matching jobs were removed by your excluded title words.")
        elif hidden_count:
            print("All matching jobs were already submitted or skipped (hidden by --hide-applied).")
        else:
            print("No remaining jobs matched your description_keywords.")
        print("Coverage depends on enabled public feeds and employer boards.")
        print(
            "Major-board browser searches are separate from collected listings; zero collected matches "
            "does not mean those boards have no jobs."
        )
        if not boards:
            print("No employer boards are configured. Add relevant Greenhouse/Lever/Ashby boards for local openings.")
        if not cfg.get("adzuna", {}).get("enabled"):
            print("Adzuna collection is disabled; you can enable it with your own credentials.")
        print("Keep your required location. Add sources if current feeds do not cover it.")
    print(f"Major-board searches: {search_page.resolve()} (open this file in your browser).")
    print(f"Saved {len(selected)} matches to {output_path} and {csv_path}.")
    if not boards and not any(cfg.get(k) for k in ("direct_jobs", "public_sources")):
        print("Add employer boards or direct job URLs to sources.json first.")
    return payload


def show_status(args: Any) -> int:
    profile_path = Path(args.profile).resolve()
    log_path = profile_path.parent / "application-log.json"
    rows = load_json(log_path) if log_path.exists() else []
    if not isinstance(rows, list):
        raise ValueError("application-log.json must contain a JSON list.")

    counts = Counter(row.get("status", "unknown") for row in rows if isinstance(row, dict))
    print(f"Application log: {log_path}")
    if not rows:
        print("  No application sessions recorded yet.")
    else:
        print(f"  Total log entries: {len(rows)}")
        for status, count in sorted(counts.items()):
            print(f"  - {status}: {count}")
        print("\nRecent activity:")
        for row in rows[-10:]:
            label = " | ".join(x for x in (row.get("company"), row.get("title")) if x) or row.get("job_url", "")
            print(f"  [{row.get('status', 'unknown')}] {row.get('time', '')[:19]} — {label}")

    jobs_path = Path(args.jobs)
    if jobs_path.is_file():
        data = load_json(jobs_path)
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        statuses = load_application_statuses(log_path)
        remaining = [
            (idx, job)
            for idx, job in enumerate(jobs, 1)
            if statuses.get(canonical_url(job["url"])) not in {"submitted_by_user", "skipped_by_user"}
        ]
        print(f"\nSaved search ({jobs_path}): {len(jobs)} total, {len(remaining)} unapplied/remaining.")
        for idx, job in remaining[:10]:
            score = f" (score {job['resume_score']})" if "resume_score" in job else ""
            print(f"  {idx:3}. {job.get('company', '')} | {job.get('title', '')} | {job.get('location', '')}{score}")
    return 0


def ask_keywords(prompt: str, previous: list[str]) -> list[str]:
    hint = ", ".join(previous) or "any"
    answer = input(f"{prompt} [{hint}]: ").strip()
    if not answer:
        return previous
    if answer == "*":
        return []
    return list(dict.fromkeys(k.strip() for k in answer.split(",") if k.strip()))


def guided_search(
    args: Any,
    *,
    search_fn: Callable[..., dict[str, Any]] = search,
) -> int:
    sources_file = Path(args.sources)
    if sources_file.exists():
        settings = merge_defaults(validate_sources(load_json(sources_file)), SOURCES)
    else:
        settings = merge_defaults({}, SOURCES)

    profile_path = Path(args.profile).resolve()
    if profile_path.exists():
        profile = merge_defaults(validate_profile(load_json(profile_path)), PROFILE)
    else:
        profile = merge_defaults({}, PROFILE)

    if args.india:
        settings["india"] = {**settings.get("india", {}), "enabled": True}

    saved = profile.get("resume_file", "")
    if args.batch:
        path = args.resume or saved
    else:
        print("Enter comma-separated phrases. Enter keeps the displayed setting; * clears a filter.")
        for key, prompt in (
            ("title_keywords", "Which job titles or title keywords interest you?"),
            ("location_keywords", "Which locations or working arrangements (e.g. Remote)?"),
            ("exclude_title_keywords", "Which title words should be excluded?"),
        ):
            settings[key] = ask_keywords(prompt, settings.get(key, []))
        path = args.resume or input(f"Resume file (PDF, DOCX, TXT) [{saved or 'path required'}]: ").strip() or saved
    if not path:
        raise ValueError("A resume is required. Supply --resume or set resume_file in your profile.")

    resume_path = resolve_resume_path(path, profile_path.parent)
    resume_text = read_resume(resume_path)
    if not args.batch:
        profile["resume_file"] = format_stored_resume_path(path, resume_path, profile_path.parent)
        save_json(profile_path, profile)
        save_json(args.sources, settings)

    result = search_fn(
        args.sources,
        args.output,
        settings=settings,
        resume=resume_text,
        profile_path=profile_path,
        hide_applied=getattr(args, "hide_applied", False),
    )
    if args.open_searches:
        search_page = Path(args.output).with_suffix(".searches.html").resolve()
        if not webbrowser.open(search_page.as_uri()):
            print("Could not open a browser automatically. Double-click the .searches.html file.")
    elif not result["jobs"]:
        print("Open the .searches.html file, or rerun with --open-searches to open the search links page.")
    return 1 if result["errors"] and not result["jobs"] else 0


def init_directory(directory: str | Path) -> None:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    for name, data in (("profile.json", PROFILE), ("sources.json", SOURCES)):
        path = target / name
        if not path.exists():
            save_json(path, data)
        else:
            print(f"Preserved existing {name}.")
    print("Edit profile.json and sources.json, then run search or apply.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic job discovery, local resume matching, and assisted application filling. No AI services."
    )
    sub = parser.add_subparsers(dest="command")

    init_cmd = sub.add_parser("init", help="Create blank profile.json and sources.json")
    init_cmd.add_argument("--directory", default=".")

    find_cmd = sub.add_parser("search", help="Choose job preferences and find resume-ranked openings")
    find_cmd.add_argument("--sources", default="sources.json")
    find_cmd.add_argument("--output", default="jobs.json")
    find_cmd.add_argument("--profile", default="profile.json")
    find_cmd.add_argument("--resume", help="Resume file; relative paths use the profile folder")
    find_cmd.add_argument("--batch", action="store_true", help="Reuse saved settings without prompts")
    find_cmd.add_argument("--india", action="store_true", help="Include the India employer preset and India-targeted remote queries")
    find_cmd.add_argument("--open-searches", action="store_true", help="Open the generated major-board search links page")
    find_cmd.add_argument("--hide-applied", action="store_true", help="Exclude jobs already submitted or skipped in application-log.json")

    fill_cmd = sub.add_parser("apply", help="Open a job and interactively fill recognized application fields")
    fill_cmd.add_argument("--profile", default="profile.json")
    target = fill_cmd.add_mutually_exclusive_group(required=True)
    target.add_argument("--url")
    target.add_argument("--job", type=int)
    fill_cmd.add_argument("--jobs", default="jobs.json")
    fill_cmd.add_argument("--scope", help="CSS selector of the application form/container on custom sites")

    status_cmd = sub.add_parser("status", help="Show application history and remaining jobs from the latest search")
    status_cmd.add_argument("--profile", default="profile.json")
    status_cmd.add_argument("--jobs", default="jobs.json")

    return parser


def main(
    argv: list[str] | None = None,
    *,
    guided_search_fn: Callable[[Any], int] = guided_search,
    apply_fn: Callable[[Any], None] = run_apply,
    status_fn: Callable[[Any], int] = show_status,
) -> int:
    parser = build_parser()
    raw_args = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(raw_args or ["search"])
    try:
        if args.command == "init":
            init_directory(args.directory)
        elif args.command == "search":
            return guided_search_fn(args)
        elif args.command == "status":
            return status_fn(args)
        else:
            apply_fn(args)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except EOFError:
        print("Input ended. Use search --batch for a saved unattended search.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped. An interrupted session is not a confirmed submission.")
        return 130
    return 0

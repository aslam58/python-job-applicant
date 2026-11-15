#!/usr/bin/env python3
"""Deterministic job discovery and assisted application filling. No AI services."""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import webbrowser
from collections import Counter
from datetime import datetime, timezone

from resume_match import read_resume, rank
from board_search import BOARD_DOMAINS, adzuna_jobs, write_search_page
from india_sources import effective_boards, india_search, normalize_location
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


PROFILE = {
    "first_name": "", "last_name": "", "full_name": "", "email": "",
    "phone": "", "linkedin_url": "", "city": "", "country": "",
    "address_line_1": "", "postal_code": "", "resume_file": "",
    "questions": {},
}
SOURCES = {
    "title_keywords": [], "location_keywords": [], "exclude_title_keywords": [],
    "public_sources": ["arbeitnow", "himalayas"],
    "browser_boards": BOARD_DOMAINS,
    "adzuna": {"enabled": False, "country": "", "pages": 1},
    "india": {"enabled": False},
    "boards": [],
    "direct_jobs": [],
}


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


ALIASES = {
    "first_name": ["first name", "given name", "given names", "given name s", "legal first name"],
    "last_name": ["last name", "family name", "surname", "legal last name"],
    "full_name": ["full name", "full legal name", "name"],
    "email": ["email", "email address"],
    "phone": ["phone", "phone number", "mobile", "mobile number"],
    "linkedin_url": ["linkedin", "linkedin url", "linkedin profile"],
    "city": ["city", "current city", "current location"],
    "country": ["country", "country of residence"],
    "address_line_1": ["address line 1", "street address"],
    "postal_code": ["postal code", "zip postal code", "zip code", "pin code"],
}
BLOCKED_TYPES = {"password", "hidden", "submit", "button", "reset", "image", "checkbox", "radio"}
SENSITIVE = re.compile(r"\b(password|otp|captcha|passport|pan|aadhaar|ssn|birth|gender|religion|race|ethnic|disability|medical|signature|consent|terms|agree|privacy|nationality|citizenship|veteran)\b")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_url(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("Job URLs must be HTTPS and contain no embedded credentials.")
    return url


def canonical_url(url):
    p = urlsplit(url)
    tracking = {"source", "ref", "gh_src"}
    params = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
              if not k.lower().startswith("utm_") and k.lower() not in tracking]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), urlencode(params), ""))


def get_json(url):
    request = Request(url, headers={"User-Agent": "PersonalJobApplicant/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def plain_text(value):
    return html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(value or "")))


def fetch_board(board, fetch=get_json):
    """Read published jobs only; never use submission APIs or employer API keys."""
    kind, token = board["type"], board["token"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        raise ValueError("Invalid board token")
    company = board.get("company", token)
    if kind == "greenhouse":
        payload = fetch(f"https://boards-api.greenhouse.io/v1/boards/{quote(token)}/jobs?content=true")
        return [{"id": str(j["id"]), "company": company, "title": j["title"],
                 "location": j.get("location", {}).get("name", ""), "url": j["absolute_url"],
                 "description": plain_text(j.get("content", "")), "source": kind,
                 "status": "published_on_board"} for j in payload["jobs"]]
    if kind == "lever":
        region = board.get("region", "global")
        if region not in {"global", "eu"}:
            raise ValueError("Lever region must be global or eu")
        host = "api.eu.lever.co" if region == "eu" else "api.lever.co"
        jobs = fetch(f"https://{host}/v0/postings/{quote(token)}?mode=json")
        return [{"id": j["id"], "company": company, "title": j["text"],
                 "location": j.get("categories", {}).get("location", ""),
                 "url": j.get("applyUrl") or j["hostedUrl"],
                 "description": " ".join([j.get("descriptionPlain") or plain_text(j.get("description", "")),
                                          *(plain_text(item.get("content")) for item in j.get("lists", [])),
                                          j.get("additionalPlain") or ""]),
                 "source": kind, "status": "published_on_board"} for j in jobs]
    if kind == "smartrecruiters":
        jobs = []
        pages = int(board.get("pages", 10))
        if not 1 <= pages <= 20:
            raise ValueError("SmartRecruiters pages must be between 1 and 20")
        for page in range(pages):
            params = {"limit": 100, "offset": page * 100}
            if board.get("country"):
                params["country"] = board["country"]
            data = fetch(f"https://api.smartrecruiters.com/v1/companies/{quote(token)}/postings?" + urlencode(params))
            rows = data.get("content", [])
            for job in rows:
                if job.get("visibility", "PUBLIC") != "PUBLIC":
                    continue
                loc = job.get("location", {})
                location = loc.get("fullLocation") or ", ".join(
                    str(loc.get(k) or "") for k in ("city", "region", "country") if loc.get(k))
                if loc.get("country", "").casefold() == "in":
                    location += " | India"
                if loc.get("remote"):
                    location += " | Remote"
                jobs.append({"id": str(job["id"]), "title": job["name"], "company": company,
                             "location": location, "description": "", "source": kind,
                             "url": f"https://jobs.smartrecruiters.com/{quote(token)}/{quote(str(job['id']))}",
                             "detail_url": f"https://api.smartrecruiters.com/v1/companies/{quote(token)}/postings/{quote(str(job['id']))}",
                             "status": "published_on_board"})
            if len(rows) < 100 or (page + 1) * 100 >= data.get("totalFound", (page + 2) * 100):
                return jobs
        raise ValueError("SmartRecruiters page limit reached. Narrow the board country or increase pages (up to 20).")
    raise ValueError(f"Unsupported board type: {kind}; use direct_jobs for other platforms")


def contains_phrase(value, phrase):
    phrase = phrase.strip()
    return bool(phrase and re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", value, re.I))


def matches(job, settings):
    title, location = job["title"], job.get("location", "")
    # Common title spelling variants retain the applicant's chosen phrase.
    title = re.sub(r"full[ -]?stack", "full stack", title, flags=re.I)
    include = settings.get("title_keywords", [])
    places = settings.get("location_keywords", [])
    location = normalize_location(location)
    exclude = settings.get("exclude_title_keywords", [])
    return ((not include or any(contains_phrase(title, re.sub(r"full[ -]?stack", "full stack", k, flags=re.I)) for k in include))
            and (not places or any(contains_phrase(location, normalize_location(k)) for k in places))
            and not any(contains_phrase(title, k) for k in exclude))


def public_jobs(provider, role="", fetch=get_json, *, country="", page=1):
    if provider == "arbeitnow":
        data = fetch("https://www.arbeitnow.com/api/job-board-api")
        return [{"title": j["title"], "company": j["company_name"], "url": j["url"],
                 "location": j["location"] + (" | Remote" if j.get("remote") else ""),
                 "description": plain_text(j["description"]), "source": provider,
                 "status": "listed_on_feed"} for j in data["data"]]
    if provider != "himalayas":
        raise ValueError("Unknown public source: " + provider)
    params = {"q": role, "page": page}
    if country:
        params["country"] = country
    query = urlencode(params)
    data = fetch("https://himalayas.app/jobs/api/search?" + query)
    now = datetime.now(timezone.utc).timestamp()
    jobs = []
    for j in data["jobs"]:
        if j.get("expiryDate") and float(j["expiryDate"]) <= now:
            continue
        places = ", ".join(j.get("locationRestrictions") or ["Worldwide"])
        jobs.append({"title": j["title"], "company": j["companyName"],
                     "url": j["applicationLink"], "source_url": j["guid"],
                     "location": "Remote | " + places, "description": plain_text(j["description"]),
                     "source": provider, "status": "listed_on_feed"})
    return jobs


def search(sources_path, output_path, *, settings=None, resume=None):
    settings = load_json(sources_path) if settings is None else settings
    jobs, failures = [], []
    if india_search(settings):
        print("India coverage enabled: public employer preset and India-targeted Himalayas queries.")
    for provider in settings.get("public_sources", []):
        queries = (settings.get("title_keywords") or [""]) if provider == "himalayas" else [""]
        for query in queries:
            try:
                if provider == "himalayas" and india_search(settings):
                    jobs.extend(public_jobs(provider, query, country="IN"))
                else:
                    jobs.extend(public_jobs(provider, query))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                failures.append({"board": provider, "error": str(exc)})
                break
    if settings.get("adzuna", {}).get("enabled"):
        try:
            jobs.extend(adzuna_jobs(settings))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            failures.append({"board": "Adzuna", "error": str(exc)})
    for board in effective_boards(settings):
        try:
            jobs.extend(fetch_board(board))
        except Exception as exc:
            failures.append({"board": board.get("company", board.get("token", "")), "error": str(exc)})
    for direct in settings.get("direct_jobs", []):
        validate_url(direct["url"])
        jobs.append({**direct, "id": direct.get("id", ""), "source": "direct",
                     "status": "not_verified", "description": direct.get("description", "")})
    seen, unique = set(), []
    for job in jobs:
        validate_url(job["url"])
        key = canonical_url(job["url"])
        if key not in seen:
            seen.add(key)
            unique.append(job)
    title_settings = {**settings, "location_keywords": [], "exclude_title_keywords": []}
    title_matches = [job for job in unique if matches(job, title_settings)]
    location_settings = {**settings, "exclude_title_keywords": []}
    location_matches = [job for job in title_matches if matches(job, location_settings)]
    selected = [job for job in location_matches if matches(job, settings)]
    diagnostics = {
        "collected_unique": len(unique),
        "by_source": dict(Counter(job["source"] for job in unique)),
        "after_title_filter": len(title_matches),
        "after_location_filter": len(location_matches),
        "after_exclusions": len(selected),
        "filters": {key: settings.get(key, []) for key in
                    ("title_keywords", "location_keywords", "exclude_title_keywords")},
    }
    for job in selected:
        if job.get("detail_url"):
            try:
                detail = get_json(job["detail_url"])
                sections = detail.get("jobAd", {}).get("sections", {})
                job["description"] = " ".join(plain_text(section.get("text", ""))
                                              for section in sections.values() if isinstance(section, dict))
                if detail.get("applyUrl"):
                    job["url"] = validate_url(detail["applyUrl"])
            except (OSError, ValueError, KeyError, TypeError) as exc:
                failures.append({"board": job["company"], "error": "Job detail unavailable: " + str(exc)})
    if resume is not None:
        rank(selected, resume)
    links, search_page = write_search_page(settings, output_path)
    payload = {"diagnostics": diagnostics, "board_searches": links, "checked_at": datetime.now(timezone.utc).isoformat(), "jobs": selected, "errors": failures}
    save_json(output_path, payload)
    csv_path = Path(output_path).with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["company", "title", "location", "url", "status", "source", "source_url", "resume_score", "matched_terms"], extrasaction="ignore")
        writer.writeheader()
        for job in selected:
            writer.writerow({**job, "matched_terms": ", ".join(job.get("matched_terms", []))})
    for i, job in enumerate(selected, 1):
        print(f"{i:3}. {job['company']} | {job['title']} | {job.get('location', '')}")
        if resume is not None:
            print("     Resume overlap: " + (", ".join(job["matched_terms"]) or "no shared keywords"))
        if job.get("source_url"):
            print("     Source: " + job["source_url"])
    for failure in failures:
        print(f"Board failed: {failure['board']}: {failure['error']}", file=sys.stderr)
    print(f"Collected {len(unique)} unique listings from automatic sources.")
    for source, count in diagnostics["by_source"].items():
        print(f"  {source}: {count}")
    print(f"After title filter: {len(title_matches)}; after location filter: {len(location_matches)}; "
          f"after exclusions: {len(selected)}.")
    if not selected:
        if not unique:
            print("Automatic sources returned no usable listings. Check source errors and configuration.")
        elif not title_matches:
            print("No collected titles matched your title phrases. Try separate shorter phrases or spelling variants.")
        elif not location_matches:
            print("Titles matched, but none matched the listed location text. Check city/country wording.")
        else:
            print("All matching jobs were removed by your excluded title words.")
        print("Coverage depends on enabled public feeds and employer boards.")
        print("Major-board browser searches are separate from collected listings; zero collected matches "
              "does not mean those boards have no jobs.")
        if not effective_boards(settings):
            print("No employer boards are configured. Add relevant Greenhouse/Lever boards for local openings.")
        if not settings.get("adzuna", {}).get("enabled"):
            print("Adzuna collection is disabled; you can enable it with your own credentials.")
        print("Keep your required location. Add sources if current feeds do not cover it.")
    print(f"Major-board searches: {search_page.resolve()} (open this file in your browser).")
    print(f"Saved {len(selected)} matches to {output_path} and {csv_path}.")
    if not effective_boards(settings) and not any(settings.get(k) for k in ("direct_jobs", "public_sources")):
        print("Add employer boards or direct job URLs to sources.json first.")
    return payload


def profile_value(field, profile):
    """Conservative exact matching; unknown questions remain unanswered."""
    label = norm(field.get("label", ""))
    if field.get("type", "").lower() in BLOCKED_TYPES or field.get("role") == "combobox":
        return None
    if SENSITIVE.search(label):
        return None
    explicit = {norm(k): v for k, v in profile.get("questions", {}).items()}
    if label in explicit:
        value = explicit[label]
        return None if value is None or str(value).strip() == "" else str(value)
    for key, aliases in ALIASES.items():
        if label in aliases:
            value = profile.get(key)
            if key == "full_name" and not value:
                value = " ".join(str(profile.get(k) or "").strip() for k in ("first_name", "last_name")).strip()
            return str(value) if value is not None and str(value).strip() else None
    return None


FIELD_INFO = """el => {
  const by = (el.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean)
    .map(id => el.ownerDocument.getElementById(id)?.textContent || '').join(' ');
  const labels = Array.from(el.labels || []).map(label => {
    const copy = label.cloneNode(true);
    copy.querySelectorAll('input, textarea, select, button').forEach(control => control.remove());
    return copy.textContent || '';
  }).join(' ');
  return {label: el.getAttribute('aria-label') || labels || by || el.placeholder || '',
    name: el.name || '', id: el.id || '', type: el.type || '', role: el.getAttribute('role') || '',
    tag: el.tagName.toLowerCase(), value: el.value || '', required: el.required || el.getAttribute('aria-required') === 'true'};
}"""


def form_scopes(page, explicit_scope=None):
    """Only consider application forms with resume controls or an explicit user selector."""
    result = []
    for frame in page.frames:
        if explicit_scope:
            for root in frame.locator(explicit_scope).all():
                if root.is_visible():
                    result.append(root)
            continue
        for form in frame.locator("form").all():
            if not form.is_visible():
                continue
            uploads = form.locator('input[type="file"]').all()
            if any(is_resume_input(f.evaluate(FIELD_INFO)) for f in uploads):
                result.append(form)
        if result:
            continue
        host = (urlsplit(frame.url).hostname or "").lower()
        if any(host == d or host.endswith('.' + d) for d in
               ("greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com")):
            uploads = frame.locator('input[type="file"]').all()
            if any(is_resume_input(f.evaluate(FIELD_INFO)) for f in uploads):
                result.append(frame.locator("body"))
    return result


def is_resume_input(info):
    text = norm(" ".join(str(info.get(k, "")) for k in ("label", "name", "id")))
    return bool(re.search(r"\b(resume|cv)\b", text)) and not re.search(r"\b(cover|photo|picture)\b", text)


def autofill(page, profile, resume, scope=None):
    scopes = form_scopes(page, scope)
    if not scopes:
        print("No recognizable resume/application form. Open the application, then retry.")
        print("For a custom site, restart with --scope 'CSS SELECTOR' to target its form container.")
        return {"filled": 0, "uploaded": 0}
    if len(scopes) > 1:
        print("More than one candidate form is visible. Use --scope to choose the intended form.")
        return {"filled": 0, "uploaded": 0}
    root = scopes[0]
    filled, uploaded = 0, 0
    for locator in root.locator("input, textarea, select").all():
        try:
            info = locator.evaluate(FIELD_INFO)
            if info["type"] == "file":
                # Hidden native file inputs are normal. Never replace an existing attachment.
                if resume and is_resume_input(info) and not info["value"]:
                    locator.set_input_files(str(resume), timeout=5000)
                    uploaded += 1
                    print("Attached resume.")
                continue
            if not locator.is_visible() or not locator.is_enabled():
                continue
            if info["tag"] != "select" and not locator.is_editable():
                continue
            if info["value"]:  # Preserve manual answers, defaults and parsed information for review.
                continue
            value = profile_value(info, profile)
            if value is None:
                if info["required"] and info["type"] not in BLOCKED_TYPES:
                    print(f"Manual answer required: {info['label'] or info['name'] or '[unlabelled field]'}")
                continue
            if info["tag"] == "select":
                options = locator.locator("option").evaluate_all("es => es.map(e => ({label: e.label, value: e.value}))")
                exact = [o for o in options if norm(o["label"]) == norm(value)]
                if len(exact) == 1:
                    locator.select_option(value=exact[0]["value"])
                else:
                    print(f"Select manually: {info['label']}")
                    continue
            else:
                locator.fill(value, timeout=3000)
            filled += 1
            print(f"Filled: {info['label']}")  # Do not print the applicant's answer.
        except Exception as exc:
            # Exception strings can contain typed data or URLs; avoid logging their contents.
            print(f"A field needs manual attention ({type(exc).__name__}).")
    print(f"Filled {filled} fields; attached {uploaded} resume(s). Review all parsed fields and dates.")
    return {"filled": filled, "uploaded": uploaded}


def evidence(page):
    """A receipt signal, not an AI judgement. Scope excludes script/template text."""
    patterns = [r"your application (?:has been|was) (?:successfully )?submitted",
                r"application submitted", r"we.ve received your application",
                r"thank you for (?:applying|submitting your (?:application|cv))",
                r"you have successfully applied"]
    for frame in page.frames:
        try:
            body = frame.locator("body").inner_text(timeout=2500)
        except Exception:
            continue
        for pattern in patterns:
            match = re.search(pattern, body, re.I)
            if match:
                return match.group(0)
    return None


def log_result(path, url, status, receipt=None, screenshot=None):
    path = Path(path)
    rows = load_json(path) if path.exists() else []
    rows.append({"time": datetime.now(timezone.utc).isoformat(), "job_url": url,
                 "status": status, "receipt": receipt, "screenshot": screenshot})
    save_json(path, rows)


def apply(args):
    from playwright.sync_api import sync_playwright
    profile_path = Path(args.profile).resolve()
    profile = load_json(profile_path)
    url = args.url
    if not url:
        jobs = load_json(args.jobs)["jobs"]
        if not args.job or not 1 <= args.job <= len(jobs):
            raise ValueError("Choose --job using the 1-based number printed by search, or provide --url")
        url = jobs[args.job - 1]["url"]
    validate_url(url)
    log_path = profile_path.parent / "application-log.json"
    if log_path.exists():
        previous = load_json(log_path)
        if any(canonical_url(r["job_url"]) == canonical_url(url) and r["status"] in
               {"submitted_signal_detected", "submitted_by_user"} for r in previous):
            print("This URL already has a submitted entry in application-log.json. Not reopening it.")
            return
    resume = None
    if profile.get("resume_file"):
        resume = Path(profile["resume_file"]).expanduser()
        if not resume.is_absolute():
            resume = profile_path.parent / resume
        resume = resume.resolve()
        if not resume.is_file():
            raise ValueError("The configured resume_file does not exist")
    user_dir = profile_path.parent / ".browser-profile"
    print("Opening a dedicated local browser profile. Sign in in the browser when needed.")
    print("Navigate to the application form, then return here. No buttons are submitted automatically.")
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(str(user_dir), headless=False)
        context.set_default_timeout(5000)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            while True:
                print("\nTabs:")
                pages = [p for p in context.pages if not p.is_closed()]
                for i, tab in enumerate(pages, 1):
                    print(f"  {i}: {tab.title()} | {urlsplit(tab.url).hostname}")
                command = input("Enter: fill [tab number], verify [tab number], done, or quit: ").strip().split()
                if not command:
                    continue
                action = command[0].lower()
                if action in {"quit", "q"}:
                    log_result(log_path, url, "awaiting_manual_completion")
                    break
                if action == "done":
                    answer = input("Did you personally see the employer's submission receipt? Type yes or no: ").strip().lower()
                    if answer == "yes":
                        log_result(log_path, url, "submitted_by_user")
                        break
                    print("Use verify to detect a receipt, or quit to record an unfinished application.")
                    continue
                if action not in {"fill", "verify"}:
                    print("Unknown command.")
                    continue
                try:
                    index = int(command[1]) - 1 if len(command) > 1 else len(pages) - 1
                    if not 0 <= index < len(pages):
                        raise ValueError()
                except ValueError:
                    print("Choose a tab number from the list.")
                    continue
                page = pages[index]
                if action == "fill":
                    # Prevent accidental entry in unrelated pages opened during sign-in.
                    print(f"Target: {page.url}")
                    if input("Fill this application using your profile/resume? [y/N] ").strip().lower() == "y":
                        autofill(page, profile, resume, args.scope)
                        print("Complete remaining fields and click the employer's final Submit button yourself.")
                else:
                    receipt = evidence(page)
                    if receipt:
                        folder = profile_path.parent / "receipts"
                        folder.mkdir(exist_ok=True)
                        shot = folder / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".png")
                        page.screenshot(path=str(shot), full_page=False)
                        log_result(log_path, url, "submitted_signal_detected", receipt, str(shot))
                        print(f"Receipt text detected: {receipt}. Saved screenshot and log. Check remaining employer tasks.")
                        break
                    print("No known receipt text detected. Complete any remaining steps; do not assume success.")
        finally:
            context.close()


def ask_keywords(prompt, previous):
    hint = ", ".join(previous) or "any"
    answer = input(f"{prompt} [{hint}]: ").strip()
    if not answer:
        return previous
    if answer == "*":
        return []
    return list(dict.fromkeys(k.strip() for k in answer.split(",") if k.strip()))


def guided_search(args):
    settings = load_json(args.sources) if Path(args.sources).exists() else dict(SOURCES)
    profile_path = Path(args.profile).resolve()
    profile = load_json(profile_path) if profile_path.exists() else dict(PROFILE)
    if args.india:
        settings["india"] = {**settings.get("india", {}), "enabled": True}
    saved = profile.get("resume_file", "")
    if args.batch:
        path = args.resume or saved
    else:
        print("Enter comma-separated phrases. Enter keeps the displayed setting; * clears a filter.")
        for key, prompt in (("title_keywords", "Which job titles or title keywords interest you?"),
                            ("location_keywords", "Which locations or working arrangements (e.g. Remote)?"),
                            ("exclude_title_keywords", "Which title words should be excluded?")):
            settings[key] = ask_keywords(prompt, settings.get(key, []))
        path = args.resume or input(f"Resume file (PDF, DOCX, TXT) [{saved or 'path required'}]: ").strip() or saved
    if not path:
        raise ValueError("A resume is required. Supply --resume or set resume_file in your profile.")
    resume_path = profile_path.parent / Path(path.strip().strip('"')).expanduser()
    resume_text = read_resume(resume_path)
    if not args.batch:
        profile["resume_file"] = str(resume_path.resolve())
        save_json(profile_path, profile)
        save_json(args.sources, settings)
    result = search(args.sources, args.output, settings=settings, resume=resume_text)
    if args.open_searches:
        search_page = Path(args.output).with_suffix(".searches.html").resolve()
        if not webbrowser.open(search_page.as_uri()):
            print("Could not open a browser automatically. Double-click the .searches.html file.")
    elif not result["jobs"]:
        print("Open the .searches.html file, or rerun with --open-searches to open the search links page.")
    return 1 if result["errors"] and not result["jobs"] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")
    init = sub.add_parser("init", help="Create blank profile.json and sources.json")
    init.add_argument("--directory", default=".")
    find = sub.add_parser("search", help="Choose job preferences and find resume-ranked openings")
    find.add_argument("--sources", default="sources.json")
    find.add_argument("--output", default="jobs.json")
    find.add_argument("--profile", default="profile.json")
    find.add_argument("--resume", help="Resume file; relative paths use the profile folder")
    find.add_argument("--batch", action="store_true", help="Reuse saved settings without prompts")
    find.add_argument("--india", action="store_true", help="Include the India employer preset and India-targeted remote queries")
    find.add_argument("--open-searches", action="store_true", help="Open the generated major-board search links page")
    fill = sub.add_parser("apply", help="Open a job and interactively fill recognized application fields")
    fill.add_argument("--profile", default="profile.json")
    target = fill.add_mutually_exclusive_group(required=True)
    target.add_argument("--url")
    target.add_argument("--job", type=int)
    fill.add_argument("--jobs", default="jobs.json")
    fill.add_argument("--scope", help="CSS selector of the application form/container on custom sites")
    args = parser.parse_args(sys.argv[1:] or ["search"])
    try:
        if args.command == "init":
            directory = Path(args.directory)
            directory.mkdir(parents=True, exist_ok=True)
            for name, data in (("profile.json", PROFILE), ("sources.json", SOURCES)):
                path = directory / name
                if not path.exists():
                    save_json(path, data)
                else:
                    print(f"Preserved existing {name}.")
            print("Edit profile.json and sources.json, then run search or apply.")
        elif args.command == "search":
            return guided_search(args)
        else:
            apply(args)
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


if __name__ == "__main__":
    raise SystemExit(main())

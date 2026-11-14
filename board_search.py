"""Major-board search links and optional Adzuna collection, without AI."""
import html
import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Service addresses are configuration defaults, independent of applicant identity.
BOARD_DOMAINS = {
    "LinkedIn": "linkedin.com/jobs", "Indeed": "indeed.com",
    "Naukri": "naukri.com", "Foundit": "foundit.in",
    "Glassdoor": "glassdoor.com", "Shine": "shine.com",
    "TimesJobs": "timesjobs.com", "Instahyre": "instahyre.com",
    "Wellfound": "wellfound.com", "Cutshort": "cutshort.io",
    "ZipRecruiter": "ziprecruiter.com", "Dice": "dice.com",
    "Reed": "reed.co.uk", "Totaljobs": "totaljobs.com",
    "Greenhouse": "greenhouse.io", "Lever": "jobs.lever.co",
    "Workday": "myworkdayjobs.com", "Ashby": "jobs.ashbyhq.com",
    "SmartRecruiters": "jobs.smartrecruiters.com",
}


def search_links(settings):
    domains = settings.get("browser_boards", BOARD_DOMAINS)
    rows = []
    for name, domain in domains.items():
        if not re.fullmatch(r"[A-Za-z0-9./_-]+", domain):
            raise ValueError("Invalid board domain for " + name)
        for role in settings.get("title_keywords") or ["jobs"]:
            for place in settings.get("location_keywords") or [""]:
                query = " ".join(x for x in ("site:" + domain, role, place) if x)
                rows.append({"board": name, "role": role, "location": place,
                             "url": "https://www.google.com/search?" + urlencode({"q": query})})
    return rows


def write_search_page(settings, output):
    links = search_links(settings)
    output = Path(output).with_suffix(".searches.html")
    rows = []
    for link in links:
        label = " | ".join(x for x in (link["board"], link["role"], link["location"]) if x)
        rows.append('<li><a target="_blank" rel="noopener" href="' +
                    html.escape(link["url"], quote=True) + '">' + html.escape(label) + '</a></li>')
    output.write_text('<!doctype html><html lang="en"><meta charset="utf-8">'
                      '<title>Job board searches</title><body><h1>Search job boards</h1>'
                      '<p>Open a search below. These are indexed web searches. Check the employer page '
                      'for current availability. These links are separate from the collected and '
                      'resume-ranked jobs in the JSON/CSV files.</p><ul>' +
                      "".join(rows) + '</ul></body></html>', encoding="utf-8")
    return links, output


def adzuna_jobs(settings):
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
    jobs = []
    for role in settings.get("title_keywords") or [""]:
        for place in settings.get("location_keywords") or [""]:
            for page in range(1, pages + 1):
                params = urlencode({"app_id": app_id, "app_key": key, "what": role,
                                    "where": place, "results_per_page": 50})
                url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}?{params}"
                try:
                    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=30) as response:
                        data = json.load(response)
                except Exception:
                    # Request errors may include API credentials in their URL.
                    raise ValueError("Adzuna request failed. Check country, credentials, quota and connection.") from None
                results = data.get("results", [])
                for row in results:
                    jobs.append({"title": row["title"], "company": row.get("company", {}).get("display_name", ""),
                                 "location": row.get("location", {}).get("display_name", ""),
                                 "url": row["redirect_url"], "description": row.get("description", ""),
                                 "source": "Adzuna", "source_url": "https://www.adzuna.com",
                                 "status": "listed_on_feed"})
                if len(results) < 50:
                    break
    return jobs

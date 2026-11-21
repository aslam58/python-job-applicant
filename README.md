# Python Job Applicant

Find jobs using your preferences, compare listings with your résumé, and fill common application fields in a browser. Runs locally with Python. No AI service is required.

## Start here

1. Clone this repository (or download the ZIP from GitHub and extract it).
2. Open the folder in VS Code or a terminal.
3. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/).
4. Follow the installation commands for your operating system below.
5. Run `init` (or start directly with `search`), enter your preferences and résumé path, and review the results.

Keep the package files together when copying or running from an extracted folder:

```text
python-job-applicant/
├── applicant/
│   ├── autofill.py
│   ├── cli.py
│   ├── http_client.py
│   ├── matching.py
│   ├── models.py
│   └── providers.py
├── job_applicant.py
├── board_search.py
├── india_sources.py
├── resume_match.py
├── profile.example.json
├── sources.example.json
├── pyproject.toml
├── requirements.txt
└── tests/
```

## Install

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m playwright install chromium
job-applicant init
job-applicant
```

### Windows (Command Prompt)

```bat
py -m venv .venv
.venv\Scripts\activate
python -m pip install -e .
python -m playwright install chromium
job-applicant init
job-applicant
```

You can also install directly from `requirements.txt` and invoke `python job_applicant.py` instead of `job-applicant`. On Linux systems missing browser libraries, Playwright may prompt you to install OS dependencies.

## Step 1 — Enter your search preferences

Running `job-applicant` (or `python job_applicant.py search`) asks four questions:

| Prompt | What to enter |
| --- | --- |
| Job titles or keywords | Comma-separated titles, such as `backend engineer, python developer` |
| Locations or working arrangements | City names, country names, `Remote` or `Worldwide` |
| Title words to exclude | Optional words such as `director` or `manager` |
| Résumé file | Path to your own PDF, DOCX, or UTF-8 TXT file |

Press Enter to keep the displayed setting. Enter `*` to clear a preference filter.

* A first-time blank location matches any listed location.
* Use a text-based PDF (not an image-only scan), DOCX, or UTF-8 TXT file. Relative résumé paths are stored portably when inside the `profile.json` folder.
* Preferences are saved in your local, git-ignored `sources.json` and the résumé path in `profile.json` (see `profile.example.json` and `sources.example.json` for full templates).

## Step 2 — Review the results

Each search creates three files next to `--output`:

| File | How to use it |
| --- | --- |
| `jobs.csv` | Open in Excel or another spreadsheet app (CSV cells are formula-injection sanitized) |
| `jobs.json` | Numbered jobs, diagnostics, and source errors used by `apply` and `status` |
| `jobs.searches.html` | Double-click (or pass `--open-searches`) to open searches across major job boards |

Collected jobs are ranked locally against your résumé using rarity-weighted word/bigram overlap (with title hits weighted twice). Each job reports both `matched_terms` and top `missing_terms` so you can quickly spot skill gaps. Only search preferences are sent to job providers; your résumé stays local.

### Automatic sources & coverage

| Source | Automatic collection | Setup and coverage |
| --- | --- | --- |
| Arbeitnow | Yes | Enabled by default. Configurable `arbeitnow_pages` (1–10, default 1), mainly Europe |
| Himalayas | Yes | Enabled by default. Up to `himalayas_pages` (1–10, default 3) pages per title phrase, remote jobs |
| India employer preset | Yes | Enabled automatically for recognized Indian cities/locations (including compound wording like `Bangalore, India`), or with `--india` |
| SmartRecruiters | Yes | Public postings, paginated by employer and optional country, with concurrent detail fetching |
| Greenhouse | Yes | Add each employer's board token |
| Lever | Yes | Add each employer's board token (`global` or `eu` region) |
| Ashby | Yes | Add each employer's public board token (`type: "ashby"`) |
| Adzuna | Optional | Requires your own `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` and a supported two-letter country code |
| Major-board search links | Browser review | Google `site:` search links for LinkedIn, Indeed, Naukri, Foundit, Glassdoor, Shine, TimesJobs, Instahyre, Wellfound, Cutshort, ZipRecruiter, Dice, Reed, Totaljobs, Greenhouse, Lever, Workday, Ashby, and SmartRecruiters |

### Useful search flags

```bash
# Repeat saved search without prompts
job-applicant search --batch

# Open the generated major-board search links page automatically
job-applicant search --batch --open-searches

# Hide jobs already recorded as submitted or skipped in application-log.json
job-applicant search --batch --hide-applied

# Force the India employer preset and India-targeted Himalayas queries
job-applicant search --batch --india --open-searches
```

### Filtering behavior & zero-result diagnostics

Title and optional `description_keywords` filters normalize common spelling variants (`full-stack`/`fullstack`, `front-end`/`frontend`, `back-end`/`backend`, `dev-ops`/`devops`, `e-commerce`, `micro-services`).

After each search, the terminal and `diagnostics` in `jobs.json` report unique counts per source and how many listings survive each filter stage (`after_title_filter`, `after_location_filter`, `after_exclusions`, `after_description_filter`, and `hidden_already_processed`). Invalid provider rows or failed pages are recorded under `errors` without discarding valid sibling listings.

## Step 3 — Enter your contact details

Run `job-applicant init` (or copy `profile.example.json` to `profile.json`) and fill in your confirmed details:

```json
{
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
  "questions": {}
}
```

You may add exact question-label-to-answer pairs under `questions` for answers you have personally confirmed. Sensitive fields (passwords, OTP, CAPTCHA, IDs, demographics, legal consents) are never autofilled.

## Step 4 — Fill and track an application

Choose a result by its 1-based number from `jobs.json` (editing `jobs.csv` does not change numbering), or pass an HTTPS application URL directly:

```bash
job-applicant apply --job 1
job-applicant apply --url "https://employer.example/actual-job-url"
```

A dedicated local Chromium profile opens so you can sign in, solve any security verification, and navigate to the application form. Return to the terminal and use the interactive commands:

| Command | Result |
| --- | --- |
| `check [N]` | Check whether tab `N` (including iframes) is showing security verification |
| `preview [N]` | Dry-run inspection showing which fields will be filled and which required fields need manual input |
| `fill [N]` | Fill recognized empty fields and attach your résumé in tab `N` (supports multi-step ATS forms) |
| `scope <selector>` | Set a custom CSS container selector at runtime without restarting the browser (`scope clear` resets) |
| `open` | Navigate the active tab to a direct HTTPS employer URL (invalid URLs or timeouts keep the session open) |
| `verify [N]` | Check tab `N` for submission receipt text, confirm with `yes`, save screenshot, and log submission |
| `done` | Record a submission receipt you personally observed after confirming `yes` |
| `skip` | Record the job as skipped and close the session |
| `quit` | Record the application as unfinished and close the session |

You handle login, CAPTCHA, OTP, consent, custom questions, and the final Submit button yourself. Logs are saved in `application-log.json` (with company, title, and actual applied URL) and screenshots in `receipts/`.

### Check application status

View a summary of all logged applications and unapplied jobs remaining from your latest search:

```bash
job-applicant status
```

## Add employer boards, description keywords, and direct jobs

Edit your local `sources.json`:

```json
{
  "description_keywords": ["python", "postgresql"],
  "boards": [
    {"type": "greenhouse", "token": "BOARD_TOKEN", "company": "Employer name"},
    {"type": "lever", "token": "BOARD_TOKEN", "company": "Employer name", "region": "global"},
    {"type": "ashby", "token": "BOARD_TOKEN", "company": "Employer name"},
    {"type": "smartrecruiters", "token": "BOARD_TOKEN", "company": "Employer name", "country": "in"}
  ],
  "direct_jobs": [
    {
      "company": "Employer name",
      "title": "Actual job title",
      "location": "Listed location",
      "url": "https://employer.example/actual-job-url",
      "description": "Paste the actual job description here."
    }
  ]
}
```

## India job coverage

Searches containing a recognized Indian city or `India` (including compound phrases like `"Bangalore, India"` or `"Hyderabad, Telangana"`) enable a public-employer preset automatically without an API key: Freshworks, Bosch Group, and Sopra Steria (SmartRecruiters, filtered to India), plus CRED and Smart Working Solutions (Lever), and India-targeted Himalayas queries (`country=IN`).

Location filters normalize Indian city aliases (`Bangalore`/`Bengaluru`, `Gurgaon`/`Gurugram`, `Vizag`/`Visakhapatnam`, `Bombay`/`Mumbai`, `Madras`/`Chennai`, `Calcutta`/`Kolkata`, `Cochin`/`Kochi`, `Trivandrum`/`Thiruvananthapuram`, `Pondicherry`/`Puducherry`).

Customize or disable the preset via `india.boards` in `sources.json`:

```json
"india": {
  "enabled": true,
  "boards": [
    {"type": "smartrecruiters", "token": "Freshworks", "company": "Freshworks", "country": "in"}
  ]
}
```

## Optional Adzuna setup

Register at [Adzuna Developer](https://developer.adzuna.com/overview), enable it in `sources.json` (`"adzuna": {"enabled": true, "country": "in", "pages": 1}`), and export credentials in your shell:

```bash
export ADZUNA_APP_ID="your-app-id"
export ADZUNA_APP_KEY="your-app-key"
job-applicant search --batch
```

## Privacy and separate applicants

`profile.json`, `sources.json`, `jobs.json`, `jobs.csv`, `*.searches.html`, `application-log.json`, `receipts/`, `.browser-profile/`, `users/`, and common résumé formats are listed in `.gitignore` and kept untracked.

For multiple applicants, initialize separate directories:

```bash
job-applicant init --directory users/applicant
job-applicant search --profile users/applicant/profile.json --sources users/applicant/sources.json --output users/applicant/jobs.json
job-applicant apply --profile users/applicant/profile.json --jobs users/applicant/jobs.json --job 1
job-applicant status --profile users/applicant/profile.json --jobs users/applicant/jobs.json
```

## Development and verification

Run the offline test suite:

```bash
python -m unittest discover -s tests -v
```

Run the opt-in Chromium form regression tests after installing Chromium:

```bash
RUN_BROWSER_TESTS=1 python -m unittest discover -s tests -v
```

Lint with Ruff (after `pip install -e ".[dev]"`):

```bash
ruff check applicant job_applicant.py board_search.py india_sources.py resume_match.py tests
```

## License

MIT — see [LICENSE](LICENSE).

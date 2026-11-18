# Python Job Applicant

Find jobs using your preferences, compare listings with your résumé, and fill common application fields in a browser. Runs on your computer with Python. No AI service is required.

## Start here

1. Download this repository using **Code → Download ZIP** on GitHub, then extract the ZIP.
2. Open the extracted folder in VS Code or a terminal.
3. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/).
4. Follow the installation commands for your operating system below.
5. Run the tool, enter your preferences and résumé path, and review the results.

Keep these files together. Opening or copying only job_applicant.py will cause import errors.

```text
python-job-applicant/
├── job_applicant.py
├── board_search.py
├── india_sources.py
├── resume_match.py
├── requirements.txt
└── tests/
```

## Install on Windows

Open **Command Prompt** in the extracted folder. You can open the folder in File Explorer, type cmd in its address bar, and press Enter.

```bat
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m playwright install chromium
python job_applicant.py
```

If py is unavailable, try python. If neither command works, reinstall Python and enable its PATH option.

## Install on macOS or Linux

Open Terminal in the extracted folder and run these commands in order.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
python job_applicant.py
```

On a Linux system missing browser libraries, Playwright may ask you to install operating-system dependencies.

For later sessions, open the same folder, activate .venv again, and run python job_applicant.py.

## Step 1 — Enter your search preferences

The program asks four questions.

| Prompt | What to enter |
| --- | --- |
| Job titles or keywords | Comma-separated titles, such as laboratory technician, research assistant |
| Locations or working arrangements | City names, country names, Remote or Worldwide |
| Title words to exclude | Optional words such as director or manager |
| Résumé file | The path to your own PDF, DOCX or UTF-8 TXT file |

Press Enter to keep the displayed setting. Enter a single * to clear a preference filter.

A first-time blank location means any listed location. Locations match the posting's wording. Add city names when a posting may omit the country. Remote positions can still have country or time-zone restrictions.

Use a text-based PDF. For an image-only scan, provide a searchable PDF or a text copy. Relative résumé paths start in the folder containing profile.json. You can enter an absolute path when the résumé is elsewhere.

The tool saves your preferences in sources.json and the résumé path in profile.json.

## Step 2 — Review the results

The search creates three files next to the selected output path.

| File | How to use it |
| --- | --- |
| jobs.csv | Open in Excel or another spreadsheet app to review collected jobs |
| jobs.json | Contains the numbered jobs used by the apply command |
| jobs.searches.html | Double-click to open searches across major job boards |

Collected jobs are ordered by words shared with your résumé. Each result shows matching words. Title matches receive extra weight. The score measures keyword overlap within that search. Check the actual requirements, experience, eligibility and posting availability yourself.

The résumé is read locally for ranking. Only search preferences are used for online job queries.

### What each source provides

| Source | Automatic collection | Setup and coverage |
| --- | --- | --- |
| Arbeitnow | Yes | Enabled by default. First feed page, mainly Europe |
| Himalayas | Yes | Enabled by default. First page per title phrase, remote jobs |
| India employer preset | Yes | Enabled automatically for recognized Indian locations, or with --india |
| SmartRecruiters | Yes | Public postings, paginated by employer and optional country |
| Greenhouse | Yes | Add each employer's board token |
| Lever | Yes | Add each employer's board token |
| Adzuna | Optional | Your API credentials and supported country required |
| Major-board search links | Browser review | Searches indexed pages using Google site searches |

Browser search links cover LinkedIn, Indeed, Naukri, Foundit, Glassdoor, Shine, TimesJobs, Instahyre, Wellfound, Cutshort, ZipRecruiter, Dice, Reed, Totaljobs, Greenhouse, Lever, Workday, Ashby and SmartRecruiters.

Those links open searches for each role/location combination. Their pages need browser review. Collected JSON/CSV records and résumé scores cover the automatic sources and any direct jobs you supply. Indexed pages can be missing or outdated.

To repeat a saved search without prompts, run the following.

```bash
python job_applicant.py search --batch
```

## Step 3 — Enter your contact details

Open profile.json in a text editor and fill in your own details. Keep the quotation marks and commas valid. This is the full supported structure.

```json
{
  "first_name": "",
  "last_name": "",
  "full_name": "",
  "email": "",
  "phone": "",
  "linkedin_url": "",
  "city": "",
  "country": "",
  "address_line_1": "",
  "postal_code": "",
  "resume_file": "",
  "questions": {}
}
```

Keep the résumé path saved by your search. On Windows, JSON paths need forward slashes or doubled backslashes. A filename such as resume.pdf works when that file is beside profile.json.

The tool reads contact details from this file. It does not extract them from the résumé. You may add exact question-label-to-answer pairs under questions for answers you have personally confirmed. Unknown questions need manual answers.

## Step 4 — Fill an application

Choose a result by its number from the latest search.

```bash
python job_applicant.py apply --job 1
```

For an opening found elsewhere, use its actual HTTPS application URL.

```bash
python job_applicant.py apply --url "https://employer.example/actual-job-url"
```

A browser opens. Navigate to the application, sign in if required, and reach its form. Return to the terminal and check the displayed tab numbers.

```text
fill 2
```

Replace 2 with the number of the application tab. Confirm the target URL when asked. The tool fills recognized empty contact fields and attaches the selected résumé. Review existing fields, including anything the employer parsed incorrectly. Complete employment history and other questions yourself.

For a multi-page application, click Next in the browser and use fill again where appropriate. You handle login, CAPTCHA, OTP, consent, personal questions and the final Submit button.

After you personally submit the application, return to the terminal.

```text
verify 2
```

When verify finds possible receipt text, it shows the application, tab URL, and matched phrase. Answer yes only if you personally see a receipt for this job. Confirming saves a screenshot and records the submission. Any other answer returns you to the open session.

| Command | Result |
| --- | --- |
| check N | Check whether tab N is showing security verification |
| open | Navigate the last listed tab to an employer application URL you provide |
| skip | Record the job as skipped and close this session |
| fill N | Fill supported fields in tab N |
| verify N | Look for known submission receipt text in tab N |
| done | Record a receipt you personally observed after answering yes |
| quit | Record the application as unfinished and close the session |

The log is saved in application-log.json and screenshots in receipts/. URLs you personally confirmed as submitted are skipped. Older entries marked submitted_signal_detected display a reminder and allow reopening. Different URLs for the same job can still need a manual duplicate check.

## Add employer boards and direct jobs

Edit sources.json. Keep existing fields and replace the empty boards array with entries for actual employers.

```json
"boards": [
  {"type": "greenhouse", "token": "BOARD_TOKEN", "company": "Employer name"},
  {"type": "lever", "token": "BOARD_TOKEN", "company": "Employer name", "region": "global"}
]
```

These are fields inside the existing JSON object. Replace the placeholder tokens before running. A token is the employer segment in its Greenhouse or Lever board URL. For EU Lever boards, set region to eu.

For another platform, add an actual opening to direct_jobs.

```json
"direct_jobs": [
  {
    "company": "Employer name",
    "title": "Actual job title",
    "location": "Listed location",
    "url": "https://employer.example/actual-job-url",
    "description": "Paste the actual job description here."
  }
]
```

A description allows résumé comparison. Direct jobs remain labelled unverified.

Remove a provider from public_sources to disable it. Edit browser_boards to change the catalog of domains used for browser search links.

## Optional Adzuna setup

Register for your own credentials at [Adzuna Developer](https://developer.adzuna.com/overview). Check its supported countries, quotas and usage terms.

Set enabled to true in the existing adzuna object in sources.json. Use your preferred supported two-letter country code. For example, in selects India.

```json
"adzuna": {"enabled": true, "country": "in", "pages": 1}
```

Set credentials in the terminal before starting the program. Replace the example strings with your own values.

macOS or Linux

```bash
export ADZUNA_APP_ID="your-app-id"
export ADZUNA_APP_KEY="your-app-key"
python job_applicant.py
```

Windows Command Prompt

```bat
set ADZUNA_APP_ID=your-app-id
set ADZUNA_APP_KEY=your-app-key
python job_applicant.py
```

The page count applies to each role/location combination. Adzuna records enter the same filtering and ranking process. Coverage depends on its inventory. The integration requires verification with your valid credentials.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Import board_search or resume_match could not be resolved | Extract the complete ZIP and open the folder containing all Python files. Reload the editor if only its warning remains |
| No module named playwright or pypdf | Activate .venv and run python -m pip install -r requirements.txt |
| Playwright browser executable missing | Run python -m playwright install chromium in the active environment |
| Résumé not found | Check the file path. Use an absolute path or put the résumé beside profile.json |
| No readable résumé text | Supply a text-based PDF, DOCX or TXT |
| No results | Read the collected, title, location and exclusion counts. Open jobs.searches.html for major-board searches. Add sources that cover your required location |
| A source failed | Check the reported source and connection. Results from other sources can still be available |
| No recognizable application form | Open the actual form first. Some custom sites require manual filling |
| JSON error | Check commas, double quotes and path escaping. Avoid trailing commas |
| Sensitive or custom fields remain blank | Complete them in the browser |
| No receipt detected | Inspect the employer page. Use done only after personally seeing its submission receipt |

Advanced users can target a custom application container with --scope and an actual CSS selector.

```bash
python job_applicant.py apply --url "https://employer.example/actual-job-url" --scope "form#application"
```

## Privacy and sharing

Your populated profile, résumé, browser session, application log and screenshots contain private information. Keep them out of public repositories. Search queries go to the selected providers. Profile information and the résumé reach an employer when you choose fill, potentially before final submission.

The included .gitignore excludes common local data, environments and résumé formats. Check every file before publishing your own copy, especially TXT résumés and custom filenames. Share the original clean download.

## Development and verification

Run the offline checks from the project folder after installing dependencies.

```bash
python -m unittest discover -s tests -v
```

Tests cover feed parsing, filtering, résumé extraction and ranking, URL handling, search-page escaping, credential-error redaction and application field rules. Live employer form compatibility varies. Automatic collection from every job board and autonomous application submission are outside the current implementation.

## References

- [Playwright Python](https://playwright.dev/python/docs/input)
- [pypdf text extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
- [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html)
- [Lever Postings API](https://github.com/lever/postings-api)
- [Himalayas API](https://himalayas.app/api)
- [Arbeitnow API](https://www.arbeitnow.com/blog/job-board-api)
- [Adzuna API](https://developer.adzuna.com/overview)

## If the search saves zero matches

The terminal now reports how many unique jobs were collected from each automatic source
and how many remain after title, location and exclusion filters. Invalid listings are skipped individually and recorded under errors. The same information
is saved under diagnostics in jobs.json.

Himalayas searches up to three pages per title phrase by default. Set the integer
`himalayas_pages` in sources.json from 1 to 10 to change the limit. The terminal and
`diagnostics.himalayas_pages` show how many pages were read for each query and whether
a full last page reached the configured limit.

- Zero collected listings means the sources returned no usable records. Check reported errors.
- Zero after title filtering means none of the fetched titles matched your phrases.
- Zero after location filtering means matching titles had different location wording.
- Zero after exclusions means the excluded title words removed every remaining match.

Arbeitnow and Himalayas provide a limited sample of mainly European and remote jobs.
India searches also include the employer preset described below. Other local coverage
depends on configured employer boards and optional Adzuna.
Keep your required location and add relevant sources. Résumé ranking orders collected
matches; it does not remove them for low overlap.

To open the major-board search links page automatically after searching, run:

```bash
python job_applicant.py search --open-searches
```

To reuse saved preferences and résumé:

```bash
python job_applicant.py search --batch --open-searches
```

This opens one local page containing the search links. Choose a board link to review its
indexed results. The links page can still be useful when the collected CSV has no rows.

## India job coverage

India collection now works without an API key. Searches containing a recognized Indian
city or India enable a public-employer preset automatically. Existing sources.json files
also receive this behavior when the code is updated.

The preset currently includes Freshworks, Bosch Group and Sopra Steria through
SmartRecruiters, plus CRED and Smart Working Solutions through Lever. Each employer's
public postings are fetched live, with the first three boards filtered to India.
These five boards provide a starting catalog. They cover only those employers' published
inventory and do not guarantee an opening for every skill or city.

To force the preset on, including for a location the recognizer does not know, run:

```bash
python job_applicant.py search --india --open-searches
```

To reuse existing preferences and résumé:

```bash
python job_applicant.py search --batch --india --open-searches
```

Interactive runs save the explicit --india setting. Batch runs use it for that run only.
The preset adds to the boards you configured, and duplicate board entries are removed.

Location filters recognize Bangalore/Bengaluru, Gurgaon/Gurugram,
Vizag/Visakhapatnam, Bombay/Mumbai, Madras/Chennai, Calcutta/Kolkata,
Cochin/Kochi, Trivandrum/Thiruvananthapuram and Pondicherry/Puducherry.
Full-stack, fullstack and full stack spellings match the same title phrase.

Indian locations also make Himalayas query country=IN before local filtering.
City filters still require that city in the posting. To include remote jobs labelled
India or Worldwide, explicitly add Remote to location_keywords and review eligibility.

SmartRecruiters board listings include location and title. Descriptions are fetched
for selected matching jobs before résumé ranking. The default is up to 10 pages of
100 records per configured SmartRecruiters board. A board reaching the cap reports
a warning and keeps the listings already collected. You can configure pages up to 20.

To customize the India employer catalog, set india.boards to your own board array in
sources.json. An empty array disables the preset boards while keeping your other sources.
For example, this configuration selects one employer:

```json
"india": {
  "enabled": true,
  "boards": [
    {"type": "smartrecruiters", "token": "Freshworks", "company": "Freshworks", "country": "in"}
  ]
}
```

The country field filters this SmartRecruiters board. Existing title, location and
exclusion preferences remain in effect. No job preferences or applicant details
have been filled in for you.

Sources and API references
- https://developers.smartrecruiters.com/docs/posting-api
- https://careers.smartrecruiters.com/Freshworks
- https://jobs.lever.co/cred
- https://jobs.lever.co/smart-working-solutions
- https://himalayas.app/api


### Optional browser regression check

After installing Chromium, set RUN_BROWSER_TESTS=1 and run the same test command to
include a controlled local browser form check. On macOS/Linux:

```bash
RUN_BROWSER_TESTS=1 python -m unittest discover -s tests -v
```

On Windows Command Prompt:

```bat
set RUN_BROWSER_TESTS=1
python -m unittest discover -s tests -v
```

This verifies native dropdown labels, existing-value preservation and a synthetic
résumé upload on a local test form.


## Security verification and navigation timeouts

The application browser uses a separate local profile. A job board may display a
security verification page before showing the listing. Complete any verification
in the browser, then enter `check N` in the terminal using the displayed tab number.
If the page remains blocked, enter `open` and paste the employer's direct HTTPS
application URL, or enter `skip` and run the apply command for another result.
A navigation timeout returns control to the terminal after 30 seconds.
Recognized verification pages are recorded as `needs_manual_verification` and
are checked before filling fields. Other loading errors may still require manual review.

`--job 1` selects the first entry in `jobs.json`. Editing or sorting `jobs.csv`
does not change that numbering. The selected company and title are printed before
opening the browser.

## Separate applicants and private files

Each applicant should keep their profile, sources, job results, browser session,
logs and receipts in a separate directory. For example, from the repository folder:

```bash
python job_applicant.py init --directory users/applicant
python job_applicant.py search --profile users/applicant/profile.json --sources users/applicant/sources.json --output users/applicant/jobs.json
python job_applicant.py apply --profile users/applicant/profile.json --jobs users/applicant/jobs.json --job 1
```

Each applicant enters their own resume path and confirmed contact information.
Role and location preferences are configurable. No applicant details are required
in source code. Keep local profiles, resumes, generated results, screenshots and
credentials out of commits and shared ZIP files. The `users/` directory is ignored.
The init command and interactive search generate profile.json and sources.json locally.

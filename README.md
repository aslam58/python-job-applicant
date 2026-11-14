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
├── resume_match.py
├── requirements.txt
├── profile.json
├── sources.json
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

A recognized receipt message produces a screenshot and a log entry. Check for any remaining screening tasks. Receipt matching can miss unfamiliar wording or match misleading text.

| Command | Result |
| --- | --- |
| fill N | Fill supported fields in tab N |
| verify N | Look for known submission receipt text in tab N |
| done | Record a receipt you personally observed after answering yes |
| quit | Record the application as unfinished and close the session |

The log is saved in application-log.json and screenshots in receipts/. Submitted URLs already in the log are skipped. Different URLs for the same job can still need a manual duplicate check.

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
| Import board_search or resume_match could not be resolved | Extract the complete ZIP and open the folder containing all three Python files. Reload the editor if only its warning remains |
| No module named playwright or pypdf | Activate .venv and run python -m pip install -r requirements.txt |
| Playwright browser executable missing | Run python -m playwright install chromium in the active environment |
| Résumé not found | Check the file path. Use an absolute path or put the résumé beside profile.json |
| No readable résumé text | Supply a text-based PDF, DOCX or TXT |
| No results | Try shorter title phrases and alternate locations, then add relevant employer boards or use jobs.searches.html |
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

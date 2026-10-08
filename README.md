# Jobhunt

A personal Python job finder that fetches public job-board listings, filters for
remote software roles, scores them against a skills profile, tracks listings in
SQLite, and writes a Markdown digest. It can also email the digest through
Gmail.

The project is designed to run locally on Windows. It does not apply for jobs
or access private accounts on job boards.

## How a run works

1. Load `profile.json` and `companies.json` from the Downloads folder beside
   `jobhunt.py`.
2. Fetch listings from the configured Greenhouse, Lever, and Ashby boards and
   the built-in Remote OK and Remotive sources.
3. Keep remote software-development roles that pass the location and title
   filters; score them against the profile.
4. Store and update listings in `jobs.db`, close jobs missing from a successfully
   fetched source, and avoid repeating jobs already shown in the console digest.
5. Write newly selected console results to `digest-YYYY-MM-DD.md`. If Gmail is
   configured, send jobs not previously emailed and record successful email
   notifications separately.

Company-board results are preferred when duplicate company/title listings are
found. In the console and email digest, up to 15 internships and 15 other roles
are selected per run.

## Requirements

- Windows 10 or later
- Python 3.10 or later
- Internet access to the public job-board APIs
- The Python package `requests`

## Install and run

Open PowerShell and install the dependency:

```powershell
cd C:\Users\noaha\Downloads
py --version
py -m pip install requests
```

Run a source check before the first scrape:

```powershell
py jobhunt.py check
```

`check` contacts every configured company board and both built-in sources. It
prints the number of jobs returned or the error for each source and does not
write job data to the database.

Fetch and score jobs:

```powershell
py jobhunt.py run
```

Show the best currently open results (15 per role type by default):

```powershell
py jobhunt.py top
py jobhunt.py top 25
```

The `jobhunt.py` file in Downloads is a small launcher for the `jobhunt_app`
package. These commands can also be run as `py -m jobhunt_app.cli run` from
Downloads.

## Configuration

Both configuration files belong in `C:\Users\noaha\Downloads`, beside
`jobhunt.py`—not inside the `jobhunt_app` package directory.

### `profile.json`

The profile controls skill matching, title preferences, exclusions, and the
minimum score. The current profile in Downloads was created from Noah's CV.
Its structure is:

```json
{
  "skills": ["javascript", "typescript", "python", "node.js", "mongodb"],
  "core": ["javascript", "typescript", "node.js", "mongodb"],
  "exclude_titles": "\\b(senior|staff|principal|manager|director)\\b",
  "prefer_titles": "intern|junior|entry[- ]level|software engineer|backend|full[\\s-]?stack",
  "min_score": 45
}
```

- `skills`: skills the scorer should look for, written as non-empty strings.
- `core`: skills from `skills` that count twice as much in the score.
- `exclude_titles`: a Python regular expression for titles to reject.
- `prefer_titles`: a Python regular expression that adds a title-match bonus;
  it does not independently reject titles that do not match.
- `min_score`: an integer from 0 to 100. Lower it to see more matches; raise it
  for a stricter digest.

Skills are matched against the scorer vocabulary in `jobhunt_app/scoring.py`.
An unrecognized skill causes a warning and will not contribute to matching
until a corresponding pattern is added to that vocabulary.

### `companies.json`

This must be a JSON array. An empty array is valid and still enables the two
built-in remote-job sources. To include a company, add an object with the
company's name, ATS, public board slug, and a label for the digest:

```json
[
  {
    "name": "Example Company",
    "ats": "greenhouse",
    "slug": "examplecompany",
    "tier": "target"
  },
  {
    "name": "Another Example",
    "ats": "lever",
    "slug": "another-example",
    "tier": "other",
    "scope": "another-example-jobs"
  }
]
```

Supported `ats` values are `greenhouse`, `lever`, and `ashby`. The `slug` is the
board identifier used in that provider's public postings API; it is not
necessarily the company's display name or the full careers-page URL. Check the
company's careers page to identify the board. `scope` is optional and must be
unique; it gives the board a stable identity when tracking jobs over time.
Every entry needs non-empty `name`, `ats`, `slug`, and `tier` fields.

The built-in sources are:

- **Remote OK** — public remote listings.
- **Remotive** — public remote software-development listings.

The scraper only treats its built-in sources as remote. Configured ATS jobs
must report a remote workplace, include “remote” in the title, or include
“remote” in their location to pass the remote filter.

## Matching and scoring

A listing must have a software-development-related title and pass the remote
filter. It is then rejected if its title matches `exclude_titles`. Known
location text indicating Nigeria, Africa, EMEA, worldwide, or similar is
treated as open; a set of country/region names is rejected. Locations that
don't clearly establish eligibility are retained but marked **region unclear**,
so check the original posting before applying. The location lists and software
title rules are currently defined in `jobhunt_app/scoring.py`, not in the JSON
configuration.

The score is based on skills detected in the title and description, with core
skills weighted twice, plus a small bonus when the title matches
`prefer_titles`. A missing score match does not mean a job is unsuitable; use
the linked posting to evaluate the actual requirements and eligibility.

Internships are grouped separately when the title or employment-type hint
contains internship-related wording. Other roles appear under **Roles**.

## Gmail email delivery

Email is optional. Without any email settings, `run` prints and saves the
console digest but does not send email. To send through Gmail, use a Google
**App Password**, not your regular account password:

1. Enable 2-Step Verification on the Google Account that will send the digest.
2. Create an App Password for this application in your Google Account security
   settings.
3. In Windows, open **Edit environment variables for your account** and add:
   - `JOBHUNT_EMAIL_FROM` — the Gmail sender address
   - `JOBHUNT_EMAIL_TO` — the recipient address (it may be the same address)
   - `JOBHUNT_EMAIL_PASSWORD` — the Gmail App Password
4. Close and reopen PowerShell, then run `py jobhunt.py run`.
5. Confirm the output says `Email: sent` and check the recipient inbox and Spam
   folder.

The sender connects to `smtp.gmail.com` over TLS on port 587. If no variables
are set, email is reported as `not configured`. If only some variables are
set, or Gmail rejects delivery, the run reports an email error and exits with a
failure status. The job database only marks jobs as emailed after Gmail accepts
the message. Do not put an App Password in `profile.json`, `companies.json`,
this README, or source control.

## Schedule a daily run on Windows

Use Windows Task Scheduler to run the same command daily:

1. Open **Task Scheduler** and select **Create Basic Task**.
2. Name it (for example, `Daily Jobhunt Digest`) and select a **Daily** trigger.
3. Choose the desired time. Task Scheduler uses the computer's local time; set
   the task for 7:00 AM only if Windows is using Lagos time, or convert the time
   for the machine's configured time zone.
4. Select **Start a program**.
5. Set **Program/script** to the Python executable returned by:

   ```powershell
   py -c "import sys; print(sys.executable)"
   ```

6. Set **Add arguments** to:

   ```text
   C:\Users\noaha\Downloads\jobhunt.py run
   ```

7. Set **Start in** to:

   ```text
   C:\Users\noaha\Downloads
   ```

8. In the task's properties, enable **Run task as soon as possible after a
   scheduled start is missed** if desired.

The account running the task must have access to the three Gmail environment
variables. The computer must be on and connected to the internet when the task
runs; Task Scheduler can optionally wake the computer if its power settings
allow it.

## Files and data

| Path | Purpose |
|---|---|
| `jobhunt.py` (in Downloads) | Command-line launcher |
| `jobhunt_app/` | Scraper, scoring, configuration, email, and storage code |
| `profile.json` (in Downloads) | Personal skills and matching preferences |
| `companies.json` (in Downloads) | Optional Greenhouse, Lever, and Ashby boards |
| `jobs.db` (in Downloads) | SQLite job history and notification state |
| `digest-YYYY-MM-DD.md` (in Downloads) | Console digest, appended to when more new results are found that day |

The database is created automatically. Existing databases are migrated to add
email-notification tracking when needed. Back up `jobs.db` if you want to
preserve your job history; deleting it resets that history and notification
state.

## Troubleshooting

- **Configuration file not found** — put `profile.json` and `companies.json` in
  Downloads beside `jobhunt.py`.
- **Invalid JSON / configuration error** — check commas and quotes; ensure
  `skills` and `core` are arrays of strings, every core skill is also in
  `skills`, both title patterns are valid regular expressions, and `min_score`
  is an integer from 0 to 100.
- **Unsupported ATS** — use exactly `greenhouse`, `lever`, or `ashby`.
- **A source fails in `check`** — check the board slug, network connection, and
  provider availability. One failing source does not prevent other successful
  sources from being used in a run.
- **No results** — lower `min_score`, review title and location filters, and
  remember that the built-in sources are remote-only. `top` shows previously
  stored open jobs, if any.
- **Malformed-posting count** — individual unusable postings are skipped when
  possible and reported in the run summary. If every posting in a non-empty
  response is malformed, that source is treated as failed to avoid closing its
  previously stored jobs based on unusable data.
- **`Email: not configured`** — set all three `JOBHUNT_EMAIL_*` variables and
  open a new PowerShell window.
- **Gmail authentication/delivery failure** — verify the sender address and
  create a new App Password; a normal Gmail password will not work.
- **Scheduled task doesn't send** — review the task's **Last Run Result**, make
  sure its user account can access the email variables, and check that Windows
  was awake and online at the scheduled time.

## Limitations

- The scraper uses public APIs and only the three ATS providers listed above;
  it does not crawl arbitrary websites or scrape LinkedIn/Indeed.
- Public source data, board APIs, rate limits, and response formats can change.
- Remote job eligibility and regional restrictions cannot always be inferred
  from a listing. Always review the employer's requirements and the linked job
  page.
- This is a personal matching aid, not a guarantee that a role is available,
  legitimate, or suitable.

# JobEnhancingPipeline

Collect LinkedIn job descriptions from a manually opened Chrome tab, store them in PostgreSQL, and browse them in the local Job Library.

## Project layout

- [collector/](collector/) reads LinkedIn search results and job details through Playwright.
- [storage/](storage/) handles PostgreSQL writes, collection runs, metadata, and maintenance commands.
- [web/](web/) serves the Job Library and its stylesheet.
- [sql/](sql/) contains the PostgreSQL schema, migrations, and verification query.

The root scripts `run.py`, `jobs_web.py`, and `linkedin_storage.py` are command-line entry points.

## Setup

The project uses PostgreSQL 17 with these connection defaults: `PGHOST=localhost`, `PGPORT=5432`, `PGDATABASE=resume_db`, and `PGUSER=resume_user`. Set `PGPASSWORD` in the terminal environment if your PostgreSQL server requires a password.

```sh
cd ~/Desktop/JobEnhancingPipeline
venv/bin/python -m pip install -r requirements.txt
```

For a new database, apply [the schema](sql/schema.sql). For an existing database created from an earlier schema, apply the applicable migrations in this order:

1. [Match fields](sql/add_match_fields.sql)
2. [Job metadata](sql/add_job_metadata.sql)
3. [Hiring model](sql/add_hiring_model.sql)
4. [Company review fields](sql/add_delivery_review.sql)
5. [Capture classification and technologies](sql/add_capture_classification.sql)
6. [Company blacklist](sql/add_company_blacklist.sql)
7. [Applied jobs](sql/add_applied_jobs.sql)
8. [Excluded jobs](sql/add_excluded_jobs.sql)

After applying the capture classification migration to an existing database, run `venv/bin/python -m storage.posting` to classify earlier captures and extract their key technologies.

After applying the blacklist migration to an existing database, populate the company keys for earlier captures:

```sh
venv/bin/python -c 'from storage.postgres import connect; from storage.blacklist import backfill_company_keys; conn = connect(); backfill_company_keys(conn); conn.close()'
```

To populate city and clearance fields on existing captures, run `venv/bin/python linkedin_storage.py --backfill-metadata`.

## View captured jobs

```sh
venv/bin/python jobs_web.py
```

Open the [Job Library](http://127.0.0.1:8765/). The sidebar groups captures by Sydney local date. Each date combines all collection runs, and the Source column identifies the job board. The list sorts by displayed match score, with unscored jobs last. Outsourced roles receive a 10-point display adjustment, floored at zero. The 60-point visibility threshold uses the adjusted score. Application document eligibility uses the stored score. Select a job title to see the full description, original posting link, match details, company review evidence, and available downloads. You can also run the [verification query](sql/verify_latest_capture.sql) in DBeaver.

The **In-house** column shows `Y` for work on a company's own products or systems and `N` for external client delivery. Pending and unconfirmed roles have a blank cell. Company review starts automatically after the collector finishes a run and processes that run's pending captures. It uses a signed-in Codex CLI available on `PATH` to research the company, then uses the job description to connect the role to the relevant product or service line. Every classification requires a public source, linked in the job detail. The job detail shows whether the review is pending or unconfirmed. A change to the title, company, or description queues a new review.

To retry pending reviews for a finished run without collecting the jobs again, use:

```sh
venv/bin/python -m storage.delivery_review --run-id 1
```

The list shows new and explicitly reposted jobs for the selected run. It uses the LinkedIn job ID and identical posting text with matching job metadata to identify repeats. The Key technologies column shows up to five terms found in the job description.

Open **Company blacklist** in the Job Library header to add or remove a company. Captures from blocked companies are hidden and receive a match score of 0. Removing a company restores its earlier scores. Block a company when you know that its roles are unsuitable, for example when all of its roles require security clearance.

Use **Applied** in the **Status** column to hide that posting from the default list, including captures from later runs. Open **Applied jobs** to see marked jobs for the selected date, and use **Undo** to return a posting to the default list.

Use `--score-with-codex` to send the resume text and job descriptions to Codex for matching after company review succeeds. To score a finished run separately, use `venv/bin/python -m storage.match_review --run-id 2`, replacing `2` with the actual run ID. The collector assigns a score of 0 to jobs requiring security clearance. Place application documents under the same capture ID, for example `application_files/1/resume.pdf` and `application_files/1/cover-letter.docx`. Both PDF and DOCX are supported. The PDF is preferred when both versions exist.

## Collect LinkedIn Jobs search results

Sign in to LinkedIn in the dedicated Chrome debugging instance and open the Jobs search results. Confirm that the Chrome DevTools endpoint is available at `127.0.0.1:9222`.

```sh
venv/bin/python run.py --list-tabs
venv/bin/python run.py --tab 1 --title "Lead Software Engineer" --limit 1
```

Replace `1` with the actual tab number. Without `--title` and `--limit`, the script collects up to five jobs from the current page. After the first attempted job, it waits 3 to 10 seconds before each subsequent attempt. Page selectors are defined at the top of [the LinkedIn collector](collector/linkedin.py).

To collect every results page, select the first page in Chrome and run:

```sh
venv/bin/python run.py --tab 1 --all-pages
```

The collector stores captures directly in PostgreSQL. PostgreSQL retains separate captures for new runs. Pass the run ID printed in the terminal with `--run-id` to retry the same run. When used with `--all-pages`, the retry skips jobs already stored for that run.

## Import existing JSONL records

```sh
venv/bin/python linkedin_storage.py --jsonl path/to/archive.jsonl --run-id 1
```

To create a new run for historical data, replace `--run-id` with `--search-url 'LINKEDIN_SEARCH_RESULTS_URL'`. Split files containing multiple search runs before importing. The importer also accepts a single JSON record on standard input.

- `public.linkedin_searches` stores saved searches.
- `public.linkedin_collection_runs` stores each run and the search URL used.
- `public.linkedin_jobs` stores job identities and canonical URLs.
- `public.linkedin_job_captures` stores the details for each run. The job identity and capture are written in one transaction. `captured_at` records when the full description was read, and imports retain the original timestamp.


## Application document guidelines

Keep confirmed education, work arrangements and role preferences in the local
`applicant_profile.md` file. The application guidance references this file for
eligibility and role screening. Git ignores the profile.

The [application guidance](storage/application_guidance.py) defines the
eligibility checks, score thresholds, resume editing rules, cover letter
format and delivery checks for preparing application documents. Use the
[Markdown resume master](resume_master.md) as the source of verified bullets
and the confirmed Word resume as the layout template. For each application,
select the strongest evidence for the posting and adapt the wording where the
meaning stays the same. Add newly confirmed responsibilities and corrections
to the matching role in the master. The scoring command also uses
the same Markdown master for resume matching, starting at the Summary section.
On a new checkout, place your private master at `resume_master.md` in the
project root with a `## Summary` heading. Git ignores this file.

For cover letters, map the
posting's main responsibilities and mandatory requirements to verified evidence
before drafting. Use the [Markdown cover letter template](templates/cover_letter.md)
for structure and inspect the rendered one-page DOCX before delivery. The Job
Library serves files placed in the capture's application directory using the
download names specified in the guidance. Collection and scoring do not
generate application documents.

Use **Exclude** in the list or job detail to hide a posting from captured and applied views. Open **Excluded jobs** and select **Restore** to show it again. The job detail also supports **Applied** and **Undo**.

### Mandatory citizenship and permanent residency

After creating a new database or upgrading an existing one, apply `storage/sql/add_citizenship_screening.sql`. It adds `citizenship_pr_required`, detects mandatory Australian citizenship/PR restrictions, backfills existing captures, and enforces a zero score and explanatory match details through a database trigger and constraint. The rule reflects the confirmed subclass 485 visa. Explicit visa alternatives, optional preferences and unrelated citizenship references do not trigger it. Reapply the migration to refresh the detector and backfill after rule changes. Changing the applicant's residency status requires reviewing this rule.

Run `venv/bin/python -m unittest discover -s tests -p test_citizenship_screening.py -v` against the migrated local database. The rescore enforcement test rolls back its attempted update.

### Cross-platform display deduplication

Apply `storage/sql/add_display_deduplication.sql` after the schema and other migrations. It retains raw captures, records `display_duplicate_of`, and marks equivalent same-day postings from different job identities as duplicates before scoring or generation. Matching requires the same normalized title, company, metro city and complete unique-word vocabulary from a substantial JD. Company legal suffixes, whitespace, a duplicated body and the standard repeated skills heading do not create separate jobs. Different cities, levels and technology versions remain distinct. The earliest eligible capture is retained; search also excludes linked duplicate captures.

Verify with `venv/bin/python -m unittest discover -s tests -p test_display_deduplication.py -v`.

### Live Captured jobs layout

The approved preview is implemented by `web/library_view.py`, `web/library.css` and `web/library.js`. The list uses real capture dates, final scores, delivery models, document links and application status forms. Global keyword search remains server-side; source, minimum-score and 75+ filters narrow the loaded view. Comfortable or compact density is stored as a browser preference. The mobile date selector provides access to the same capture history as the desktop sidebar. Detail and filter pages retain their existing routes and styling.

CSS and JavaScript are served as same-origin assets under the existing security policy; inline scripts/styles are not enabled. Run `venv/bin/python -m unittest discover -s tests -p test_library_view.py -v` for rendering and escaping checks.

## Workflow entry point and policy

Use `./start_job.sh` for the complete daily workflow. Use
`./collector/start_collection.sh` for interactive collection and browser setup.
See [the prompt and rule index](prompts/README.md) for persisted model prompts,
scoring adjustments, database filters and private applicant inputs.

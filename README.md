# LinkedIn Job Collection

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
cd ~/Desktop/ResumeSubmissionAssistance
venv/bin/python -m pip install -r requirements.txt
```

For a new database, apply [the schema](sql/schema.sql). For an existing database created from an earlier schema, apply the applicable migrations in this order:

1. [Match fields](sql/add_match_fields.sql)
2. [Job metadata](sql/add_job_metadata.sql)
3. [Hiring model](sql/add_hiring_model.sql)
4. [Company review fields](sql/add_delivery_review.sql)

To populate city and clearance fields on existing captures, run `venv/bin/python linkedin_storage.py --backfill-metadata`.

## View captured jobs

```sh
venv/bin/python jobs_web.py
```

Open the [Job Library](http://127.0.0.1:8765/). The sidebar groups captures by Sydney local date. The list sorts jobs by match score in descending order, with unscored jobs last. Select a job title to see the full description, original LinkedIn link, match details, company review evidence, and available downloads. You can also run the [verification query](sql/verify_latest_capture.sql) in DBeaver.

The **Model** column shows `In-house` for work on a company's own products or systems, and `Outsourced` for external client delivery. The scheduled review checks finished collection runs and uses the job description together with public company sources. Jobs awaiting a review show `Pending review`. Completed reviews with insufficient evidence show `Unconfirmed`. A change to the title, company, or description queues a new review.

The matching workflow can write `match_score` and `match_details` by capture ID. Skip records with `clearance_required = true`, which the collector assigns a score of 0. Place application documents under the same capture ID, for example `application_files/1/resume.pdf` and `application_files/1/cover-letter.docx`. Both PDF and DOCX are supported. The PDF is preferred when both versions exist.

## Collect LinkedIn Jobs search results

Sign in to LinkedIn in the dedicated Chrome debugging instance and open the Jobs search results. Confirm that the Chrome DevTools endpoint is available at `127.0.0.1:9222`.

```sh
venv/bin/python run.py --list-tabs
venv/bin/python run.py --tab 1 --title "Lead Software Engineer" --limit 1
```

Replace `1` with the actual tab number. Without `--title` and `--limit`, the script collects up to five jobs from the current page. After the first attempted job, it waits 5 to 30 seconds before each subsequent attempt. Page selectors are defined at the top of [the LinkedIn collector](collector/linkedin.py).

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

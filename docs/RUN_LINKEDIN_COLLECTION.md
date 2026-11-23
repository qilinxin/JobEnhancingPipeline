# Collect LinkedIn jobs on a Mac

## Run the daily pipeline

With the dedicated Chrome window signed in, leave one search tab open for
LinkedIn and one for SEEK. Make sure PostgreSQL and the signed-in Codex CLI are available.
Run the pipeline from the project directory:

```sh
./start_job.sh
```

It starts each open search on its first page using the current keywords and
filters, then runs company review, resume matching and document preparation in
order. Company review and scoring continue for saved jobs if one board fails.
A PostgreSQL lock prevents overlapping pipeline invocations. The command uses
the Sydney calendar date and prepares Word documents for eligible, unapplied,
non-excluded postings with a displayed score of at least 75 by default. It
requires the local resume master, applicant profile and single-column Word
template for new application documents. Document drafting and rendering use the
signed-in Codex CLI and the local document tooling. Saved files appear on their
Job Library detail pages.

Use `--source linkedin` or `--source seek` to collect from one board, or
repeat `--source` to select multiple boards. Indeed is opt-in via
`--source indeed`. Use `--min-score 80` to change the
document threshold, or `--skip-documents` to stop after resume scoring. Press
`Ctrl+C` to stop the current run.

## Start with one command

From the project directory, run:

```sh
./collector/start_collection.sh --all-pages
```

The launcher opens the saved LinkedIn, Indeed, and SEEK searches in the dedicated Chrome profile and starts PostgreSQL 17 when needed. Review the search filters and sign in if prompted. Return to Terminal, press Enter, and select the tab number shown. To start with one job, use `./collector/start_collection.sh --limit 1`. Running the launcher without options collects up to five jobs from the current results page.

The collector saves the LinkedIn results, marks repeat postings, and extracts up to five technologies from each job description. It keeps explicitly reposted jobs in the current run and then researches company business models for the new and reposted jobs.

To run resume matching after company review succeeds, opt in to sending the resume text and job descriptions to Codex:

```sh
./collector/start_collection.sh --all-pages --score-with-codex
```

To open all three searches without starting a collection, run:

```sh
./collector/start_collection.sh --browser-only
```

The presets use the LinkedIn Australia query `java software engineer hybrid or on-site posted in the past 24 hours`, the Indeed Australia query `java software developer` with the last 24 hours selected, and the SEEK query `java developer` with the last three days selected. The launcher tries to select **New to you** on SEEK and prints a prompt if it cannot find the control. Use `--source indeed` or `--source seek` to collect from a different board.

If PostgreSQL requires a password, set `PGPASSWORD` as described below before launching. To use a different existing Chrome debugging profile, set `LINKEDIN_CHROME_PROFILE` to its directory.

## 1. Prepare the project and database

Open Terminal and switch to the project directory.

```sh
cd ~/Desktop/JobEnhancingPipeline
```

Install dependencies into the project's virtual environment on first use or after a dependency update.

```sh
venv/bin/python -m pip install -r requirements.txt
```

Check that your existing PostgreSQL server is running. Test the connection in DBeaver or use this command.

```sh
psql -h localhost -p 5432 -U resume_user -d resume_db -c 'SELECT current_database(), current_user;'
```

The collector defaults to `localhost:5432`, database `resume_db`, and user `resume_user`. If PostgreSQL requires a password, set it in the zsh terminal where you will run the collector. The input stays hidden.

```zsh
read -rs 'PGPASSWORD?PostgreSQL password: '
export PGPASSWORD
printf '\n'
```

If the connection fails, run `brew services list`. If the installed `postgresql@17` service is stopped, run `brew services start postgresql@17` and test the connection again.

Company review runs after collection. Use `codex login status` to check that the same terminal can find the Codex CLI and that it is signed in. If you have the ChatGPT desktop app and the terminal cannot find `codex`, add its bundled CLI to the current terminal's path.

```sh
export PATH="/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS:$PATH"
codex login status
```

## 2. Open a dedicated Chrome debugging window

```sh
open -na "Google Chrome" --args \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/Library/Application Support/Chrome-LinkedIn-Debug" \
  --new-window "https://www.linkedin.com/jobs/"
```

If you already use a dedicated Chrome profile, pass its existing path to `--user-data-dir` to keep its login session. Check the debugging endpoint.

```sh
curl -fsS http://127.0.0.1:9222/json/version
```

A response containing `Browser` and `webSocketDebuggerUrl` confirms that the endpoint is ready. If the connection is refused, check that the debugging window is running. You can reuse an existing debugging window if the endpoint already responds.

## 3. Open your LinkedIn search results

1. Sign in to LinkedIn in the debugging window.
2. Open **Jobs**, enter your keywords, and choose the location and filters.
3. Leave the search results open. Select the first results page to collect all pages.
4. Return to the project terminal and list the LinkedIn tabs.

```sh
venv/bin/python run.py --list-tabs
```

Use the number shown for your search tab. The examples below use tab `1`.

## 4. Collect jobs

Start with one job to verify that the printed title and link match your search.

```sh
venv/bin/python run.py --tab 1 --limit 1
```

Choose a command for the scope you want.

- Current results page, up to five jobs — `venv/bin/python run.py --tab 1`
- All results from the current page onward — `venv/bin/python run.py --tab 1 --all-pages`
- First job on the current page with a matching title — `venv/bin/python run.py --tab 1 --title "Senior Java Engineer" --limit 1`

Keep the debugging window and the search tab open during collection. After the first attempted job, the collector waits 3 to 10 seconds before each subsequent attempt. The terminal prints the PostgreSQL run ID, saved jobs, and failures. When the run finishes, the collector checks public company information for pending jobs in that run.

Each invocation creates a new run unless you supply `--run-id`. To continue the same search after a trial or interruption, return to its first results page and pass the run ID shown in the terminal. Replace `2` with the actual run ID.

```sh
venv/bin/python run.py --tab 1 --all-pages --run-id 2
```

With `--all-pages --run-id`, the collector skips jobs already stored for that run.

## 5. Review the results

If the web server is running, refresh the [Job Library](http://127.0.0.1:8765/) and select the collection date. Otherwise, start it in another terminal.

```sh
cd ~/Desktop/JobEnhancingPipeline
venv/bin/python jobs_web.py
```

If PostgreSQL requires a password, set `PGPASSWORD` in the web server's terminal as well. Open a job to check its title, company, LinkedIn link, and full description. You can also run the [latest capture query](../storage/sql/verify_latest_capture.sql) in DBeaver.

If the jobs were saved and company review stopped because of a Codex sign-in or network issue, fix the issue and retry company review on its own. Replace `2` with the actual run ID.

```sh
venv/bin/python -m scoring.delivery_review --run-id 2
```

## Collect from Indeed Australia or SEEK

Open an Indeed Australia or SEEK search results page in the same debugging Chrome and set the search filters there. Use the corresponding source below.

```sh
venv/bin/python run.py --source indeed --list-tabs
venv/bin/python run.py --source indeed --tab 1 --limit 1
venv/bin/python run.py --source seek --list-tabs
venv/bin/python run.py --source seek --tab 1 --limit 1
```

Compare the terminal title and link with the JD in Job Library. After verifying one job, use `--limit 5`. Add `--score-with-codex` to send the JD and resume master to Codex for scoring. Company review runs after collection.

The collector reads visible cards on the selected results page and opens each posting in a separate Chrome tab. The card and detail selectors are in [Indeed](../collector/indeed.py) and [SEEK](../collector/seek.py). Check that the description selector matches the full JD for the URL printed by the collector.

If an Indeed detail URL returns HTTP 403, the collector stops that source.
Check the listing manually or use an authorised Indeed integration. To bring a
manually saved posting into the Job Library, use the existing JSONL importer
with the Indeed posting's canonical URL, title, company, location, full description
and capture timestamp. For example:

```sh
venv/bin/python linkedin_storage.py --search-name "Indeed Jobs" \
  --search-url "https://au.indeed.com/jobs?q=software+developer" \
  --jsonl path/to/indeed-postings.jsonl
```

The JSON keys are `canonical_url`, `title`, `company`, `location`, `description`
and `captured_at`. Use an ISO 8601 timestamp with a time zone. The importer
prints the run ID for company review and scoring.

For a full SEEK search, start on the first results page and run `venv/bin/python run.py --source seek --all-pages --score-with-codex`. Add `--run-id ID` to resume an existing batch and skip postings already saved in that batch.

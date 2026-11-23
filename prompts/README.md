# Workflow prompts and executable rules

The project stores its workflow policy locally. Prompts describe model decisions;
Python and SQL enforce deterministic rules. Editing a prompt does not replace a
Python rule or a database migration.

## Entry points

Run `./start_job.sh` from the project root for collection, company review, scoring
and document preparation in order. It forwards options to
`python -m workflow.daily_pipeline`; the default sources are LinkedIn and SEEK,
and the default document threshold is 75. Add `--source indeed` explicitly when
that source is available. The full pipeline requires PostgreSQL and the dedicated,
signed-in debugging Chrome with saved search tabs to be running already.

Use `./collector/start_collection.sh --browser-only` to prepare search tabs, or
`./collector/start_collection.sh --source seek --all-pages` for interactive
collection only. This launcher can start local PostgreSQL when collecting.

## Model prompts

- `daily_job_pipeline.md`: instructions read by the scheduled agent, including
  retries, recovery, eligibility, output checks and Chinese run summaries.
  `workflow/daily_pipeline.py` executes the stages; it does not itself load this
  scheduler prompt or configure schedules.
- `company_review.md`: loaded by `scoring/delivery_review.py`; public-source
  research distinguishes in-house work from client delivery.
- `resume_matching.md`: loaded by `scoring/match_review.py`; the base rubric is
  required technical skills 45, experience/scope 25, domain/responsibilities 20,
  preferred qualifications 10, normalized for applicable categories.
- `document_generation.md`: loaded by `documents/generate.py`; inserts the run
  date, minimum displayed score and current guides from `documents/guidance.py`.
- `resume_matching_references.md`: explanatory references, not a runtime prompt.

The scoring and company modules read their prompts when the Python process starts;
start a new process after changing those files.

## Rules outside prompts

- `scoring/match_review.py`: Java alignment multipliers: core/alternative 1.0,
  peripheral 0.8, absent 0.75. The model returns the base score.
- `storage/visibility.py`: client-delivery adjustment of minus 10, floored at zero;
  visible score threshold 60. `documents/generate.py` selects documents using the
  displayed score and requested threshold (default 75).
- `storage/title_blacklist.py` and `storage/sql/add_title_blacklist.sql`: title
  exclusion logic and initial keywords, including intern, graduate, sales,
  director and executive titles. The database table `linkedin_title_blacklist`
  holds the current editable list; it can differ from the initial SQL defaults.
- `storage/blacklist.py`: company exclusions, with current entries in PostgreSQL.
- `storage/metadata.py`: clearance detection. Mandatory citizenship/PR screening
  and zero-score enforcement live in
  `storage/sql/add_citizenship_screening.sql`; that migration must be applied.
- `storage/posting.py` and `storage/sql/add_display_deduplication.sql`: duplicate
  classification and cross-platform display rules.
- `documents/guidance.py`: verified evidence, eligibility, resume selection,
  cover-letter content and rendering checks.
- `documents/templates/cover_letter.md`: letter structure, staged for generation.
- `local/resume/resume_master.md` and the applicant profile: private verified
  facts and bullets, ignored by Git. Confirmed new responsibilities belong here.

## Reproducibility and scheduling

Schedules are stored by Codex outside this repository. Their instruction should
point to `prompts/daily_job_pipeline.md` in the current project directory
(`/Users/qilinxin0421/Desktop/JobEnhancingPipeline` on this machine). Saved browser
search filters, database blacklist entries, applicant facts, model/CLI versions
and external job postings also affect results. Persistent prompts keep the policy
reviewable; model output is not guaranteed to be identical between runs.

Never commit applicant files, generated documents, browser profiles or credentials.

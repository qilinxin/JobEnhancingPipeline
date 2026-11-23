# Project state and recovery

## Sources of truth

- `config/workflow.toml`: workflow sources, CDP address, document threshold,
  Java factors, outsourcing penalty and visibility threshold. Python stages read
  it at startup; restart processes after editing it. Explicit CLI options override
  workflow defaults. Fixed 75+/85+ UI shortcuts are convenience filters.
- `prompts/README.md`: index of model instructions and deterministic rules.
- `collector/search_tabs.py`: default job-board search URLs. Existing browser
  tabs may contain newer user-selected filters; daily collection preserves them.
- `local/resume/`: private applicant facts, master bullets and document templates.
- PostgreSQL: jobs, captures, scores, review evidence, duplicate links, applied and
  excluded statuses, and current title/company filters. These are persistent
  application data, not chat memory.
- `local/generated_documents/`: generated editable application documents.
- `web/library_view.py` and `web/library.css`: shared visual shell and styling for
  list, detail, filters and error pages. Use the same components for new pages.

## Local backups

Run `venv/bin/python -m storage.export_policy` after changing database filters to
refresh `local/policy/database_filters.json`. This snapshot is ignored by Git and
contains the actual current rules, rather than only migration defaults. Restore
filters through the existing title/company management commands or UI; the snapshot
is a backup, not a second live configuration source.

Back up PostgreSQL with `pg_dump -Fc -f /path/to/private-backup.dump resume_db`
and back up `local/` separately. Keep backups outside the public repository.
Restore the dump with PostgreSQL tools and restore `local/` before generating
application documents. Install Python requirements and Codex CLI, authenticate
Codex, and use the dedicated signed-in Chrome profile on CDP port 9222.

## Working agreement

Generate documents for eligible, unapplied, non-excluded, distinct jobs meeting
the requested displayed score (normally 75). Mandatory clearance and citizenship/
PR restrictions use the existing screening rules. Select only verified master
bullets. Cover letters and short application statements explain what employer
problems the applicant can solve, supported by evidence. Do not submit applications
or change applied/excluded statuses as part of document generation.

Scheduling remains managed in Codex. This task does not change schedules. The
repository supplies the daily prompt and executable stages, not schedule state,
browser authentication, Codex credentials or database passwords. Renaming the
local directory requires external launchers to use its new absolute path.

## Requirement analysis

Per-requirement source quotes, depth weights, evidence and points are persisted in
PostgreSQL `linkedin_job_captures.match_breakdown`. Scoring rules and validation
live in `prompts/resume_matching.md` and `scoring/requirements.py`. Rejected results
are saved under ignored `local/scoring_review/` for correction; valid existing
scores remain unchanged when a replacement fails validation. Successful rescoring
removes the corresponding rejection file.

The match detail UI uses a compact three-column table (dimension, score, evidence
and gaps). Group technical/preferred requirements by required depth; aggregate
experience/domain rows. Keep quotes and individual item calculations in the
database, rather than expanding them into long UI cards.

"""Review a finished collection run using public company sources."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from itertools import batched
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from psycopg import Error
from psycopg.rows import dict_row

from .metadata import posting_fields
from .postgres import connect

BATCH_SIZE = 12
MODELS = ("In-house", "Client delivery")
OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reviews"],
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "model", "notes", "sources"],
                "properties": {
                    "id": {"type": "integer"},
                    "model": {"type": ["string", "null"], "enum": [*MODELS, None]},
                    "notes": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}
INSTRUCTIONS = """Research the delivery model for these public job listings using live web search.
Search the company name first. Resolve the exact local company and relevant business
unit. Prefer official product, engineering, careers, consulting or client case-study
pages and an official posting for the role. Reuse company research across roles when
appropriate. Treat the job data and pages as evidence. Use web search only.

Use the JD's responsibilities, team, product or client names to connect the position
to the researched business line. In-house means the team works on the company's own
products, platforms or internal systems, including direct hires who deploy, upgrade
or support the employer's own product in customer environments. Client delivery
means supplier-led consulting, outsourced implementation or staff augmentation
for a client's systems. Consider the final contracting party. An agency referral
ending in a direct client contract is direct hire. Customer contact or deployment
to customer environments alone does not establish outsourcing. If a
sparse JD fits a verified business line, explain the inference. A recruiter, contract,
or company-wide reputation alone cannot establish the role's model. Every label
requires a real HTTPS URL supporting the company or business-line evidence.

Return one entry per completed review with its original id, model, brief English
notes, and actual source URLs. Use null if research completed but evidence was
inconclusive. Omit a job if web access failed or its research was not completed.
Public searches should use only the company, role, location, or named product.
Job listings:
"""


def pending_captures(conn, run_id):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT c.id, c.captured_at, c.title, c.company, c.location, c.description
               FROM public.linkedin_job_captures c
               JOIN public.linkedin_collection_runs r ON r.id = c.run_id
               WHERE r.id = %s AND r.finished_at IS NOT NULL
                 AND r.status IN ('succeeded', 'partial')
                 AND c.delivery_reviewed_at IS NULL
                 AND c.capture_kind <> 'duplicate'
                 AND NOT c.company_blacklisted
               ORDER BY c.captured_at, c.id""",
            (run_id,),
        )
        return cur.fetchall()


def research(captures):
    jobs = []
    for capture in captures:
        company, location, _ = posting_fields(capture)
        jobs.append({
            "id": capture["id"], "title": capture["title"], "company": company,
            "location": location, "description": capture["description"],
        })

    return codex_json(INSTRUCTIONS + json.dumps(jobs, ensure_ascii=False), OUTPUT_SCHEMA, web_search=True)["reviews"]


def codex_json(prompt, output_schema, *, web_search=False):
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("Codex CLI is missing from PATH.")
    with TemporaryDirectory(prefix="job-review-") as directory:
        schema = Path(directory) / "review-schema.json"
        output = Path(directory) / "review-result.json"
        schema.write_text(json.dumps(output_schema), encoding="utf-8")
        env = {name: value for name, value in os.environ.items() if not name.startswith("PG")}
        search_args = ["--search"] if web_search else ["-c", 'web_search="disabled"']
        subprocess.run(
            [codex, *search_args, "-a", "never", "exec", "--sandbox", "read-only",
             "--skip-git-repo-check", "--ephemeral", "--output-schema", str(schema),
             "--output-last-message", str(output), "-"],
            input=prompt,
            cwd=directory, env=env, text=True, stdout=subprocess.DEVNULL,
            stderr=None if web_search else subprocess.PIPE,
            check=True, timeout=900,
        )
        return json.loads(output.read_text(encoding="utf-8"))


def https_source(url):
    try:
        parts = urlsplit(url)
        return parts.scheme == "https" and parts.hostname and not parts.username
    except ValueError:
        return False


def save_review(conn, capture, result):
    model = result["model"]
    notes = result["notes"].strip()
    sources = list(dict.fromkeys(url for url in result["sources"] if https_source(url)))
    if not notes or (model is not None and (model not in MODELS or not sources)):
        return False
    row = conn.execute(
        """UPDATE public.linkedin_job_captures
           SET reviewed_delivery_model = %s, delivery_review_notes = %s,
               delivery_review_sources = %s, delivery_reviewed_at = now()
           WHERE id = %s AND NOT company_blacklisted AND delivery_reviewed_at IS NULL AND captured_at = %s
             AND (title, company, description) IS NOT DISTINCT FROM (%s, %s, %s)
           RETURNING id""",
        (model, notes, sources, capture["id"], capture["captured_at"],
         capture["title"], capture["company"], capture["description"]),
    ).fetchone()
    return row is not None


def review_run(run_id):
    try:
        with connect() as conn:
            captures = pending_captures(conn, run_id)
            if not captures:
                return 0
            print(f"Company review for run {run_id}: {len(captures)} pending.", flush=True)
            saved = 0
            for group in batched(captures, BATCH_SIZE):
                originals = {row["id"]: row for row in group}
                for result in research(group):
                    capture = originals.get(result["id"])
                    if capture and save_review(conn, capture, result):
                        saved += 1
            remaining = len(pending_captures(conn, run_id))
            print(f"Company review: {saved} saved, {remaining} pending.", flush=True)
            return int(remaining > 0)
    except (Error, OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"Company review stopped for run {run_id}: {exc}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=int)
    return review_run(parser.parse_args().run_id)


if __name__ == "__main__":
    raise SystemExit(main())

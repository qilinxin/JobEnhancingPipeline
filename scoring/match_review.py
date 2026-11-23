"""Score new and reposted jobs against the local resume master."""

import argparse
from datetime import date
import json
import subprocess
import sys
from itertools import batched
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from psycopg import Error
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .requirements import calculate_requirements, CATEGORY_POINTS

from documents.guidance import RESUME_MASTER
from storage.title_blacklist import TITLE_ALLOWED
from storage.metadata import posting_fields
from storage.postgres import connect
from .delivery_review import codex_json
from workflow.settings import SETTINGS

RESUME_PATH = Path(__file__).resolve().parents[1] / RESUME_MASTER
JAVA_FACTORS = SETTINGS["scoring"]["java_factors"]
REQUIREMENT_FIELDS = {"name": "string", "category": "string", "jd_quote": "string",
                      "required_level": "integer", "evidence_level": "integer",
                      "resume_quote": "string", "explanation": "string"}
ITEM_SCHEMA = {"type": "object", "additionalProperties": False,
               "required": list(REQUIREMENT_FIELDS),
               "properties": {**{k: {"type": v} for k, v in REQUIREMENT_FIELDS.items()},
                              "category": {"type": "string", "enum": list(CATEGORY_POINTS)},
                              "required_level": {"type": "integer", "enum": [1, 2, 3, 4]},
                              "evidence_level": {"type": "integer", "enum": [0, 1, 2, 3, 4]}}}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["matches"],
          "properties": {"matches": {"type": "array", "items": {
              "type": "object", "additionalProperties": False,
              "required": ["id", "details", "java_role", "requirements"],
              "properties": {"id": {"type": "integer"}, "details": {"type": "string"},
                             "java_role": {"type": "string", "enum": list(JAVA_FACTORS)},
                             "requirements": {"type": "array", "items": ITEM_SCHEMA}}
          }}}}
PROMPT = (Path(__file__).resolve().parents[1] / "prompts/resume_matching.md").read_text(encoding="utf-8")


def score_run(run_id, *, rescore=False, capture_id=None, missing_breakdown=False, capture_day=None):
    try:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """UPDATE public.linkedin_job_captures c SET match_details = %s
                   FROM public.linkedin_collection_runs r
                   WHERE r.id = c.run_id AND c.run_id = %s AND c.clearance_required
                     AND NOT c.company_blacklisted
                     AND r.status IN ('succeeded', 'partial') AND c.capture_kind <> 'duplicate'
                     AND NULLIF(btrim(c.match_details), '') IS NULL""",
                ("The posting requires security clearance. The match score is 0.", run_id),
            )
            cur.execute(
                f"""SELECT c.id, c.title, c.company, c.location, c.posted_label, c.description, c.captured_at
                   FROM public.linkedin_job_captures c JOIN public.linkedin_collection_runs r ON r.id = c.run_id
                   WHERE c.run_id = %s AND r.status IN ('succeeded', 'partial')
                     AND c.capture_kind <> 'duplicate' AND NOT c.clearance_required AND NOT c.company_blacklisted
                     AND NOT c.citizenship_pr_required
                     AND {TITLE_ALLOWED}
                     AND (%s OR c.match_score IS NULL OR NULLIF(btrim(c.match_details), '') IS NULL OR c.match_breakdown IS NULL)
                     AND (%s::bigint IS NULL OR c.id = %s)
                     AND (NOT %s OR c.match_breakdown IS NULL)
                     AND (%s::date IS NULL OR (c.captured_at AT TIME ZONE 'Australia/Sydney')::date = %s)
                   ORDER BY c.id""",
                (run_id, rescore, capture_id, capture_id, missing_breakdown, capture_day, capture_day),
            )
            captures = cur.fetchall()
            if not captures:
                return 0
            resume = RESUME_PATH.read_text(encoding="utf-8").partition("## Summary\n")[2].strip()
            if not resume:
                raise ValueError("The resume master is missing its Summary section or resume content.")
            print(f"Resume matching for run {run_id}: {len(captures)} jobs pending.", flush=True)
            saved = 0
            def evaluate(group):
                jobs = [{"id": row["id"], "title": row["title"], "company": posting_fields(row)[0],
                         "description": row["description"]} for row in group]
                payload = json.dumps({"resume": resume, "jobs": jobs}, ensure_ascii=False)
                return codex_json(PROMPT + "\n" + payload, SCHEMA)["matches"]

            groups = list(batched(captures, 4))
            with ThreadPoolExecutor(max_workers=3) as pool:
                for group, matches in zip(groups, pool.map(evaluate, groups)):
                    originals = {row["id"]: row for row in group}
                    for result in matches:
                        row = originals.get(result["id"])
                        if row is None:
                            continue
                        details = result["details"].strip()
                        try:
                            score, ledger, breakdown = calculate_requirements(result["requirements"], row["description"], resume)
                        except ValueError as error:
                            review_folder = RESUME_PATH.parents[1] / "scoring_review"
                            review_folder.mkdir(parents=True, exist_ok=True)
                            (review_folder / f"{row['id']}.json").write_text(
                                json.dumps({"error": str(error), "result": result}, ensure_ascii=False, indent=2),
                                encoding="utf-8",
                            )
                            print(f"Capture {row['id']} requires review: {error}", file=sys.stderr)
                            continue
                        details = f"Score breakdown: {breakdown}.\n\n{details}"
                        java_role = result["java_role"]
                        factor = JAVA_FACTORS[java_role]
                        ledger["java_role"] = java_role
                        ledger["java_factor"] = factor
                        details += f"\n\nJava alignment: {java_role.capitalize()} (×{factor:g}). Base score: {score:.2f}."
                        cur.execute(
                            """UPDATE public.linkedin_job_captures SET match_score = %s, match_details = %s, match_breakdown = %s
                               WHERE id = %s AND captured_at = %s AND description = %s
                                 AND capture_kind <> 'duplicate' AND NOT clearance_required AND NOT company_blacklisted
                                 AND (%s OR match_score IS NULL OR NULLIF(btrim(match_details), '') IS NULL OR match_breakdown IS NULL)""",
                            (round(score * factor, 2), details, Jsonb(ledger), row["id"], row["captured_at"], row["description"], rescore),
                        )
                        saved += cur.rowcount
                        if cur.rowcount:
                            (RESUME_PATH.parents[1] / "scoring_review" / f"{row['id']}.json").unlink(missing_ok=True)
                    conn.commit()
                    print(f"Resume matching for run {run_id}: {saved}/{len(captures)} saved.", flush=True)
            return int(saved != len(captures))
    except (Error, OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"Resume matching stopped for run {run_id}: {exc}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--run-id", type=int)
    selection.add_argument("--date", type=date.fromisoformat, help="Rescore captures from this Sydney calendar date.")
    parser.add_argument("--missing-breakdown", action="store_true", help="Only enrich jobs without a structured requirement ledger.")
    parser.add_argument("--rescore", action="store_true", help="Replace existing match scores.")
    parser.add_argument("--capture-id", type=int, help="Score only this capture within the run.")
    args = parser.parse_args()
    if args.date:
        with connect() as conn:
            runs = conn.execute("SELECT DISTINCT run_id FROM linkedin_job_captures WHERE (captured_at AT TIME ZONE 'Australia/Sydney')::date = %s ORDER BY run_id", (args.date,)).fetchall()
        return int(any([score_run(run[0], rescore=True, missing_breakdown=args.missing_breakdown, capture_day=args.date) for run in runs]))
    return score_run(args.run_id, rescore=args.rescore, capture_id=args.capture_id, missing_breakdown=args.missing_breakdown)


if __name__ == "__main__":
    raise SystemExit(main())

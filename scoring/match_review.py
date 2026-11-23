"""Score new and reposted jobs against the local resume master."""

import argparse
import json
import math
import subprocess
import sys
from itertools import batched
from pathlib import Path

from psycopg import Error
from psycopg.rows import dict_row

from documents.guidance import RESUME_MASTER
from storage.title_blacklist import TITLE_ALLOWED
from storage.metadata import posting_fields
from storage.postgres import connect
from .delivery_review import codex_json
from workflow.settings import SETTINGS

RESUME_PATH = Path(__file__).resolve().parents[1] / RESUME_MASTER
JAVA_FACTORS = SETTINGS["scoring"]["java_factors"]
FIELDS = {"id": "integer", "score": "number", "details": "string", "java_role": "string"}
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["matches"],
    "properties": {
        "matches": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": list(FIELDS),
            "properties": {
                **{name: {"type": kind} for name, kind in FIELDS.items()},
                "java_role": {"type": "string", "enum": list(JAVA_FACTORS)},
            },
        }},
    },
}
PROMPT = (Path(__file__).resolve().parents[1] / "prompts/resume_matching.md").read_text(encoding="utf-8")


def score_run(run_id, *, rescore=False, capture_id=None):
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
                     AND {TITLE_ALLOWED}
                     AND (%s OR c.match_score IS NULL OR NULLIF(btrim(c.match_details), '') IS NULL)
                     AND (%s::bigint IS NULL OR c.id = %s)
                   ORDER BY c.id""",
                (run_id, rescore, capture_id, capture_id),
            )
            captures = cur.fetchall()
            if not captures:
                return 0
            resume = RESUME_PATH.read_text(encoding="utf-8").partition("## Summary\n")[2].strip()
            if not resume:
                raise ValueError("The resume master is missing its Summary section or resume content.")
            print(f"Resume matching for run {run_id}: {len(captures)} jobs pending.", flush=True)
            saved = 0
            for group in batched(captures, 14):
                originals = {row["id"]: row for row in group}
                jobs = [{"id": row["id"], "title": row["title"], "company": posting_fields(row)[0],
                         "description": row["description"]} for row in group]
                payload = json.dumps({"resume": resume, "jobs": jobs}, ensure_ascii=False)
                for result in codex_json(PROMPT + "\n" + payload, SCHEMA)["matches"]:
                    row = originals.get(result["id"])
                    score, details = result["score"], result["details"].strip()
                    if row is None or not details or not math.isfinite(score) or not 0 <= score <= 100:
                        continue
                    java_role = result["java_role"]
                    factor = JAVA_FACTORS[java_role]
                    details += f"\n\nJava alignment: {java_role.capitalize()} (×{factor:g}). Base score: {score:.2f}."
                    cur.execute(
                        """UPDATE public.linkedin_job_captures SET match_score = %s, match_details = %s
                           WHERE id = %s AND captured_at = %s AND description = %s
                             AND capture_kind <> 'duplicate' AND NOT clearance_required AND NOT company_blacklisted
                             AND (%s OR match_score IS NULL OR NULLIF(btrim(match_details), '') IS NULL)""",
                        (round(score * factor, 2), details, row["id"], row["captured_at"], row["description"], rescore),
                    )
                    saved += cur.rowcount
                print(f"Resume matching for run {run_id}: {saved}/{len(captures)} saved.", flush=True)
            return int(saved != len(captures))
    except (Error, OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"Resume matching stopped for run {run_id}: {exc}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--rescore", action="store_true", help="Replace existing match scores.")
    parser.add_argument("--capture-id", type=int, help="Score only this capture within the run.")
    args = parser.parse_args()
    return score_run(args.run_id, rescore=args.rescore, capture_id=args.capture_id)


if __name__ == "__main__":
    raise SystemExit(main())

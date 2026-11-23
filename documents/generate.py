"""Select eligible jobs and prepare staged application documents."""

from collections import defaultdict
from datetime import datetime, time, timedelta
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from psycopg.rows import dict_row

from storage.metadata import posting_fields
from storage.visibility import DISPLAY_SCORE, SYDNEY, VISIBLE_CAPTURES
from . import guidance
from .files import GENERATED_DOCUMENTS, PROJECT_ROOT, document_file

DOC_KINDS = ("resume", "cover-letter")
TEMPLATE = "local/resume/William_Qi_Technical_Resume_Single_Column.docx"
LETTER_STYLE = GENERATED_DOCUMENTS / "620" / "cover-letter.docx"
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def candidates(conn, day, min_score):
    start = datetime.combine(day, time.min, tzinfo=SYDNEY)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT * FROM (
                 SELECT DISTINCT ON (c.job_id) c.id, c.title, c.company, c.location, c.city, c.posted_label,
                        c.description, c.match_details, c.match_score, c.hiring_model,
                        c.reviewed_delivery_model, c.delivery_review_notes, {DISPLAY_SCORE} AS display_score
                 FROM public.linkedin_job_captures c JOIN public.linkedin_jobs j ON j.id = c.job_id
                 WHERE c.captured_at >= %s AND c.captured_at < %s
                   AND j.applied_at IS NULL AND j.excluded_at IS NULL AND {VISIBLE_CAPTURES}
                 ORDER BY c.job_id, c.captured_at DESC, c.id DESC
               ) AS latest
               WHERE display_score >= %s ORDER BY display_score DESC, id DESC""",
            (start, start + timedelta(days=1), min_score),
        )
        jobs = cur.fetchall()
    groups = defaultdict(list)
    for job in jobs:
        company, location, _ = posting_fields(job)
        job.update(company=company, location=location)
        description = re.sub(r"\W+", " ", job["description"].casefold()).strip()
        key = (job["title"].strip().casefold(), (company or "").casefold(),
               (job["city"] or location or "").casefold(), description)
        groups[key].append(job)
    return groups.values()


def valid_docx(path):
    if not path.is_file() or path.is_symlink():
        return False
    try:
        with ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
            return root.tag == f"{WORD_NS}document" and any(
                part.text and part.text.strip() for part in root.iter(f"{WORD_NS}t")
            )
    except (OSError, ValueError, KeyError, BadZipFile, ElementTree.ParseError):
        return False


def install_documents(paths, jobs):
    for job in jobs:
        capture = job["id"]
        folder = GENERATED_DOCUMENTS / str(capture)
        folder.mkdir(parents=True, exist_ok=True)
        for kind, source in paths.items():
            if document_file(capture, kind) is None:
                target = folder / f"{kind}{source.suffix}"
                with NamedTemporaryFile(dir=folder) as staged:
                    staged.write(source.read_bytes())
                    staged.flush()
                    try:
                        # Linking publishes the complete file without replacing an existing draft.
                        os.link(staged.name, target)
                    except FileExistsError:
                        if document_file(capture, kind) is None:
                            raise
        print(f"Application documents: http://127.0.0.1:8765/captures/{capture}")


def prepare_documents(conn, day, min_score):
    todo = {}
    for jobs in candidates(conn, day, min_score):
        complete = None
        for job in jobs:
            paths = {kind: document_file(job["id"], kind) for kind in DOC_KINDS}
            if all(paths.values()):
                complete = paths
                break
        if complete:
            install_documents(complete, jobs)
        else:
            todo[jobs[0]["id"]] = jobs
    if not todo:
        print("No new application document sets are needed.")
        return False

    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("Codex CLI is missing from PATH.")
    with TemporaryDirectory(prefix="job-documents-") as directory:
        stage = Path(directory)
        for name in (guidance.RESUME_MASTER, guidance.APPLICANT_PROFILE, TEMPLATE,
                     guidance.COVER_LETTER_TEMPLATE):
            shutil.copyfile(PROJECT_ROOT / name, stage / Path(name).name)
        if LETTER_STYLE.is_file():
            shutil.copyfile(LETTER_STYLE, stage / "cover-letter-example.docx")
        data = [jobs[0] for jobs in todo.values()]
        (stage / "jobs.json").write_text(json.dumps(data, ensure_ascii=False, default=float), encoding="utf-8")
        prompt = (PROJECT_ROOT / "prompts/document_generation.md").read_text(encoding="utf-8").format(
            run_date=day.strftime("%d %B %Y"), min_score=min_score, guidance=guidance,
        )
        env = {name: value for name, value in os.environ.items() if not name.startswith("PG")}
        result = subprocess.run(
            [codex, "-a", "never", "-c", 'web_search="disabled"', "exec", "--sandbox", "workspace-write",
             "--skip-git-repo-check", "--ephemeral", "-"],
            cwd=stage, input=prompt, text=True, env=env, timeout=1800, check=False,
        )
        skipped_path = stage / "skipped.json"
        skipped = json.loads(skipped_path.read_text(encoding="utf-8")) if skipped_path.is_file() else {}
        failed = bool(result.returncode)
        for capture, jobs in todo.items():
            paths = {kind: stage / "output" / str(capture) / f"{kind}.docx" for kind in DOC_KINDS}
            if all(valid_docx(path) and path.resolve().is_relative_to(stage.resolve()) for path in paths.values()):
                install_documents(paths, jobs)
            elif str(capture) in skipped:
                print(f"Skipped capture {capture}: {skipped[str(capture)]}")
            else:
                print(f"Documents missing or invalid for capture {capture}.", file=sys.stderr)
                failed = True
        return failed

"""Store LinkedIn captures and maintain collection runs in PostgreSQL."""

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg.rows import dict_row

from .blacklist import company_key, lock_company
from .metadata import classify_hiring_model, derive_metadata, posting_fields
from .posting import posting_features


def connect():
    # libpq reads PGPASSWORD from the runtime environment when supplied.
    return psycopg.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "resume_db"),
        user=os.environ.get("PGUSER", "resume_user"),
        autocommit=True,
        connect_timeout=5,
    )


def search_url_without_selection(url):
    parts = urlsplit(url)
    ignored = {"currentJobId", "eBP", "refId", "trackingId"}
    if parts.hostname == "au.indeed.com" and parts.path == "/jobs":
        ignored.update({"vjk", "jk"})
    params = sorted((key, value) for key, value in parse_qsl(parts.query) if key not in ignored)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))


@dataclass
class CollectionRun:
    id: int
    saved: int = 0
    errors: list[str] = field(default_factory=list)


@contextmanager
def collection_run(conn, *, run_id=None, search_url=None, search_name=None):
    with conn.transaction():
        if run_id is None:
            if not search_url:
                raise ValueError("A search results URL is required for a new run.")
            normalized = search_url_without_selection(search_url)
            name = search_name or dict(parse_qsl(urlsplit(normalized).query)).get("keywords")
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 1))", (normalized,))
            search = conn.execute(
                """SELECT id FROM public.linkedin_searches
                   WHERE search_url = %s ORDER BY id LIMIT 1""",
                (normalized,),
            ).fetchone()
            if search is None:
                search = conn.execute(
                    """INSERT INTO public.linkedin_searches (name, search_url)
                       VALUES (%s, %s) RETURNING id""",
                    (name or "LinkedIn Jobs", normalized),
                ).fetchone()
            run_id = conn.execute(
                """INSERT INTO public.linkedin_collection_runs (search_id, search_url_used)
                   VALUES (%s, %s) RETURNING id""",
                (search[0], search_url),
            ).fetchone()[0]
        existing = conn.execute(
            "SELECT search_url_used FROM public.linkedin_collection_runs WHERE id = %s",
            (run_id,),
        ).fetchone()
        if existing is None or (search_url and search_url_without_selection(existing[0]) !=
                                search_url_without_selection(search_url)):
            raise ValueError(f"Run {run_id} does not exist or does not match the current search.")
        locked = conn.execute("SELECT pg_try_advisory_lock(%s)", (run_id,)).fetchone()[0]
        if not locked:
            raise ValueError(f"Collection run {run_id} is already in progress.")
        conn.execute(
            """UPDATE public.linkedin_collection_runs
               SET status = 'running', finished_at = NULL, error_message = NULL WHERE id = %s""",
            (run_id,),
        )
    run = CollectionRun(run_id)
    print(f"PostgreSQL run_id={run_id}", flush=True)
    try:
        yield run
    except BaseException as exc:
        run.errors.append(str(exc) or type(exc).__name__)
        try:
            finish_run(conn, run)
        except psycopg.Error as finish_error:
            exc.add_note(f"Failed to update the collection run status: {finish_error}")
        raise
    else:
        finish_run(conn, run)
    finally:
        if not conn.closed:
            try:
                conn.execute("SELECT pg_advisory_unlock(%s)", (run_id,))
            except psycopg.Error:
                conn.close()


def finish_run(conn, run):
    has_capture = run.saved or conn.execute(
        "SELECT EXISTS (SELECT 1 FROM public.linkedin_job_captures WHERE run_id = %s)",
        (run.id,),
    ).fetchone()[0]
    status = ("partial" if has_capture else "failed") if run.errors else "succeeded"
    conn.execute(
        """UPDATE public.linkedin_collection_runs
           SET status = %s, finished_at = GREATEST(now(), started_at), error_message = %s
           WHERE id = %s""",
        (status, "\n".join(run.errors) or None, run.id),
    )


def captured_urls(conn, run_id):
    return {url for (url,) in conn.execute(
        """SELECT j.canonical_url FROM public.linkedin_job_captures c
           JOIN public.linkedin_jobs j ON j.id = c.job_id WHERE c.run_id = %s""",
        (run_id,),
    )}


def save_capture(conn, run_id, capture):
    """Store the job identity and capture atomically."""
    job_id = capture.get("linkedin_job_id") or None
    url = capture["canonical_url"]
    captured_at = datetime.fromisoformat(capture["captured_at"])
    if captured_at.utcoffset() is None:
        raise ValueError("captured_at must include a UTC offset.")
    city, clearance_required = derive_metadata(capture)
    hiring_model = classify_hiring_model(capture["description"])
    fingerprint, repost, technologies = posting_features(capture)
    key = company_key(posting_fields(capture)[0])

    with conn.transaction(), conn.cursor() as cur:
        lock_company(cur, key)
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM public.linkedin_company_blacklist WHERE company_key = %s)",
            (key,),
        )
        blacklisted = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO public.linkedin_jobs (linkedin_job_id, canonical_url)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (job_id, url),
        )
        cur.execute(
            """
            SELECT id, linkedin_job_id, canonical_url
            FROM public.linkedin_jobs
            WHERE linkedin_job_id = %s OR canonical_url = %s
            ORDER BY id
            FOR UPDATE
            """,
            (job_id, url),
        )
        rows = cur.fetchall()
        if len(rows) != 1:
            raise ValueError("The LinkedIn job ID and canonical URL resolve to different rows.")
        db_job_id, stored_id, stored_url = rows[0]
        if stored_url != url or (stored_id is not None and job_id is not None and stored_id != job_id):
            raise ValueError("The job identity conflicts with the stored ID or canonical URL.")
        if stored_id is None and job_id is not None:
            cur.execute(
                "UPDATE public.linkedin_jobs SET linkedin_job_id = %s WHERE id = %s",
                (job_id, db_job_id),
            )

        if fingerprint:
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 2))", (fingerprint,))
        cur.execute(
            """SELECT
                   (SELECT capture_kind FROM public.linkedin_job_captures WHERE run_id = %s AND job_id = %s),
                   EXISTS (SELECT 1 FROM public.linkedin_job_captures
                           WHERE run_id = %s AND job_id <> %s AND posting_fingerprint = %s),
                   EXISTS (SELECT 1 FROM public.linkedin_job_captures
                           WHERE run_id <> %s AND captured_at <= %s
                             AND (job_id = %s OR posting_fingerprint = %s))""",
            (run_id, db_job_id, run_id, db_job_id, fingerprint, run_id, captured_at, db_job_id, fingerprint),
        )
        current_kind, same_run, earlier = cur.fetchone()
        kind = current_kind or ("duplicate" if same_run else "repost" if repost else "duplicate" if earlier else "new")
        cur.execute(
            """
            INSERT INTO public.linkedin_job_captures AS existing (
                run_id, job_id, captured_at, title, company, location,
                description, posted_label, posted_at, salary_text,
                city, clearance_required, match_score, hiring_model,
                capture_kind, posting_fingerprint, key_technologies, company_key, company_blacklisted
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id, job_id) DO UPDATE SET
                captured_at = EXCLUDED.captured_at,
                title = EXCLUDED.title,
                company = EXCLUDED.company,
                company_key = EXCLUDED.company_key,
                company_blacklisted = EXCLUDED.company_blacklisted,
                location = EXCLUDED.location,
                description = EXCLUDED.description,
                posted_label = EXCLUDED.posted_label,
                posted_at = EXCLUDED.posted_at,
                salary_text = EXCLUDED.salary_text,
                city = EXCLUDED.city,
                posting_fingerprint = EXCLUDED.posting_fingerprint,
                key_technologies = EXCLUDED.key_technologies,
                delivery_reviewed_at = CASE
                    WHEN (existing.title, existing.company, existing.description)
                      IS NOT DISTINCT FROM (EXCLUDED.title, EXCLUDED.company, EXCLUDED.description)
                    THEN existing.delivery_reviewed_at
                END,
                hiring_model = EXCLUDED.hiring_model,
                clearance_required = EXCLUDED.clearance_required,
                match_score = CASE
                    WHEN EXCLUDED.company_blacklisted OR EXCLUDED.clearance_required THEN 0
                    WHEN existing.clearance_required OR (existing.title, existing.company, existing.description)
                         IS DISTINCT FROM (EXCLUDED.title, EXCLUDED.company, EXCLUDED.description) THEN NULL
                    WHEN existing.company_blacklisted THEN existing.score_before_blacklist
                    ELSE existing.match_score
                END,
                score_before_blacklist = CASE
                    WHEN EXCLUDED.company_blacklisted AND NOT EXCLUDED.clearance_required
                         AND (existing.title, existing.company, existing.description)
                             IS NOT DISTINCT FROM (EXCLUDED.title, EXCLUDED.company, EXCLUDED.description)
                    THEN CASE WHEN existing.company_blacklisted THEN existing.score_before_blacklist
                              ELSE existing.match_score END
                END,
                match_details = CASE
                    WHEN (existing.title, existing.company, existing.description, existing.clearance_required)
                      IS NOT DISTINCT FROM (EXCLUDED.title, EXCLUDED.company, EXCLUDED.description, EXCLUDED.clearance_required)
                    THEN existing.match_details
                END
            WHERE EXCLUDED.captured_at >= existing.captured_at
            """,
            (
                run_id, db_job_id, captured_at, capture["title"],
                capture.get("company"), capture.get("location"),
                capture["description"], capture.get("posted_label"),
                capture.get("posted_at"), capture.get("salary_text"),
                city, clearance_required, 0 if clearance_required or blacklisted else None, hiring_model,
                kind, fingerprint, technologies, key, blacklisted,
            ),
        )
    return db_job_id


def backfill_job_metadata(conn):
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT id, title, company, location, posted_label, description
               FROM public.linkedin_job_captures ORDER BY id FOR UPDATE"""
        )
        rows = cur.fetchall()
        for row in rows:
            city, clearance_required = derive_metadata(row)
            cur.execute(
                """UPDATE public.linkedin_job_captures
                   SET city = %s,
                       match_score = CASE WHEN %s OR company_blacklisted THEN 0
                                          WHEN clearance_required THEN NULL ELSE match_score END,
                       clearance_required = %s
                   WHERE id = %s""",
                (city, clearance_required, clearance_required, row["id"]),
            )
    return len(rows)


def classify_hiring_for_captures(conn, run_id=None):
    with conn.transaction():
        rows = conn.execute(
            """SELECT id, description FROM public.linkedin_job_captures
               WHERE %s::bigint IS NULL OR run_id = %s ORDER BY id FOR UPDATE""",
            (run_id, run_id),
        ).fetchall()
        counts = {"Direct hire": 0, "Outsourced": 0, None: 0}
        for capture_id, description in rows:
            model = classify_hiring_model(description)
            conn.execute(
                """UPDATE public.linkedin_job_captures SET hiring_model = %s
                   WHERE id = %s AND hiring_model IS DISTINCT FROM %s""",
                (model, capture_id, model),
            )
            counts[model] += 1
    return counts

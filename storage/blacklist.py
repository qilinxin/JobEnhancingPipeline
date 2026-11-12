"""Manage companies whose jobs are excluded from the library."""

import unicodedata

from psycopg.rows import dict_row

from .metadata import posting_fields


def company_key(name):
    text = unicodedata.normalize("NFKC", name or "").casefold()
    return "".join(character for character in text if character.isalnum())


def lock_company(cur, key):
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 3))", (key,))


def set_blacklisted(conn, name, reason="", *, remove=False):
    name = " ".join(name.split())
    reason = reason.strip()
    key = company_key(name)
    if not key or len(name) > 200 or len(reason) > 500:
        raise ValueError("Enter a company name of up to 200 characters and a reason of up to 500 characters.")

    with conn.transaction(), conn.cursor() as cur:
        lock_company(cur, key)
        if remove:
            cur.execute("DELETE FROM public.linkedin_company_blacklist WHERE company_key = %s", (key,))
            cur.execute(
                """UPDATE public.linkedin_job_captures
                   SET company_blacklisted = false,
                       match_score = CASE WHEN clearance_required THEN 0 ELSE score_before_blacklist END,
                       score_before_blacklist = NULL
                   WHERE company_key = %s AND company_blacklisted""",
                (key,),
            )
        else:
            cur.execute(
                """INSERT INTO public.linkedin_company_blacklist (company_key, company_name, reason)
                   VALUES (%s, %s, %s) ON CONFLICT (company_key) DO UPDATE
                   SET company_name = EXCLUDED.company_name, reason = EXCLUDED.reason""",
                (key, name, reason),
            )
            cur.execute(
                """UPDATE public.linkedin_job_captures
                   SET company_blacklisted = true, score_before_blacklist = match_score, match_score = 0
                   WHERE company_key = %s AND NOT company_blacklisted""",
                (key,),
            )
        return cur.rowcount


def backfill_company_keys(conn):
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT id, title, company, location, posted_label
               FROM public.linkedin_job_captures WHERE company_key IS NULL"""
        )
        for row in cur.fetchall():
            key = company_key(posting_fields(row)[0])
            cur.execute(
                "UPDATE public.linkedin_job_captures SET company_key = %s WHERE id = %s AND company_key IS NULL",
                (key, row["id"]),
            )

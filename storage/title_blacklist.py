"""Manage case-insensitive job title exclusions."""

import re

TITLE_ALLOWED = """
    NOT EXISTS (
        SELECT 1 FROM public.linkedin_title_blacklist b WHERE c.title ~* b.pattern
    )
"""


def title_exclusion_filter(conn):
    rows = conn.execute("SELECT pattern FROM public.linkedin_title_blacklist").fetchall()
    pattern = re.compile("|".join(row[0] for row in rows), re.IGNORECASE) if rows else None

    def excluded(title):
        return pattern is not None and pattern.search(title or "") is not None

    return excluded


def set_title_keyword(conn, keyword, *, remove=False):
    keyword = " ".join(keyword.lower().split())
    if not keyword or len(keyword) > 200 or "\x00" in keyword:
        raise ValueError("Enter a keyword or phrase of up to 200 characters.")

    if remove:
        conn.execute("DELETE FROM public.linkedin_title_blacklist WHERE keyword = %s", (keyword,))
    else:
        literal = r"\s+".join(re.escape(word) for word in keyword.split())
        pattern = rf"(?<!\w){literal}(?!\w)"
        conn.execute(
            """INSERT INTO public.linkedin_title_blacklist (keyword, pattern)
               VALUES (%s, %s) ON CONFLICT (keyword) DO NOTHING""",
            (keyword, pattern),
        )

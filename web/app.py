"""Serve a read-only view of the local PostgreSQL job captures."""

import argparse
import re
from datetime import date, datetime, time, timedelta
from html import escape, unescape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import parse_qs, quote, urlsplit
from zoneinfo import ZoneInfo

from psycopg import Error
from psycopg.rows import dict_row

from collector.job_boards import source_for_url
from storage.blacklist import set_blacklisted
from storage.metadata import posting_fields
from storage.postgres import connect

SYDNEY = ZoneInfo("Australia/Sydney")
STYLESHEET = Path(__file__).with_name("jobs_web.css").read_bytes()
APPLICATION_FILES = Path(__file__).resolve().parents[1] / "application_files"
CAPTURE_PATH = re.compile(r"/captures/([0-9]{1,18})(?:/download/(resume|cover-letter))?")
DOCUMENTS = {"resume": "Resume", "cover-letter": "Cover letter"}
DOCUMENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
VISIBLE_CAPTURES = """
    c.capture_kind <> 'duplicate' AND NOT c.company_blacklisted AND NOT c.clearance_required
    AND (c.match_score IS NULL OR c.match_score >= 50)
"""


def html(value):
    return escape(str(value)) if value is not None else ""


def local_time(value):
    return value.astimezone(SYDNEY).strftime("%Y-%m-%d %H:%M %Z")


def match_score(value):
    return str(int(value)) if value is not None else ""


def format_match_details(value):
    items = []
    for line in (value or "").splitlines():
        line = re.sub(r"^[-*•]\s+", "", line.strip())
        if not line:
            continue
        label, separator, content = line.partition(": ")
        if label == "Score breakdown" and separator:
            breakdown = re.match(
                r"((?:[^,\n]+?\s+\d+(?:\.\d+)?/\d+(?:\.\d+)?)(?:,\s*[^,\n]+?\s+\d+(?:\.\d+)?/\d+(?:\.\d+)?)*)"
                r"(?:\.\s*|$)",
                content,
            )
            if breakdown:
                scores = "".join(f"<li>{html(score.strip())}</li>" for score in breakdown[1].split(","))
                note = content[breakdown.end():]
                extra = f"<p>{html(note)}</p>" if note else ""
                items.append(f"<li><strong>{label}</strong><ul>{scores}</ul>{extra}</li>")
                continue
        if separator and label in {"Resume evidence", "Gaps and requirements to verify"}:
            items.append(f"<li><strong>{label}</strong><div>{html(content)}</div></li>")
        else:
            items.append(f"<li>{html(line)}</li>")
    return f'<ul class="match-details">{"".join(items)}</ul>' if items else ""


def model_label(row):
    if not row["delivery_reviewed_at"]:
        return "Pending review"
    return {
        "In-house": "In-house",
        "Client delivery": "Outsourced",
    }.get(row["reviewed_delivery_model"], "Unconfirmed")


def application_file(capture_id, kind):
    for suffix in DOCUMENT_TYPES:
        path = APPLICATION_FILES / str(capture_id) / f"{kind}{suffix}"
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved == path and resolved.is_file():
            return resolved
    return None


def application_company(row):
    company, _, _ = posting_fields(row)
    company_name = unescape(company or "").split(" (", 1)[0]
    company_name = re.sub(r"[^\w]+", "_", company_name).strip("_")[:40].rstrip("_")
    return company_name or f"Job_{row['id']}"


def application_filename(row, kind, suffix, *, include_role=False):
    parts = ["William", application_company(row)]
    if include_role:
        role_words = re.findall(r"[^\W_]+", unescape(row["title"] or ""))[:2]
        parts.extend(word[:20] for word in role_words)
    parts.append("Coverletter" if kind == "cover-letter" else kind)
    return "_".join(parts) + suffix


def layout(title, body):
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html(title)}</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <header class="top"><nav class="wrap top-nav" aria-label="Main navigation">
    <a href="/">Job Library</a>
    <a href="https://au.indeed.com/jobs?q=Java+Software+Engineer" target="_blank" rel="noopener">Search Indeed</a>
    <a href="https://www.seek.com.au/java-software-engineer-jobs" target="_blank" rel="noopener">Search SEEK</a>
    <a href="/blacklist">Company blacklist</a>
  </nav></header>
  <main class="wrap">{body}</main>
</body>
</html>"""


def company_blacklist(conn):
    rows = conn.execute(
        """SELECT b.company_name, b.reason, count(c.id)
           FROM public.linkedin_company_blacklist b
           LEFT JOIN public.linkedin_job_captures c ON c.company_key = b.company_key
           GROUP BY b.company_key ORDER BY lower(b.company_name)"""
    )
    companies = "".join(
        f"""<li><div><strong>{html(name)}</strong><div>{count} hidden captures</div>
{f'<div>{html(reason)}</div>' if reason else ''}</div>
<form action="/blacklist" method="post"><input type="hidden" name="company" value="{html(name)}">
<button name="action" value="remove">Remove</button></form></li>"""
        for name, reason, count in rows
    )
    return layout("Company blacklist", f"""
<h1>Company blacklist</h1>
<form class="blacklist-form" action="/blacklist" method="post">
  <label>Company name <input name="company" required maxlength="200"></label>
  <label>Reason <input name="reason" maxlength="500" placeholder="Optional"></label>
  <button name="action" value="add">Add company</button>
</form>
{f'<ul class="blacklist-companies">{companies}</ul>' if companies else '<p>No companies are blocked.</p>'}
""")


def list_jobs(conn, selected_date, *, show_applied=False):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT (captured_at AT TIME ZONE %s)::date AS day,
                      count(DISTINCT c.job_id) FILTER (WHERE {VISIBLE_CAPTURES}
                                        AND (j.applied_at IS NOT NULL) = %s) AS total
               FROM public.linkedin_job_captures c JOIN public.linkedin_jobs j ON j.id = c.job_id
               GROUP BY 1 ORDER BY 1 DESC""",
            (SYDNEY.key, show_applied),
        )
        dates = cur.fetchall()
        if not dates:
            return layout("Job Library", '<h1>Captured jobs</h1><p class="empty">No jobs have been captured yet.</p>')
        day = selected_date or dates[0]["day"]
        start = datetime.combine(day, time.min, tzinfo=SYDNEY)
        end = start + timedelta(days=1)
        cur.execute(
            f"""SELECT * FROM (
                   SELECT DISTINCT ON (c.job_id)
                          c.id, title, company, location, city, posted_label, captured_at,
                          match_score, delivery_reviewed_at, reviewed_delivery_model,
                          key_technologies, j.canonical_url
                   FROM public.linkedin_job_captures c JOIN public.linkedin_jobs j ON j.id = c.job_id
                   WHERE captured_at >= %s AND captured_at < %s
                     AND {VISIBLE_CAPTURES}
                     AND (j.applied_at IS NOT NULL) = %s
                   ORDER BY c.job_id, captured_at DESC, c.id DESC
               ) AS latest
               ORDER BY match_score DESC NULLS LAST, captured_at DESC, id DESC""",
            (start, end, show_applied),
        )
        rows = cur.fetchall()
    applied_query = "&amp;applied=1" if show_applied else ""
    tabs = []
    for entry in dates:
        capture_day = entry["day"]
        active = ' aria-current="page"' if capture_day == day else ""
        tabs.append(f'<a href="/?date={capture_day.isoformat()}{applied_query}"{active}>'
                    f'<time datetime="{capture_day.isoformat()}">{capture_day:%d %b %Y}</time>'
                    f'<span class="date-count">{entry["total"]}</span></a>')
    items = []
    action, button = ("unmark", "Undo") if show_applied else ("mark", "Applied")
    button_hint = "Undo applied status" if show_applied else "Mark as applied"
    for row in rows:
        company, _, _ = posting_fields(row)
        technologies = ", ".join(row["key_technologies"])
        in_house = {"In-house": "Y", "Outsourced": "N"}.get(model_label(row), "")
        items.append(f"""<tr>
  <th scope="row"><a class="job" href="/captures/{row['id']}">{html(row['title'])}</a></th>
  <td>{html(source_for_url(row['canonical_url']) or 'LinkedIn')}</td><td>{html(company)}</td><td>{html(row['city'])}</td>
  <td>{html(technologies)}</td><td>{in_house}</td>
  <td>{match_score(row['match_score'])}</td>
  <td><form action="/applied" method="post">
    <input type="hidden" name="capture_id" value="{row['id']}">
    <button class="applied-button" name="action" value="{action}" title="{button_hint}">{button}</button>
  </form></td>
</tr>""")
    content = f"""<div class="table-wrap" role="region" aria-label="Job list" tabindex="0">
  <table class="jobs" aria-label="Jobs captured on {day:%d %B %Y}">
    <colgroup><col class="title-col"><col class="source-col"><col class="company-col"><col class="city-col">
      <col class="technologies-col"><col class="delivery-col">
      <col class="score-col"><col class="applied-col"></colgroup>
    <thead><tr><th scope="col">Job title</th><th scope="col">Source</th><th scope="col">Company</th>
      <th scope="col">City</th>
      <th scope="col">Key technologies</th><th scope="col">In-house</th>
      <th scope="col" aria-sort="descending">Match score</th><th scope="col">Status</th></tr></thead>
    <tbody>{"".join(items)}</tbody>
  </table>
</div>""" if items else (
        '<p class="empty">No applied jobs on this date.</p>' if show_applied
        else '<p class="empty">No jobs match the current filters on this date.</p>'
    )
    count = f"{len(rows)} {'job' if len(rows) == 1 else 'jobs'}"
    heading = "Applied jobs" if show_applied else "Captured jobs"
    toggle_label = "Back to captured jobs" if show_applied else "Applied jobs"
    toggle_query = "" if show_applied else "&amp;applied=1"
    return layout(heading, f"""
<h1>{heading}</h1>
<p><a href="/?date={day.isoformat()}{toggle_query}">{toggle_label}</a></p>
<div class="library">
  <aside><h2>Capture dates</h2><nav class="dates" aria-label="Capture dates">{"".join(tabs)}</nav></aside>
  <section aria-labelledby="selected-date">
    <div class="list-heading"><h2 id="selected-date">{day:%d %B %Y}</h2><span>{count}</span></div>
    {content}
  </section>
</div>""")


def job_detail(conn, capture_id):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT c.*, j.linkedin_job_id, j.canonical_url
               FROM public.linkedin_job_captures AS c
               JOIN public.linkedin_jobs AS j ON j.id = c.job_id
               WHERE c.id = %s AND NOT c.company_blacklisted""",
            (capture_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    url = urlsplit(row["canonical_url"])
    link = ""
    source = source_for_url(row["canonical_url"])
    if url.scheme == "https" and url.hostname in {"www.linkedin.com", "linkedin.com"}:
        source = "LinkedIn"
    if source:
        link = (
            f'<a class="external" href="{html(row["canonical_url"])}" '
            f'target="_blank" rel="noopener">View on {source}</a>'
        )
    company, _, _ = posting_fields(row)
    delivery_review = "<p>Company research pending.</p>"
    if row["delivery_reviewed_at"]:
        model = model_label(row)
        sources = "".join(
            f'<li><a href="{html(source)}">{html(urlsplit(source).netloc)}</a></li>'
            for source in (row["delivery_review_sources"] or [])
            if source.startswith("https://") and urlsplit(source).hostname
        )
        source_list = f"<ul>{sources}</ul>" if sources else ""
        delivery_review = f"<p><strong>{html(model)}</strong></p><p>{html(row['delivery_review_notes'])}</p>{source_list}"
    fields = [
        ("Company", company),
        ("City", row["city"]),
        ("Salary", row["salary_text"]),
        ("LinkedIn job ID", row["linkedin_job_id"]),
        ("Captured", local_time(row["captured_at"])),
    ]
    metadata = "".join(
        f"<div><dt>{label}</dt><dd>{html(value)}</dd></div>" for label, value in fields if value
    )
    description = re.sub(r"\n(?:[^\S\n]*\n){2,}", "\n\n", row["description"])
    score = match_score(row["match_score"]) or "Not scored yet"
    details = format_match_details(row["match_details"])
    if row["clearance_required"]:
        clearance_note = "<p>Security clearance is required by this posting.</p>"
    else:
        clearance_note = ""
        details = details or "<p>No match details available yet.</p>"
    downloads = []
    for kind, label in DOCUMENTS.items():
        path = application_file(capture_id, kind)
        if path:
            downloads.append(
                f'<li><a href="/captures/{capture_id}/download/{kind}">'
                f'Download {label.lower()} ({path.suffix[1:].upper()})</a></li>'
            )
        else:
            downloads.append(f"<li>{label} <span>Not available yet</span></li>")
    return layout(row["title"], f"""
<div class="detail">
<a class="back" href="/?date={row['captured_at'].astimezone(SYDNEY).date().isoformat()}">‹ Back to captured jobs</a>
<h1>{html(row['title'])}</h1>
<dl>{metadata}</dl>
{link}
<section class="description"><h2>Match details</h2><p>Match score <strong>{score}</strong></p>
  {clearance_note}{details}</section>
<section class="description"><h2>Application documents</h2><ul class="documents">{"".join(downloads)}</ul></section>
<section class="description"><h2>Job description</h2><div class="prewrap">{html(description)}</div></section>
<section class="description"><h2>Model</h2>{delivery_review}</section>
</div>""")


class JobsHandler(BaseHTTPRequestHandler):
    def respond(self, status, body, content_type="text/html; charset=utf-8", filename=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            fallback = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
            disposition = f'attachment; filename="{fallback}"'
            if fallback != filename:
                disposition += f"; filename*=UTF-8''{quote(filename, safe='')}"
            self.send_header("Content-Disposition", disposition)
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        target = urlsplit(self.path)
        if target.path == "/style.css":
            self.respond(HTTPStatus.OK, STYLESHEET, "text/css; charset=utf-8")
            return
        capture = CAPTURE_PATH.fullmatch(target.path)
        try:
            if target.path == "/":
                query = parse_qs(target.query)
                value = query.get("date", [None])[0]
                try:
                    selected_date = date.fromisoformat(value) if value else None
                    if selected_date and not 1 < selected_date.year < 9999:
                        raise ValueError("Date is out of range")
                except ValueError:
                    self.respond(HTTPStatus.BAD_REQUEST, layout("Invalid date", "<h1>Invalid date</h1>"))
                    return
                with connect() as conn:
                    body = list_jobs(conn, selected_date, show_applied=query.get("applied") == ["1"])
            elif target.path == "/blacklist":
                with connect() as conn:
                    body = company_blacklist(conn)
            elif capture:
                capture_id = int(capture[1])
                kind = capture[2]
                with connect() as conn:
                    if kind:
                        with conn.cursor(row_factory=dict_row) as cur:
                            cur.execute(
                                """SELECT id, title, company, location, posted_label
                                   FROM public.linkedin_job_captures WHERE id = %s AND NOT company_blacklisted""",
                                (capture_id,),
                            )
                            row = cur.fetchone()
                        path = application_file(capture_id, kind) if row else None
                        if path:
                            try:
                                document = path.read_bytes()
                            except OSError:
                                pass
                            else:
                                with conn.cursor(row_factory=dict_row) as cur:
                                    cur.execute(
                                        """SELECT id, title, company, location, posted_label
                                           FROM public.linkedin_job_captures
                                           WHERE id <> %s AND (captured_at AT TIME ZONE %s)::date = (
                                               SELECT (captured_at AT TIME ZONE %s)::date
                                               FROM public.linkedin_job_captures WHERE id = %s
                                           )""",
                                        (capture_id, SYDNEY.key, SYDNEY.key, capture_id),
                                    )
                                    company_name = application_company(row).casefold()
                                    include_role = any(
                                        application_company(peer).casefold() == company_name
                                        and application_file(peer["id"], kind)
                                        for peer in cur
                                    )
                                filename = application_filename(row, kind, path.suffix, include_role=include_role)
                                self.respond(HTTPStatus.OK, document, DOCUMENT_TYPES[path.suffix], filename)
                                return
                        body = None
                    else:
                        body = job_detail(conn, capture_id)
            else:
                body = None
        except Error as exc:
            self.log_error("Database: %s", exc)
            self.respond(
                HTTPStatus.SERVICE_UNAVAILABLE,
                layout("Database unavailable", "<h1>Database unavailable</h1><p>Check your local PostgreSQL server and connection settings.</p>"),
            )
            return
        if body is None:
            title = "Document not found" if capture and capture[2] else "Capture not found"
            self.respond(HTTPStatus.NOT_FOUND, layout(title, f"<h1>{title}</h1>"))
        else:
            self.respond(HTTPStatus.OK, body)

    def do_POST(self):
        if self.path not in {"/blacklist", "/applied"}:
            self.respond(HTTPStatus.NOT_FOUND, layout("Page not found", "<h1>Page not found</h1>"))
            return
        port = self.server.server_port
        if self.headers.get("Origin") not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
            self.respond(HTTPStatus.FORBIDDEN, layout("Request rejected", "<h1>Open Job Library to make changes.</h1>"))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise ValueError("Invalid form size.")
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
            action = form.get("action", [""])[0]
            with connect() as conn:
                if self.path == "/blacklist":
                    if action not in {"add", "remove"}:
                        raise ValueError("Invalid blacklist action.")
                    set_blacklisted(conn, form.get("company", [""])[0], form.get("reason", [""])[0],
                                    remove=action == "remove")
                    redirect = "/blacklist"
                else:
                    capture_id = form.get("capture_id", [""])[0]
                    if action not in {"mark", "unmark"} or not re.fullmatch(r"[0-9]{1,18}", capture_id):
                        raise ValueError("Invalid application action.")
                    capture = conn.execute(
                        """UPDATE public.linkedin_jobs AS j
                           SET applied_at = CASE WHEN %s THEN COALESCE(j.applied_at, now()) ELSE NULL END
                           FROM public.linkedin_job_captures AS c
                           WHERE c.id = %s AND c.job_id = j.id AND NOT c.company_blacklisted
                           RETURNING c.captured_at""",
                        (action == "mark", int(capture_id)),
                    ).fetchone()
                    if capture is None:
                        self.respond(HTTPStatus.NOT_FOUND, layout("Capture not found", "<h1>Capture not found</h1>"))
                        return
                    captured_at, = capture
                    redirect = f"/?date={captured_at.astimezone(SYDNEY).date().isoformat()}"
                    if action == "unmark":
                        redirect += "&applied=1"
        except ValueError as exc:
            self.respond(HTTPStatus.BAD_REQUEST, layout("Invalid request", f"<p>{html(exc)}</p>"))
            return
        except Error as exc:
            self.log_error("Database: %s", exc)
            self.respond(HTTPStatus.SERVICE_UNAVAILABLE, layout("Database unavailable", "<h1>Database unavailable</h1>"))
            return
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", redirect)
        self.send_header("Content-Length", "0")
        self.end_headers()


class LocalJobsServer(ThreadingHTTPServer):
    def server_bind(self):
        # A loopback-only server already has its address. Skip reverse DNS.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with LocalJobsServer(("127.0.0.1", args.port), JobsHandler) as server:
        print(f"Job Library http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

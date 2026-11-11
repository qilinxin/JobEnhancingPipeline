"""Serve a read-only view of the local PostgreSQL job captures."""

import argparse
import re
from datetime import date, datetime, time, timedelta
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from psycopg import Error
from psycopg.rows import dict_row

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


def html(value):
    return escape(str(value)) if value is not None else ""


def local_time(value):
    return value.astimezone(SYDNEY).strftime("%Y-%m-%d %H:%M %Z")


def match_score(value):
    return f"{value.normalize():f}" if value is not None else ""


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
  <header class="top"><div class="wrap"><a href="/">Job Library</a></div></header>
  <main class="wrap">{body}</main>
</body>
</html>"""


def list_jobs(conn, selected_date):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT (captured_at AT TIME ZONE %s)::date AS day, count(*) AS total
               FROM public.linkedin_job_captures GROUP BY 1 ORDER BY 1 DESC""",
            (SYDNEY.key,),
        )
        dates = cur.fetchall()
        if not dates:
            return layout("Job Library", '<h1>Captured jobs</h1><p class="empty">No jobs have been captured yet.</p>')
        day = selected_date or dates[0]["day"]
        start = datetime.combine(day, time.min, tzinfo=SYDNEY)
        end = start + timedelta(days=1)
        cur.execute(
            """SELECT id, run_id, title, company, location, city, posted_label, posted_at,
                      match_score, delivery_reviewed_at, reviewed_delivery_model
               FROM public.linkedin_job_captures
               WHERE captured_at >= %s AND captured_at < %s
               ORDER BY match_score DESC NULLS LAST, captured_at DESC, id DESC""",
            (start, end),
        )
        rows = cur.fetchall()
    tabs = []
    for entry in dates:
        capture_day = entry["day"]
        active = ' aria-current="page"' if capture_day == day else ""
        tabs.append(f'<a href="/?date={capture_day.isoformat()}"{active}>'
                    f'<time datetime="{capture_day.isoformat()}">{capture_day:%d %b %Y}</time>'
                    f'<span class="date-count">{entry["total"]}</span></a>')
    items = []
    for row in rows:
        company, _, posted = posting_fields(row)
        posted = posted or (local_time(row["posted_at"]) if row["posted_at"] else None)
        items.append(f"""<tr>
  <th scope="row"><a class="job" href="/captures/{row['id']}">{html(row['title'])}</a></th>
  <td>{html(company)}</td><td>{html(row['city'])}</td><td>{html(posted)}</td>
  <td>{html(model_label(row))}</td>
  <td class="run">Run {row['run_id']}</td><td>{match_score(row['match_score'])}</td>
</tr>""")
    content = f"""<div class="table-wrap" role="region" aria-label="Job list" tabindex="0">
  <table class="jobs" aria-label="Jobs captured on {day:%d %B %Y}">
    <colgroup><col class="title-col"><col class="company-col"><col class="city-col">
      <col class="posted-col"><col class="delivery-col">
      <col class="run-col"><col class="score-col"></colgroup>
    <thead><tr><th scope="col">Job title</th><th scope="col">Company</th>
      <th scope="col">City</th><th scope="col">Posted</th>
      <th scope="col">Model</th><th scope="col">Batch</th>
      <th scope="col" aria-sort="descending">Match score</th></tr></thead>
    <tbody>{"".join(items)}</tbody>
  </table>
</div>""" if items else '<p class="empty">No jobs captured on this date.</p>'
    count = f"{len(rows)} {'capture' if len(rows) == 1 else 'captures'}"
    return layout("Captured jobs", f"""
<h1>Captured jobs</h1>
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
               WHERE c.id = %s""",
            (capture_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    url = urlsplit(row["canonical_url"])
    link = ""
    if url.scheme == "https" and url.hostname in {"www.linkedin.com", "linkedin.com"}:
        link = f'<a class="external" href="{html(row["canonical_url"])}">View on LinkedIn</a>'
    company, _, posted = posting_fields(row)
    posted = posted or (local_time(row["posted_at"]) if row["posted_at"] else None)
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
        ("Posted", posted),
        ("Salary", row["salary_text"]),
        ("LinkedIn job ID", row["linkedin_job_id"]),
        ("Captured", local_time(row["captured_at"])),
        ("Run", row["run_id"]),
    ]
    metadata = "".join(
        f"<div><dt>{label}</dt><dd>{html(value)}</dd></div>" for label, value in fields if value
    )
    score = match_score(row["match_score"]) or "Not scored yet"
    details = html(row["match_details"])
    if row["clearance_required"]:
        clearance_note = "<p>Security clearance is required by this posting.</p>"
    else:
        clearance_note = ""
        details = details or "No match details available yet."
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
<section class="description"><h2>Job description</h2><div class="prewrap">{html(row['description'])}</div></section>
<section class="description"><h2>Model</h2>{delivery_review}</section>
<section class="description"><h2>Match details</h2><p>Match score <strong>{score}</strong></p>
  {clearance_note}<div class="prewrap">{details}</div></section>
<section class="description"><h2>Application documents</h2><ul class="documents">{"".join(downloads)}</ul></section>
</div>""")


class JobsHandler(BaseHTTPRequestHandler):
    def respond(self, status, body, content_type="text/html; charset=utf-8", filename=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'self'; base-uri 'none'; frame-ancestors 'none'")
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
                value = parse_qs(target.query).get("date", [None])[0]
                try:
                    selected_date = date.fromisoformat(value) if value else None
                    if selected_date and not 1 < selected_date.year < 9999:
                        raise ValueError("Date is out of range")
                except ValueError:
                    self.respond(HTTPStatus.BAD_REQUEST, layout("Invalid date", "<h1>Invalid date</h1>"))
                    return
                with connect() as conn:
                    body = list_jobs(conn, selected_date)
            elif capture:
                capture_id = int(capture[1])
                kind = capture[2]
                with connect() as conn:
                    if kind:
                        exists = conn.execute(
                            "SELECT 1 FROM public.linkedin_job_captures WHERE id = %s",
                            (capture_id,),
                        ).fetchone()
                        path = application_file(capture_id, kind) if exists else None
                        if path:
                            try:
                                document = path.read_bytes()
                            except OSError:
                                pass
                            else:
                                self.respond(HTTPStatus.OK, document, DOCUMENT_TYPES[path.suffix], path.name)
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

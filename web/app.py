"""Serve a read-only view of the local PostgreSQL job captures."""

import argparse
import re
from datetime import date, datetime, time, timedelta
from html import escape, unescape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from psycopg import Error
from psycopg.rows import dict_row

from documents.files import DOCUMENT_TYPES, document_file
from web.library_view import render_shell, render_library, CSS as LIBRARY_CSS, SCRIPT as LIBRARY_SCRIPT
from collector.job_boards import source_for_url
from storage.blacklist import set_blacklisted
from storage.metadata import posting_fields
from storage.postgres import connect
from storage.title_blacklist import TITLE_ALLOWED, set_title_keyword
from scoring.requirements import CATEGORY_LABELS, LEVELS
from storage.visibility import CLIENT_DELIVERY_PENALTY, DISPLAY_SCORE, SYDNEY, VISIBLE_CAPTURES

STYLESHEET = LIBRARY_CSS
CAPTURE_PATH = re.compile(r"/captures/([0-9]{1,18})(?:/download/(resume|cover-letter))?")
DOCUMENTS = {"resume": "Resume", "cover-letter": "Cover letter"}

def html(value):
    return escape(str(value)) if value is not None else ""


def local_time(value):
    return value.astimezone(SYDNEY).strftime("%Y-%m-%d %H:%M %Z")


def match_score(value):
    return f"{value:.2f}".rstrip("0").rstrip(".") if value is not None else ""


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


def format_requirement_ledger(ledger):
    """Show compact score dimensions; retain the source ledger in PostgreSQL."""
    if not isinstance(ledger, dict) or ledger.get("version") != 1:
        return ""
    rows = []
    for category, label in CATEGORY_LABELS.items():
        levels = (4, 3, 2, 1) if category in {"technical", "preferred"} else (None,)
        for level in levels:
            items = [item for item in ledger.get("requirements", [])
                     if item["category"] == category and (level is None or item["required_level"] == level)]
            if not items:
                continue
            dimension = html(label)
            if level is not None:
                dimension += f'<small>{html(LEVELS[level])} · weight {level}</small>'
            evidence = []
            for state, status in (("met", "Evidenced"), ("partial", "Partial"), ("unverified", "To confirm")):
                names = [html(item["name"]) for item in items if item["status"] == state]
                if names:
                    evidence.append(f'<span class="evidence-summary {state}"><strong>{status}:</strong> {", ".join(names)}.</span>')
            earned = sum(item["earned"] for item in items)
            available = sum(item["available"] for item in items)
            rows.append(f'<tr><th scope="row">{dimension}</th><td class="requirement-score">{earned:.2f} / {available:.2f}</td><td>{" ".join(evidence)}</td></tr>')
    return ('<div class="requirement-ledger"><table class="requirement-table"><thead><tr><th scope="col">Dimension</th><th scope="col">Score</th><th scope="col">Evidence / gaps</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table>'
            + f'<p class="rubric-note">Base score {ledger["base_score"]:.2f} · Java alignment ×{ledger.get("java_factor", 1):g}. '
              'Depth weights: expert 4, proficient 3, working knowledge 2, familiarity 1. '
              '“To confirm” means not evidenced in the current master.</p></div>')


def model_label(row):
    if not row["delivery_reviewed_at"]:
        return "Pending review"
    return {
        "In-house": "In-house",
        "Client delivery": "Outsourced",
    }.get(row["reviewed_delivery_model"], "Unconfirmed")


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


def layout(title, body, *, history=""):
    active = {"Company filters": "companies", "Title filters": "titles"}.get(title, "jobs")
    return render_shell(title, f'<div class="workspace-page">{body}</div>', active=active, history=history)


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
    return layout("Company filters", f"""
<div class="overline">Workspace preferences</div><h1>Company filters</h1>
<p class="subtitle">Hide companies you do not want to include in your job search.</p>
<form class="blacklist-form" action="/blacklist" method="post">
  <label>Company name <input name="company" required maxlength="200"></label>
  <label>Reason <input name="reason" maxlength="500" placeholder="Optional"></label>
  <button name="action" value="add">Add company</button>
</form>
{f'<ul class="blacklist-companies">{companies}</ul>' if companies else '<p>No company filters have been added.</p>'}
""")


def title_blacklist(conn):
    rows = conn.execute("SELECT keyword FROM public.linkedin_title_blacklist ORDER BY keyword")
    items = "".join(
        f"""<li><strong>{html(keyword)}</strong>
<form action="/title-blacklist" method="post">
  <input type="hidden" name="keyword" value="{html(keyword)}">
  <button name="action" value="remove">Remove</button>
</form></li>"""
        for (keyword,) in rows
    )
    return layout("Title filters", f"""
<div class="overline">Workspace preferences</div><h1>Title filters</h1>
<p>Matching job titles are skipped during collection and hidden from the Job Library.</p>
<form class="blacklist-form" action="/title-blacklist" method="post">
  <label>Title keyword or phrase <input name="keyword" required maxlength="200" placeholder="e.g. sales"></label>
  <button name="action" value="add">Add keyword</button>
</form>
{f'<ul class="blacklist-companies">{items}</ul>' if items else '<p>No title filters have been added.</p>'}
""")


def status_buttons(row, *, keyword=""):
    buttons = []
    for status, label, undo in (
        ("applied", "Applied", "Undo"),
        ("excluded", "Exclude", "Restore"),
    ):
        marked = row[f"{status}_at"] is not None
        action = "unmark" if marked else "mark"
        text = undo if marked else label
        endpoint = "/applied" if status == "applied" else "/excluded"
        search_field = f'<input type="hidden" name="q" value="{html(keyword)}">' if keyword else ""
        buttons.append(f"""
<form action="{endpoint}" method="post">
  <input type="hidden" name="capture_id" value="{row['id']}">
  {search_field}
  <button class="applied-button" name="action" value="{action}">{text}</button>
</form>""")
    return f'<div class="status-buttons">{"".join(buttons)}</div>'


def list_jobs(conn, selected_date, *, show_applied=False, show_excluded=False, keyword=""):
    status_filter = (
        "j.excluded_at IS NOT NULL" if show_excluded else
        f"j.excluded_at IS NULL AND (j.applied_at IS NOT NULL) = %s AND {VISIBLE_CAPTURES}"
    )
    status_params = () if show_excluded else (show_applied,)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT (captured_at AT TIME ZONE %s)::date AS day,
                      count(DISTINCT c.job_id) FILTER (WHERE {status_filter}) AS total
               FROM public.linkedin_job_captures c JOIN public.linkedin_jobs j ON j.id = c.job_id
               GROUP BY 1 ORDER BY 1 DESC""",
            (SYDNEY.key, *status_params),
        )
        dates = cur.fetchall()
        day = selected_date or (dates[0]["day"] if dates else datetime.now(SYDNEY).date())
        if keyword:
            job_filter = f"""NOT c.company_blacklisted AND {TITLE_ALLOWED}
                AND strpos(lower(concat_ws(' ', c.title, c.company, c.city, c.location,
                    array_to_string(c.key_technologies, ' '), c.description)), lower(%s)) > 0"""
            job_params = (keyword,)
        else:
            start = datetime.combine(day, time.min, tzinfo=SYDNEY)
            end = start + timedelta(days=1)
            job_filter = f"c.captured_at >= %s AND c.captured_at < %s AND {status_filter}"
            job_params = (start, end, *status_params)
        cur.execute(
            f"""SELECT * FROM (
                   SELECT DISTINCT ON (c.job_id)
                          c.id, title, company, location, city, posted_label, captured_at,
                          {DISPLAY_SCORE} AS display_score, delivery_reviewed_at, reviewed_delivery_model,
                          key_technologies, j.canonical_url, j.applied_at, j.excluded_at
                   FROM public.linkedin_job_captures c JOIN public.linkedin_jobs j ON j.id = c.job_id
                   WHERE {job_filter}
                     AND c.display_duplicate_of IS NULL
                   ORDER BY c.job_id, captured_at DESC, c.id DESC
               ) AS latest
               ORDER BY display_score DESC NULLS LAST, captured_at DESC, id DESC""",
            job_params,
        )
        rows = cur.fetchall()
    return render_library(rows, dates, day, show_applied=show_applied,
                          show_excluded=show_excluded, keyword=keyword)


def detail_capture_history(conn, selected_day):
    """Keep the default capture-date navigation available from a job detail."""
    rows = conn.execute(
        f"""SELECT (c.captured_at AT TIME ZONE %s)::date AS day,
                   count(DISTINCT c.job_id) FILTER (
                       WHERE j.applied_at IS NULL AND j.excluded_at IS NULL
                         AND {VISIBLE_CAPTURES}
                   ) AS total
            FROM public.linkedin_job_captures c
            JOIN public.linkedin_jobs j ON j.id = c.job_id
            GROUP BY 1 ORDER BY 1 DESC""",
        (SYDNEY.key,),
    ).fetchall()
    return "".join(
        f'<a class="day{ " active" if day == selected_day else ""}" '
        f'href="/?date={day.isoformat()}"'
        f'{ " aria-current=page" if day == selected_day else ""}>'
        f'<span>{day:%d %B}</span><small>{total}</small></a>'
        for day, total in rows
    )


def job_detail(conn, capture_id):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT c.*, {DISPLAY_SCORE} AS display_score, j.linkedin_job_id, j.canonical_url, j.applied_at, j.excluded_at
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
            f'<a href="{html(row["canonical_url"])}" '
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
    score = match_score(row["display_score"]) or "Not scored yet"
    score_note = ""
    if row["display_score"] != row["match_score"]:
        score_note = f' <span>(Base score {match_score(row["match_score"])}, outsourcing adjustment −{CLIENT_DELIVERY_PENALTY})</span>'
    details = format_match_details(row["match_details"])
    ledger = format_requirement_ledger(row.get("match_breakdown"))
    if ledger:
        details = ""
    if row["clearance_required"]:
        clearance_note = "<p>Security clearance is required by this posting.</p>"
    else:
        clearance_note = ""
        details = details or "<p>No match details available yet.</p>"
    downloads = []
    for kind, label in DOCUMENTS.items():
        path = document_file(capture_id, kind)
        if path:
            downloads.append(
                f'<a href="/captures/{capture_id}/download/{kind}">'
                f'Download {label.lower()} ({path.suffix[1:].upper()})</a>'
            )
        else:
            downloads.append(f'<span class="document-pending">{label} not generated yet</span>')
    return layout(row["title"], f"""
<div class="detail">
<a class="back" href="/?date={row['captured_at'].astimezone(SYDNEY).date().isoformat()}">‹ Back to captured jobs</a>
<div class="overline">Opportunity overview</div><h1>{html(row['title'])}</h1>
<dl>{metadata}</dl>
<nav class="detail-links" aria-label="Job and application links">{link}{"".join(downloads)}</nav>
{status_buttons(row)}
<section class="description"><h2>Match details</h2><p>Match score <strong>{score}</strong>{score_note}</p>
  {clearance_note}{details}{ledger}</section>
<section class="description"><h2>Job description</h2><div class="prewrap">{html(description)}</div></section>
<section class="description"><h2>Company research</h2>{delivery_review}</section>
</div>""", history=detail_capture_history(conn, row["captured_at"].astimezone(SYDNEY).date()))


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
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'self'; script-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        target = urlsplit(self.path)
        if target.path == "/style.css":
            self.respond(HTTPStatus.OK, STYLESHEET, "text/css; charset=utf-8")
            return
        if target.path == "/library.css":
            self.respond(HTTPStatus.OK, LIBRARY_CSS, "text/css; charset=utf-8")
            return
        if target.path == "/library.js":
            self.respond(HTTPStatus.OK, LIBRARY_SCRIPT, "text/javascript; charset=utf-8")
            return
        capture = CAPTURE_PATH.fullmatch(target.path)
        try:
            if target.path == "/":
                query = parse_qs(target.query)
                keyword = query.get("q", [""])[0].strip()
                if len(keyword) > 200 or "\x00" in keyword:
                    self.respond(HTTPStatus.BAD_REQUEST, layout("Invalid search", "<h1>Invalid search keyword</h1>"))
                    return
                value = query.get("date", [None])[0]
                try:
                    selected_date = date.fromisoformat(value) if value else None
                    if selected_date and not 1 < selected_date.year < 9999:
                        raise ValueError("Date is out of range")
                except ValueError:
                    self.respond(HTTPStatus.BAD_REQUEST, layout("Invalid date", "<h1>Invalid date</h1>"))
                    return
                with connect() as conn:
                    body = list_jobs(conn, selected_date, show_applied=not keyword and query.get("applied") == ["1"],
                                     show_excluded=not keyword and query.get("excluded") == ["1"], keyword=keyword)
            elif target.path == "/blacklist":
                with connect() as conn:
                    body = company_blacklist(conn)
            elif target.path == "/title-blacklist":
                with connect() as conn:
                    body = title_blacklist(conn)
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
                        path = document_file(capture_id, kind) if row else None
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
                                        and document_file(peer["id"], kind)
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
        if self.path not in {"/blacklist", "/title-blacklist", "/applied", "/excluded"}:
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
                        raise ValueError("Invalid filter action.")
                    set_blacklisted(conn, form.get("company", [""])[0], form.get("reason", [""])[0],
                                    remove=action == "remove")
                    redirect = "/blacklist"
                elif self.path == "/title-blacklist":
                    if action not in {"add", "remove"}:
                        raise ValueError("Invalid filter action.")
                    set_title_keyword(conn, form.get("keyword", [""])[0], remove=action == "remove")
                    redirect = "/title-blacklist"
                else:
                    capture_id = form.get("capture_id", [""])[0]
                    if action not in {"mark", "unmark"} or not re.fullmatch(r"[0-9]{1,18}", capture_id):
                        raise ValueError("Invalid application action.")
                    status_column = "excluded_at" if self.path == "/excluded" else "applied_at"
                    capture = conn.execute(
                        f"""UPDATE public.linkedin_jobs AS j
                           SET {status_column} = CASE WHEN %s THEN COALESCE(j.{status_column}, now()) ELSE NULL END
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
                    if keyword := form.get("q", [""])[0]:
                        redirect = "/?" + urlencode({"q": keyword})
                    elif action == "unmark":
                        redirect += "&excluded=1" if status_column == "excluded_at" else "&applied=1"
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

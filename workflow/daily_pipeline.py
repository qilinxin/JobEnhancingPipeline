"""Run collection, company review, scoring and document preparation in order."""

import argparse
from collections import defaultdict
from datetime import datetime
import subprocess
import sys

from playwright.sync_api import Error as BrowserError, sync_playwright
from psycopg import Error as DatabaseError

from documents.generate import prepare_documents
from collector import linkedin
from collector.job_boards import SELECTORS, source_for_url
from scoring.delivery_review import review_run
from scoring.match_review import score_run
from storage.postgres import connect, search_url_without_selection
from storage.visibility import SYDNEY
from .settings import SETTINGS

SOURCES = ("linkedin", "seek", "indeed")
DEFAULT_SOURCES = tuple(SETTINGS["workflow"]["sources"])
PIPELINE_LOCK = -1048576

def search_tabs(browser):
    tabs = defaultdict(list)
    for context in browser.contexts:
        for page in context.pages:
            path = page.url.split("?", 1)[0]
            if linkedin.is_linkedin(page.url) and "/jobs/search" in path:
                tabs["linkedin"].append(page)
            elif source_for_url(page.url) == "SEEK" and "-jobs" in path:
                tabs["seek"].append(page)
            elif source_for_url(page.url) == "Indeed" and path.rstrip("/").endswith("/jobs"):
                tabs["indeed"].append(page)
    return tabs


def collect_sources(cdp, sources, run_ids):
    failed = False
    print("Collecting job postings.")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(cdp, timeout=5000)
            tabs = search_tabs(browser)
            for source in sources:
                print(f"Collecting {source}.")
                if len(tabs[source]) != 1:
                    print(f"Expected one {source} search tab, found {len(tabs[source])}.", file=sys.stderr)
                    failed = True
                    continue
                page = tabs[source][0]
                try:
                    page.bring_to_front()
                    page.goto(search_url_without_selection(page.url), wait_until="domcontentloaded", timeout=15000)
                    if source == "linkedin":
                        page.locator(f"{linkedin.SEMANTIC_CARDS}, {linkedin.CARD_LINKS}").filter(
                            visible=True
                        ).first.wait_for(timeout=12000)
                    else:
                        board_name = "SEEK" if source == "seek" else "Indeed"
                        page.locator(SELECTORS[board_name]["cards"]).filter(visible=True).first.wait_for(
                            timeout=12000
                        )
                    args = argparse.Namespace(
                        run_id=None, title=None, all_pages=source != "indeed",
                        limit=100 if source == "indeed" else None, score_with_codex=False,
                    )
                    result = linkedin.collect(
                        page, args, BrowserError, defer_postprocessing=True, run_ids=run_ids,
                    )
                    failed |= bool(result)
                except (BrowserError, DatabaseError, OSError, ValueError, linkedin.StopCollection) as error:
                    print(f"{source} collection stopped: {str(error).splitlines()[0]}", file=sys.stderr)
                    failed = True
    except BrowserError as error:
        print(f"Could not connect to the dedicated Chrome window: {str(error).splitlines()[0]}", file=sys.stderr)
        return True
    return failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp", default=SETTINGS["workflow"]["cdp_url"])
    parser.add_argument("--source", action="append", choices=SOURCES,
                        help="Select sources explicitly. Repeat for multiple boards. Default: LinkedIn and SEEK.")
    parser.add_argument("--min-score", type=int, choices=range(101), metavar="0-100", default=SETTINGS["workflow"]["min_document_score"])
    parser.add_argument("--skip-documents", action="store_true", help="Stop after collecting, reviewing and scoring.")
    args = parser.parse_args()
    day = datetime.now(SYDNEY).date()
    print(f"Job Library pipeline for {day} (Australia/Sydney).")
    try:
        with connect() as conn:
            locked, = conn.execute("SELECT pg_try_advisory_lock(%s)", (PIPELINE_LOCK,)).fetchone()
            if not locked:
                print("A Job Library pipeline is already running.", file=sys.stderr)
                return 1
            run_ids = []
            failed = collect_sources(args.cdp, tuple(dict.fromkeys(args.source or DEFAULT_SOURCES)), run_ids)
            print("Reviewing companies.")
            for run_id in run_ids:
                failed |= bool(review_run(run_id))
            print("Scoring resume matches.")
            for run_id in run_ids:
                failed |= bool(score_run(run_id))
            if not args.skip_documents:
                print("Preparing application documents.")
                failed |= prepare_documents(conn, day, args.min_score)
            print(f"Job Library: http://127.0.0.1:8765/?date={day}")
            return int(failed)
    except (DatabaseError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"Pipeline stopped: {str(error).splitlines()[0]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

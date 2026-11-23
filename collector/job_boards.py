"""Shared browser reading and capture loop for Indeed and SEEK."""

import re
import sys
from datetime import datetime, timezone
from random import uniform
from time import sleep
from urllib.parse import urljoin, urlsplit

from storage.postgres import captured_urls, save_capture

from . import indeed, seek
from storage.title_blacklist import title_exclusion_filter

BOARDS = {"Indeed": indeed, "SEEK": seek}
SELECTORS = {name: board.SELECTORS for name, board in BOARDS.items()}
HOSTS = {host: name for name, board in BOARDS.items() for host in board.HOSTS}
ACCESS_PATH = re.compile(r"/(?:login|signin|sign-in|auth|challenge|checkpoint)(?:/|$)", re.I)
BLOCK_HEADING = re.compile(
    r"^(?:sign in|log in)(?:\s|$)|verify.{0,30}human|just a moment|access denied|"
    r"too many requests|security check|captcha|request blocked",
    re.I,
)


class BoardAccessError(ValueError):
    """The board requires user intervention."""


def source_for_url(url):
    parts = urlsplit(url)
    return HOSTS.get(parts.hostname) if parts.scheme == "https" else None


def canonical_job_url(href, base, source):
    url = urljoin(base, href)
    if source_for_url(url) != source:
        return None
    return BOARDS[source].canonical_job_url(urlsplit(url))

def check_board_access(page, source):
    if source_for_url(page.url) != source or ACCESS_PATH.search(urlsplit(page.url).path):
        raise BoardAccessError(f"{source} redirected to a sign-in, challenge, or external page.")
    challenge = page.locator(
        'iframe[src*="captcha"], iframe[title*="captcha" i], input[autocomplete="current-password"]'
    )
    if any(item.is_visible() for item in challenge.all()):
        raise BoardAccessError(f"{source} shows a sign-in form or CAPTCHA.")
    for item in page.locator('h1, h2, [role="alert"], [role="dialog"]').all():
        if item.is_visible() and BLOCK_HEADING.search(item.inner_text().strip()):
            raise BoardAccessError(f"{source} shows a sign-in prompt or access restriction.")


def board_cards(page, source, title_filter):
    check_board_access(page, source)
    if canonical_job_url(page.url, page.url, source):
        raise ValueError(f"Select a {source} search results tab.")
    cards = page.locator(SELECTORS[source]["cards"])
    found = {}
    for card in cards.all():
        if not card.is_visible():
            continue
        title = card.inner_text().strip()
        if not title or (title_filter and title_filter.casefold() not in title.casefold()):
            continue
        href = BOARDS[source].card_href(card)
        if url := canonical_job_url(href, page.url, source):
            found.setdefault(url, title)
    if not found:
        raise ValueError(f"No matching {source} cards found. Check the search tab and card selector.")
    return found


def read_board_job(page, source, url):
    response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
    if response and response.status in {401, 403, 429, 503}:
        message = f"{source} detail page returned HTTP {response.status}."
        if source == "Indeed" and response.status == 403:
            message += " Use a manually imported posting or an authorised integration."
        raise BoardAccessError(message)
    check_board_access(page, source)
    selectors = SELECTORS[source]
    description = page.locator(selectors["description"]).first
    description.wait_for(state="visible", timeout=8000)
    check_board_access(page, source)
    if canonical_job_url(page.url, url, source) != url:
        raise ValueError("The displayed job URL does not match the search card.")
    record = {"canonical_url": url}
    for field, selector in selectors.items():
        if field == "cards":
            continue
        element = page.locator(selector).first
        record[field] = element.inner_text().strip() if element.is_visible() else None
    if not record["title"] or not record["description"]:
        raise ValueError("The job title or description is empty.")
    record["captured_at"] = datetime.now(timezone.utc).isoformat()
    return record


def collect_board_cards(page, args, playwright_error, conn, run, source, cards, delay):
    seen = captured_urls(conn, run.id)
    excluded_title = title_exclusion_filter(conn)
    detail = page.context.new_page()
    failed = 0
    attempted = False
    try:
        if args.all_pages:
            urls = seek.result_urls(page, cards, board_cards, BoardAccessError, excluded_title)
        else:
            urls = (url for url, title in cards.items() if not excluded_title(title))
        for url in urls:
            if url in seen:
                continue
            if attempted:
                sleep(uniform(*delay))
            attempted = True
            check_board_access(page, source)
            try:
                record = read_board_job(detail, source, url)
            except BoardAccessError:
                raise
            except (playwright_error, ValueError) as exc:
                if source_for_url(detail.url) == source:
                    check_board_access(detail, source)
                error = f"Failed to read {url} | {str(exc).splitlines()[0]}"
                print(error, file=sys.stderr)
                run.errors.append(error)
                failed += 1
                continue
            if excluded_title(record["title"]):
                continue
            save_capture(conn, run.id, record)
            seen.add(url)
            run.saved += 1
            print(f"{record['title']} | {url}", flush=True)
            if run.saved == args.limit:
                break
    finally:
        detail.close()
    print(f"Saved {run.saved} jobs to PostgreSQL. Failed to read {failed}.", flush=True)
    return int(failed > 0 and (args.all_pages or run.saved == 0))

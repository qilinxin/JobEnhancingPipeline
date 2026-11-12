"""Collect jobs from a manually opened job search tab in Chrome."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from random import uniform
from time import monotonic, sleep
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from psycopg import Error as DatabaseError

from collector.job_boards import BoardAccessError, board_cards, collect_board_cards, source_for_url
from storage.delivery_review import review_run
from storage.match_review import score_run
from storage.postgres import captured_urls, collection_run, connect, save_capture

# Verify these against the live page in Chrome DevTools.
CARD_LINKS = (
    '.jobs-search-results-list a[href*="/jobs/view/"], '
    '.jobs-search-results-list a.job-card-list__title, '
    '.scaffold-layout__list a[href*="/jobs/view/"]'
)
DETAILS = {
    "panel": ".jobs-search__job-details--wrapper, .jobs-search__job-details, .scaffold-layout__detail",
    "title": ".job-details-jobs-unified-top-card__job-title h1, h1",
    "identity": ".job-details-jobs-unified-top-card__job-title a[href], h1 a[href]",
    "company": ".job-details-jobs-unified-top-card__company-name",
    "location": ".job-details-jobs-unified-top-card__primary-description-container .tvm__text",
    "description": "#job-details, .jobs-description__content",
    "posted_label": "time, .job-details-jobs-unified-top-card__primary-description-container .tvm__text--positive",
}
SEMANTIC_CARD_PREFIX = "job-card-component-ref-"
SEMANTIC_CARDS = f'[role="button"][componentkey^="{SEMANTIC_CARD_PREFIX}"]'
SEMANTIC_CARD_TITLE = 'p span[aria-hidden="true"]'
NEXT_PAGE = "Next"
CAPTURE_DELAY_SECONDS = (5, 30)
SEMANTIC_DETAILS = {
    "panel": '[data-sdui-screen$=".SemanticJobDetails"]',
    "identity": 'a[href*="/jobs/view/"]',
    "description_heading": "h2",
    "description_heading_text": "About the job",
}
MORE_BUTTON = re.compile(r"^(?:see more|show more|(?:…|\.\.\.)\s*more|\u67e5\u770b\u66f4\u591a|\u663e\u793a\u66f4\u591a|\u986f\u793a\u66f4\u591a)$", re.I)
CARD_POSTED = re.compile(r"\b(?:reposted\s+)?(?:\d+\s+(?:minutes?|hours?|days?|weeks?|months?|years?)\s+ago|just now)\b", re.I)
BLOCK_ELEMENTS = (
    'form[action*="login"], input[autocomplete="current-password"], '
    'iframe[src*="captcha"], iframe[title*="captcha" i], '
    'h1, h2, [role="alert"], [role="dialog"]'
)
BLOCK_TEXT = re.compile(
    r"^(?:sign in|log in|\u767b\u5f55|\u767b\u5165)\b|sign in to (?:view|continue)|"
    r"security (?:check|verification)|verify (?:that )?you(?: are|'re) human|captcha|"
    r"access (?:denied|restricted)|too many requests|temporarily restricted|"
    r"\u8bf7\u767b\u5f55|\u9a8c\u8bc1\u7801|\u5b89\u5168\u9a8c\u8bc1|\u8bbf\u95ee\u53d7\u9650|\u62d2\u7edd\u8bbf\u95ee|\u8bf7\u6c42\u8fc7\u591a",
    re.I,
)

SNAPSHOT = r"""({legacy, semantic}) => {
    const visible = el => el && el.getClientRects().length > 0 &&
        getComputedStyle(el).visibility === "visible";
    const find = (root, selector) =>
        [...root.querySelectorAll(selector)].find(visible);
    const semanticPanel = [...document.querySelectorAll(semantic.panel)]
        .find(panel => find(panel, semantic.identity));
    if (semanticPanel) {
        const title = find(semanticPanel, semantic.identity);
        const header = title?.closest("p")?.parentElement?.parentElement?.parentElement;
        const fields = (header?.querySelector(":scope > p")?.innerText || "").split("·")
            .map(text => text.trim());
        const heading = [...semanticPanel.querySelectorAll(semantic.description_heading)]
            .find(el => visible(el) && el.innerText.trim() === semantic.description_heading_text);
        const description = heading?.parentElement?.nextElementSibling;
        const aboveDescription = heading
            ? semanticPanel.innerText.split(heading.innerText, 1)[0] : header?.innerText || "";
        const posted = fields.find(text => /\b(?:ago|just now)\b/i.test(text))
            || aboveDescription.match(/\b(?:reposted\s+)?(?:\d+\s+(?:minutes?|hours?|days?|weeks?|months?|years?)\s+ago|just now)\b/i)?.[0]
            || "";
        return {
            title: title?.innerText.trim() || "",
            identity: title?.href || "",
            company: header?.firstElementChild?.innerText.trim() || "",
            location: fields[0] || "",
            posted_label: posted,
            posted_at: find(header || semanticPanel, "time[datetime]")?.getAttribute("datetime") || null,
            description: visible(description) ? description.innerText : "",
        };
    }
    const selectors = legacy;
    const panel = find(document, selectors.panel);
    if (!panel) return null;
    const get = key => find(panel, selectors[key]);
    const text = key => get(key)?.innerText?.trim() || "";
    const location = text("location").split("·", 1)[0].trim();
    const posted = [...panel.querySelectorAll(selectors.posted_label)]
        .filter(visible)
        .find(el => el.matches("time") ||
            /\b(?:ago|just now)\b|\u524d|\u521a\u521a|\u525b\u525b/i.test(el.innerText));
    return {
        title: text("title"),
        identity: get("identity")?.href || "",
        company: text("company"),
        location: /\b(?:ago|just now|applicants?)\b|\u524d|\u521a\u521a|\u525b\u525b|\u7533\u8bf7\u4eba/i.test(location)
            ? "" : location,
        description: get("description")?.innerText || "",
        posted_label: posted?.innerText?.trim() || "",
        posted_at: posted?.getAttribute("datetime") || null,
    };
}"""
SNAPSHOT_SELECTORS = {"legacy": DETAILS, "semantic": SEMANTIC_DETAILS}


class StopCollection(Exception):
    pass


def is_linkedin(url):
    host = urlsplit(url).hostname or ""
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def job_key(href, base="https://www.linkedin.com"):
    """Return the visible job ID and a tracking-free URL."""
    if not href:
        return "", ""
    absolute = urljoin(base, href)
    parts = urlsplit(absolute)
    if parts.scheme not in {"https", "http"} or not is_linkedin(absolute):
        return "", ""
    match = re.search(r"^/jobs/view/(?:[^/]+-)?(\d+)/?$", parts.path)
    if match:
        job_id = match[1]
        return job_id, f"https://www.linkedin.com/jobs/view/{job_id}/"
    if parts.path.startswith("/jobs/"):
        current = parse_qs(parts.query).get("currentJobId", [""])[0]
        if current.isascii() and current.isdecimal():
            return current, f"https://www.linkedin.com/jobs/view/{current}/"
    if parts.path.startswith("/jobs/view/") and parts.path.strip("/") != "jobs/view":
        return "", urlunsplit(("https", "www.linkedin.com", parts.path.rstrip("/") + "/", "", ""))
    return "", ""


def check_access(page):
    path = urlsplit(page.url).path
    if not is_linkedin(page.url):
        raise StopCollection(f"The tab navigated away from LinkedIn ({page.url}).")
    if path.startswith(("/login", "/uas/login", "/authwall", "/signup")):
        raise StopCollection("LinkedIn requires sign-in.")
    if path.startswith(("/checkpoint", "/challenge")):
        raise StopCollection("LinkedIn requires a security check or has restricted access.")
    blockers = page.locator(BLOCK_ELEMENTS)
    for blocker in blockers.all():
        if not blocker.is_visible():
            continue
        tag = blocker.evaluate("(el) => el.tagName")
        if tag in {"FORM", "INPUT", "IFRAME"}:
            raise StopCollection("The page shows a sign-in form or CAPTCHA.")
        label = blocker.inner_text().strip()
        if BLOCK_TEXT.search(label):
            raise StopCollection("LinkedIn shows a sign-in prompt, security check, or access restriction.")


def matching_detail(page, expected, previous, timeout=10):
    deadline = monotonic() + timeout
    last = None
    stable_since = None
    while monotonic() < deadline:
        check_access(page)
        detail = page.evaluate(SNAPSHOT, SNAPSHOT_SELECTORS)
        if detail:
            actual = job_key(detail["identity"], page.url)
            changed = (
                not previous
                or job_key(previous["identity"], page.url) == expected
                or detail["description"] != previous["description"]
            )
            if actual == expected and changed and detail["title"] and detail["description"].strip():
                if detail != last:
                    last = detail
                    stable_since = monotonic()
                elif detail["posted_label"] or detail["posted_at"] or monotonic() - stable_since >= 2:
                    return detail
            else:
                last = None
        page.wait_for_timeout(250)
    raise ValueError("The detail link did not confirm the current job, or the description did not load or still matches the previous job.")


def read_job(page, card, expected):
    card_text = card.evaluate("(el) => (el.closest('li, [role=button]') || el).innerText")
    previous = page.evaluate(SNAPSHOT, SNAPSHOT_SELECTORS)
    card.click(timeout=4000)
    detail = matching_detail(page, expected, previous)
    panel = page.locator(SEMANTIC_DETAILS["panel"]).filter(visible=True).first
    if panel.is_visible():
        panel = panel.get_by_role("heading", name=SEMANTIC_DETAILS["description_heading_text"],
                                  exact=True).locator("../..")
    else:
        panel = page.locator(DETAILS["panel"]).filter(visible=True).first
    more = panel.get_by_role("button", name=MORE_BUTTON).or_(
        panel.locator('button, [role="button"]').filter(has_text=MORE_BUTTON)
    ).filter(visible=True).first
    if more.is_visible():
        more.click(timeout=4000)
        if more.is_visible():
            more.wait_for(state="hidden", timeout=4000)
        detail = matching_detail(page, expected, previous)
    captured_at = datetime.now(timezone.utc).isoformat()
    card_labels = CARD_POSTED.findall(card_text or "")
    repost_label = next((label for label in card_labels if label.lower().startswith("reposted")), None)
    if repost_label or (not detail["posted_label"] and card_labels):
        detail["posted_label"] = repost_label or card_labels[0]
    del detail["identity"]
    return {
        "linkedin_job_id": expected[0],
        "canonical_url": expected[1],
        **detail,
        "captured_at": captured_at,
    }


def collect(page, args, playwright_error):
    source = source_for_url(page.url)
    if source:
        cards = board_cards(page, source, args.title)
    else:
        check_access(page)
        if not urlsplit(page.url).path.startswith(("/jobs/search", "/jobs/collections/")):
            raise StopCollection("Select a tab that shows LinkedIn Jobs search results.")
    run = None
    try:
        with connect() as conn, collection_run(
            conn, run_id=args.run_id, search_url=page.url, search_name=f"{source} Jobs" if source else None,
        ) as run:
            if source:
                result = collect_board_cards(
                    page, args, playwright_error, conn, run, source, cards, CAPTURE_DELAY_SECONDS,
                )
            else:
                result = collect_cards(page, args, playwright_error, conn, run)
    except (StopCollection, BoardAccessError, playwright_error):
        if run is not None and run.saved:
            postprocess_run(run.id, args.score_with_codex)
        raise
    postprocess_result = postprocess_run(run.id, args.score_with_codex)
    return result or postprocess_result


def postprocess_run(run_id, score_with_codex):
    review_result = review_run(run_id)
    if review_result:
        return review_result
    return score_run(run_id) if score_with_codex else 0


def page_cards(page, title_filter):
    semantic = page.locator(SEMANTIC_CARDS)
    if semantic.count():
        candidates = semantic.evaluate_all(
            """(cards, titleSelector) => cards.map(card => [
                card.getAttribute('componentkey'),
                card.querySelector(titleSelector)?.innerText.trim() || '',
            ])""",
            SEMANTIC_CARD_TITLE,
        )
        candidates = [
            (f"/jobs/view/{key.removeprefix(SEMANTIC_CARD_PREFIX)}/", title,
             f'{SEMANTIC_CARDS}[componentkey={json.dumps(key)}]')
            for key, title in candidates
        ]
    else:
        links = page.locator(CARD_LINKS).evaluate_all(
            "(links) => links.map(link => [link.getAttribute('href'), link.innerText.trim()])"
        )
        candidates = [
            (href, title, f":is({CARD_LINKS})[href={json.dumps(href, ensure_ascii=False)}]")
            for href, title in links
            if href
        ]
    cards = {}
    for href, title, selector in candidates:
        key = job_key(href, page.url)
        if key[1] and (not title_filter or title_filter.casefold() in title.casefold()):
            cards.setdefault(key, selector)
    return cards


def result_pages(page):
    visited = set()
    while True:
        check_access(page)
        cards = page_cards(page, None)
        signature = tuple(cards)
        if not signature or signature in visited:
            raise StopCollection("No new job list appeared after changing pages.")
        visited.add(signature)
        yield cards
        next_page = page.get_by_role("button", name=NEXT_PAGE, exact=True).filter(visible=True).first
        if not next_page.is_visible() or not next_page.is_enabled():
            return
        next_page.click(timeout=5000)
        deadline = monotonic() + 12
        while monotonic() < deadline:
            check_access(page)
            current = tuple(page_cards(page, None))
            if current and current not in visited:
                break
            page.wait_for_timeout(250)
        else:
            raise StopCollection("The job list did not change after clicking Next.")


def result_cards(page, args):
    if args.all_pages:
        for number, cards in enumerate(result_pages(page), 1):
            print(f"Results page {number} contains {len(cards)} job cards.", flush=True)
            yield from cards.items()
        return
    cards = page_cards(page, args.title)
    if not cards:
        raise StopCollection("No matching job cards were found on the current page.")
    yield from cards.items()


def collect_cards(page, args, playwright_error, conn, run):
    seen = captured_urls(conn, run.id) if args.all_pages else set()
    failed = 0
    attempted = False
    for expected, selector in result_cards(page, args):
        check_access(page)
        _, url = expected
        if url in seen:
            continue
        if attempted:
            sleep(uniform(*CAPTURE_DELAY_SECONDS))
            check_access(page)
        attempted = True
        try:
            record = read_job(page, page.locator(selector).first, expected)
        except (playwright_error, ValueError) as exc:
            check_access(page)
            error = f"Failed to read {url} | {str(exc).splitlines()[0]}"
            print(error, file=sys.stderr)
            run.errors.append(error)
            failed += 1
            if args.title and args.limit == 1:
                break
            continue
        save_capture(conn, run.id, record)
        run.saved += 1
        seen.add(url)
        print(f"{record['title']} | {url}", flush=True)
        if run.saved == args.limit:
            break
    print(f"Saved {run.saved} jobs to PostgreSQL. Failed to read {failed}.", flush=True)
    return int(failed > 0 and (args.all_pages or run.saved == 0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp", default="http://127.0.0.1:9222")
    parser.add_argument("--source", choices=("linkedin", "indeed", "seek"), default="linkedin")
    parser.add_argument("--list-tabs", action="store_true")
    parser.add_argument("--tab", type=int, help="Search tab number, starting at 1.")
    parser.add_argument("--limit", type=int, help="Maximum jobs to save. The single-page default is 5.")
    parser.add_argument("--all-pages", action="store_true", help="Collect all results from the current page onward.")
    parser.add_argument("--title", help="Collect only jobs whose card title contains this text.")
    parser.add_argument("--run-id", type=int, help="Reuse this database run ID when retrying.")
    parser.add_argument("--score-with-codex", action="store_true",
                        help="Send the resume text and job descriptions to Codex for match scoring.")
    args = parser.parse_args()
    if args.all_pages and args.source != "linkedin":
        parser.error("--all-pages is currently available for LinkedIn only.")
    if args.all_pages and args.title:
        parser.error("--all-pages and --title cannot be used together.")
    if args.limit is None and not args.all_pages:
        args.limit = 5
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be greater than 0.")
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        parser.exit(1, "Install playwright in the current virtual environment.\n")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(args.cdp, timeout=5000)
            pages = [
                page for context in browser.contexts for page in context.pages
                if (is_linkedin(page.url) if args.source == "linkedin"
                    else (source_for_url(page.url) or "").lower() == args.source)
            ]
            if args.list_tabs or (args.tab is None and len(pages) != 1):
                for number, page in enumerate(pages, 1):
                    print(f"{number}\t{page.title()}\t{page.url}")
                if not pages:
                    print(f"No tabs were found for {args.source}.")
                elif not args.list_tabs:
                    print("Use --tab to select a tab.")
                return 0 if args.list_tabs else 1
            tab = 1 if args.tab is None else args.tab
            if not 1 <= tab <= len(pages):
                raise StopCollection("Invalid tab number. Run --list-tabs again.")
            return collect(pages[tab - 1], args, Error)
    except (StopCollection, Error, DatabaseError, OSError, ValueError) as exc:
        print(f"Collection stopped | {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

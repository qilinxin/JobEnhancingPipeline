"""SEEK search-card, posting and pagination rules."""

import re
from urllib.parse import urljoin, urlsplit

HOSTS = ("www.seek.com.au", "seek.com.au", "au.seek.com")
SELECTORS = {
    "cards": 'a[data-automation="jobTitle"], article a[href*="/job/"]',
    "title": '[data-automation="job-detail-title"], h1',
    "company": '[data-automation="advertiser-name"]',
    "location": '[data-automation="job-detail-location"]',
    "description": '[data-automation="jobAdDetails"]',
    "posted_label": "time",
}


def card_href(card):
    return card.get_attribute("href") or ""


def canonical_job_url(parts):
    match = re.fullmatch(r"/job/([0-9]+)/?", parts.path)
    return f"https://www.seek.com.au/job/{match[1]}" if match else None


def result_urls(page, first_cards, read_cards, access_error, excluded_title):
    cards = first_cards
    visited = {page.url}
    number = 1
    while True:
        print(f"SEEK results page {number} contains {len(cards)} job cards.", flush=True)
        yield from (url for url, title in cards.items() if not excluded_title(title))
        next_page = page.get_by_role("link", name="Next", exact=True).filter(visible=True).first
        if not next_page.is_visible():
            return
        href = next_page.get_attribute("href")
        if not href:
            return
        url = urljoin(page.url, href)
        target = urlsplit(url)
        if target.scheme != "https" or target.hostname not in HOSTS or url in visited:
            raise access_error("SEEK did not provide a new results page.")
        response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
        if response and response.status in {401, 403, 429, 503}:
            raise access_error(f"SEEK returned HTTP {response.status}.")
        visited.add(url)
        page.locator(SELECTORS["cards"]).filter(visible=True).first.wait_for(state="visible", timeout=8000)
        cards = read_cards(page, "SEEK", None)
        number += 1

"""Open the project's saved searches in the dedicated Chrome profile."""

import sys
from urllib.parse import urlencode, urlsplit

from playwright.sync_api import Error, sync_playwright

from collector.job_boards import source_for_url

LINKEDIN_QUERY = "java software engineer hybrid or on-site posted in the past 24 hours"
SEARCH_URLS = {
    "LinkedIn": "https://www.linkedin.com/jobs/search-results/?" + urlencode({
        "keywords": LINKEDIN_QUERY,
        "location": "Australia",
        "geoId": "101452733",
        "origin": "SEMANTIC_SEARCH_LANDING_PAGE",
        "f_TPR": "r86400",
        "f_WT": "1,3",
    }),
    "Indeed": "https://au.indeed.com/jobs?" + urlencode({
        "q": "java software developer",
        "fromage": 1,
    }),
    "SEEK": "https://au.seek.com/java-developer-jobs?daterange=3&tags=new",
}


def open_searches(cdp_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url, timeout=5000)
        context = browser.contexts[0]
        for source, url in SEARCH_URLS.items():
            target = urlsplit(url)
            page = next(
                (tab for tab in context.pages if urlsplit(tab.url).hostname == target.hostname
                 and urlsplit(tab.url).path.rstrip("/") == target.path.rstrip("/")),
                None,
            )
            if page is None and source != "LinkedIn":
                page = next((tab for tab in context.pages if source_for_url(tab.url) == source), None)
            if page is None:
                page = next((tab for tab in context.pages if tab.url == "about:blank"), None)
            if page is None:
                page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=12000)
                if source == "SEEK":
                    select_new_to_you(page)
            except Error:
                print(f"Check the {source} search tab in Chrome.", file=sys.stderr)


def select_new_to_you(page):
    control = page.locator('[data-automation="newToYouFilterPill"]:visible').first
    try:
        control.wait_for(state="visible", timeout=3500)
        if control.get_attribute("aria-checked") != "true":
            control.click(timeout=3500)
        page.wait_for_url(lambda url: "tags=new" in url, timeout=3500)
    except Error:
        print("SEEK: Select New to you in Chrome if available.", file=sys.stderr)


if __name__ == "__main__":
    try:
        open_searches(sys.argv[1])
    except Error as exc:
        sys.exit(f"Could not open searches in debugging Chrome: {exc}")

"""Indeed Australia search-card and posting rules."""

import re
from urllib.parse import parse_qs

HOSTS = ("au.indeed.com",)
SELECTORS = {
    "cards": 'a[data-jk], a.jcs-JobTitle, h2 a[href*="/viewjob"]',
    "title": '[data-testid="jobsearch-JobInfoHeader-title"], h1',
    "company": '[data-testid="inlineHeader-companyName"], [data-testid="company-name"]',
    "location": '[data-testid="job-location"], [data-testid="inlineHeader-companyLocation"]',
    "description": "#jobDescriptionText",
    "posted_label": "time",
}


def card_href(card):
    key = card.get_attribute("data-jk")
    return f"/viewjob?jk={key}" if key else card.get_attribute("href") or ""


def canonical_job_url(parts):
    if parts.path != "/viewjob":
        return None
    key = parse_qs(parts.query).get("jk", [""])[0]
    if re.fullmatch(r"[a-fA-F0-9]{16}", key):
        return f"https://au.indeed.com/viewjob?jk={key.lower()}"
    return None

"""Derive display and screening fields from the original LinkedIn capture."""

import re

METRO_NAMES = {
    "brisbane city": "Brisbane",
    "carlton": "Melbourne",
    "greater melbourne area": "Melbourne",
    "greater sydney area": "Sydney",
    "hornsby": "Sydney",
    "woollahra": "Sydney",
}
NON_CITY_LOCATIONS = {
    "australia", "australian capital territory", "new south wales", "northern territory",
    "queensland", "south australia", "tasmania", "victoria", "western australia",
    "act", "nsw", "nt", "qld", "sa", "tas", "vic", "wa", "remote", "hybrid", "on-site",
}
CLEARANCE_TERM = (
    r"(?:\b(?:government |defence )?security clearance\b|"
    r"\b(?:nv[\s-]*[12]|negative vetting(?:\s+level)?\s*(?:one|two|[12])|"
    r"positive vetting)\b|\b(?:baseline|pv) clearance\b)"
)
CLEARANCE_OPTIONAL = re.compile(
    r"\b(?:not (?:strictly )?(?:required|mandatory|needed|necessary)|no (?:active |current )?"
    r"(?:government |defence )?security clearance|optional|preferred|desirable|"
    r"nice to have|advantageous|a plus|an advantage)\b", re.I,
)
CLEARANCE_REQUIRED = re.compile(
    rf"(?:\b(?:must|requires?|required to|need to|eligible to|ability to)\b.{{0,115}}{CLEARANCE_TERM}|"
    rf"{CLEARANCE_TERM}.{{0,65}}\b(?:required|mandatory|essential|a must|is must|ability to obtain)\b|"
    r"^\W*(?:(?:government |defence )?security clearance\s*:\s*)?"
    r"(?:(?:active|current|valid)\s+)?"
    r"(?:nv[\s-]*[12]|negative vetting(?:\s+level)?\s*(?:one|two|[12])|positive vetting|baseline clearance)"
    r"(?:\s+(?:security )?clearance)?\W*$|"
    r"^\W*security clearance\s*:\s*(?:baseline|nv[\s-]*[12]|pv|positive vetting)\W*$)",
    re.I,
)
OUTSOURCED_HIRE = re.compile(
    r"\b(?:this (?:is|will be) an outsourced (?:role|position)|"
    r"(?:this|the) (?:role|position) (?:is|will be) outsourced|"
    r"hiring model\s*:\s*outsourced|"
    r"(?:be|are|will be) seconded to (?:our |a |the )?client|"
    r"labou?r hire (?:role|position|engagement|arrangement)|"
    r"(?:employed by us|on our payroll)[^.!?;]{0,90}"
    r"(?:placed with|assigned to|working (?:at|for)) (?:our |a |the )?client)\b", re.I,
)
DIRECT_HIRE = re.compile(
    r"\b(?:hiring model\s*:\s*direct hire|this (?:is|will be) (?:a )?direct hire|"
    r"direct employment (?:with|by) (?:the (?:client|employer|company)|us)|"
    r"(?:you(?:'ll| will) be|successful (?:candidate|applicant) will be) "
    r"(?:employed|hired) directly by)\b", re.I,
)
HIRING_NEGATION = re.compile(r"\b(?:not (?:an? )?|no |rather than )$", re.I)


def classify_hiring_model(description):
    """Classify the hiring arrangement when the posting states it explicitly."""
    text = " ".join(description.split())
    labels = {
        label
        for label, pattern in (("Outsourced", OUTSOURCED_HIRE), ("Direct hire", DIRECT_HIRE))
        if any(not HIRING_NEGATION.search(text[:match.start()]) for match in pattern.finditer(text))
    }
    return labels.pop() if len(labels) == 1 else None


def posting_fields(capture):
    company = capture.get("company")
    location = capture.get("location")
    posted = capture.get("posted_label")
    if company and not location:
        # Some earlier captures stored the complete LinkedIn header as company.
        lines = [line.strip() for line in company.splitlines() if line.strip()]
        if len(lines) == 2 and lines[0] == capture["title"] and " • " in lines[1]:
            company, location = lines[1].split(" • ", 1)
        elif len(lines) >= 3 and lines[1] == capture["title"] and " · " in lines[2]:
            location, label, *_ = lines[2].split(" · ")
            company = lines[0]
            if not posted and re.search(r"\b(?:ago|just now)\b", label, re.I):
                posted = label
    return company, location, posted


def derive_metadata(capture):
    _, location, _ = posting_fields(capture)
    locality = re.sub(r"\s*\([^)]*\)\s*$", "", (location or "").split(",", 1)[0]).strip()
    city = None if locality.casefold() in NON_CITY_LOCATIONS else (
        METRO_NAMES.get(locality.casefold(), locality) or None
    )
    description = capture["description"]
    clauses = re.split(r"[.!?;]\s+|\n", description)
    clearance_required = any(
        CLEARANCE_REQUIRED.search(clause) and not CLEARANCE_OPTIONAL.search(clause)
        for clause in (" ".join(part.split()).rstrip(".") for part in clauses)
    )
    return city, clearance_required

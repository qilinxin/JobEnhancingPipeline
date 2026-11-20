"""Classify captures and extract technology names from their descriptions."""

import argparse
import hashlib
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from psycopg.rows import dict_row

from .metadata import posting_fields

REPOST = re.compile(r"\bre[- ]?posted\b|\u91cd\u65b0\u53d1\u5e03|\u91cd\u65b0\u767c\u5e03", re.I)
TECHNOLOGIES = (
    ("Java", r"Java(?:\s+\d+)?|JDK"),
    ("Spring Boot", r"Spring Boot"), ("Spring", r"Spring(?! Boot)"),
    ("Kafka", r"(?:Apache )?Kafka"), ("Kubernetes", r"Kubernetes|K8s|GKE|AKS|EKS"),
    ("AWS", r"AWS|Amazon Web Services"), ("Azure", r"(?:Microsoft )?Azure"),
    ("Google Cloud", r"Google Cloud(?: Platform)?|GCP"),
    ("Python", r"Python"), ("TypeScript", r"TypeScript"), ("JavaScript", r"JavaScript"),
    ("React", r"React(?:\.js|JS)?"), ("AngularJS", r"AngularJS"), ("Angular", r"Angular(?!JS)"),
    ("Node.js", r"Node(?:\.js|JS)"), ("Vue", r"Vue(?:\.js|JS)?"),
    (".NET", r"\.NET(?: Core)?|ASP\.NET"), ("C#", r"C#"), ("C++", r"C\+\+"),
    ("Go", r"Golang|Go\s+(?:programming|services|developers?)"),
    ("SQL", r"SQL"), ("SQL Server", r"(?:Microsoft )?SQL Server|MSSQL"),
    ("PostgreSQL", r"PostgreSQL|Postgres"), ("MySQL", r"MySQL"),
    ("Oracle", r"Oracle(?: Database)?"), ("MongoDB", r"MongoDB"),
    ("Redis", r"Redis"), ("DynamoDB", r"DynamoDB"), ("NoSQL", r"NoSQL"),
    ("Hibernate", r"Hibernate"), ("JPA", r"JPA|Jakarta Persistence"), ("MyBatis", r"MyBatis(?: Plus)?"),
    ("REST APIs", r"REST(?:ful)?(?: APIs?)?"), ("GraphQL", r"GraphQL"), ("SOAP", r"SOAP"),
    ("Microservices", r"microservices?"), ("Event-driven architecture", r"event[- ]driven"),
    ("Docker", r"Docker"), ("Terraform", r"Terraform"), ("Helm", r"Helm"),
    ("CloudFormation", r"CloudFormation"), ("Linux", r"Linux"), ("Bash", r"Bash|shell scripting"),
    ("CI/CD", r"CI\s*/\s*CD|continuous integration"), ("Jenkins", r"Jenkins"),
    ("GitHub Actions", r"GitHub Actions"), ("Git", r"Git"), ("Maven", r"Maven"), ("Gradle", r"Gradle"),
    ("JUnit", r"JUnit"), ("Playwright", r"Playwright"), ("Selenium", r"Selenium"),
    ("Cypress", r"Cypress"), ("Postman", r"Postman"), ("WireMock", r"WireMock"),
    ("Prometheus", r"Prometheus"), ("Grafana", r"Grafana"), ("Splunk", r"Splunk"),
    ("Datadog", r"Datadog"), ("OpenTelemetry", r"OpenTelemetry"), ("ELK", r"ELK|Elastic Stack"),
    ("OAuth 2.0", r"OAuth\s*2(?:\.0)?"), ("OpenID Connect", r"OpenID Connect|OIDC"),
    ("JWT", r"JWT"), ("OpenAPI", r"OpenAPI|Swagger"),
    ("Spark", r"(?:Apache )?Spark"), ("Databricks", r"Databricks"), ("Snowflake", r"Snowflake"),
    ("Airflow", r"(?:Apache )?Airflow"), ("LLMs", r"LLMs?|large language models?"),
    ("RAG", r"RAG|retrieval[- ]augmented generation"), ("LangGraph", r"LangGraph"),
    ("Salesforce", r"Salesforce"), ("ServiceNow", r"ServiceNow"),
    ("Power Platform", r"Power Platform|Power Automate"), ("Dynamics 365", r"Dynamics 365"),
)
TECH_PATTERNS = [(label, re.compile(r"(?<![\w.])(?:" + term + r")(?!\w)", re.I))
                 for label, term in TECHNOLOGIES]
REQUIREMENT = re.compile(
    r"\b(?:must|required|essential|proficien\w*|hands[- ]on|experience (?:with|in)|"
    r"strong knowledge|expertise|technical skills)\b", re.I,
)
PREFERENCE = re.compile(r"\b(?:preferred|desirable|nice to have|advantageous|bonus)\b", re.I)


def key_technologies(description):
    scores = {}
    for line in description.splitlines():
        weight = 1 if PREFERENCE.search(line) else (4 if REQUIREMENT.search(line) else 2)
        for name, pattern in TECH_PATTERNS:
            if pattern.search(line):
                scores[name] = scores.get(name, 0) + weight
    return sorted(scores, key=scores.get, reverse=True)[:5]


# Contact redaction and board formatting must not create new posting identities.
EMAIL = re.compile(r"[\w.+•-]+@[\w.-]+\.[a-z]{2,}", re.I)
PHONE = re.compile(
    r"(?<!\w)(?:\+61[ \t]*|0[23478]|1[38])"
    r"(?:[ \t().-]*[\d•]){7,10}(?!\w)"
)
COMPANY_REGION = re.compile(r"\s*\((?:ACT|QLD|NSW|VIC|WA|SA|NT|TAS)\)\s*$", re.I)
LOCATION_SUFFIX = re.compile(
    r"\b(?:new south wales|queensland|victoria|western australia|south australia|"
    r"australian capital territory|northern territory|tasmania|nsw|qld|vic|wa|sa|act|nt|tas|australia)\b",
    re.I,
)


def posting_text(value):
    text = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(re.sub(r"[^\w+#$<>]+", " ", text).split())


def posting_location(location, description=""):
    modes = (("onsite", r"\bon[ -]?site\b"), ("hybrid", r"\bhybrid\b"),
             ("remote", r"\bremote\b"))
    mode = next((name for name, pattern in modes if re.search(pattern, location or "", re.I)), "")
    if not mode:
        if re.search(r"\bfull[ -]time on[ -]?site\b", description, re.I):
            mode = "onsite"
        elif re.search(r"\b(?:fully|100%) remote\b", description, re.I):
            mode = "remote"
    location = re.sub(r"\([^)]*\)", "", location or "")
    # Prefer the metro name when a board includes both suburb and city.
    for city in ("sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra", "hobart", "darwin"):
        if re.search(r"\b" + city + r"\b", location, re.I):
            return city + "|" + mode
    locality = posting_text(LOCATION_SUFFIX.sub("", location))
    return locality + "|" + mode if locality else ""


def posting_features(capture):
    company, location, posted = posting_fields(capture)
    description = EMAIL.sub(" contactemail ", capture["description"])
    description = PHONE.sub(" contactphone ", description)
    description = re.sub(r"^\s*Job Description\s+", "", description, flags=re.I)
    description = re.sub(r"\s*(?:#hybrid|#LI|Apply for This Job)\s*$", "", description, flags=re.I)
    normalized = [
        posting_text(capture["title"]),
        posting_text(COMPANY_REGION.sub("", company or "")),
        posting_location(location, capture["description"]),
        posting_text(description),
    ]
    # Include location so identical templates in different cities stay separate.
    fingerprint = hashlib.sha256("\x1f".join(normalized).encode()).hexdigest() if all(normalized) else None
    return fingerprint, bool(REPOST.search(posted or "")), key_technologies(capture["description"])


POST_AGE = re.compile(r"\b(\d+)\s*(minute|hour|day|week)s?\s+ago\b", re.I)
AGE_UNITS = {"minute": 60, "hour": 3600, "day": 86400, "week": 604800}


def posting_window(posted_at, label, captured_at):
    """Return the possible publication interval based on the available precision."""
    if isinstance(posted_at, str):
        try:
            posted_at = datetime.fromisoformat(posted_at)
        except ValueError:
            posted_at = None
    if posted_at and posted_at.utcoffset() is not None:
        return posted_at, posted_at
    captured_at = captured_at.astimezone(timezone.utc)
    match = POST_AGE.search(label or "")
    if match:
        unit = timedelta(seconds=AGE_UNITS[match[2].lower()])
        upper = captured_at - int(match[1]) * unit
        return upper - unit, upper
    if re.search(r"\bjust now\b", label or "", re.I):
        return captured_at - timedelta(minutes=1), captured_at
    return None


def classify_capture(repost, window, previous):
    if not previous:
        return "repost" if repost else "new"
    if repost and window and all(prior and window[0] > prior[1] for prior in previous):
        return "repost"
    return "duplicate"


def backfill(conn, *, fingerprints_only=False):
    seen_jobs, seen_postings = defaultdict(list), defaultdict(list)
    seen_in_run = set()
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT id, run_id, job_id, title, company, location, posted_label, posted_at, captured_at, description
                       FROM public.linkedin_job_captures ORDER BY captured_at, id FOR UPDATE""")
        for capture in cur.fetchall():
            fingerprint, repost, technologies = posting_features(capture)
            if fingerprints_only:
                cur.execute("UPDATE public.linkedin_job_captures SET posting_fingerprint = %s WHERE id = %s",
                            (fingerprint, capture["id"]))
                continue
            job, run = capture["job_id"], capture["run_id"]
            repeated_in_run = fingerprint and (run, fingerprint) in seen_in_run
            window = posting_window(capture["posted_at"], capture["posted_label"], capture["captured_at"])
            previous = seen_jobs[job] + (seen_postings[fingerprint] if fingerprint else [])
            kind = "duplicate" if repeated_in_run else classify_capture(repost, window, previous)
            cur.execute("""UPDATE public.linkedin_job_captures SET capture_kind = %s,
                           posting_fingerprint = %s, key_technologies = %s WHERE id = %s""",
                        (kind, fingerprint, technologies, capture["id"]))
            seen_jobs[job].append(window)
            if fingerprint:
                seen_postings[fingerprint].append(window)
                seen_in_run.add((run, fingerprint))


def main():
    from .postgres import connect

    parser = argparse.ArgumentParser(description="Backfill capture classification and key technologies.")
    parser.add_argument("--fingerprints-only", action="store_true",
                        help="Refresh posting identities while preserving classifications and application status.")
    args = parser.parse_args()
    with connect() as conn:
        backfill(conn, fingerprints_only=args.fingerprints_only)


if __name__ == "__main__":
    main()

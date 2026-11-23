"""Validate requirement evidence and calculate an auditable score ledger."""
import re
import unicodedata

CATEGORY_POINTS = {"technical": 45, "experience": 25, "domain": 20, "preferred": 10}
CATEGORY_LABELS = {"technical": "Required technical skills", "experience": "Experience and scope",
                   "domain": "Domain and responsibilities", "preferred": "Preferred qualifications"}
LEVELS = {0: "No evidence", 1: "Familiarity / exposure", 2: "Working knowledge",
          3: "Hands-on proficiency", 4: "Expert / production ownership"}


def normalized(text):
    text = unicodedata.normalize("NFKC", text).translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"}))
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip().casefold()


def calculate_requirements(items, description, resume):
    if not items:
        raise ValueError("No job requirements were returned.")
    totals = {}
    seen = set()
    for item in items:
        category = item["category"]
        level, evidence = item["required_level"], item["evidence_level"]
        if category not in CATEGORY_POINTS or level not in (1, 2, 3, 4) or evidence not in LEVELS:
            raise ValueError("Invalid requirement category or evidence level.")
        key = (category, normalized(item["name"]))
        if key in seen or not key[1]:
            raise ValueError("Empty or duplicate requirement.")
        seen.add(key)
        if not normalized(item["jd_quote"]) or normalized(item["jd_quote"]) not in normalized(description):
            raise ValueError(f"Requirement quote is not present in the job description: {item['name']}")
        quote = normalized(item["resume_quote"])
        if evidence and (not quote or quote not in normalized(resume)):
            raise ValueError(f"Evidence quote is not present in the verified resume master: {item['name']}")
        totals[category] = totals.get(category, 0) + level
    normalization = 100 / sum(CATEGORY_POINTS[c] for c in totals)
    ledger = []
    for item in items:
        maximum = CATEGORY_POINTS[item["category"]] * normalization * item["required_level"] / totals[item["category"]]
        credit = min(item["evidence_level"] / item["required_level"], 1)
        ledger.append(dict(item, available=maximum, earned=maximum * credit,
                           status="met" if credit == 1 else "partial" if credit else "unverified"))
    score = round(sum(item["earned"] for item in ledger), 2)
    breakdown = ", ".join(f"{CATEGORY_LABELS[c]} {sum(i['earned'] for i in ledger if i['category']==c):.2f}/{CATEGORY_POINTS[c]*normalization:.2f}"
                          for c in CATEGORY_POINTS if c in totals)
    return score, {"version": 1, "base_score": score, "requirements": ledger}, breakdown

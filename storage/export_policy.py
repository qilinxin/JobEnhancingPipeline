"""Export current database filters to an ignored local policy snapshot."""
import json
from pathlib import Path
from storage.postgres import connect


def main():
    target = Path(__file__).resolve().parents[1] / "local/policy/database_filters.json"
    with connect() as conn:
        titles = conn.execute("SELECT keyword, pattern FROM public.linkedin_title_blacklist ORDER BY keyword").fetchall()
        companies = conn.execute("SELECT company_name, reason FROM public.linkedin_company_blacklist ORDER BY company_name").fetchall()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"title_filters": [dict(zip(("keyword", "pattern"), row)) for row in titles],
                                 "company_filters": [dict(zip(("company", "reason"), row)) for row in companies]},
                                indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Exported database filters to {target}")


if __name__ == "__main__":
    main()

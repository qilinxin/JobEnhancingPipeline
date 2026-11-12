"""Run database maintenance and import captures from external files."""

import argparse
import json
import sys
from pathlib import Path

import psycopg

from .postgres import (
    backfill_job_metadata,
    classify_hiring_for_captures,
    collection_run,
    connect,
    save_capture,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--search-url", help="LinkedIn search results URL used for the new run.")
    parser.add_argument("--search-name")
    task = parser.add_mutually_exclusive_group()
    task.add_argument("--backfill-metadata", action="store_true")
    task.add_argument("--classify-hiring", action="store_true", help="Reclassify the hiring model for existing captures.")
    args = parser.parse_args()
    if not (args.backfill_metadata or args.classify_hiring or args.run_id or args.search_url):
        parser.error("Specify --run-id or --search-url.")
    try:
        if args.classify_hiring:
            with connect() as conn:
                counts = classify_hiring_for_captures(conn, args.run_id)
            print(f"Direct hire: {counts['Direct hire']}. Outsourced: {counts['Outsourced']}. Unconfirmed: {counts[None]}.")
            return
        if args.backfill_metadata:
            with connect() as conn:
                print(f"Updated city and security clearance metadata for {backfill_job_metadata(conn)} captures.")
            return
        with connect() as conn, collection_run(
            conn, run_id=args.run_id, search_url=args.search_url, search_name=args.search_name,
        ) as run:
            if args.jsonl:
                with args.jsonl.open(encoding="utf-8") as source:
                    for number, line in enumerate(source, 1):
                        if not line.strip():
                            continue
                        try:
                            save_capture(conn, run.id, json.loads(line))
                        except (KeyError, TypeError, ValueError, psycopg.Error) as exc:
                            raise ValueError(f"{args.jsonl}, line {number}: {exc}") from exc
                        run.saved += 1
            else:
                save_capture(conn, run.id, json.load(sys.stdin))
                run.saved += 1
            print(f"Saved {run.saved} job captures.")
    except (OSError, KeyError, TypeError, ValueError, psycopg.Error) as exc:
        parser.exit(1, f"Write failed | {exc}\n")


if __name__ == "__main__":
    main()

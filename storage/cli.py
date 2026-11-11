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
    parser.add_argument("--search-url", help="新批次实际使用的 LinkedIn 搜索结果页链接")
    parser.add_argument("--search-name")
    task = parser.add_mutually_exclusive_group()
    task.add_argument("--backfill-metadata", action="store_true")
    task.add_argument("--classify-hiring", action="store_true", help="重跑已采集岗位的聘用模式判断")
    args = parser.parse_args()
    if not (args.backfill_metadata or args.classify_hiring or args.run_id or args.search_url):
        parser.error("请提供 --run-id 或 --search-url")
    try:
        if args.classify_hiring:
            with connect() as conn:
                counts = classify_hiring_for_captures(conn, args.run_id)
            print(f"直接聘用 {counts['Direct hire']}，外包派驻 {counts['Outsourced']}，待确认 {counts[None]}")
            return
        if args.backfill_metadata:
            with connect() as conn:
                print(f"已更新 {backfill_job_metadata(conn)} 条岗位的城市、交付模式和安全许可标记")
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
                            raise ValueError(f"{args.jsonl} 第 {number} 行: {exc}") from exc
                        run.saved += 1
            else:
                save_capture(conn, run.id, json.load(sys.stdin))
                run.saved += 1
            print(f"已写入 {run.saved} 条岗位采集记录")
    except (OSError, KeyError, TypeError, ValueError, psycopg.Error) as exc:
        parser.exit(1, f"写入失败 | {exc}\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Query dfr_repair.db for stability fix cases."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = SKILL_ROOT / "data" / "dfr_repair.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Query stability fix database")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--stability-class", dest="stability_class", default=None)
    parser.add_argument("--case-id", default=None)
    parser.add_argument("--search", default=None, help="Search in title or problem_description")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--format", choices=["table", "json"], default="table")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"ERROR: database not found: {args.db}", file=sys.stderr)
        print("Run ./run_fetch_crs.sh first.", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    if args.case_id:
        row = conn.execute(
            "SELECT * FROM dfr_repair_cases WHERE case_id = ?", (args.case_id,)
        ).fetchone()
        if not row:
            print(f"No case: {args.case_id}", file=sys.stderr)
            return 2
        changes = conn.execute(
            "SELECT file_path, code_before, code_after, file_diff, truncated "
            "FROM code_changes WHERE case_id = ?",
            (args.case_id,),
        ).fetchall()
        payload = {**dict(row), "code_changes": [dict(c) for c in changes]}
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"case_id: {row['case_id']}")
            print(f"class:   {row['stability_class']}")
            print(f"title:   {row['title']}")
            print(f"url:     {row['web_url']}")
            print(f"files:   {len(changes)}")
        return 0

    sql = "SELECT case_id, mr_iid, stability_class, confidence, title, web_url FROM dfr_repair_cases WHERE 1=1"
    params: list = []
    if args.stability_class:
        sql += " AND stability_class = ?"
        params.append(args.stability_class)
    if args.search:
        sql += " AND (title LIKE ? OR problem_description LIKE ?)"
        params.extend([f"%{args.search}%", f"%{args.search}%"])
    sql += " ORDER BY confidence DESC LIMIT ?"
    params.append(args.limit)

    rows = conn.execute(sql, params).fetchall()
    if args.format == "json":
        print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
    else:
        print(f"{'iid':>6}  {'class':<12}  {'conf':>4}  title")
        print("-" * 80)
        for r in rows:
            print(f"{r['mr_iid']:>6}  {r['stability_class']:<12}  {r['confidence']:>4.2f}  {r['title'][:50]}")
        print(f"\n{len(rows)} row(s). Use --case-id <id> --format json for full case.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Fetch CodeHub merge requests, classify stability fixes, extract diffs + before/after.
Self-contained: defaults to data/ and output/ under the skill folder root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE = "https://open.codehub.huawei.com"
DEFAULT_PROJECT = "OpenSourceCenter_CR/openharmony/filemanagement_app_file_service"
DEFAULT_CLASSES = ("appfreeze", "jserror", "jsleak", "memoryleak")
DEFAULT_OUTPUT_DIR = SKILL_ROOT / "output" / "codehub"
DEFAULT_DB = SKILL_ROOT / "data" / "dfr_repair.db"

CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("appfreeze", [
        "appfreeze", "app freeze", "appfrozen", "freeze", "frozen", "thread_block",
        "ui_block", "anr", "no_draw", "lifecycle_timeout", "卡死", "冻屏", "无响应", "主线程",
    ]),
    ("jserror", [
        "jserror", "js error", "jscrash", "typeerror", "referenceerror", "syntaxerror",
        "is not callable", "is not defined", "cannot read property", "undefined is not",
    ]),
    ("jsleak", [
        "jsleak", "js leak", "js_leak", "heapsnapshot", "heapdump", "retained size",
        "gc root", "retainer", "heap leak",
    ]),
    ("memoryleak", [
        "memoryleak", "memory leak", "memory_leak", "pss_memory", "kernel_memory",
        "oom", "out of memory", "内存泄漏", "内存泄露",
    ]),
    ("thread_leak", ["threadleak", "thread leak", "thread_leak", "线程泄漏"]),
    ("fd_leak", ["fd leak", "fd_leak", "句柄泄漏"]),
    ("appcrash", ["appcrash", "app crash", "crash", "cppcrash", "sigsegv", "崩溃"]),
    ("asan", ["asan", "ksan", "use-after-free", "heap-buffer-overflow", "踩内存"]),
]


@dataclass
class CodeChange:
    file_path: str
    file_diff: str
    code_before: str | None = None
    code_after: str | None = None
    truncated: bool = False


@dataclass
class StabilityFixCase:
    case_id: str
    project: str
    mr_iid: int
    title: str
    state: str
    web_url: str
    stability_class: str
    confidence: float
    matched_keywords: list[str]
    problem_description: str
    before_commit_sha: str
    after_commit_sha: str
    unified_diff: str
    code_changes: list[CodeChange] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    commit_messages: list[str] = field(default_factory=list)
    author: str = ""
    merged_at: str | None = None


def api_get(base_url: str, path: str, token: str, params: dict | None = None) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"PRIVATE-TOKEN": token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def enc_project(project: str) -> str:
    return urllib.parse.quote(project, safe="")


def enc_file_path(path: str) -> str:
    return urllib.parse.quote(path, safe="")


def fetch_merge_requests(base_url: str, token: str, project: str, state: str = "all") -> list[dict]:
    encoded = enc_project(project)
    page, results, per_page = 1, [], 100
    while True:
        batch = api_get(
            base_url,
            f"/api/v4/projects/{encoded}/merge_requests",
            token,
            {"state": state, "per_page": per_page, "page": page, "order_by": "updated_at", "sort": "desc"},
        )
        if not batch:
            break
        results.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
        time.sleep(0.25)
    return results


def fetch_mr_detail(base_url: str, token: str, project: str, iid: int) -> dict:
    encoded = enc_project(project)
    return api_get(base_url, f"/api/v4/projects/{encoded}/merge_requests/{iid}", token)


def fetch_mr_commits(base_url: str, token: str, project: str, iid: int) -> list[dict]:
    encoded = enc_project(project)
    try:
        return api_get(base_url, f"/api/v4/projects/{encoded}/merge_requests/{iid}/commits", token) or []
    except urllib.error.HTTPError:
        return []


def fetch_mr_changes_raw(base_url: str, token: str, project: str, iid: int) -> list[dict]:
    encoded = enc_project(project)
    data = api_get(base_url, f"/api/v4/projects/{encoded}/merge_requests/{iid}/changes", token)
    return data.get("changes", [])


def fetch_file_raw(
    base_url: str, token: str, project: str, file_path: str, ref: str, max_lines: int
) -> tuple[str | None, bool]:
    encoded = enc_project(project)
    fenc = enc_file_path(file_path)
    try:
        url = (
            f"{base_url.rstrip('/')}/api/v4/projects/{encoded}/repository/files/"
            f"{fenc}/raw?ref={urllib.parse.quote(ref, safe='')}"
        )
        req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            return (
                "\n".join(lines[:max_lines]) + f"\n... [truncated {len(lines) - max_lines} lines]",
                True,
            )
        return text, False
    except urllib.error.HTTPError:
        return None, False


def classify_text(text: str) -> tuple[str, float, list[str]]:
    lowered = text.lower()
    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}
    for category, keywords in CATEGORY_RULES:
        hits = [kw for kw in keywords if kw.lower() in lowered]
        if hits:
            scores[category] = scores.get(category, 0) + len(hits)
            matched.setdefault(category, []).extend(hits)
    if not scores:
        return "general", 0.0, []
    best = max(scores, key=scores.get)
    return best, min(1.0, scores[best] / 5.0), sorted(set(matched[best]))


def make_case_id(project: str, iid: int) -> str:
    return hashlib.sha256(f"{project}:mr:{iid}".encode()).hexdigest()[:32]


def build_problem_description(
    title: str, description: str, commits: list[str], cls: str, kws: list[str]
) -> str:
    parts = [
        f"[Summary] {cls} fix: {title}",
        f"[Keywords] {', '.join(kws)}",
        f"[Description] {(description or '')[:1500]}",
    ]
    if commits:
        parts.append("[Commits]\n" + "\n".join(commits[:8]))
    return "\n".join(parts)


def enrich_mr(
    base_url: str,
    token: str,
    project: str,
    mr: dict,
    max_file_lines: int,
    fetch_file_content: bool,
) -> StabilityFixCase | None:
    iid = mr["iid"]
    detail = fetch_mr_detail(base_url, token, project, iid)
    commits = fetch_mr_commits(base_url, token, project, iid)
    commit_messages = [c.get("title", "") + "\n" + (c.get("message") or "") for c in commits]
    changes = fetch_mr_changes_raw(base_url, token, project, iid)

    paths = [c.get("new_path") or c.get("old_path", "") for c in changes]
    blob = "\n".join([mr.get("title", ""), mr.get("description") or "", *commit_messages, *paths])
    stability_class, confidence, keywords = classify_text(blob)

    diff_refs = detail.get("diff_refs") or {}
    before_sha = diff_refs.get("base_sha") or (
        commits[0].get("parent_ids", [None])[0] if commits else ""
    )
    after_sha = diff_refs.get("head_sha") or detail.get("sha", "")

    unified_parts: list[str] = []
    code_changes: list[CodeChange] = []

    for ch in changes:
        old_path = ch.get("old_path") or ""
        new_path = ch.get("new_path") or old_path
        file_path = new_path or old_path
        file_diff = ch.get("diff") or ""
        if file_diff:
            unified_parts.append(file_diff)

        code_before, code_after = None, None
        truncated = False
        if fetch_file_content and before_sha and after_sha:
            if old_path and not ch.get("new_file"):
                code_before, tb = fetch_file_raw(
                    base_url, token, project, old_path, before_sha, max_file_lines
                )
                truncated = truncated or tb
                time.sleep(0.1)
            if new_path and not ch.get("deleted_file"):
                code_after, ta = fetch_file_raw(
                    base_url, token, project, new_path, after_sha, max_file_lines
                )
                truncated = truncated or ta
                time.sleep(0.1)

        code_changes.append(
            CodeChange(
                file_path=file_path,
                file_diff=file_diff,
                code_before=code_before,
                code_after=code_after,
                truncated=truncated,
            )
        )

    author = (detail.get("author") or {}).get("username", "")
    return StabilityFixCase(
        case_id=make_case_id(project, iid),
        project=project,
        mr_iid=iid,
        title=detail.get("title", ""),
        state=detail.get("state", ""),
        web_url=detail.get("web_url", ""),
        stability_class=stability_class,
        confidence=confidence,
        matched_keywords=keywords,
        problem_description=build_problem_description(
            detail.get("title", ""),
            detail.get("description") or "",
            commit_messages,
            stability_class,
            keywords,
        ),
        before_commit_sha=before_sha or "",
        after_commit_sha=after_sha or "",
        unified_diff="\n".join(unified_parts),
        code_changes=code_changes,
        changed_files=paths,
        commit_messages=[m[:500] for m in commit_messages[:10]],
        author=author,
        merged_at=detail.get("merged_at"),
    )


def save_outputs(
    cases: list[StabilityFixCase],
    project: str,
    json_path: Path,
    db_path: Path,
) -> None:
    by_class: dict[str, list] = {}
    for c in cases:
        by_class.setdefault(c.stability_class, []).append(asdict(c))

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "project": project,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "total": len(cases),
                "by_stability_class": {k: len(v) for k, v in sorted(by_class.items())},
                "cases": [asdict(c) for c in cases],
                "grouped": by_class,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS dfr_repair_cases (
            case_id TEXT PRIMARY KEY,
            project TEXT,
            mr_iid INTEGER,
            title TEXT,
            stability_class TEXT,
            confidence REAL,
            matched_keywords TEXT,
            problem_description TEXT,
            before_commit_sha TEXT,
            after_commit_sha TEXT,
            unified_diff TEXT,
            web_url TEXT,
            state TEXT,
            author TEXT,
            merged_at TEXT,
            source TEXT DEFAULT 'codehub_stability',
            fetched_at TEXT
        );
        CREATE TABLE IF NOT EXISTS code_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT,
            file_path TEXT,
            code_before TEXT,
            code_after TEXT,
            file_diff TEXT,
            truncated INTEGER DEFAULT 0,
            FOREIGN KEY (case_id) REFERENCES dfr_repair_cases(case_id)
        );
        CREATE INDEX IF NOT EXISTS idx_class ON dfr_repair_cases(stability_class);
    """)
    now = datetime.now(timezone.utc).isoformat()
    for c in cases:
        conn.execute(
            """INSERT OR REPLACE INTO dfr_repair_cases
            (case_id, project, mr_iid, title, stability_class, confidence, matched_keywords,
             problem_description, before_commit_sha, after_commit_sha, unified_diff,
             web_url, state, author, merged_at, source, fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                c.case_id,
                c.project,
                c.mr_iid,
                c.title,
                c.stability_class,
                c.confidence,
                json.dumps(c.matched_keywords, ensure_ascii=False),
                c.problem_description,
                c.before_commit_sha,
                c.after_commit_sha,
                c.unified_diff[:500000] if c.unified_diff else "",
                c.web_url,
                c.state,
                c.author,
                c.merged_at,
                "codehub_stability",
                now,
            ),
        )
        conn.execute("DELETE FROM code_changes WHERE case_id=?", (c.case_id,))
        for ch in c.code_changes:
            conn.execute(
                """INSERT INTO code_changes
                (case_id, file_path, code_before, code_after, file_diff, truncated)
                VALUES (?,?,?,?,?,?)""",
                (
                    c.case_id,
                    ch.file_path,
                    ch.code_before,
                    ch.code_after,
                    ch.file_diff,
                    int(ch.truncated),
                ),
            )
    conn.commit()
    conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine stability code fixes from CodeHub MRs")
    parser.add_argument("--base-url", default=os.environ.get("CODEHUB_BASE_URL", DEFAULT_BASE))
    parser.add_argument("--project", default=os.environ.get("CODEHUB_PROJECT", DEFAULT_PROJECT))
    parser.add_argument("--state", default="merged", choices=["opened", "closed", "merged", "all"])
    parser.add_argument(
        "--classes",
        default=",".join(DEFAULT_CLASSES),
        help="Comma-separated classes to keep",
    )
    parser.add_argument("--min-confidence", type=float, default=0.2)
    parser.add_argument("--max-file-lines", type=int, default=2000)
    parser.add_argument("--no-file-content", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    token = os.environ.get("CODEHUB_TOKEN")
    if not token:
        print("ERROR: export CODEHUB_TOKEN=...", file=sys.stderr)
        return 1

    allowed = {c.strip() for c in args.classes.split(",") if c.strip()}

    print(f"Skill root: {SKILL_ROOT}")
    print(f"Project: {args.project}")
    print(f"Filter classes: {sorted(allowed)}")
    print("Fetching merge requests...")

    try:
        mrs = fetch_merge_requests(args.base_url, token, args.project, state=args.state)
    except urllib.error.URLError as e:
        print(f"ERROR: network — {e}", file=sys.stderr)
        return 2
    except urllib.error.HTTPError as e:
        print(f"ERROR: HTTP {e.code} — {e.read().decode()[:400]}", file=sys.stderr)
        return 3

    cases: list[StabilityFixCase] = []
    for i, mr in enumerate(mrs, 1):
        print(f"  [{i}/{len(mrs)}] MR !{mr['iid']} {mr.get('title', '')[:60]}...")
        try:
            case = enrich_mr(
                args.base_url,
                token,
                args.project,
                mr,
                max_file_lines=args.max_file_lines,
                fetch_file_content=not args.no_file_content,
            )
        except urllib.error.HTTPError as e:
            print(f"    skip: HTTP {e.code}")
            continue
        if case is None:
            continue
        if case.stability_class not in allowed:
            continue
        if case.confidence < args.min_confidence:
            continue
        if not case.code_changes and not case.unified_diff:
            continue
        cases.append(case)
        time.sleep(0.2)

    slug = args.project.replace("/", "-")
    json_path = args.output_dir / f"{slug}-stability-fixes.json"
    save_outputs(cases, args.project, json_path, args.db)

    counts: dict[str, int] = {}
    for c in cases:
        counts[c.stability_class] = counts.get(c.stability_class, 0) + 1
    print(f"\nStability fixes mined: {len(cases)}")
    for cls, n in sorted(counts.items()):
        print(f"  {cls}: {n}")
    print(f"JSON: {json_path}")
    print(f"DB:   {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

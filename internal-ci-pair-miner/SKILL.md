---
name: internal-ci-pair-miner
description: >-
  Mines stability-related code fixes from intranet CodeHub merge requests
  (appfreeze, jserror, jsleak, memoryleak, appcrash). Classifies MRs by keywords,
  extracts per-file diff plus code_before/code_after, loads dfr_repair.db for
  downstream repair agents. Use when building a stability fix knowledge base from
  CodeHub change requests without CI or device fault logs.
---

# CodeHub Stability Fix Miner

Mine **stability-related code fixes** from an **intranet CodeHub** (GitLab/Gitee API). Scan merge requests / change requests, classify by stability type, extract **code_before / code_after / diff**, load **SQLite repair DB**.

**Single mode only** — CodeHub MR mining. No device faultlog, no CI fail→pass, no fault↔fix linking.

Pipeline: **Fetch MRs → Classify → Enrich → Load DB → Query**

## When to use

- User has **intranet CodeHub** (e.g. `open.codehub.huawei.com`)
- User wants **stability fix cases** with actual code changes
- Target classes: `appfreeze`, `jserror`, `jsleak`, `memoryleak` (+ optional `appcrash`, etc.)
- Downstream agents query DB to repair similar stability issues

## Core flow

```
CodeHub API: list merge_requests
  → classify by title + description + commits + changed paths (keyword rules)
  → filter: stability_class in target set, confidence >= threshold
  → enrich: MR /changes → file_diff; files/raw API → code_before + code_after
  → load dfr_repair.db + JSON export
```

## Stability classes (keyword classifier)

Default filter: `appfreeze`, `jserror`, `jsleak`, `memoryleak`

| stability_class | Keywords (examples) |
|-----------------|---------------------|
| `appfreeze` | freeze, appfreeze, ANR, THREAD_BLOCK, UI_BLOCK, 卡死, 冻屏, 无响应 |
| `jserror` | jserror, TypeError, ReferenceError, is not callable, jscrash |
| `jsleak` | jsleak, JS_LEAK, heapsnapshot, heapdump, retainer, GC root |
| `memoryleak` | memory leak, memoryleak, OOM, 内存泄漏, pss_memory |
| `appcrash` | appcrash, crash, cppcrash, SIGSEGV (optional) |
| `general` | no keyword match — **excluded** by default |

Rules in [config.sample.yaml](config.sample.yaml) → `classification.keywords`.

## Phase 0: Config (ask if missing)

| Item | Example |
|------|---------|
| CodeHub URL | `https://open.codehub.huawei.com` |
| API | `{base}/api/v4` |
| Project slug | `OpenSourceCenter_CR/openharmony/filemanagement_app_file_service` |
| Auth | `export CODEHUB_TOKEN=...` (never commit token) |
| MR state | `merged` (default) or `all` |
| DB path | `data/dfr_repair.db` (skill 目录内) |

Copy [config.sample.yaml](config.sample.yaml) → `config/codehub.yaml`（可选，主要用环境变量 + 脚本参数）。

## Phase 1: Folder layout (self-contained)

```
internal-ci-pair-miner/          # skill 根目录，clone 即用
├── SKILL.md
├── config.sample.yaml
├── config/codehub.yaml          # 可选，勿提交 token
├── run_fetch_crs.sh             # 抓取入口
├── run_query.sh                 # 查询入口
├── scripts/
│   ├── fetch_codehub_crs.py     # 主程序
│   └── query_db.py
├── data/dfr_repair.db           # 运行时生成
└── output/codehub/*.json        # 运行时生成
```

No external `pair-miner/` directory required.

## Phase 2: Fetch merge requests

GitLab-compatible API:

```
GET /api/v4/projects/{encoded_project}/merge_requests?state=merged&per_page=100
GET /api/v4/projects/{encoded_project}/merge_requests/{iid}
GET /api/v4/projects/{encoded_project}/merge_requests/{iid}/commits
GET /api/v4/projects/{encoded_project}/merge_requests/{iid}/changes
```

Paginate all pages. Rate-limit ~0.25s between requests.

## Phase 3: Classify

Concatenate: `title + description + commit_messages + changed_file_paths`.

Score each `stability_class` by keyword hits (see config). Pick highest score.

- `confidence = min(1.0, hits / 5)`
- Skip if `stability_class == general` or not in `--classes` filter
- Skip if `confidence < min_confidence` (default 0.2)

## Phase 4: Enrich (required)

Per accepted MR:

| Field | API |
|-------|-----|
| `before_commit_sha` | `diff_refs.base_sha` from MR detail |
| `after_commit_sha` | `diff_refs.head_sha` |
| `file_diff` | `changes[].diff` |
| `unified_diff` | concat all file diffs |
| `code_before` | `GET .../repository/files/{path}/raw?ref=base_sha` |
| `code_after` | `GET .../repository/files/{path}/raw?ref=head_sha` |
| `problem_description` | structured MR text (see below) |

Truncate files at `enrichment.max_file_lines` (default 2000); set `truncated=true`.

### problem_description format

```text
[Summary] {stability_class} fix: {MR title}
[Keywords] {matched_keywords}
[Description] {MR description excerpt}
[Commits] {commit messages}
[Files] {changed paths}
```

## Phase 5: Filter

| Reason | Rule |
|--------|------|
| `not_stability` | class is `general` or not in filter |
| `low_confidence` | below threshold |
| `no_diff` | empty changes |
| `duplicate` | same project + mr_iid |

Optional: `docs_only` if only `*.md` changed.

## Phase 6: Load database

**Default**: `pair-miner/data/dfr_repair.db`

### Table `dfr_repair_cases`

`case_id`, `project`, `mr_iid`, `title`, `stability_class`, `confidence`, `matched_keywords`, `problem_description`, `before_commit_sha`, `after_commit_sha`, `unified_diff`, `web_url`, `state`, `author`, `merged_at`, `source` (`codehub_stability`), `fetched_at`

### Table `code_changes`

`case_id`, `file_path`, `code_before`, `code_after`, `file_diff`, `truncated`

Index: `(stability_class)`, FTS on `problem_description` if enabled.

Schema details: [pair-schema.json](pair-schema.json), [reference.md](reference.md).

## Phase 7: Query (repair agents)

```bash
./run_query.sh --stability-class appfreeze --limit 10
./run_query.sh --stability-class jserror --search "TypeError"
./run_query.sh --case-id <id> --format json
```

Return JSON with `code_before`, `code_after`, `file_diff`, `problem_description`, `stability_class`.

## Run

```bash
cd internal-ci-pair-miner   # skill 根目录

export CODEHUB_TOKEN='...'
export CODEHUB_PROJECT='group/project'   # 可选

./run_fetch_crs.sh
# 或
python3 scripts/fetch_codehub_crs.py --classes appfreeze,jserror,jsleak,memoryleak --state merged
```

Query:

```bash
./run_query.sh --stability-class appfreeze
./run_query.sh --case-id <id> --format json
```

## Agent checklist

```
- [ ] config/codehub.yaml: base_url, project slug, token via env
- [ ] Verify API: one MR list call succeeds
- [ ] Run fetch_codehub_crs.py on target repo
- [ ] Confirm dfr_repair.db row counts per stability_class
- [ ] Spot-check: code_before, code_after, file_diff populated
- [ ] run_query.sh returns full case JSON
```

## Tell mining agent

```text
Use skill internal-ci-pair-miner.
Mine stability fixes from intranet CodeHub only (no faultlog, no CI).
Repo: <group/project>, API: <base_url>, token: CODEHUB_TOKEN env.
Classes: appfreeze, jserror, jsleak, memoryleak.
Deliver: data/dfr_repair.db with code_before, code_after, unified_diff, problem_description per MR.
Scripts: ./run_fetch_crs.sh and ./run_query.sh in skill folder.
```

## Tell repair agent

```text
Query data/dfr_repair.db in skill folder
./run_query.sh --stability-class <class> --search "<keyword>"
Use code_before, code_after, file_diff, problem_description to propose fix.
```

## Anti-patterns

- Do not require device fault logs or CI failures
- Do not store tokens in git or yaml committed to repo
- Do not skip code_before/code_after when API is available
- Do not silently drop MRs — log filter reasons in output summary

## Limitations

Classification is **keyword-based on MR text**. MRs titled vaguely (e.g. "fix bug") may be missed. Accuracy improves when commits mention freeze/leak/crash/TypeError.

## Resources

- [config.sample.yaml](config.sample.yaml)
- [pair-schema.json](pair-schema.json)
- [reference.md](reference.md)

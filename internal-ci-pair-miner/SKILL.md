---
name: internal-ci-pair-miner
description: >-
  Builds a stability-focused repair knowledge base from an internal (intranet)
  CodeHub by mining fail-pass CI pairs, extracting before/after code and diffs,
  classifying stability issues, and loading a queryable database for downstream
  repair agents. Use when the user wants to mine internal CodeHub CI history,
  prioritize stability-related fixes, capture code diffs and failure descriptions,
  or produce a database that other agents can use for stability code repair.
---

# Internal CI Pair Miner — Stability Repair Knowledge Base

Mine **fail→pass** CI job pairs from an **internal (intranet) CodeHub**, enrich each pair with **before code / after code / diff / problem description / category**, and **load a queryable database** so other agents can perform **stability-related code repair**.

Pipeline: **Find → Filter → Enrich → Classify → Load DB → (optional) Export JSON**

This skill is **platform-agnostic** (GitLab, Gitea, Jenkins, custom CodeHub). Do not assume GitHub API unless the user confirms GitHub.

## Primary goal vs secondary goal

| Priority | Goal | What to capture |
|----------|------|-----------------|
| **P0 — Stability** | Cases useful for **stability / reliability repair** | Full enrichment: logs, diff, per-file before/after, stability category, problem description |
| **P1 — General defect** | Other fail→pass fixes (build, test, logic) | Same schema, lighter optional fields; tag `primary_focus: general` |
| **P2 — Filtered** | Non-reproducible or low-value pairs | Keep row with `is_filtered_out=true` and reason for audit |

**Default behavior**: classify and rank stability first; still ingest non-stability pairs when mining cost is low, but mark them lower priority for repair agents.

## When to use

- User has an **intranet CodeHub** with CI (GitLab CI, Jenkins, Gitea Actions, custom)
- User wants a **repair knowledge base**, not just a JSON dump
- User wants **before/after code + diff + failure description + category** per fix
- Downstream agents will **query the DB** to learn how similar stability issues were fixed

## Core idea

```
Internal CodeHub CI history
  → find fail/error → pass pairs (same branch, same job config)
  → filter non-reproducible pairs
  → enrich: git diff + per-file before/after + CI log excerpts + MR/commit messages
  → classify: stability-first taxonomy + confidence
  → load SQLite (default) or user-chosen DB
  → expose query helpers for repair agents
```

**Pair definition** (unchanged): failed job **before** passed job, **same branch** (or same MR thread), **same CI config** (`config_hash`: job name + runner + matrix).

## Phase 0: Gather platform facts (ask if missing)

Before coding, confirm:

| Item | Example |
|------|---------|
| CodeHub type | GitLab 16, Gitea, Jenkins+Gerrit, custom |
| **Intranet** API base URL | `https://codehub.corp.internal/api/v4` |
| Auth | PAT / OAuth / service account (`CODEHUB_TOKEN` env) |
| CI system | GitLab CI, Jenkins, custom |
| Repo identifier | `group/project` or numeric ID |
| Run / job objects | pipeline + job, build + stage, workflow run |
| Status values | map to `passed` \| `failed` \| `error` \| `canceled` |
| Log retention | days; can old job logs still be fetched? |
| Clone URL | `https://codehub.corp.internal/group/project.git` |
| **DB choice** | SQLite (default), PostgreSQL, MongoDB |

Write answers to `pair-miner/config/codehub.yaml` (copy from [config.sample.yaml](config.sample.yaml)).

## Phase 1: Scaffold (first time only)

Create under the user's project (default: `pair-miner/`):

```
pair-miner/
├── config/
│   └── codehub.yaml              # API, auth, DB URL, stability keywords
├── data/
│   └── stability_repair.db       # default SQLite output (gitignore if large)
├── output/
│   ├── pairs/                    # optional JSON export per repo
│   ├── filtered/
│   ├── logs/                     # downloaded CI logs
│   └── raw/<repo>/               # raw API responses
├── src/
│   ├── normalize.py              # Run, Job, RepairCase models
│   ├── fetch_runs.py             # CodeHub API → normalized runs
│   ├── extract_pairs.py          # fail→pass detection
│   ├── filter_pairs.py
│   ├── enrich_pairs.py           # diff, before/after code, problem text
│   ├── classify_stability.py     # stability-first taxonomy
│   ├── load_db.py                # schema + upsert
│   ├── query_db.py               # CLI/API for repair agents
│   └── db_schema.sql             # canonical schema
├── run_mine.sh                   # full pipeline
└── run_query.sh                  # repair-agent lookup helper
```

Implement **normalized models** first ([reference.md](reference.md)), then the CodeHub adapter.

## Phase 2: Fetch CI history

Same as BugSwarm-style mining:

1. List repos or take `-r group/project`
2. Paginate pipeline/build runs within `mining.max_age_days`
3. For each run, fetch jobs: `job_id`, `run_id`, `status`, timestamps, `branch`, `commit_sha`, `job_name`, `config_hash`
4. Persist raw API under `output/raw/<repo>/`
5. Rate-limit, retry, resume from last run ID

## Phase 3: Extract pairs

Per `(repo, branch, pipeline/workflow, config_hash)`:

1. Sort by `started_at`
2. Consecutive `(A, B)`: `A ∈ {failed, error}`, `B == passed`, `A.commit_sha != B.commit_sha`
3. Attach `repo`, `branch`, `pr_id`, `failed_job`, `passed_job`

```python
for branch in group_by_branch(runs):
    for a, b in consecutive(branch.runs):
        if a.failed_or_errored() and b.passed():
            yield FailPassPair(a, b)
```

## Phase 4: Filter pairs

Set `is_filtered_out=true` and `filtered_reason`. Keep all rows in DB for audit.

| Filter | Reason | Rule |
|--------|--------|------|
| `no_sha` | missing commit | SHA empty |
| `same_commit` | same commit fail→pass | fluke / rerun |
| `unavailable` | SHA not in git log | clone cannot resolve |
| `expired_logs` | log 404 | cannot describe failure |
| `unsupported_runner` | runner not reproducible | not in allowlist |
| `secrets_exposed` | secrets in CI config | security |
| `unsupported_syntax` | CI parser error | skip |
| `no_code_change` | empty diff between SHAs | unlikely real fix |
| `docs_only` | only `*.md` / docs paths changed | deprioritize (still store if user asks) |

## Phase 5: Enrich pairs (required for non-filtered)

For each non-filtered pair, populate **repair case** fields. This phase is mandatory for DB load.

### 5.1 Git diff and per-file code

Between `failed_job.commit_sha` (before) and `passed_job.commit_sha` (after):

1. `git diff failed_sha..passed_sha` → store unified diff string
2. For each changed file in diff:
   - `code_before`: `git show failed_sha:path` (null if added file)
   - `code_after`: `git show passed_sha:path` (null if deleted file)
   - `language`: infer from extension
   - `is_test_file`: path matches `*test*`, `*spec*`, etc.

Limit large files: truncate at configurable line cap (default 2000 lines) and set `truncated=true`.

### 5.2 Problem description (`problem_description`)

Build a structured text block from (in order):

1. **CI log excerpt**: last N lines around first stack trace / error / `FAIL` / panic / timeout (from failed job log)
2. **Exception list**: parsed stack traces, error types, assert messages
3. **Commit messages** between failed and passed SHA (`git log failed..passed --oneline`)
4. **MR/PR title + description** if CodeHub API provides them

Format:

```text
[Summary] One-line failure summary (agent-generated or rule-based from log)
[Errors] ...
[Context] branch=..., job=..., failed_sha=..., passed_sha=...
[Commits] ...
```

### 5.3 Stability relevance pre-score

Before full classification, score 0–1 using signals:

- Log keywords: `timeout`, `deadlock`, `race`, `OOM`, `panic`, `flaky`, `retry`, `connection reset`, `nil`, `null`, `ConcurrentModification`, `goroutine`, `leak`, etc. (configurable in `codehub.yaml`)
- Changed paths: concurrency, network client, retry, circuit breaker, lock, pool, cache modules
- Test-only changes fixing intermittent failures → stability candidate

Store `stability_relevance_score` on the case. **P0 queue**: score ≥ threshold (default 0.5).

## Phase 6: Classify (stability-first)

For each enriched pair, set:

### Primary focus

- `primary_focus`: `stability` | `general` | `unknown`
- Rule: `stability` if score ≥ threshold OR category in stability taxonomy; else `general`

### Stability categories (use one primary + optional secondary)

| Category | Examples |
|----------|----------|
| `concurrency_race` | race, deadlock, lock ordering |
| `timeout_retry` | timeouts, missing retries, backoff |
| `resource_leak` | fd/memory/goroutine leak |
| `null_safety` | NPE, nil deref, optional unwrapping |
| `exception_handling` | swallowed errors, wrong catch, missing recovery |
| `network_resilience` | connection drops, DNS, partial failure |
| `flaky_test` | test timing, sleep, order dependence |
| `state_consistency` | stale cache, wrong shared state |
| `capacity_load` | OOM, throttling, queue overflow |
| `configuration` | wrong timeout/limit/pool size causing instability |
| `other_stability` | stability-related but uncategorized |
| `non_stability` | pure build/feature fix |

Also retain BugSwarm-style axes when useful:

- `build` / `test` / `code`: Yes | No | Partial
- `exceptions`: string array from log parser

Store `classification` JSON on the case row.

## Phase 7: Load database (required deliverable)

**Default**: SQLite at `pair-miner/data/stability_repair.db`.

Implement `src/db_schema.sql` and `load_db.py`. Upsert by stable `case_id` (hash of repo + failed_job_id + passed_job_id).

### Table: `repair_cases`

| Column | Type | Notes |
|--------|------|-------|
| `case_id` | TEXT PK | stable hash |
| `repo` | TEXT | group/project |
| `branch` | TEXT | |
| `pr_id` | INTEGER NULL | |
| `ci_service` | TEXT | gitlab-ci, jenkins, ... |
| `primary_focus` | TEXT | stability \| general \| unknown |
| `stability_category` | TEXT | taxonomy above |
| `stability_relevance_score` | REAL | 0–1 |
| `problem_description` | TEXT | full structured text |
| `classification` | JSON | build/test/code, exceptions |
| `failed_job_id` | TEXT | |
| `passed_job_id` | TEXT | |
| `failed_commit_sha` | TEXT | **before** |
| `passed_commit_sha` | TEXT | **after** |
| `failed_job_name` | TEXT | |
| `unified_diff` | TEXT | full diff failed..passed |
| `is_filtered_out` | BOOLEAN | |
| `filtered_reason` | TEXT NULL | |
| `mined_at` | TIMESTAMP | |

### Table: `code_changes`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `case_id` | TEXT FK | |
| `file_path` | TEXT | |
| `language` | TEXT | |
| `is_test_file` | BOOLEAN | |
| `code_before` | TEXT NULL | full file at failed SHA |
| `code_after` | TEXT NULL | full file at passed SHA |
| `file_diff` | TEXT | hunks for this file only |
| `truncated` | BOOLEAN | |

### Table: `failure_signals`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `case_id` | TEXT FK | |
| `signal_type` | TEXT | stack_trace \| error_line \| assert \| timeout \| keyword |
| `content` | TEXT | |
| `source` | TEXT | ci_log \| commit \| mr |

### Indexes (for repair agents)

- `(primary_focus, stability_category)`
- `(repo, stability_relevance_score DESC)`
- `(stability_category, repo)`
- Full-text on `problem_description` if SQLite FTS5 enabled

### Optional JSON export

Also write `output/pairs/<group>-<project>.json` using extended fields; see [pair-schema.json](pair-schema.json) as baseline — extend with `code_changes`, `problem_description`, `stability_category`.

## Phase 8: Repair-agent query interface

Implement `query_db.py` (or document SQL) so **other agents** can retrieve repair examples without re-mining.

Required query modes:

```bash
# Similar stability cases by category
./run_query.sh --category concurrency_race --limit 10

# Full case for repair (includes before/after/diff/description)
./run_query.sh --case-id <id> --format json

# Search by log keyword / error text
./run_query.sh --search "deadlock" --focus stability

# List top stability cases for a repo
./run_query.sh -r group/project --focus stability --min-score 0.6
```

**Repair-agent consumption contract**: return JSON with:

```json
{
  "case_id": "...",
  "problem_description": "...",
  "stability_category": "timeout_retry",
  "failed_commit_sha": "...",
  "passed_commit_sha": "...",
  "unified_diff": "...",
  "code_changes": [
    {
      "file_path": "src/client.go",
      "code_before": "...",
      "code_after": "...",
      "file_diff": "..."
    }
  ],
  "classification": { "exceptions": ["context deadline exceeded"] }
}
```

Document this contract in `pair-miner/docs/repair-agent-api.md` (create on first run).

## Phase 9: Optional reproduce

Do not implement unless user asks. If requested: Docker replay + stability score `k/n` reruns → update `repair_cases.stability_rerun_score`.

## Agent execution checklist

```
- [ ] Read config/codehub.yaml (intranet URL, token env, DB path)
- [ ] Verify API: one test repo returns pipelines/jobs
- [ ] Verify git clone/fetch works on intranet
- [ ] Run fetch → extract → filter → enrich → classify → load_db
- [ ] Confirm DB exists and row counts: total / stability / filtered
- [ ] Run sample query_db.sh --focus stability
- [ ] Write repair-agent-api.md with example queries
- [ ] Report: stability vs general counts, top categories, filtered_reason breakdown
```

## CLI contract

```bash
# Full mine + DB load (default)
./run_mine.sh -r group/project

# Multiple repos
./run_mine.sh -f repos.txt

# Stability-only load (skip general unless --include-general)
./run_mine.sh -r group/project --focus stability

# Include general defect pairs too (default: yes, lower priority)
./run_mine.sh -r group/project --include-general

# Skip classify (faster; not recommended for repair DB)
./run_mine.sh -r group/project --skip-classify

# Re-export JSON from DB
./run_query.sh --export-json -r group/project
```

## Tell another agent (prompt snippet)

```text
Use skill internal-ci-pair-miner.
Intranet CodeHub: <type> at <base URL>.
Target repo: <group/project>.
Auth: CODEHUB_TOKEN in env / codehub.yaml.
Deliver: pair-miner/data/stability_repair.db loaded with repair_cases,
  each with problem_description, stability_category, code_before/code_after, unified_diff.
Priority: stability-related fail→pass pairs first; include general pairs if cheap.
Expose query_db.sh for repair agents. Do not use BugSwarm github-pair-finder unless repo is on github.com.
```

## Tell a repair agent (downstream)

```text
Query stability repair DB at pair-miner/data/stability_repair.db.
Use ./run_query.sh --search "<error>" --focus stability or --category <cat>.
For each case, use code_before, code_after, file_diff, and problem_description
to propose a fix for the current failing code. Prefer cases with high stability_relevance_score.
```

## Anti-patterns

- Do not hardcode `api.github.com` for intranet CodeHub
- Do not pair jobs with different `config_hash`
- Do not treat flaky pass-after-pass (no fail) as fixes
- Do not store tokens in git; use env vars + `.gitignore`
- Do not skip **enrich** (before/after/diff) if building a repair DB
- Do not silently drop filtered pairs — keep in DB with reason
- Do not store only diff without **code_before** / **code_after** when files are small enough

## Additional resources

- Platform adapters: [reference.md](reference.md)
- JSON baseline schema: [pair-schema.json](pair-schema.json) (extend for DB fields)
- Config template: [config.sample.yaml](config.sample.yaml)

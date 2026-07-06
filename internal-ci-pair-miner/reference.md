# Internal CI Pair Miner — Reference

## Normalized data model

All platform adapters map API responses to these types. Enrichment and DB load add **RepairCase** fields.

### Run (pipeline / workflow / build)

| Field | Purpose |
|-------|---------|
| `run_id` | Unique pipeline/build ID |
| `repo` | `group/project` |
| `branch` | Branch name |
| `commit_sha` | HEAD commit for the run |
| `status` | `passed` \| `failed` \| `error` \| `canceled` |
| `started_at` | ISO8601 |
| `pr_id` | Optional merge request / PR number |

### Job

| Field | Purpose |
|-------|---------|
| `job_id` | Unique job ID |
| `run_id` | Parent run |
| `job_name` | CI job name |
| `config_hash` | Hash of runner labels + matrix vars |
| `status` | Normalized status |
| `commit_sha` | Usually same as run |
| `log_url` or log API path | For enrich + classify |

### FailPassPair (mining stage)

| Field | Purpose |
|-------|---------|
| `failed_job` | Earlier failing job |
| `passed_job` | Next passing job, same config_hash |
| `repo`, `branch`, `pr_id` | Context |

### RepairCase (enriched + DB row)

| Field | Purpose |
|-------|---------|
| `case_id` | SHA256 prefix of `repo:failed_job_id:passed_job_id` |
| `primary_focus` | `stability` \| `general` \| `unknown` |
| `stability_category` | Taxonomy enum (see below) |
| `stability_relevance_score` | 0–1 pre-score from logs + paths |
| `problem_description` | Structured failure narrative |
| `failed_commit_sha` / `passed_commit_sha` | Before / after |
| `unified_diff` | Full diff between commits |
| `code_changes[]` | Per-file before, after, file_diff |
| `failure_signals[]` | Parsed log/commit/MR signals |
| `classification` | build/test/code + exceptions |
| `is_filtered_out`, `filtered_reason` | Audit trail |

## Stability category taxonomy

Use exactly these strings in DB and JSON:

| Value | Typical signals |
|-------|-----------------|
| `concurrency_race` | race, deadlock, lock ordering |
| `timeout_retry` | deadline, missing retry/backoff |
| `resource_leak` | fd/memory/goroutine leak |
| `null_safety` | NPE, nil deref |
| `exception_handling` | wrong catch, swallowed error |
| `network_resilience` | connection drop, DNS, partial failure |
| `flaky_test` | timing, sleep, order dependence |
| `state_consistency` | stale cache, shared state bug |
| `capacity_load` | OOM, throttling, queue overflow |
| `configuration` | wrong timeout/limit/pool size |
| `other_stability` | stability-related, uncategorized |
| `non_stability` | build/feature-only fix |

## Database schema (SQLite default)

Canonical DDL lives in `pair-miner/src/db_schema.sql`. Summary:

### `repair_cases`

Primary table; one row per mined pair. Key columns: `case_id`, `repo`, `primary_focus`, `stability_category`, `stability_relevance_score`, `problem_description`, `failed_commit_sha`, `passed_commit_sha`, `unified_diff`, `classification` (JSON), `is_filtered_out`, `filtered_reason`, `mined_at`.

### `code_changes`

FK `case_id` → `repair_cases`. Columns: `file_path`, `language`, `is_test_file`, `code_before`, `code_after`, `file_diff`, `truncated`.

### `failure_signals`

FK `case_id`. Columns: `signal_type` (`stack_trace` \| `error_line` \| `assert` \| `timeout` \| `keyword`), `content`, `source` (`ci_log` \| `commit` \| `mr`).

### Recommended indexes

- `(primary_focus, stability_category)`
- `(repo, stability_relevance_score DESC)`
- FTS5 virtual table on `problem_description` when `database.enable_fts: true`

## Platform adapter cheat sheet

### GitLab (intranet)

- Pipelines: `GET /projects/:id/pipelines`
- Jobs: `GET /projects/:id/pipelines/:pipeline_id/jobs`
- Log: `GET /projects/:id/jobs/:job_id/trace`
- MR: `GET /projects/:id/merge_requests/:iid`
- `config_hash`: hash of `runner.name` + `tag_list` + `job.name`
- Clone: `https://{host}/{group}/{project}.git` with `PRIVATE-TOKEN` header

### Gitea / Forgejo Actions

- Check Actions API: `/repos/{owner}/{repo}/actions/runs`
- Adapter similar to BugSwarm github-pair-finder with different `base_url`
- Or parse external Jenkins logs if Actions unavailable

### Jenkins

- Runs: `GET /job/{folder}/{job}/api/json?tree=builds[number,result,timestamp,changeSet]`
- Map `result`: SUCCESS→passed, FAILURE→failed, UNSTABLE→error
- `config_hash`: job name + parameter set
- Logs: `GET /job/.../build/{n}/consoleText`

### Custom CodeHub

Implement `fetch_runs(repo) -> List[Run]` and `fetch_jobs(run) -> List[Job]`.
Reuse extract → filter → enrich → classify → load_db unchanged.

## config_hash example

```python
import hashlib, json

def config_hash(job) -> str:
    key = {
        "job_name": job.job_name,
        "runner": job.runner,
        "matrix": sorted(job.matrix.items()) if job.matrix else [],
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]
```

Only pair jobs with identical `config_hash`.

## Filter reason strings (use exactly)

- `no_sha` / `missing_commit_sha`
- `same_commit`
- `unavailable` / `commit_not_in_log`
- `expired_logs` / `log_expired`
- `unsupported_runner`
- `secrets_exposed` / `secrets_in_config`
- `unsupported_syntax` / `unsupported_ci_syntax`
- `no_code_change`
- `docs_only`

## Enrichment helpers

### case_id

```python
import hashlib
def case_id(repo: str, failed_job_id: str, passed_job_id: str) -> str:
    raw = f"{repo}:{failed_job_id}:{passed_job_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
```

### Per-file code snapshot

```python
def snapshot(repo_path, sha, path):
    # added file  → code_before = None
    # deleted file → code_after = None
    return subprocess.check_output(
        ["git", "-C", repo_path, "show", f"{sha}:{path}"],
        text=True, errors="replace",
    )
```

## Repair-agent query examples

```bash
./run_query.sh --category timeout_retry --limit 10
./run_query.sh --case-id abc123 --format json
./run_query.sh --search "deadlock" --focus stability
./run_query.sh -r group/project --focus stability --min-score 0.6
```

Response must include `code_before`, `code_after`, `file_diff`, `problem_description`, `stability_category` per [pair-schema.json](pair-schema.json).

## BugSwarm files to read for inspiration

| BugSwarm module | Borrow |
|-----------------|--------|
| `github-pair-finder/.../extract_all_build_pairs.py` | Consecutive fail→pass scan |
| `github-pair-finder/.../align_job_pairs.py` | Same-config alignment |
| `pair-filter/` | `is_filtered_out` pattern |
| `pair-classifier/` | build/test/code + exceptions |

## Reproduce phase (optional)

1. Checkout `failed_commit_sha` in Docker
2. Replay CI steps from parsed config
3. Compare log to stored failure_signals
4. Repeat N times → update `stability_rerun_score` (e.g. `4/5`)

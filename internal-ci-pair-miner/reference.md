# Internal CI Pair Miner — Reference

## Normalized data model

All platform adapters must map API responses to these types.

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
| `log_url` or log API path | For classifier |

### FailPassPair

| Field | Purpose |
|-------|---------|
| `failed_job` | Earlier failing job |
| `passed_job` | Next passing job, same config_hash |
| `repo`, `branch`, `pr_id` | Context |

## Platform adapter cheat sheet

### GitLab

- Pipelines: `GET /projects/:id/pipelines`
- Jobs: `GET /projects/:id/pipelines/:pipeline_id/jobs`
- Log: `GET /projects/:id/jobs/:job_id/trace`
- `config_hash`: hash of `runner.name` + `tag_list` + relevant `job.name`
- Clone: `https://{host}/{group}/{project}.git` with `PRIVATE-TOKEN` header

### Gitea / Forgejo Actions

- Check if Actions API mirrors GitHub (`/repos/{owner}/{repo}/actions/runs`)
- If yes, adapter similar to BugSwarm github-pair-finder with different `base_url`
- If no, parse webhook DB or CI logs from external Jenkins

### Jenkins

- Runs: `GET /job/{folder}/{job}/api/json?tree=builds[number,result,timestamp,changeSet]`
- Map `result`: SUCCESS→passed, FAILURE→failed, UNSTABLE→error
- `config_hash`: job name + parameter set
- Logs: `GET /job/.../build/{n}/consoleText`

### Custom CodeHub

Implement `fetch_runs(repo) -> List[Run]` and `fetch_jobs(run) -> List[Job]` only.
Reuse extract/filter/classify unchanged.

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

## Filter reason strings (use exactly for tooling)

- `missing_commit_sha`
- `same_commit`
- `commit_not_in_log`
- `log_expired`
- `unsupported_runner`
- `secrets_in_config`
- `unsupported_ci_syntax`

## BugSwarm files to read for inspiration (if user has bugswarm cloned)

| BugSwarm module | Borrow |
|-----------------|--------|
| `github-pair-finder/pipeline/steps/extract_all_build_pairs.py` | Consecutive fail→pass scan |
| `github-pair-finder/pipeline/steps/align_job_pairs.py` | Same-config alignment |
| `pair-filter/` | Filter naming and `is_filtered_out` pattern |
| `pair-classifier/` | build/test/code ratios + exceptions |
| `docs/Artifact-Structure.md` | Final artifact metadata shape |

## Reproduce phase (future)

Not required for mining. When added:

1. Checkout `failed_job.commit_sha` in Docker
2. Execute CI script steps from parsed config
3. Compare stdout/stderr to stored log (BugSwarm "match" levels)
4. Repeat N times → `stability: k/n`

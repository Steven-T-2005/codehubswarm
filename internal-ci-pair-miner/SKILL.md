---
name: internal-ci-pair-miner
description: >-
  Mines fail-pass and error-pass CI job pairs from an internal CodeHub (GitLab,
  Gitee, Gitea, Bitbucket, or custom) using a BugSwarm-inspired pipeline.
  Use when the user wants to find bug-fix candidates from CI history, build a
  defect dataset, replicate BugSwarm mining on a non-GitHub platform, or set up
  an agent to discover reproducible fail-to-pass pairs from internal pipelines.
---

# Internal CI Pair Miner

Mine **fail→pass** (and **error→pass**) CI job pairs from an internal CodeHub, following BugSwarm's split pipeline: **Find → Filter → Classify → (optional) Reproduce**.

This skill is for **platform-agnostic** CodeHubs. Do not assume GitHub API or GitHub Actions unless the user confirms them.

## When to use

- User has an **internal / self-hosted CodeHub** with CI (GitLab CI, Jenkins, Gitea Actions, custom)
- User wants **BugSwarm-like pair mining**, not the stock BugSwarm repo (which only supports GitHub + Travis/GHA)
- User asks an agent to **discover defect-fix candidates** from CI history

## Core idea (borrowed from BugSwarm)

```
CI run history (per repo, per branch, per job config)
  → sort by time
  → find consecutive runs where status flips: FAIL/ERROR → PASS
  → align same job name + same runner/matrix config
  → filter pairs that cannot be checked out or reproduced
  → classify failure type from logs + diff
  → output JSON + optional DB
```

**Pair definition**: two CI jobs where the **failed job ran before** the **passed job**, on the **same branch** (or same MR/PR thread), with the **same CI configuration** (runner, matrix, job name).

## Phase 0: Gather platform facts (ask if missing)

Before coding, confirm or document:

| Item | Example |
|------|---------|
| CodeHub type | GitLab 16, Gitea, Jenkins+Gerrit, custom |
| API base URL | `https://codehub.internal/api/v4` |
| Auth | PAT, OAuth, service account |
| CI system | GitLab CI, Jenkins, custom |
| Repo identifier | `group/project` or numeric ID |
| Run object | pipeline, build, workflow run |
| Job object | job, stage job, matrix cell |
| Status values | `success`, `failed`, `canceled`, ... |
| Log retention | days; are old logs still available? |
| Clone URL pattern | `https://codehub.internal/group/project.git` |

Write answers to `pair-miner/config/codehub.yaml` (copy from [config.sample.yaml](config.sample.yaml)).

## Phase 1: Scaffold (first time only)

Create this layout under the user's project (default: `pair-miner/`):

```
pair-miner/
├── config/
│   └── codehub.yaml          # API URL, auth, field mappings
├── output/
│   ├── pairs/                # final JSON per repo
│   ├── filtered/             # pairs removed + reason
│   └── logs/                 # downloaded CI logs
├── src/
│   ├── fetch_runs.py         # API → normalized runs
│   ├── extract_pairs.py      # fail-pass detection
│   ├── filter_pairs.py       # drop non-reproducible
│   ├── classify_pairs.py     # build/test/code/exceptions
│   └── normalize.py          # shared Run/Job models
└── run_mine.sh               # orchestrator
```

Implement **normalized models** first (`reference.md`), then adapters for the specific CodeHub API.

## Phase 2: Fetch CI history

1. List repos (or take `-r group/project` from CLI)
2. For each repo, paginate **all pipeline/build runs** within retention window
3. For each run, fetch **jobs** with: `job_id`, `run_id`, `status`, `started_at`, `finished_at`, `branch`, `commit_sha`, `job_name`, `config_hash` (matrix/runner labels)
4. Persist raw API responses under `output/raw/<repo>/` for debugging
5. Rate-limit and retry with backoff; support resuming from last fetched run ID

**Config hash**: stable string from runner + matrix + job name (BugSwarm's `AlignJobPairs` equivalent). Same hash required to pair failed vs passed jobs.

## Phase 3: Extract pairs

Per `(repo, branch, workflow_or_pipeline, config_hash)`:

1. Sort jobs/runs by `started_at`
2. Scan consecutive pairs `(A, B)`:
   - `A.status ∈ {failed, error}` AND `B.status == passed`
   - `A.commit_sha != B.commit_sha` (skip same-commit flukes)
3. Emit **build pair** (two runs) then **align job pairs** inside (same config_hash)
4. Attach metadata: `repo`, `branch`, `pr_id` (if any), `failed_job`, `passed_job`

Algorithm (same spirit as BugSwarm `ExtractAllBuildPairs`):

```python
for branch in group_by_branch(runs):
    for a, b in consecutive(branch.runs):
        if a.failed_or_errored() and b.passed():
            yield FailPassPair(a, b)
```

## Phase 4: Filter pairs

Mark `is_filtered_out: true` and set `filtered_reason`. Default filters (adapt to platform):

| Filter | Reason string | Rule |
|--------|---------------|------|
| `no_sha` | missing trigger/base commit | SHA empty |
| `same_commit` | failed and passed same commit | `failed.sha == passed.sha` |
| `unavailable` | commit not in git log | clone/fetch cannot resolve SHA |
| `expired_logs` | CI log no longer available | log API 404 |
| `unsupported_runner` | runner not reproducible | not in allowlist |
| `secrets_exposed` | workflow contains raw secrets | regex scan CI config |
| `unsupported_syntax` | CI config parser cannot handle | parser error |

Keep filtered pairs in output with reason (do not silently drop).

## Phase 5: Classify pairs (optional but recommended)

For each non-filtered pair:

1. Download **failed job log** (and passed if needed)
2. Get **file diff** between `failed.commit_sha` and `passed.commit_sha`
3. Label:
   - `build` / `test` / `code`: Yes | No | Partial (by changed file paths)
   - `exceptions`: parse from failed log (stack traces, error lines)

Store in pair JSON under `classification`.

## Phase 6: Output

Write one file per repo: `output/pairs/<group>-<project>.json`

Use schema in [pair-schema.json](pair-schema.json).

Print summary:

```
Repo: group/project
  runs fetched: N
  build pairs found: N
  after filter: N
  classification complete: N
  output: output/pairs/group-project.json
```

## Phase 7: Optional reproduce (out of scope unless asked)

BugSwarm's Reproducer needs Docker + CI config replay. For internal CodeHub:

- Document **reproduce strategy** in config (docker image, runner tag)
- Do not implement Reproducer unless user explicitly requests Phase 7
- If requested: run failed job commands in container, diff log with original

## Agent execution checklist

Copy and track:

```
- [ ] Read config/codehub.yaml (create from sample if missing)
- [ ] Verify API: curl/API call returns runs for one test repo
- [ ] Verify git clone works for test repo
- [ ] Implement or run fetch_runs → extract_pairs → filter_pairs → classify_pairs
- [ ] Write output JSON + print summary counts
- [ ] Report filtered_reason breakdown
```

## CLI contract (implement or wrap)

```bash
# Single repo
./run_mine.sh -r group/project

# Repo list
./run_mine.sh -f repos.txt

# Skip classify (faster)
./run_mine.sh -r group/project --skip-classify
```

## Tell another agent (prompt snippet)

When delegating, include:

```text
Use skill internal-ci-pair-miner.
CodeHub: <type> at <base URL>.
Target repo: <group/project>.
Auth in pair-miner/config/codehub.yaml.
Deliver: output/pairs/<repo>.json with fail-pass pair count and top filtered_reason stats.
Do not use BugSwarm github-pair-finder directly unless repo is on github.com.
```

## Anti-patterns

- Do not hardcode `api.github.com` unless platform is GitHub
- Do not pair jobs with different matrix/runner config
- Do not treat flaky pass-after-pass as bug fixes
- Do not store tokens in git; use env vars or local config in `.gitignore`

## Additional resources

- Field mappings and adapter notes: [reference.md](reference.md)
- JSON pair schema: [pair-schema.json](pair-schema.json)
- Config template: [config.sample.yaml](config.sample.yaml)

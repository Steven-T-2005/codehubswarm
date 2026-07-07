# CodeHub Stability Fix Miner — Reference

Self-contained skill: all paths relative to skill folder root.

## Quick start

```bash
cd internal-ci-pair-miner
export CODEHUB_TOKEN='...'
export CODEHUB_PROJECT='group/project'
./run_fetch_crs.sh
./run_query.sh --stability-class appfreeze
```

## Scripts

| Script | Purpose |
|--------|---------|
| `run_fetch_crs.sh` | Fetch MRs, classify, save DB + JSON |
| `scripts/fetch_codehub_crs.py` | Python implementation |
| `run_query.sh` | Query `data/dfr_repair.db` |
| `scripts/query_db.py` | Query implementation |

## Outputs

| Path | Content |
|------|---------|
| `data/dfr_repair.db` | SQLite: `dfr_repair_cases`, `code_changes` |
| `output/codehub/<slug>-stability-fixes.json` | Full JSON export |

## API (GitLab-compatible)

- `GET /api/v4/projects/{id}/merge_requests`
- `GET /api/v4/projects/{id}/merge_requests/{iid}/changes`
- `GET /api/v4/projects/{id}/repository/files/{path}/raw?ref={sha}`

Header: `PRIVATE-TOKEN: {CODEHUB_TOKEN}`

## Query examples

```bash
./run_query.sh --stability-class jserror --limit 10
./run_query.sh --search "TypeError" --format json
./run_query.sh --case-id abc123 --format json
```

```bash
sqlite3 data/dfr_repair.db \
  "SELECT stability_class, COUNT(*) FROM dfr_repair_cases GROUP BY 1;"
```

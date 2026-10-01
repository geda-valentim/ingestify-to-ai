# Runbook: spec 0003 migration (projects and folders)

The design and the reasons behind each step are in
[spec 0003 § 4.3](../specs/0003-projects-and-folders.md). This page lists the commands only.
The owner runs it. The script prints each step and stops at the first `FAIL`.

**Never** run `alembic upgrade` in production: the database is not stamped there.

## Where to run it from

Run the script from a checkout of the **new** code that is **not** the directory
bind-mounted into the containers (`/var/app/ingestify-to-ai`). The new `models.py`
must not reach the running workers before the columns exist. A throwaway container
from the API image is enough. It does not touch the running containers:

```bash
NEW=/path/to/checkout-of-the-new-code
IMG=$(docker inspect --format '{{.Config.Image}}' ingestify-to-ai-api-1)
docker run --rm -it --network host -v "$NEW":/mig:ro -w /mig --entrypoint python "$IMG" \
  scripts/migrate_0003_projects.py --database-url 'mysql+pymysql://USER:PASS@127.0.0.1:3306/ingestify' --check
```

## Steps

| # | What | Command / check |
|---|------|-----------------|
| 0a | MariaDB 10.11 | the script checks `SELECT VERSION()` (`--check`) |
| 0b | Backup | `mariadb-dump --single-transaction ingestify users api_keys jobs > pre-0003.sql` |
| 0c | **Owner action, not verified by anyone.** Callers without an API key | grep the API logs for `/upload`, `/convert`, `/transcribe` and `/images` calls without `X-API-Key` (for example `meumentor-api`). Bind a key for them, or set `UPLOAD_FALLBACK_PROJECT` on the deploy. |
| 0d | Quiet window | the script prints transcriptions per hour (UTC, last 7 days) |
| 0e | Long transactions | the script refuses to run while any InnoDB transaction is older than 30 s. Wait, or pause the queues (`docker compose stop worker worker-audio`), or pass `--allow-long-transactions`. |
| 1 | DDL | the same command without `--check`. It asks for confirmation; `--yes` skips the prompt. A lock timeout is retried 5× at 30 s intervals, then the script aborts cleanly. |
| 2 | Code pre-flight | printed right after step 1. Continue only on `OK`. |
| 3 | Backfill | runs right after step 2. It prints the API keys bound to "Inbox"; re-bind the ones that deserve their own project. |
| 4 | Deploy | api + workers + frontend |
| 5 | API boot | automatic: the schema guard runs, then the one-shot tail backfill, then the invariant check. If the guard fails, the API exits with `SystemExit(1)`. |

The process-level environment variables are `UPLOAD_FALLBACK_PROJECT` (empty by default),
`MAX_PROJECTS_PER_USER` (200) and `MAX_FOLDERS_PER_PROJECT` (500). The API container only
sees them if `docker-compose.yml` passes them in its `environment:` block.

## Rollback

The old code ignores the new tables and columns, so a code rollback needs no DDL.
To remove the schema anyway (this loses the project organisation, not the jobs):

```bash
... scripts/migrate_0003_projects.py --database-url '...' --downgrade
```

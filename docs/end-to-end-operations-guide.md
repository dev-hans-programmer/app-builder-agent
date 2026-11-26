# End-to-End Operations Guide

This is the operator runbook for the queue-backed App Builder. Start here when running the product
locally, submitting a build, monitoring it, or diagnosing why it is not progressing.

The guide assumes the repository root is the current directory and uses the local Docker Compose
configuration. The examples use `curl` and `jq`; the same operations are available interactively at
`http://127.0.0.1:8080/docs`.

## 1. Know which system answers which question

```text
Client
  │ POST project/run
  ▼
FastAPI ──transaction──► PostgreSQL: run state, events, steps, outbox, artifacts
                              │
                              │ Celery Beat schedules outbox dispatch
                              ▼
                         RabbitMQ: durable task delivery
                              │
                              ▼
                         Celery worker
                              │
                 ┌────────────┼─────────────┐
                 ▼            ▼             ▼
             LangGraph    local files    OpenAI/GitHub
             checkpoints  under data/    external APIs
```

Use the following ownership rules during an investigation:

| Question | Authoritative place |
|---|---|
| What is the public status of a run? | Run API or PostgreSQL `runs` |
| Which step is running or failed? | Run API, `run_steps`, and `run_events` |
| Is work waiting for or held by a worker? | RabbitMQ `runs` queue |
| Is the scheduler/dispatcher operating? | Celery Beat log, maintenance worker log, and `outbox_messages` |
| What is the worker doing now? | Celery worker log and Celery Inspect |
| What files and reports were generated? | Run artifacts API and `CONTROL_ARTIFACT_ROOT` |
| Was code committed to GitHub? | Run delivery fields and the returned GitHub URLs |

PostgreSQL is the source of truth. RabbitMQ and Celery are delivery and execution infrastructure;
their state is not the public run lifecycle contract. Celery intentionally has no result backend.

## 2. One-time local setup

Prerequisites:

- Python 3.11 or later
- `uv`
- Docker with Docker Compose
- `curl`; `jq` is recommended for the examples
- an OpenAI API key
- optional GitHub credentials when successful output should be published

Create the environment file and install dependencies:

```bash
cp .env.example .env
uv sync --all-extras
```

At minimum, set this value in `.env`:

```env
OPENAI_API_KEY=your_openai_api_key
```

For GitHub delivery, set both the owner and token. A partial configuration causes delivery to fail:

```env
GITHUB_OWNER=your-github-username
GITHUB_TOKEN=github_pat_xxxxxxxxx
GITHUB_REPOSITORY_VISIBILITY=private
GITHUB_COMMIT_AUTHOR_NAME=Your Name
GITHUB_COMMIT_AUTHOR_EMAIL=you@example.com
```

Choose whether successfully published source should remain under `data/`:

```env
# true: retain local generated source after GitHub publishing (default)
# false: remove only builds/ after GitHub publishing succeeds
CONTROL_RETAIN_LOCAL_BUILDS=false
```

The worker must always generate into a local workspace so it can run build, lint, type, test, smoke,
and publishing steps. The flag controls retention after delivery. PostgreSQL always keeps run,
step, event, artifact hash/availability, and GitHub reference data; it does not store source blobs.
If publishing is skipped or fails, source remains local to prevent data loss.

Never commit `.env` or print the GitHub token in logs. Restart the worker after changing `.env`;
long-running processes do not automatically reload all settings.

Start PostgreSQL, RabbitMQ, and Redis, then create both kinds of database schema:

```bash
make deps-up
make db-migrate
```

`make db-migrate` applies the async Alembic migrations for control-plane tables and creates the
LangGraph checkpoint tables. It is safe to rerun after pulling new migrations.

Check the containers:

```bash
docker compose -f docker-compose.control-plane.yml ps
```

The `postgres`, `rabbitmq`, and `redis` services should all be healthy. `make deps-down` stops them
without deleting their named volumes and stored data.

## 3. Start the product

Use three terminals from the repository root:

Terminal 1 — API:

```bash
make run-api
```

This is the stable operator mode. It deliberately does not use Uvicorn auto-reload, so generated
Python files under `data/` cannot restart the control plane during a run.

When changing control-plane source code, use the development command instead:

```bash
make run-api-dev
```

Development reload watches only `src/`, excluding generated workspaces, and limits graceful
shutdown waiting to five seconds when an SSE client is connected.

Terminal 2 — worker:

```bash
make run-worker
```

Terminal 3 — scheduler:

```bash
make run-beat
```

The standard worker consumes both `runs` and `maintenance`. For a larger deployment, run generation
and maintenance independently; `make run-maintenance-worker` starts a maintenance-only worker.

What each process does:

| Process | Responsibility | Expected startup evidence |
|---|---|---|
| FastAPI | Accept requests and serve run state/events/artifacts | Uvicorn listening on `127.0.0.1:8080` |
| Celery worker | Dispatch outbox records, execute runs, recover stale runs | Worker reports `celery@... ready` and lists `runs,maintenance` |
| Celery Beat | Schedule outbox dispatch every second and stale recovery every 60 seconds | Beat reports that it has started |

If the API log repeatedly says `WatchFiles detected changes` for paths under `data/projects`, it was
started with the old unrestricted reload command. Stop that process and restart it with
`make run-api` (stable) or `make run-api-dev` (source-only reload).

Verify liveness and dependency readiness:

```bash
curl -s http://127.0.0.1:8080/health/live | jq
curl -s http://127.0.0.1:8080/health/ready | jq
```

Healthy readiness output is:

```json
{
  "status": "ok",
  "checks": {
    "postgres": "ok",
    "redis": "ok",
    "rabbitmq": "ok"
  }
}
```

If `CONTROL_API_KEY` is configured, add `-H "X-API-Key: your-key"` to every `/api/v1` request.
Health endpoints do not require the API key.

## 4. Create a project

Create a durable project record:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Todo",
    "slug": "todo",
    "description": "Production Todo backend"
  }' | jq
```

Copy the returned `id`. It is a UUID such as `f27a2bb7-7741-49b2-a648-a4372f0b3ff5`:

```bash
PROJECT_ID="paste-project-uuid-here"
```

Use this UUID in URLs—not the project name or slug. Passing `todo` as `project_id` produces the
validation error “Value must be a Guid.”

Useful project operations:

```bash
curl -s http://127.0.0.1:8080/api/v1/projects | jq
curl -s "http://127.0.0.1:8080/api/v1/projects/$PROJECT_ID" | jq
curl -s "http://127.0.0.1:8080/api/v1/projects/$PROJECT_ID/runs" | jq
```

## 5. Submit a generation run

Create the run and queue it atomically:

```bash
curl -sS -X POST "http://127.0.0.1:8080/api/v1/projects/$PROJECT_ID/runs" \
  -H "Content-Type: application/json" \
  -d '{
    "request": "Build a production-grade Todo backend. Include user registration and login, secure JWT authentication, user profiles, and strict per-user data ownership. Implement create, update, delete, view, complete, and reopen operations for todos. A todo has title, description, Low/Medium/High priority, and an optional due date. Provide list, search, filter, sort, pagination, completed, pending, and overdue views. Include database migrations, validation, security, tests, linting, typing, and smoke checks.",
    "target_stack": "python",
    "clarification_gate_enabled": false,
    "idempotency_key": "todo-initial-build-001"
  }' | tee /tmp/app-builder-run.json | jq
```

Copy the returned run UUID:

```bash
RUN_ID="paste-run-uuid-here"
```

The API normally returns `202 Accepted` with `status=queued`. The request does not wait for code
generation.

The idempotency key is unique within the project. Repeating the same key returns the original run
with HTTP 200 and does not create a fresh build. Change the key or use the retry endpoint when a new
run is intended.

`target_stack` can be `python`, `nodejs`, or `both`. Use one stack unless a comparison is actually
needed; `both` performs both generations and their comparison.

## 6. Monitor the run through the API

### 6.1 Current status

```bash
curl -s "http://127.0.0.1:8080/api/v1/runs/$RUN_ID" \
  | jq '{status,phase,progress,current_step_id,worker_id,heartbeat_at,error_type,error_message,delivery_status,delivery_error,repository_url,repository_commit_url}'
```

Run statuses:

| Status | Meaning |
|---|---|
| `queued` | Accepted in PostgreSQL and awaiting or waiting in durable delivery |
| `running` | Claimed by a worker |
| `cancelling` | Cancellation recorded; worker will stop cooperatively at a boundary |
| `paused` | Resumable checkpointed work |
| `completed` | Generation, gates, and configured delivery succeeded |
| `failed` | Generation, verification, or configured delivery failed |
| `cancelled` | Work was cancelled |

While a run is active, `heartbeat_at` should advance about every 30 seconds and
`lease_expires_at` should remain in the future. `progress` and `current_step_id` are workflow
projections, not queue percentages.

### 6.2 Live events

Open a separate terminal:

```bash
curl -N "http://127.0.0.1:8080/api/v1/runs/$RUN_ID/events/stream"
```

The Server-Sent Events stream replays committed PostgreSQL events and then follows new ones. Each
frame includes an `id`. After a disconnect, resume after a known event with:

```bash
curl -N \
  -H "Last-Event-ID: 184" \
  "http://127.0.0.1:8080/api/v1/runs/$RUN_ID/events/stream"
```

The stream stops after a terminal run and sends heartbeat comments while idle.

### 6.3 Durable event and log replay

```bash
curl -s "http://127.0.0.1:8080/api/v1/runs/$RUN_ID/events?after_id=0&limit=1000" | jq
curl -s "http://127.0.0.1:8080/api/v1/runs/$RUN_ID/logs?after_id=0&limit=1000" | jq
```

Use `events` for the complete ordered audit stream. Use `logs` for the human-relevant projection.
For pagination, take the final returned event `id` and pass it as the next `after_id`.

### 6.4 Steps, attempts, and failures

```bash
curl -s "http://127.0.0.1:8080/api/v1/runs/$RUN_ID/steps" \
  | jq '.[] | {step_id,attempt,status,duration_ms,model,input_tokens,output_tokens,command,exit_code,retry_reason,error_type,error_message}'
```

This is the fastest structured view for finding the failed step and deciding what must be repaired.
For a failure, inspect `error_message`, `stack_trace`, `command`, `exit_code`, and `retry_reason`, then
correlate `step_id` with the readable step report on disk.

### 6.5 Artifacts and generated files

```bash
curl -s "http://127.0.0.1:8080/api/v1/runs/$RUN_ID/artifacts" | jq
```

Download one artifact using the artifact UUID returned above:

```bash
ARTIFACT_ID="paste-artifact-uuid-here"
curl -OJ "http://127.0.0.1:8080/api/v1/artifacts/$ARTIFACT_ID/download"
```

Artifact rows are indexed after workflow execution. An empty list during an active run does not mean
that the worker has not started writing files. A retained metadata row with
`local_available=false` represents published source removed by policy; its download endpoint returns
`410 Gone`, and the run's GitHub URL is the source location.

## 7. Inspect readable output on disk

With the default `CONTROL_ARTIFACT_ROOT=./data`, the run workspace is:

```text
data/projects/<project-uuid>/runs/<run-uuid>/
├── README.md                 # Start here: outcome, failures, and next actions
├── timeline.md               # Human-readable ordered step timeline
├── events.jsonl              # Append-only machine event stream
├── steps/                    # Per-step reports, prompts, responses, and errors
├── _machine/                 # Machine indexes and summaries
├── policy/
├── requirements/
├── architecture/
├── specs/
├── plans/
├── execution/
├── builds/
│   ├── python/               # Generated FastAPI project
│   └── nodejs/               # Generated Node.js project when selected
├── verification/
├── repairs/
├── reports/
└── checkpoints/
```

Open the run folder on macOS:

```bash
open "data/projects/$PROJECT_ID/runs/$RUN_ID"
```

For debugging, read files in this order:

1. `README.md` for the outcome and recommended action.
2. `timeline.md` to locate the first failed or retried step.
3. The matching file under `steps/` for its prompt, response, command, or error.
4. `verification/` and `reports/traceability.md` for gate evidence.
5. `events.jsonl` only for complete machine-level investigation.

Generated code can exist even when the overall run fails a later quality or traceability gate. Such
a run remains failed and is not published to GitHub, but the local build and diagnostic artifacts
remain available.

## 8. Verify PostgreSQL

Open an interactive SQL session inside the Compose container:

```bash
docker compose -f docker-compose.control-plane.yml exec postgres \
  psql -U app_builder -d app_builder
```

List the relevant tables:

```sql
\dt
```

### 8.1 Projects and runs

```sql
SELECT id, slug, name, archived_at, created_at
FROM projects
ORDER BY created_at DESC;

SELECT
    id,
    project_id,
    retry_of_id,
    status,
    phase,
    round(progress::numeric, 4) AS progress,
    current_step_id,
    queue_task_id,
    worker_id,
    queued_at,
    started_at,
    heartbeat_at,
    lease_expires_at,
    finished_at,
    error_type,
    error_message,
    delivery_status,
    repository_url,
    repository_commit_sha
FROM runs
ORDER BY created_at DESC
LIMIT 20;
```

For one run, replace the UUID:

```sql
SELECT *
FROM runs
WHERE id = 'paste-run-uuid-here'::uuid;
```

### 8.2 Outbox dispatch

```sql
SELECT
    id,
    aggregate_id AS run_id,
    topic,
    attempts,
    available_at,
    published_at,
    last_error,
    created_at
FROM outbox_messages
ORDER BY created_at DESC
LIMIT 20;
```

Interpretation:

- `published_at IS NULL`, a future `available_at`, and `last_error` set: broker publishing failed and
  exponential backoff is active.
- `published_at IS NULL` with no error for more than a few seconds: Beat or the maintenance worker is
  not dispatching.
- `published_at IS NOT NULL`: the command was confirmed to RabbitMQ; inspect the `runs` queue next.
- `outbox_messages.id` becomes the Celery task ID and should match `runs.queue_task_id` after claim.

### 8.3 Steps and events

```sql
SELECT
    step_id,
    attempt,
    status,
    duration_ms,
    model,
    input_tokens,
    output_tokens,
    command,
    exit_code,
    retry_reason,
    error_type,
    error_message
FROM run_steps
WHERE run_id = 'paste-run-uuid-here'::uuid
ORDER BY started_at, attempt;

SELECT
    id,
    occurred_at,
    event_type,
    step_id,
    status,
    level,
    message
FROM run_events
WHERE run_id = 'paste-run-uuid-here'::uuid
ORDER BY id;
```

`run_events` is append-only and its numeric `id` is the SSE replay cursor. `run_steps` is the compact
attempt projection.

### 8.4 Artifacts and checkpoints

```sql
SELECT id, step_id, kind, filename, sha256, size_bytes, created_at
FROM artifacts
WHERE run_id = 'paste-run-uuid-here'::uuid
ORDER BY created_at;

SELECT thread_id, checkpoint_id
FROM checkpoints
WHERE thread_id = 'paste-run-uuid-here'
ORDER BY checkpoint_id DESC
LIMIT 10;
```

The `artifacts` table stores metadata, hashes, `local_available`, and `local_deleted_at`. Bytes remain
under `CONTROL_ARTIFACT_ROOT` while locally retained; published build bytes can be removed by the
retention policy without deleting their metadata.
`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, and `checkpoint_migrations` belong to
LangGraph and are created separately from Alembic.

Exit `psql` with `\q`. Avoid manually changing run, outbox, event, or checkpoint records; use the
API lifecycle operations so transitions remain auditable.

## 9. Inspect RabbitMQ

Open `http://127.0.0.1:15672` and log in with:

```text
Username: app_builder
Password: app_builder
Virtual host: app_builder
```

Select the `app_builder` virtual host before interpreting queue data.

### 9.1 `runs` queue

Open **Queues and Streams → runs** and check:

| Metric | Meaning | Healthy expectation |
|---|---|---|
| Type | Queue implementation | `quorum` |
| State | Queue process state | `running` |
| Ready | Published tasks waiting for a consumer | Usually zero; may rise when all workers are busy |
| Unacked | Tasks delivered but not yet acknowledged | Positive while generation is actively running |
| Total | `Ready + Unacked` | Matches current broker backlog, not all database runs |
| Consumers | Worker task slots consuming this queue | Greater than zero when the worker is running |
| Incoming | Publish rate | Increases when outbox records are dispatched |
| Deliver/Get | Delivery rate to workers | Increases when workers claim tasks |
| Ack | Completed acknowledgements | Increases after tasks finish |
| Redelivered | Tasks delivered again | Normally low; sustained growth suggests worker loss/crashes |

Workers use late acknowledgement and a prefetch multiplier of one. Consequently, a long-running
generation remains `Unacked` for minutes; that is expected. If a worker dies, RabbitMQ can redeliver
the unacknowledged task.

### 9.2 `maintenance` queue

This queue carries:

- `control_plane.dispatch_outbox`, scheduled every second
- `control_plane.recover_stale_runs`, scheduled every 60 seconds

Its Ready count should remain near zero and it should have a consumer. A steadily growing Ready
count indicates that no worker is consuming maintenance work or all available worker slots are
starved. If maintenance is not processed, new database runs can remain queued without reaching the
`runs` queue.

### 9.3 Connections, channels, exchanges, and bindings

Also inspect:

- **Connections/Channels:** confirm Celery worker and Beat broker connections exist and are not
  repeatedly reconnecting.
- **Exchanges:** `runs` and `maintenance` are declared as durable direct exchanges.
- **Bindings:** confirm both queues have bindings and that the default exchange also has the normal
  queue-name bindings. Celery can use those direct-to-queue bindings as an optimization, so the
  queue's incoming/delivery counters are more useful than a named exchange's counters alone.
- **Overview rates:** publish, deliver, acknowledge, and redelivery trends expose a stalled or
  crash-looping system.

Do not use **Get messages** on a live queue unless you understand its acknowledgement/requeue
behavior. Do not purge either queue during normal operation; purging can discard pending work.

The local Compose setup has one RabbitMQ node. Its queues use quorum semantics, but one node does not
provide node-level high availability. A production RabbitMQ quorum queue normally needs a
multi-node cluster. The management UI retains recent operational metrics, not durable run history.

Official references: [RabbitMQ management UI](https://www.rabbitmq.com/docs/management),
[queue metrics](https://www.rabbitmq.com/docs/queues), and
[quorum queues](https://www.rabbitmq.com/docs/quorum-queues).

## 10. Inspect Celery

The worker and Beat terminal logs are the first Celery-level views. The worker should log task
receipt and completion/failure; Beat should continue scheduling maintenance tasks.

Run these from another terminal:

```bash
uv run celery -A src.control_plane.queue:celery_app status
uv run celery -A src.control_plane.queue:celery_app inspect registered
uv run celery -A src.control_plane.queue:celery_app inspect active
uv run celery -A src.control_plane.queue:celery_app inspect reserved
uv run celery -A src.control_plane.queue:celery_app inspect stats
```

What to look for:

| Inspection | Expected evidence |
|---|---|
| `status` | At least one online worker |
| `registered` | `control_plane.execute_run`, `control_plane.dispatch_outbox`, and `control_plane.recover_stale_runs` |
| `active` | `control_plane.execute_run` while a generation is running; task ID should match `queue_task_id` |
| `reserved` | Tasks prefetched but not started; normally small because prefetch is one |
| `stats` | Pool/concurrency and broker information for capacity diagnosis |

Celery Inspect only reaches online workers. An empty or “No nodes replied” result usually means the
worker is stopped, connected to a different broker/vhost, or not reachable. Beat schedules periodic
tasks but is not itself an execution worker, and its schedule does not appear as run status.

No Flower dashboard is configured. RabbitMQ shows delivery, Celery logs/Inspect show execution, and
the API/PostgreSQL show durable product state.

## 11. Inspect Redis

Redis is used for best-effort run event notifications. PostgreSQL events and SSE polling preserve
correctness if notification publishing fails, although `/health/ready` reports Redis as degraded.

Check it with:

```bash
docker compose -f docker-compose.control-plane.yml exec redis redis-cli PING
```

Expected output is `PONG`. Do not use Redis keys or Pub/Sub state as proof that a run completed.

## 12. Verify GitHub delivery

GitHub publishing begins only after the selected builders and required gates complete successfully.
Inspect the run response:

```bash
curl -s "http://127.0.0.1:8080/api/v1/runs/$RUN_ID" \
  | jq '{status,delivery_status,delivery_error,repository_owner,repository_name,repository_url,repository_branch,repository_commit_sha,repository_commit_url,published_at}'
```

Delivery statuses:

| Status | Meaning |
|---|---|
| `pending` | Run has not reached delivery yet |
| `publishing` | Repository creation/commit is in progress |
| `completed` | Repository and commit fields are populated |
| `skipped` | Neither GitHub owner nor token was configured |
| `failed` | GitHub configuration or API operation failed; see `delivery_error` |
| `not_attempted` | Generation did not reach successful delivery |

Publishing behavior:

1. The project slug is tried as the repository name.
2. If it already exists, a random six-character suffix is added.
3. A successful Python-only run publishes `builds/python` at repository root.
4. The run stores the repository, branch, commit SHA, and clickable URLs.
5. Run markers make redelivered publishing idempotent rather than creating duplicate commits.

The event stream records `github_publish_started`, `github_publish_completed`,
`github_publish_failed`, or `github_publish_skipped`.

## 13. Cancel, resume, or retry

Cancel queued or running work:

```bash
curl -sS -X POST "http://127.0.0.1:8080/api/v1/runs/$RUN_ID/cancel" | jq
```

A queued run is cancelled immediately. A running run is cancelled cooperatively at workflow
boundaries, so it may not stop in the middle of a model or shell call.

Resume a `failed`, `cancelled`, or `paused` run from the same run ID and latest LangGraph checkpoint:

```bash
curl -sS -X POST "http://127.0.0.1:8080/api/v1/runs/$RUN_ID/resume" | jq
```

Create a completely new run with the same request and a `retry_of_id` link:

```bash
curl -sS -X POST "http://127.0.0.1:8080/api/v1/runs/$RUN_ID/retry" \
  | tee /tmp/app-builder-retry.json | jq
```

Use resume for a checkpoint-safe continuation after an environmental interruption. Use retry when
you want independent events, artifacts, and checkpoint state or after changing code/configuration.

## 14. Troubleshooting matrix

| Symptom | Check in order | Likely cause/action |
|---|---|---|
| `/health/ready` is 503 | Returned check, then Compose `ps` | Start or repair the named dependency |
| Run stays `queued`; outbox `published_at` is null | Beat log, maintenance consumer, `last_error` | Start Beat/worker or repair broker connectivity |
| Outbox is published; RabbitMQ `runs` Ready grows | `runs` Consumers, worker terminal | Generation worker is absent or at capacity |
| Run is `running`; RabbitMQ shows one Unacked; heartbeat is fresh | Worker `active`, events | Normal long-running generation |
| Run is `running`; no Unacked task; heartbeat/lease are stale | Worker crash log, Beat recovery log | Wait for 60-second recovery scan or restart scheduler/worker |
| RabbitMQ redeliveries continually increase | Worker exceptions and restarts | Crash loop, lost worker, or infrastructure instability |
| Run failed but generated code exists | Steps, verification, traceability report | A later gate failed; repair evidence/code and retry or resume |
| Run failed with no useful API message | Last events, failed step, worker traceback | Inspect durable event payload and per-step report |
| `artifact_index_failed` event | Artifact path and worker log | Runtime links/dependency trees are excluded; the event remains secondary to an earlier gate failure |
| Artifacts API is empty while status is running | Local run directory | Artifact indexing occurs after workflow execution |
| Status completed but delivery is skipped | Worker startup environment | Configure both GitHub variables and restart worker for future runs |
| Delivery failed | `delivery_error`, GitHub publish events | Owner/token mismatch, permissions, limits, or GitHub API failure |
| Artifact download returns 410 | Run repository/commit URL | Local retention was disabled after successful publishing |
| Request returns existing completed run immediately | HTTP status and idempotency key | Reused key; use a new key or retry endpoint |
| “Value must be a Guid” | URL path parameter | Use returned project/run UUID, not name or slug |
| Celery Inspect says no nodes replied | Worker process and broker/vhost config | Start worker or align `CONTROL_BROKER_URL` |

## 15. End-to-end success checklist

A run is fully successful when all of the following are true:

- `/health/ready` is healthy.
- The project and run exist in PostgreSQL.
- The outbox record has `published_at` set.
- RabbitMQ delivered the task and eventually acknowledged it.
- The run reached `completed`, with `finished_at` populated and no terminal error.
- All required `run_steps` and quality/traceability evidence passed.
- The artifact list and local run directory contain reports and generated code.
- When GitHub is configured, `delivery_status=completed` and the stored commit URL opens the
  generated code.

For schema details, see [Control-plane data model](control-plane-data-model.md). For request and
response contracts, see [Control-plane API contracts](control-plane-api-contracts.md). For the
internal sequence, see [Control-plane data flow](control-plane-data-flow.md).

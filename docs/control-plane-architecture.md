# Durable Control-Plane Architecture

## Purpose

The control plane turns the existing LangGraph generator into an API-driven, durable job system.
The CLI remains available, but API runs are accepted quickly and executed by queue workers.

```text
client
  │ HTTP + SSE
  ▼
FastAPI control plane ───────────────┐
  │ async SQLAlchemy / asyncpg      │ artifact download
  ▼                                 ▼
PostgreSQL                     local ArtifactStore
  │ transactional outbox             data/projects/<project>/<run>/
  ▼
Celery beat/dispatcher → RabbitMQ quorum queue → Celery run worker
                                                  │
                                                  ▼
                                     LangGraph + Postgres checkpoints
                                                  │
                                  events/steps/status/artifacts → PostgreSQL
                                                  │
                           successful delivery → GitHub Git database API
                                                  │
                                       notification hint → Redis
```

## Component responsibilities

- **FastAPI** validates commands and serves project, run, event, log, artifact, and health views.
- **PostgreSQL** is authoritative for lifecycle state, event history, step attempts, outbox delivery,
  leases, usage, and artifact metadata.
- **SQLAlchemy asyncio + asyncpg** is the only control-plane application persistence path.
- **RabbitMQ quorum queues** deliver long-running work at least once. RabbitMQ is not queried as a
  source of user-visible status.
- **Celery beat** schedules outbox dispatch and stale-run recovery.
- **Celery workers** claim runs, heartbeat their leases, run LangGraph, and index output artifacts.
- **LangGraph `AsyncPostgresSaver`** owns its checkpoint tables. It uses its upstream `psycopg`
  adapter in isolation; Alembic deliberately ignores these externally managed tables.
- **Redis** receives best-effort event notifications. Durable SSE replay always reads PostgreSQL,
  so a Redis outage does not lose history.
- **ArtifactStore** is a port. The current `LocalArtifactStore` provides run isolation and traversal-
  safe downloads. S3 can implement the same port later.
- **GitHub delivery** creates a new personal repository after generation gates pass, commits only the
  selected generated build, and records the repository/commit identity on the run.

## Reliability model

1. Creating a run inserts the run, initial event, and outbox row in one database transaction.
2. The dispatcher publishes an outbox row with publisher confirms, then marks it published.
3. A crash between those operations may duplicate delivery; run claims and source event IDs make
   processing idempotent.
4. Workers acknowledge late and RabbitMQ requeues work when a worker process is lost.
5. A worker holds a database lease and refreshes it every 30 seconds. The recovery task requeues an
   expired lease from the latest LangGraph checkpoint.
6. Cancellation is durable in PostgreSQL and cooperative at workflow node boundaries.
7. `resume` continues the same run/thread from a checkpoint. `retry` creates a new linked run.
8. GitHub delivery persists its repository reservation and embeds the run ID in the repository and
   commit, making worker redelivery idempotent.

This is at-least-once execution, not exactly-once execution. External side effects added later must
use their own idempotency keys.

## Scaling

- Scale API processes independently; they are stateless apart from database connections.
- Scale `runs` workers horizontally. `worker_prefetch_multiplier=1` prevents one worker from
  reserving many long jobs.
- Run maintenance workers separately at larger scale so outbox dispatch is never starved by model
  calls.
- PostgreSQL row locks with `SKIP LOCKED` allow multiple dispatchers and recovery workers.
- Local artifacts require shared storage when workers run on multiple hosts. Until S3 is introduced,
  mount one durable shared volume at `CONTROL_ARTIFACT_ROOT`.

## Security boundary

Set `CONTROL_API_KEY` to require `X-API-Key` on `/api/v1/*`. Health endpoints remain unauthenticated
for orchestrator probes. Artifact paths are never accepted directly from clients; downloads resolve
only database-owned storage keys beneath the configured artifact root.


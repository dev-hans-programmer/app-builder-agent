# Control-Plane Data Model

## Ownership

```text
projects 1 ── * runs 1 ── * run_steps
                   │  ├── * run_events
                   │  └── * artifacts
                   └── 0..1 retry_of → runs

outbox_messages ── aggregate_id → run ID (logical reference)
```

## Tables

### `projects`

Stable project identity, unique slug, metadata, and `archived_at`. Archiving prevents new runs but
keeps history queryable.

### `runs`

One submitted generation. It stores the immutable request/stack and mutable lifecycle projection:
status, phase, progress, current step, Celery task/worker, queue/start/finish times, heartbeat/lease,
cancellation, terminal error, token totals, estimated cost, retry lineage, and GitHub delivery status,
repository URL/name/branch, commit SHA/URL, error, and publication time.

`(project_id, idempotency_key)` is unique. Status and project/history access have composite indexes.

### `run_steps`

One row per `(run_id, step_id, attempt)`. It contains parent/spec/task IDs, model and prompt identity,
tokens/cost, command and exit code, retry reason, timestamps/duration, and complete error diagnostics.
This is the fastest view for “what failed and what must be fixed?”

### `run_events`

The append-only audit/log stream. Its monotonically increasing ID is the SSE cursor. The full
redacted observability payload is retained as JSON alongside indexed run/type/status fields.
`(run_id, source_event_id)` prevents duplicate ingestion after checkpoint resume or redelivery.

### `artifacts`

Metadata for files produced by a run: logical storage key, filename, type, SHA-256, byte size, and
optional producing step. `(run_id, storage_key)` is unique. `local_available` and
`local_deleted_at` distinguish retained bytes from metadata for a published build removed by policy.
File bytes live beneath the local artifact root while retained; paths are not exposed in API
responses.

### `outbox_messages`

Durable broker intent written in the same transaction as a run transition. It tracks topic,
payload, attempts, retry availability, publish time, and last broker error. Multiple dispatchers use
`FOR UPDATE SKIP LOCKED`.

### LangGraph checkpoint tables

`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, and `checkpoint_migrations` are owned by
`AsyncPostgresSaver`. They share PostgreSQL but are intentionally excluded from Alembic comparison.

## Migration ownership

Control-plane tables are managed by the async Alembic environment in
`migrations/control_plane/`. Alembic connects through `postgresql+asyncpg`. Checkpoint schema setup
is a separate idempotent command because it is versioned by LangGraph.


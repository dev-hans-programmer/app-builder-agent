# Control-Plane Data Flow

## Submit and dispatch

```text
POST run
  → validate project and idempotency key
  → transaction: runs + run_events(run_queued) + outbox_messages
  → 202 + Location
  → beat schedules dispatcher
  → dispatcher locks pending outbox rows
  → publish-confirm to RabbitMQ quorum queue
  → mark outbox published
```

No request waits for generation. If the broker is unavailable, the outbox retains the command and
backs off; the run remains visibly queued.

## Execute and observe

```text
RabbitMQ delivery
  → worker locks/claims run and starts lease heartbeat
  → open LangGraph AsyncPostgresSaver(thread_id = run_id)
  → initialize or load checkpoint
  → execute workflow node
  → append local human-readable diagnostics
  → bridge event into PostgreSQL transaction
      ├── append run_events
      ├── upsert run_steps
      └── update runs projection and lease
  → best-effort Redis notification
  → next node
  → index artifacts + hashes
  → if gates passed: reserve GitHub name → create repo → commit generated build
  → if configured: remove local builds after confirmed GitHub commit and mark metadata unavailable
  → terminal run status
  → late RabbitMQ acknowledgement
```

The synchronous generation nodes never create their own async connection pools. Their observability
callbacks submit writes to the worker's existing event loop and continue only after PostgreSQL has
committed the event.

## Monitor and replay

```text
GET run       → current projection from runs
GET steps     → attempt/error projection from run_steps
GET events    → ordered audit stream from run_events
SSE stream    → replay after Last-Event-ID, poll for committed events, heartbeat, stop at terminal
GET artifacts → metadata from PostgreSQL; bytes through ArtifactStore
```

Redis notifications are an optimization, not a correctness dependency. The initial SSE adapter polls
PostgreSQL at a short interval, so reconnect and Redis outages cannot create a monitoring gap.

## Cancel, resume, and recover

- **Cancel:** the API commits `cancel_requested_at`. The worker checks at node boundaries, emits a
  cancellation event, and ends as `cancelled`. A queued run is cancelled immediately.
- **Resume:** a resumable run is queued with the same run ID; the worker invokes LangGraph with no new
  input when a checkpoint exists.
- **Retry:** a fresh run is created with `retry_of_id`; its audit and artifacts are independent.
- **Worker loss:** RabbitMQ redelivers unacknowledged work. The same task ID may reclaim immediately.
  A periodic recovery scan also requeues expired database leases from their latest checkpoint.
- **GitHub redelivery:** the reserved repository name and run marker allow the worker to reuse a
  repository or completed commit after a crash instead of creating duplicates.


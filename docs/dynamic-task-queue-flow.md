# Dynamic Task Queue and Recovery Flow

## Planning and dispatch

```text
execute_run
  → LangGraph stops after planning
  → transaction persists task DAG
  → scheduler selects dependency-free task
  → transaction writes task=queued + outbox(run.task.execute)
  → dispatcher publishes to `run_tasks`
```

The dispatcher maps outbox topics to dedicated Celery commands:

| Topic | Celery task | Queue |
|---|---|---|
| `run.execute` | `control_plane.execute_run` | `runs` |
| `run.task.execute` | `control_plane.execute_run_task` | `run_tasks` |
| `run.finalize` | `control_plane.finalize_dynamic_run` | `runs` |

## Task execution

The task worker locks the task and run, creates an append-only attempt, establishes a five-minute
lease refreshed every 30 seconds, loads the planning checkpoint, and supplies only the current task
to the Python builder. A successful task stores its output and patch hash before unlocking the next
dependency-satisfied task.

`worker_prefetch_multiplier=1`, late acknowledgements, worker-loss rejection, publisher confirms,
and RabbitMQ quorum queues provide at-least-once delivery. Database status and row locks provide
idempotent claims.

## Recovery and retry

Beat scans expired task leases every 60 seconds. An expired running attempt is marked
`WorkerLeaseExpired`, the same task is requeued, and completed predecessors are not regenerated.
Temporary failures back off exponentially up to five minutes. Manual task retry adds one attempt
budget and creates a new outbox command.

When all tasks succeed, the scheduler emits `run.finalize`. The finalizer reconstructs the aggregated
Python output, advances the existing LangGraph checkpoint as the Python builder, and executes the
full quality, repair, traceability, report, artifact, and GitHub delivery path.


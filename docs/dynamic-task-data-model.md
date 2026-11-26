# Dynamic Task Data Model

PostgreSQL remains the source of truth. RabbitMQ only carries delivery commands.

## `runs`

`execution_mode` snapshots `legacy`, `dynamic_serial`, or `dynamic_parallel` for the complete run.
During dynamic execution, `progress` is a weighted task projection capped below completion until the
final integration gate passes.

## `run_tasks`

One mutable scheduler projection per planned task:

```text
identity: id, run_id, task_key, plan_task_id
contract: kind, objective, criteria/contracts/policy ids, allowed paths, verification
scheduling: status, sequence, priority, weight, attempt/max-attempt counts
lease: queue task, worker, heartbeat, lease expiry
evidence: input context hash, output patch hash, output JSON
failure: error type/message and lifecycle timestamps
```

Statuses are:

```text
waiting_dependencies → ready → queued → running → succeeded
                                           └────→ failed/cancelled
dependency failure   → blocked
```

## `run_task_dependencies`

A composite-key adjacency table containing `task_id → depends_on_task_id`. The scheduler queues a
task only when every predecessor is `succeeded`. Failed, cancelled, or blocked predecessors block
their downstream tasks.

## `run_task_attempts`

Append-only execution evidence for every delivery attempt, including worker identity, model and
prompt identity, tokens/cost, duration, output, and errors. Retrying never overwrites prior evidence.

## Existing observability tables

`run_events` receives task-plan, queue, start, success, failure, recovery, retry, and integration
events. `run_steps` remains the LangGraph node-attempt projection. Task scheduling state is not
stored in `run_steps` because it must be mutable and dependency-queryable.


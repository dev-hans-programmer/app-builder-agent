# Control-Plane API Contracts

The versioned base path is `/api/v1`. JSON is used except for artifact downloads and SSE. When
`CONTROL_API_KEY` is set, send `X-API-Key`.

## Projects

| Method | Path | Result |
|---|---|---|
| `POST` | `/api/v1/projects` | Create a project; `201` |
| `GET` | `/api/v1/projects` | List active projects |
| `GET` | `/api/v1/projects/{project_id}` | Get one project |
| `PATCH` | `/api/v1/projects/{project_id}` | Change name/description |
| `DELETE` | `/api/v1/projects/{project_id}` | Soft archive; `204` |

Create body:

```json
{"name":"Todo","slug":"todo","description":"Production Todo API"}
```

## Runs and monitoring

| Method | Path | Result |
|---|---|---|
| `POST` | `/api/v1/projects/{project_id}/runs` | Atomically create and queue; `202` |
| `GET` | `/api/v1/projects/{project_id}/runs` | Run history |
| `GET` | `/api/v1/runs/{run_id}` | Status, progress, usage, error, and GitHub delivery result |
| `GET` | `/api/v1/runs/{run_id}/steps` | Every node attempt and its diagnostics |
| `GET` | `/api/v1/runs/{run_id}/tasks` | Dynamic task DAG and current task status |
| `GET` | `/api/v1/runs/{run_id}/tasks/{task_id}` | One task projection and dependency IDs |
| `GET` | `/api/v1/runs/{run_id}/tasks/{task_id}/attempts` | Append-only task attempt history |
| `POST` | `/api/v1/runs/{run_id}/tasks/{task_id}/retry` | Requeue one failed task; `202` |
| `GET` | `/api/v1/runs/{run_id}/events` | Durable event replay (`after_id`, `limit`) |
| `GET` | `/api/v1/runs/{run_id}/logs` | Human-relevant event/log projection |
| `GET` | `/api/v1/runs/{run_id}/events/stream` | Live Server-Sent Events |
| `GET` | `/api/v1/runs/{run_id}/artifacts` | Artifact metadata, hashes, and local availability |
| `POST` | `/api/v1/runs/{run_id}/cancel` | Durable cooperative cancellation |
| `POST` | `/api/v1/runs/{run_id}/resume` | Requeue same checkpoint thread; `202` |
| `POST` | `/api/v1/runs/{run_id}/retry` | Create a new run linked by `retry_of_id`; `202` |

Create body:

```json
{
  "request": "Build a Todo backend with authentication and owned todos",
  "execution_mode": "dynamic_serial",
  "clarification_gate_enabled": false,
  "idempotency_key": "client-request-0182"
}
```

The idempotency key is unique within a project. Repeating it returns the existing run with `200`
instead of enqueuing another generation.

Run statuses are `queued`, `running`, `cancelling`, `paused`, `completed`, `failed`, or `cancelled`.
The run record, not Celery/RabbitMQ state, is the public lifecycle contract.

Successful configured deliveries expose `delivery_status=completed`, `repository_url`,
`repository_branch`, `repository_commit_sha`, `repository_commit_url`, and `published_at`. Delivery
failure details appear in `delivery_error` and make the overall run fail.

## SSE replay

Each frame contains the database event ID:

```text
id: 184
event: step_finished
data: {"id":184,"run_id":"...","step_id":"quality_gate",...}
```

Reconnect with `Last-Event-ID: 184`. The server replays all later events from PostgreSQL before
continuing live delivery. Heartbeat comments keep idle connections open.

## Artifacts and health

| Method | Path | Result |
|---|---|---|
| `GET` | `/api/v1/artifacts/{artifact_id}/download` | Traversal-safe file response |
| `GET` | `/health/live` | Process liveness |
| `GET` | `/health/ready` | PostgreSQL, RabbitMQ, and Redis readiness |

There are 23 operations in the current API surface. FastAPI exposes the generated OpenAPI document
at `/openapi.json` and interactive docs at `/docs`.

Artifact metadata remains queryable after retention cleanup. Download returns `410 Gone` when
`local_available=false`; use the run's `repository_url` or `repository_commit_url` for published
source code.

Errors use either FastAPI validation details or the application envelope:

```json
{"error":{"code":"conflict","message":"Run is already completed"}}
```


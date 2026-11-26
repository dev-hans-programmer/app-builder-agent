# Dynamic Python Task Architecture

## Purpose

Dynamic execution replaces the fixed foundation/platform/authentication/feature/delivery sequence
with a validated dependency graph sized from approved acceptance criteria and architecture
contracts. It is currently Python-only. Node.js and dual-stack runs remain on the legacy workflow.

Enable the rollout mode with:

```env
CONTROL_EXECUTION_MODE=dynamic_serial
```

The API may override this per run with `execution_mode`. Existing runs retain the mode stored on
their `runs` row, so configuration changes do not alter resumability.

## Components

```text
LangGraph planning through `planning`
  → deterministic Python DAG validation
  → run_tasks + run_task_dependencies
  → transactional outbox
  → RabbitMQ `run_tasks` quorum queue
  → task worker: bounded generation + syntax/Ruff checks
  → dependency scheduler
  → final integration: full quality/repair/traceability gates
  → GitHub delivery
```

The planner groups non-authentication criteria by contracted API resource or data entity and caps a
feature task at three acceptance criteria. Foundation, platform, authentication when required, and
delivery remain explicit boundary tasks. The delivery task depends on every implementation task.

The model proposes file contents, not scheduler structure. Task IDs, coverage, dependency existence,
cycle detection, maximum criteria per slice, and allowed paths are deterministic.

## Serial-first execution

`dynamic_serial` queues only one code-writing task per run. Each task is independently durable and
retryable, but tasks cannot race over the same local workspace. This provides task-level recovery
without introducing merge conflicts.

`dynamic_parallel` is present as a forward-compatible mode but should not be enabled in production
until task worktrees, conflict-safe merge ordering, and shared workspace storage are implemented.
The current local artifact backend requires every task for a run to execute on a host that can see
the same `CONTROL_ARTIFACT_ROOT`.

## Task completion

A task succeeds only after the model response passes path ownership validation and task-scoped
syntax/Ruff checks. After all tasks succeed, the existing full architecture, dependency, build,
format, lint, type, test, migration, smoke, container, repair, and traceability gates run against
the integrated workspace. GitHub delivery remains impossible before this final gate completes.

Temporary infrastructure failures retry with backoff. Exhausted API credits and invalid API keys
are terminal immediately and surface as `ModelQuotaExceeded` rather than consuming all attempts.

## Compatibility

- `legacy` preserves the original single run-worker workflow.
- `dynamic_serial` uses database-backed task scheduling.
- Existing legacy checkpoints are unchanged.
- Retried runs inherit the source run's execution mode.
- Task planning is versioned as `dynamic-v1` in the execution plan and events.


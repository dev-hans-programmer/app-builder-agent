# Generation Pipeline

The builder uses a gated, evidence-producing workflow. Code is not considered delivered merely
because a model returned files.

```text
requirements
  → Python production policy snapshot (Python runs only)
  → approved acceptance criteria
  → architecture and contracts
  → executable tasks
  → task-level code patches
  → build / lint / type / test / smoke checks
  → targeted repair loop (maximum two attempts)
  → requirement traceability gate
  → completed delivery
```

## Python production policy

The canonical `backend-prompt.md` is loaded before requirement analysis. Its SHA-256 digest and exact contents
are snapshotted into `projects/<project>/policy/`, so every later prompt and report can identify
the policy version used for that run.

The policy first becomes binding in the Python
architecture blueprint, which records mandatory clean-architecture boundaries and explicit
include/omit decisions for conditional components such as Redis and workers. Python execution uses
dedicated `PY-TASK-###` tasks for the foundation, platform, authentication when requested,
business vertical slices, and delivery.

Each Python task receives only the policy sections relevant to its purpose and must return a JSON
envelope containing its task ID, acceptance IDs, policy rule IDs, and complete changed files.
Incorrect IDs and writes outside the task's declared paths are rejected before files are applied.

## 1. Requirements and acceptance approval

The requirement analyzer normalizes only the submitted request. It does not pause every run for
generic persistence, authentication, or deployment questions. Each functional and requested
non-functional requirement receives a stable `AC-###` ID.

The request submission is treated as approval of that baseline. This keeps unattended runs moving
while making the exact generation scope explicit. Review these files before investigating later
stages:

- `requirements/prd.md`
- `requirements/acceptance-criteria.md`

## 2. Architecture and contracts

Architecture is derived after acceptance approval. Human-readable artifacts are split by purpose:

- `architecture/technical-design.md` — layers, modules, boundaries, decisions, and risks
- `architecture/api-contracts.md` — method, path, schemas, statuses, and acceptance links
- `architecture/data-contracts.md` — entity fields and acceptance links
- `architecture/python-production-architecture.md` — Python policy version, mandatory structure,
  dependency rules, deliverables, and conditional infrastructure decisions

Contract IDs (`API-###`, `DATA-###`, and `ERROR-001`) are carried into implementation tasks and
model prompts. They are generation constraints, not background prose.

## 3. Executable tasks and task-level patches

Specs are reduced to ordered `TASK-###` records in `plans/tasks.md`. Python policy runs also have
ordered `PY-TASK-###` records. A task records its module,
objective, dependencies, acceptance IDs, contract IDs, and required verification categories.

Each selected stack receives one model request per executable task. Every request includes the
approved requirements, architecture contracts, current task, and a bounded snapshot of files
already generated. The model may return only complete contents for files created or changed by
that task.

Every applied file records:

- task and spec ID
- acceptance and contract IDs
- created or updated operation
- SHA-256 before and after the patch

Model-provided absolute paths and paths that escape the stack build directory are rejected.

## 4. Quality gates

After generation, `verification/quality-report.md` records commands, exit codes, duration, and
bounded stdout/stderr for each stack. The gate covers:

- build or syntax compilation
- lint when a linter is available/configured
- type checking when a checker is available/configured
- automated tests (required)
- application import/syntax smoke check (required)

For policy-driven Python runs, dependency locking, Ruff formatting, Ruff linting, mypy, pytest,
Alembic heads, and application import are mandatory. A deterministic architecture validator also
checks required deliverables, dependency declarations, layer-import rules, centralized errors,
versioned routes, health endpoints, settings, telemetry, metrics, PostgreSQL, container posture,
conditional-infrastructure decisions, and authentication evidence when authentication is in the
approved contracts. Its actionable findings are written to
`verification/python-policy-compliance.md` and participate in the repair loop.

Missing optional tools are shown as skipped. Missing tests or application entry points fail the
gate. Commands run without a shell and model/API secrets are removed from the subprocess
environment.

## 5. Targeted repair

Failed command evidence and current files are sent to a repair prompt for only the failing stack.
The repair may update complete files but must preserve unrelated behavior and all approved
contracts. Reports are written as `repairs/attempt-1.md` and `repairs/attempt-2.md`.

The workflow reruns the full quality gate after each repair. After two unsuccessful attempts it
continues to traceability as a failed delivery; it does not report success.

## 6. Traceability and delivery

`reports/traceability.md` maps every `AC-###` criterion to:

- architecture contract IDs
- executable task IDs
- per-stack patched files
- per-stack generated acceptance-test files
- build, lint, type, test, and smoke evidence

An online generation completes successfully only when all selected builders succeeded, required
quality checks passed, generated tests are linked, and every approved criterion has complete
evidence. A Python policy run must also have a passing policy-compliance result. The final
`reports/delivery-summary.md` links the outcome and run diagnostics.

## Run diagnostics

The run remains inspectable in `runs/<run_id>/`:

- `README.md` — outcome and next actions
- `timeline.md` — chronological steps and attempts
- `steps/*.md` — readable prompts, responses, errors, and step results
- `events.jsonl` — append-only canonical event stream
- `_machine/` — compact machine indexes and summaries

Queue-backed execution can later wrap this pipeline without changing its gates: the durable job
can resume from checkpoints and expose the same events as progress updates.

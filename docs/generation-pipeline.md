# Generation Pipeline

The builder uses a gated, evidence-producing workflow. Code is not considered delivered merely
because a model returned files.

```text
requirements
  → approved acceptance criteria
  → architecture and contracts
  → executable tasks
  → task-level code patches
  → build / lint / type / test / smoke checks
  → targeted repair loop (maximum two attempts)
  → requirement traceability gate
  → completed delivery
```

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

Contract IDs (`API-###`, `DATA-###`, and `ERROR-001`) are carried into implementation tasks and
model prompts. They are generation constraints, not background prose.

## 3. Executable tasks and task-level patches

Specs are reduced to ordered `TASK-###` records in `plans/tasks.md`. A task records its module,
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
evidence. The final
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

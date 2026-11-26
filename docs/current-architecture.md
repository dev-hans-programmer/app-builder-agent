# Current Architecture

This document describes the implemented architecture of `app-builder-agent`.

## Overview

The project has two entry points over the same LangGraph generation workflow: the original CLI and
a durable FastAPI control plane. It turns one submitted backend requirement into one or two verified
implementations:

- Python with FastAPI
- Node.js with Express

`--stack python|nodejs|both` controls generation. Only dual-stack runs invoke the comparison
agent. Every online run must pass post-generation quality and requirement traceability gates
before it is marked complete.

## Workflow Graph

```text
parse input
  → requirement analysis
  → optional explicit clarification handling
  → acceptance approval
  → architecture and contracts
  → spec decomposition
  → executable task planning
  → selected builder branch(es)
  → quality gate ──failed──→ targeted repair ──→ quality gate (maximum two repairs)
  → traceability gate
  → optional dual-stack comparison
  → final report
```

The Python and Node.js builders fan out from planning and join at one quality gate. This prevents
verification from running before generated code exists.

## Requirements and Contracts

`requirement_analyst.py` creates normalized functional and non-functional requirements plus stable
`AC-###` acceptance IDs. `approve_acceptance_criteria()` freezes the submitted request as the
approved baseline without generic questions.

`architect.py` creates:

- the technical design and module boundaries
- structured `API-###` endpoint contracts
- structured `DATA-###` entity contracts
- the shared `ERROR-001` error response contract

Every contract links back to acceptance IDs.

## Planning and Generation

`spec_generator.py` produces human-readable per-module specifications. `planner.py` reduces these
to ordered `TASK-###` work items with dependencies, acceptance IDs, contract IDs, and verification
categories.

Each selected builder performs one model request per executable task. Later requests receive a
bounded snapshot of files produced by earlier tasks. Model output is parsed as complete-file
patches; each patch stores its operation and before/after SHA-256 hashes. Absolute paths and path
traversal outside the stack build directory are rejected.

The builder step aggregates token and cost information across task calls while retaining readable
per-task prompts and responses in the run diagnostics.

## Verification and Repair

`quality_gate.py` runs commands without a shell and records command, exit code, duration, and
bounded diagnostics. It evaluates build, lint, type, test, and smoke categories. Tests and smoke
checks are required; lint and type checks are skipped only when their tools are not available or
configured.

`targeted_repair.py` sends only failed check evidence and current files to the model. Complete-file
repair patches are applied and the graph reruns every quality check. The loop is bounded at two
repair attempts.

`traceability.py` requires each approved criterion to have contract, executable-task, per-stack
patch, generated-test, and passing quality evidence. A failed traceability gate yields a failed
delivery.

## State and Persistence

`BuilderState` carries normalized artifacts, selected stack outputs, quality history, repair
history, traceability results, and durable job metadata. CLI runs retain filesystem checkpoints.
Queued runs use LangGraph's async PostgreSQL checkpointer with the run ID as the thread ID.

Project artifacts live under `projects/<project>/`:

```text
requirements/   approved problem and acceptance baseline
architecture/   technical, API, and data contracts
specs/          per-module specifications
plans/          executable task plan
builds/         generated Python and/or Node.js applications
verification/   quality gate report
repairs/        targeted repair attempts
reports/        traceability, comparison, and delivery reports
checkpoints/    resumable state snapshots
runs/           human-readable and machine-readable run diagnostics
```

## Observability

Every graph node is instrumented. `runs/<run_id>/events.jsonl` is the append-only event stream;
`README.md`, `timeline.md`, and `steps/*.md` are the human debugging surface. Model steps include
prompt version/hash, token use, estimated cost when rates are configured, task prompts/responses,
input/output artifacts, hashes, retry reasons, and error diagnostics.

API runs additionally mirror every event and step attempt into PostgreSQL. RabbitMQ/Celery provides
at-least-once delivery, a transactional outbox prevents database/broker gaps, worker leases recover
lost executions, and SSE provides cursor-based live replay. See
[Durable Control-Plane Architecture](control-plane-architecture.md).

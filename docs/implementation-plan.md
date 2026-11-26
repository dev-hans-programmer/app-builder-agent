# Implementation Plan

> Historical roadmap: the gated generation portion of this plan is now implemented. See
> [Current Architecture](current-architecture.md) and
> [Generation Pipeline](generation-pipeline.md). Queue-backed execution remains future work.

This document describes how to build the next version of the agent end to end so the system can handle medium to complex, production-grade backend projects from a PRD or detailed requirement description.

It is intended to answer four questions:

1. What should be built?
2. In what order should it be built?
3. Which agent or tool executes each step?
4. What artifacts and verification evidence should exist at each stage?

## Executive Summary

The original application was a one-shot dual-stack code generator. The implemented generation
path is now spec-driven, checkpointed, quality-gated, repairable, and traceable. Durable
queue-backed workers remain the next execution-layer milestone.

The core shift is:

- from prompt -> code
- to prompt -> requirements -> architecture -> specs -> execution plan -> implementation -> verification -> repair -> release

That change requires both new orchestration logic and a richer artifact model.

## Build Objectives

The implementation must support:

- long-running jobs that may take minutes or hours
- PRD-style input, not just short prompts
- requirement decomposition into structured specs
- sequential execution of specs with controlled parallelism only where safe
- automated verification after each step
- repair cycles when a step fails
- resumable execution from checkpoints
- production-oriented output with clear traceability

## Current Stack Baseline

The current repo is already built on:

- Python 3.11+
- LangGraph for orchestration
- OpenAI SDK for model calls
- `python-dotenv` for environment loading
- `rich` for CLI UX
- local filesystem output under `builds/` and `reports/`

Current `pyproject.toml` already includes:

- `langchain`
- `langgraph`
- `openai`
- `anthropic`
- `python-dotenv`
- `rich`
- dev dependencies for `pytest`, `black`, and `ruff`

That means the next implementation can extend the current foundation instead of starting over.

## Target Operating Model

The future agent should behave like a build pipeline with multiple specialized workers:

1. Intake and normalize the request.
2. Analyze the requirement and identify missing information.
3. Draft architecture and domain boundaries.
4. Decompose the work into specs.
5. Order specs into a runnable plan.
6. Execute one spec at a time.
7. Verify each spec.
8. Repair failures.
9. Resume from checkpoints when interrupted.
10. Produce a final artifact set and release summary.

## Roles and Responsibilities

### Human User

Provides one of:

- a short prompt
- a PRD
- a product brief
- a feature list

May also answer clarifying questions when the request is ambiguous.

### CLI Orchestrator

The CLI is responsible for:

- collecting input
- loading environment variables
- starting or resuming a job
- rendering progress
- showing final output paths and reports

The CLI should not contain build logic.

### Requirement Analyst Agent

Responsible for:

- converting free-form input into structured requirements
- detecting ambiguity
- extracting business goals, constraints, assumptions, and open questions

### Architect Agent

Responsible for:

- turning requirements into a system architecture outline
- defining modules, services, APIs, storage, and integration boundaries
- producing the architecture artifact that the rest of the build follows

### Spec Generator Agent

Responsible for:

- turning architecture into a hierarchical spec tree
- defining acceptance criteria and verification steps for each spec

### Planner Agent

Responsible for:

- ordering specs
- assigning dependencies
- identifying safe parallel work
- producing an executable plan

### Executor Agent

Responsible for:

- implementing the current spec
- writing or modifying source files
- generating supporting files such as config, docs, and migrations

### Verifier Agent

Responsible for:

- running checks against the current spec
- classifying failures
- determining whether the spec is complete

### Repair Agent

Responsible for:

- reading verification failures
- patching the smallest affected area
- rerunning the relevant verification

### Reporter Agent

Responsible for:

- writing progress reports
- summarizing completed specs
- producing the final delivery report

## End-to-End Workflow

## Phase 0: Intake

### Goal

Convert raw user input into a structured build request.

### Inputs

- short prompt
- PRD document
- feature brief
- product description

### Output Artifacts

- `requirements/raw-input.md`
- `requirements/normalized-request.json`

### Execution

1. The CLI receives the input.
2. The orchestrator stores the raw request.
3. The requirement analyst normalizes it into a structured object.
4. The system detects whether the request is small, medium, or complex.

### Ownership

- CLI: user capture
- Requirement Analyst: normalization
- Orchestrator: routing

## Phase 1: Requirement Understanding

### Goal

Build a structured understanding of what needs to be built before any code is written.

### What to Extract

- business goals
- user personas
- core use cases
- functional requirements
- non-functional requirements
- constraints
- assumptions
- dependencies
- open questions
- out-of-scope items

### Output Artifacts

- `requirements/requirements-summary.md`
- `requirements/requirements.json`
- `requirements/open-questions.md`

### Verification

The system should verify that:

- all required sections exist
- assumptions are explicit
- ambiguous items are surfaced for clarification

### Ownership

- Requirement Analyst: extraction
- Orchestrator: validation
- User: optional clarification

## Phase 2: Architecture Planning

### Goal

Convert the requirement set into a system architecture that can support production-grade implementation.

### What the Architecture Should Contain

- domain boundaries
- module boundaries
- API surface
- data model outline
- service interactions
- auth and authorization strategy
- configuration strategy
- observability strategy
- deployment assumptions
- failure/retry approach

### Output Artifacts

- `architecture/system-architecture.md`
- `architecture/module-map.json`
- `architecture/decision-log.md`

### Ownership

- Architect Agent: design
- Orchestrator: consistency checks
- Reporter Agent: artifact formatting if needed

## Phase 3: Spec Decomposition

### Goal

Break the architecture into executable units that can be built and verified independently.

### Spec Layers

- Epic specs
- Feature specs
- Component specs
- Task specs
- Verification specs

### Each Spec Should Include

- identifier
- title
- objective
- scope
- dependencies
- inputs
- outputs
- acceptance criteria
- implementation notes
- verification steps
- rollback strategy
- estimated effort
- owner

### Output Artifacts

- `specs/spec-tree.json`
- `specs/epics/*.md`
- `specs/features/*.md`
- `specs/tasks/*.md`
- `specs/verification/*.md`

### Ownership

- Spec Generator Agent: decomposition
- Architect Agent: architectural consistency
- Orchestrator: dependency validation

## Phase 4: Planning and Scheduling

### Goal

Convert specs into a runnable execution graph.

### Planning Requirements

The plan should define:

- execution order
- dependency chains
- parallelizable groups
- checkpoints
- retry policy
- stop conditions
- escalation rules

### Output Artifacts

- `plans/execution-plan.json`
- `plans/execution-order.md`
- `plans/dependency-graph.json`

### Ownership

- Planner Agent: scheduling
- Orchestrator: plan approval

## Phase 5: Spec Execution

### Goal

Implement the project spec by spec rather than in a single generation pass.

### Execution Loop

For each spec:

1. Load the spec definition.
2. Load the current checkpoint and workspace state.
3. Produce code or configuration changes.
4. Write the changes to disk.
5. Run targeted verification.
6. If verification passes, mark the spec complete.
7. If verification fails, invoke repair or mark blocked.
8. Persist the updated state and checkpoint.

### Output Artifacts

- source code files
- config files
- documentation files
- migration files
- checkpoint files

### Ownership

- Executor Agent: file changes
- Orchestrator: state transitions
- Verifier Agent: success/failure determination

## Phase 6: Verification

### Goal

Prove that each spec is actually complete before moving on.

### Verification Types

- syntax check
- lint
- type check
- unit tests
- integration tests
- build command
- smoke test

### Suggested Tooling

- `pytest` for Python tests
- `ruff` for linting
- `black` for formatting
- `mypy` if static typing becomes important
- `npm test` or `pnpm test` for Node.js validation
- `npm run lint`
- `npm run build`

### Output Artifacts

- `tests/results/*.json`
- `tests/results/*.md`
- `verification/checksums.json`

### Ownership

- Verifier Agent: run and interpret checks
- Executor Agent: only when a repair is needed

## Phase 7: Repair Loop

### Goal

Fix failed specs without losing the overall job context.

### Repair Flow

1. Collect failure output.
2. Classify the failure.
3. Determine whether the issue is local or systemic.
4. Patch the minimum set of files.
5. Re-run the specific verification.
6. Repeat until pass, blocked, or escalated.

### Output Artifacts

- `repairs/repair-log.md`
- `repairs/failure-classification.json`

### Ownership

- Repair Agent: diagnosis and patching
- Verifier Agent: rerun checks
- Orchestrator: stop/resume control

## Phase 8: Final Assembly

### Goal

Package the completed project and document what was built.

### Final Outputs

- generated source code
- final architecture summary
- verification summary
- build timeline
- release notes
- optional packaging output

### Output Artifacts

- `reports/final-report.md`
- `reports/execution-summary.md`
- `reports/verification-summary.md`

### Ownership

- Reporter Agent: final documentation
- Orchestrator: completion signal

## Proposed System Components

## 1. CLI Frontend

Responsibilities:

- prompt for input
- support start/resume commands
- show progress
- show job status
- print output paths and report locations

Likely files:

- `main.py`
- future `src/cli/*.py`

## 2. Graph Orchestrator

Responsibilities:

- manage the state machine
- route between phases
- persist checkpoints
- resume interrupted jobs
- track job lifecycle

Likely files:

- `src/graph/workflow.py`
- `src/graph/state.py`
- future `src/graph/nodes/*.py`

## 3. Requirement Pipeline

Responsibilities:

- ingest input
- extract structured requirements
- resolve ambiguities

Likely files:

- `src/agents/requirement_analyst.py`
- `src/prompts/requirement_analyst_prompt.py`

## 4. Architecture Pipeline

Responsibilities:

- produce architecture decisions
- map modules and boundaries

Likely files:

- `src/agents/architect.py`
- `src/prompts/architect_prompt.py`

## 5. Spec Pipeline

Responsibilities:

- create specs
- validate spec completeness
- store spec artifacts

Likely files:

- `src/agents/spec_generator.py`
- `src/prompts/spec_generator_prompt.py`
- `src/specs/*.py` or `src/specs/*.json` helpers

## 6. Planner

Responsibilities:

- build the execution plan
- schedule tasks
- resolve dependencies

Likely files:

- `src/agents/planner.py`
- `src/prompts/planner_prompt.py`

## 7. Execution Engine

Responsibilities:

- execute one spec at a time
- write files
- manage workspace changes

Likely files:

- `src/agents/executor.py`
- `src/utils/file_writer.py`
- future `src/workspace/*`

## 8. Verification Engine

Responsibilities:

- run tests and checks
- store outputs
- decide pass/fail

Likely files:

- `src/agents/verifier.py`
- `src/utils/verification.py`

## 9. Repair Engine

Responsibilities:

- diagnose failures
- patch code
- rerun checks

Likely files:

- `src/agents/repair.py`

## 10. Reporting Engine

Responsibilities:

- generate final summary
- document execution history
- report verification status

Likely files:

- `src/agents/reporter.py`

## State and Persistence Design

The current `BuilderState` is too small for the future workflow.

## Required State Fields

- `job_id`
- `job_status`
- `input_type`
- `raw_request`
- `requirements`
- `assumptions`
- `open_questions`
- `architecture_plan`
- `spec_tree`
- `execution_plan`
- `current_phase`
- `current_spec_id`
- `completed_specs`
- `failed_specs`
- `verification_results`
- `repair_history`
- `artifacts`
- `checkpoint_id`
- `resume_token`
- `errors`
- `timestamps`

## Persistence Strategy

For long-running jobs, state should be stored durably in one of:

- local JSON checkpoints for early versions
- SQLite for durable single-machine runs
- a database-backed job store for production

Recommended progression:

1. Start with JSON checkpoint files.
2. Move to SQLite once job history and resumes matter.
3. Move to a richer datastore only if multi-user or distributed execution is required.

## Artifact Strategy

The build should not only output code. It should also output the reasoning trail.

### Recommended Folder Structure

```text
workspace/
├── requirements/
├── architecture/
├── specs/
├── plans/
├── builds/
├── verification/
├── repairs/
├── reports/
└── checkpoints/
```

### Why This Matters

This structure makes the build:

- auditable
- resumable
- debuggable
- easier to review
- more suitable for production-grade work

## Dependencies

The current repo already has the basic foundation. The next version should intentionally expand the dependency set.

## Existing Dependencies

- `langgraph`
- `langchain`
- `openai`
- `anthropic`
- `python-dotenv`
- `rich`

## Recommended New Dependencies

### Core Planning and Validation

- `pydantic`
  - structured request/spec/state models
- `PyYAML`
  - spec and plan serialization
- `networkx`
  - dependency graph and execution planning
- `tenacity`
  - retry policies for API calls and verification jobs

### Persistence and Checkpointing

- `sqlite3` or a thin wrapper around it
  - local durable checkpoint store
- optionally `sqlalchemy`
  - if the job store becomes more complex

### Verification Tooling

- `pytest`
- `ruff`
- `black`
- `mypy`
- `node` ecosystem test commands for generated Node.js projects

### CLI and UX

- `rich`
  - progress, tables, panels, markdown previews

### Optional Future Additions

- `watchdog`
  - if live file monitoring becomes useful
- `jsonschema`
  - if specs are validated against strict schemas

## Tooling and Commands

### Development Commands

- `uv run pytest`
- `uv run ruff check`
- `uv run black .`
- `uv run python main.py`

### Generated Project Verification Commands

Python side:

- `pytest`
- `ruff check`
- `python -m compileall`
- `mypy` if enabled

Node.js side:

- `npm test`
- `npm run lint`
- `npm run build`

### Orchestration Commands

- `start`
- `resume`
- `status`
- `inspect`
- `repair`
- `finalize`

These should become CLI verbs or workflow commands in the next iteration.

## Execution Ownership Matrix

| Step | Primary Executor | Supporting Executors |
|---|---|---|
| Intake | CLI | Requirement Analyst |
| Requirement extraction | Requirement Analyst | Orchestrator |
| Architecture design | Architect | Reporter |
| Spec decomposition | Spec Generator | Architect |
| Planning | Planner | Orchestrator |
| Code generation | Executor | Orchestrator |
| Verification | Verifier | CLI |
| Repair | Repair Agent | Verifier |
| Persistence | Orchestrator | CLI |
| Reporting | Reporter | Orchestrator |

## Suggested Implementation Order

### Stage 1: Stabilize the current codebase

Implement only the pieces needed to support richer orchestration:

- clean up shared state
- introduce durable job records
- make workflow phases explicit
- separate generation from verification

### Stage 2: Add requirement and architecture agents

Build the pipeline that converts a PRD into:

- structured requirements
- architecture plan
- spec tree

### Stage 3: Add planner and execution graph

Turn the spec tree into a real execution plan with dependencies and checkpoints.

### Stage 4: Add verification and repair

Make the workflow evidence-driven instead of generation-only.

### Stage 5: Add checkpointing and resume

Persist state so long-running builds can continue safely.

### Stage 6: Add release and reporting polish

Produce the final project summary, verification summary, and traceable artifact set.

## Success Criteria

The implementation is successful when the system can:

- accept a PRD or complex prompt
- extract structured requirements
- produce a meaningful architecture plan
- generate a spec tree before code
- execute specs one by one
- verify each spec
- repair failures automatically
- resume after interruption
- output a complete project with supporting artifacts

## What Will Execute Each Step

### Human

- provides the PRD or prompt
- answers clarifying questions
- optionally approves major architectural decisions

### CLI

- starts the workflow
- resumes jobs
- displays progress

### LangGraph Orchestrator

- moves between phases
- stores and loads state
- coordinates agent handoffs

### Specialized Agents

- requirement analyst
- architect
- spec generator
- planner
- executor
- verifier
- repair agent
- reporter

### Local Tools

- file system writes
- test runners
- lint and format commands
- checkpoint storage

## Final Summary

The target implementation is not a larger version of the current generator. It is a different class of system.

Today:

- prompt in
- code out
- compare once

Proposed:

- requirement in
- architecture out
- specs out
- plan out
- execution out
- verification out
- repair if needed
- resume if interrupted
- final production-grade delivery out

That is the architectural shift needed for complex, long-running, production-oriented builds.


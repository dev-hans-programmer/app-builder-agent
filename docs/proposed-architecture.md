# Proposed Architecture

> Historical proposal: the requirements, contracts, task generation, quality, repair, and
> traceability layers described here are now implemented. See
> [Current Architecture](current-architecture.md). Queue-backed execution remains proposed.

This document describes the next-stage architecture for building medium to complex production-grade backend projects from a PRD or detailed description.

## Goal

Transform the current single-pass generator into a spec-driven, resumable, multi-stage agent system that can:

- understand a PRD or detailed requirement description
- decompose the request end to end
- produce explicit specs before code
- execute those specs one after the other
- verify each stage before moving forward
- recover from partial failures
- support long-running jobs that take minutes or hours

## Design Principles

1. **Plan before code**
   - No implementation starts until the requirement is broken into structured specs.

2. **One source of truth**
   - The PRD, derived specs, execution plan, and verification results should all live as first-class artifacts.

3. **Incremental execution**
   - The system should progress spec by spec, not attempt the whole application in a single prompt.

4. **Verification gates**
   - Every major step should produce evidence before the next step starts.

5. **Durable and resumable**
   - Long-running jobs must survive interruption, failure, and retries.

6. **Production-oriented**
   - The system should optimize for maintainability, testability, modularity, and correctness, not just code generation speed.

## Target Workflow

### Phase 0: Intake

Input types:

- short prompt
- PRD
- existing product brief
- feature list

The system normalizes the input into a structured requirement object.

### Phase 1: Requirement Understanding

An analysis agent extracts:

- business goals
- users and personas
- functional requirements
- non-functional requirements
- constraints
- assumptions
- open questions
- out-of-scope items

If the input is ambiguous, the system should ask targeted clarifying questions or mark assumptions explicitly.

### Phase 2: Architecture Planning

An architecture agent converts the requirement set into:

- system boundaries
- module boundaries
- data model outline
- service boundaries
- API surface
- security model
- deployment notes
- observability plan

This produces a high-level architecture artifact before any code is generated.

### Phase 3: Spec Decomposition

The core upgrade is to decompose the build into a spec tree.

Example spec layers:

- `epic-spec`
- `feature-spec`
- `component-spec`
- `task-spec`
- `verification-spec`

Each spec should include:

- objective
- scope
- dependencies
- acceptance criteria
- implementation notes
- verification steps
- rollback strategy if relevant

### Phase 4: Execution Planning

A planner agent transforms specs into a sequenced execution plan.

The plan should include:

- order of implementation
- concurrency where safe
- dependency graph
- estimated effort
- validation checkpoints
- retry policy

### Phase 5: Spec Execution

Execution should happen one spec at a time, or in controlled parallel groups when dependencies allow.

For each spec, the system should:

1. generate or update code
2. write the relevant files
3. run targeted verification
4. inspect results
5. decide whether to advance, repair, or branch into a follow-up spec

### Phase 6: Verification and Repair

This is the biggest missing capability in the current codebase.

Each spec should be validated with a chain such as:

- syntax check
- unit tests
- lint
- type check
- build command
- smoke test

If a check fails, a repair agent should:

- inspect the failure
- identify the root cause
- patch the affected files
- rerun the relevant verification

### Phase 7: Final Assembly

Once all specs pass, the system should:

- assemble the final project
- generate a release summary
- write a final architecture and execution report
- optionally package the app for delivery

## Proposed Agent Layout

### 1. Requirement Analyst

Responsibilities:

- parse PRD or prompt
- extract entities, goals, and constraints
- produce structured requirements

### 2. Architect

Responsibilities:

- convert requirements into system design
- define modules, services, and boundaries
- propose data flow and integration points

### 3. Spec Generator

Responsibilities:

- generate hierarchical specs
- attach acceptance criteria
- split complex work into execution-friendly units

### 4. Planner

Responsibilities:

- turn specs into an executable graph
- schedule dependencies
- manage partial parallelism

### 5. Executor

Responsibilities:

- implement spec by spec
- edit files
- preserve progress
- emit structured logs and artifacts

### 6. Verifier

Responsibilities:

- run checks
- classify failures
- determine whether the spec is done

### 7. Repair Agent

Responsibilities:

- fix failing specs
- keep changes localized
- rerun checks until passing or blocked

### 8. Reporter

Responsibilities:

- summarize progress
- report architecture decisions
- document verification outcomes
- produce final delivery notes

## State Model

The current `BuilderState` is too small for long-running spec-driven work. The next version should keep richer state such as:

- `requirements`
- `assumptions`
- `open_questions`
- `architecture_plan`
- `spec_tree`
- `execution_plan`
- `current_spec_id`
- `completed_specs`
- `failed_specs`
- `verification_results`
- `repair_history`
- `artifacts`
- `checkpoint_id`
- `job_status`
- `resume_token`

This state should be stored durably so the workflow can resume after a stop or failure.

## Artifact Model

The system should generate more than source code.

Recommended artifact groups:

- `requirements/`
- `architecture/`
- `specs/`
- `plans/`
- `builds/`
- `tests/`
- `reports/`
- `checkpoints/`

Example structure:

```text
workspace/
├── requirements/
│   └── prd.md
├── architecture/
│   └── system-architecture.md
├── specs/
│   ├── epic-001.md
│   ├── feature-001.md
│   └── task-001.md
├── plans/
│   └── execution-plan.json
├── builds/
│   └── generated-project/
├── tests/
│   └── verification-results.json
├── reports/
│   └── final-report.md
└── checkpoints/
    └── job-<id>.json
```

## Orchestration Model

The current graph is a small fan-out/fan-in pipeline. The proposed system should be a dynamic workflow engine with:

- conditional branching
- retry policies
- durable checkpoints
- resumable execution
- per-spec verification gates
- structured event logging
- human-in-the-loop intervention points

LangGraph can still be part of the solution, but the graph should represent a richer lifecycle, not just a single build pass.

## Execution Strategy

### Short jobs

For small prompts, the system can still use a fast path:

- quick requirement interpretation
- minimal spec generation
- direct build

### Medium and complex jobs

For production-grade projects, the system should switch to a deep build path:

- full requirement decomposition
- architecture planning
- spec generation
- iterative execution
- verification loops
- repair cycles

The routing decision should be based on:

- prompt complexity
- number of modules implied
- presence of auth, storage, async jobs, or integrations
- presence of PRD input
- required level of correctness

## Verification Contract

A spec is not complete unless its acceptance criteria pass.

Recommended contract:

- every spec must define a machine-checkable acceptance list
- every spec execution must emit a verification result
- every verification result must be stored
- failed checks must trigger repair or escalation

## How This Solves the Current Limitations

### Current limitation: simple one-shot generation

Proposed fix:

- decompose the request before code generation
- execute incrementally instead of in one prompt

### Current limitation: no support for complex projects

Proposed fix:

- use a spec tree, module boundaries, and a planner

### Current limitation: no long-running execution

Proposed fix:

- add durable state, checkpoints, and resumable jobs

### Current limitation: no verification loop

Proposed fix:

- add test, lint, build, and repair gates after each spec

### Current limitation: flat output artifacts

Proposed fix:

- persist requirements, architecture, specs, plans, verification logs, and reports as separate artifacts

## Recommended Implementation Path

1. Add a structured requirement extraction stage.
2. Introduce spec generation artifacts in `docs/` or a dedicated workspace folder.
3. Replace the single build step with a spec execution loop.
4. Add verification and repair nodes.
5. Persist workflow checkpoints.
6. Add a resume command for interrupted jobs.
7. Add job status reporting in the CLI.
8. Add test and lint execution for generated code.

## End State

The proposed architecture turns the agent from:

> “generate two backend prototypes and compare them”

into:

> “understand the product, decompose it into specs, execute each spec with verification, repair failures, and deliver a production-grade project.”


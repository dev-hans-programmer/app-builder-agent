# User Guide

This guide explains how to use the agent, what input it expects, what it produces, and where to find the generated output.

## What This Agent Does

The agent turns a requirement description or PRD into:

- a structured requirement analysis
- an architecture plan
- a spec tree
- an execution plan
- verified code generation
- a resumable checkpointed workflow
- a final report

By default it generates two backend implementations:

- Python with FastAPI
- Node.js with Express

## Prerequisites

Before you run the agent, make sure:

- Python dependencies are installed
- `OPENAI_API_KEY` is set in your environment or `.env`
- you run the tool from the project root

Example `.env` entry:

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_COMPLETION_TOKENS=32768
OPENAI_REASONING_EFFORT=low
CLARIFICATION_GATE_ENABLED=true
```

## How To Start

Run the agent from the project root:

```bash
uv run python main.py
```

Select a single implementation when you do not need a cross-stack comparison:

```bash
uv run python main.py --stack python
uv run python main.py --stack nodejs
```

Supported values are `python`, `nodejs`, and `both`. The default is `both`.
Single-stack jobs skip the unselected builder and the comparison model call.
The selected value is stored in job state and retained when the job resumes.

The CLI will prompt you for two inputs every time you start a fresh run:

1. What you want to build
2. The project name

## How To Give Input

When prompted, provide:

- a short prompt
- a product brief
- a PRD
- a feature list

Example input:

```text
What would you like to build?
Build a secure task management backend with users, projects, and notifications.

Project name:
task-manager
```

The agent will normalize this input and then move through the gated generation pipeline.
Automatic clarification questions are disabled. The submitted request becomes the approved
acceptance baseline and the run proceeds to architecture and contract generation.

## Turning Off The Clarification Gate

The clarification gate remains available for explicitly supplied open questions.
To disable it completely, set:

```env
CLARIFICATION_GATE_ENABLED=false
```

Automatically generated open questions are currently disabled regardless of this setting.

## What Happens Next

The agent processes your request in stages:

1. Requirement analysis
2. Python production-policy snapshot when Python is selected
3. Acceptance criteria approval
4. Architecture and API/data contracts
5. Spec decomposition
6. Executable task planning
7. Task-level code generation for the selected stack or stacks
8. Build, lint, type, test, smoke, and Python policy-compliance checks
9. Targeted repair and re-check, up to two attempts
10. Requirement traceability gate
11. Comparison when `--stack both` is selected
12. Final reporting

See [Generation Pipeline](generation-pipeline.md) for completion rules and the evidence
produced by each gate.

## What Output You Will Get

After a successful run, you will get:

- generated backend code for the selected stack or stacks
- requirement artifacts
- the exact Python policy snapshot and hash when Python is selected
- architecture artifacts
- spec artifacts
- execution plans
- verification reports
- repair history
- comparison report for dual-stack jobs
- checkpoint files
- final delivery summary
- an append-only event timeline and per-step diagnostic artifacts

## Where To Find The Generated Codebase

Every project is written under `projects/<project-name>/`.

The generated code lives here:

- `projects/<project-name>/builds/python/`
- `projects/<project-name>/builds/nodejs/`

Example:

- `projects/task-manager/builds/python/`
- `projects/task-manager/builds/nodejs/`

Each of these contains the actual source files generated for that stack.

## Where To Find Supporting Artifacts

The agent also writes supporting files inside the same project folder:

- `projects/<project-name>/requirements/`
- `projects/<project-name>/policy/` (Python runs only)
- `projects/<project-name>/architecture/`
- `projects/<project-name>/specs/`
- `projects/<project-name>/plans/`
- `projects/<project-name>/execution/`
- `projects/<project-name>/verification/`
- `projects/<project-name>/repairs/`
- `projects/<project-name>/reports/`
- `projects/<project-name>/checkpoints/`
- `projects/<project-name>/runs/<run-id>/`

### Run Observability

Every invocation has a durable run directory:

```text
projects/<project-name>/runs/<run-id>/
├── README.md
├── timeline.md
├── events.jsonl
├── steps/
│   ├── 01-parse-input.md
│   ├── 09-python-builder.md
│   ├── 09-python-builder-prompt.md
│   └── 09-python-builder-response.md
└── _machine/
    ├── metadata.json
    ├── summary.json
    └── artifacts.json
```

Open `README.md` first for status, failures, and recommended actions. Use
`timeline.md` and the flat `steps/*.md` reports for investigation. `events.jsonl`
and `_machine/` retain structured data for agents, retries, and future queue workers.

Secrets and likely credentials are redacted before observability data is
persisted. Configure the optional per-million-token rates in `.env` if you want
`estimated_cost` populated.

### Requirements

Files describing the normalized and approved request:

- `requirements/prd.md`
- `requirements/acceptance-criteria.md`

### Architecture

Files describing the system design:

- `architecture/technical-design.md`
- `architecture/api-contracts.md`
- `architecture/data-contracts.md`

### Specs

Files describing the spec tree:

- `specs/spec-breakdown.md`
- `specs/<number>-<module>/spec.md`
- `specs/<number>-<module>/tasks.md`
- `specs/<number>-<module>/prompt.md`

### Plans

Files describing execution and verification:

- `plans/tasks.md`

### Verification And Repairs

Files describing checks and fixes:

- `verification/quality-report.md`
- `repairs/attempt-1.md`
- `repairs/attempt-2.md` when a second attempt is needed

### Reports And Checkpoints

Final and resumable artifacts:

- `reports/comparison-<timestamp>.md`
- `reports/traceability.md`
- `reports/delivery-summary.md`
- `checkpoints/<phase>.json`
- `checkpoints/final.json`

## What The Final Report Contains

The final report is written to `reports/` and includes:

- comparison summary
- delivery summary
- build status
- verification history
- repair history
- artifact locations

## Typical End-To-End Flow

1. Run `uv run python main.py`
2. Enter your requirement description
3. Enter the project name
4. Let the workflow complete
5. Review the generated code in `projects/<project-name>/builds/`
6. Review the reports in `projects/<project-name>/reports/`
7. Run `uv run python main.py --resume` if you want to continue a saved checkpoint

## Notes

- The agent is spec-driven, so a longer or more complex request will be broken into more intermediate artifacts.
- Generic clarification prompts are disabled. Put important persistence, authentication, and
  deployment constraints directly in the submitted request.
- All artifacts are stored relative to the project root unless you run the tool from another directory.

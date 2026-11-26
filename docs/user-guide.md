# User Guide

## What the agent creates

The agent always creates a Python/FastAPI project. It produces requirements, architecture and
contracts, an execution plan, generated source and tests, quality evidence, repair history,
traceability evidence, checkpoints, and a final delivery summary.

## Configure

```bash
cp .env.example .env
```

Set at least:

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini
```

The versioned Python architecture policy defaults to `backend-prompt.md`. Override it with
`BACKEND_POLICY_PATH` when needed.

## Run from the CLI

```bash
uv run python main.py
```

Provide:

1. A prompt, brief, PRD, or feature list.
2. A project name.

There is no stack selector. Python/FastAPI is the only generation target.

Status and resume commands:

```bash
uv run python main.py --status
uv run python main.py --resume
```

## Run through the API

Start the infrastructure and processes described in the README, create a project, then submit:

```json
{
  "request": "Build a secure task API with users and projects",
  "clarification_gate_enabled": false,
  "idempotency_key": "task-api-v1"
}
```

The API assigns Python automatically. Existing database rows retain an internal legacy language
column for migration compatibility, but it is not part of the run creation contract.

## Pipeline

1. Load and snapshot the Python production policy.
2. Normalize requirements and approve acceptance criteria.
3. Create architecture plus API/data contracts.
4. Decompose specifications and dependency-ordered tasks.
5. Generate the Python project task by task.
6. Run build, format, lint, type, test, migration, smoke, and policy checks.
7. Attempt up to two targeted repairs when checks fail.
8. Verify requirement-to-code traceability.
9. Write the final delivery summary.
10. Publish to GitHub when configured and permitted by delivery policy.

## Output location

Queued runs write generated code here:

```text
data/projects/<project-id>/runs/<run-id>/builds/python/
```

The same run directory contains:

```text
policy/
requirements/
architecture/
specs/
plans/
verification/
repairs/
reports/
checkpoints/
steps/
_machine/
```

Open the run `README.md`, `timeline.md`, and `steps/*.md` files first when diagnosing failures.

## Quality failures and GitHub

Strict behavior is the default: a failed quality gate prevents delivery. To publish generated code
for review even after quality failure:

```env
CONTROL_PUBLISH_ON_QUALITY_FAILURE=true
```

This does not mark the run successful. Cancellation and incomplete Python generation are never
published.

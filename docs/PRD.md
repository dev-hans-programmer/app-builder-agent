# Product Requirements: Python Project Builder Agent

## Purpose

Create a production-oriented Python/FastAPI project from one product request, with enough durable
evidence to understand what was requested, generated, verified, repaired, and delivered.

## Primary user outcome

Given a prompt, brief, PRD, or feature list, the system produces:

- approved, testable acceptance criteria
- a Python architecture and API/data contracts
- dependency-ordered implementation tasks
- a runnable Python/FastAPI codebase with tests and operational files
- quality, policy-compliance, and traceability reports
- resumable checkpoints and run diagnostics
- an optional GitHub repository and commit

## Functional requirements

1. Accept project requests through the CLI and versioned HTTP API.
2. Normalize requirements without silently adding product scope.
3. Apply the versioned Python production policy to planning, generation, repair, and verification.
4. Generate only Python/FastAPI projects.
5. Reject filesystem traversal and keep generated files inside the run workspace.
6. Run deterministic quality checks and retain command evidence.
7. Attempt a bounded targeted repair loop.
8. Trace every acceptance criterion to contracts, tasks, patches, tests, and quality evidence.
9. Persist run status, steps, events, checkpoints, and artifact metadata.
10. Publish generated Python source to GitHub when configured.

## Completion rules

A run is successful only when Python generation, required quality checks, and requirement
traceability pass. Operators may opt into GitHub delivery after a quality failure, but this does
not change the failed run status.

Cancellation and incomplete Python generation must never be published.

## Non-goals

- Generating projects in other programming languages
- Choosing between alternative language implementations
- Hosting or deploying the generated service
- Treating model output as trusted without deterministic checks

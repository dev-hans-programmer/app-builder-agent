# Spec 07: Checkpointing and CLI Finalization

## Purpose

Make the build resumable and expose the full workflow through the CLI.

## Scope

This spec covers checkpoint persistence, job resumption, and final reporting.

## Acceptance Criteria

- A job can be paused and resumed from a saved checkpoint.
- The CLI can show current phase, job status, and output locations.
- The final report summarizes the build and verification history.


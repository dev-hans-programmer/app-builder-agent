# Spec 04: Planning and Scheduling

## Purpose

Turn the spec tree into an executable plan with ordering, dependencies, and safe parallelism.

## Scope

This spec covers plan generation and dependency-aware scheduling.

## Acceptance Criteria

- The system can produce a runnable execution plan from a spec tree.
- The plan includes dependency ordering and optional parallel groups.
- The plan is stored as a durable artifact.


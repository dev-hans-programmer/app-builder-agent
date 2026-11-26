# Spec 00: Foundation and State Model

## Purpose

Build the structural foundation required for spec-driven development, durable job tracking, and long-running execution.

## Problem Statement

The current agent can generate code from a single prompt, but it does not have a durable state model, job identity, checkpointing, or artifact structure that can support a spec-driven workflow.

## Scope

This spec covers the foundational primitives needed before any higher-level requirement analysis or execution planning can happen.

## In Scope

- job and workflow state structure
- durable artifact and checkpoint layout
- base schema for requirement/spec/plan metadata
- updated CLI and workflow entry points for job-aware execution
- dependency and package foundation for the new workflow

## Out of Scope

- PRD analysis
- architecture generation
- spec decomposition
- planning and scheduling logic
- executor logic
- verification and repair logic

## Acceptance Criteria

- The project has a clearly defined job-oriented state model.
- The system can track `job_id`, `job_status`, `current_phase`, and checkpoint metadata.
- The repository has a stable folder structure for requirements, specs, plans, artifacts, checkpoints, and reports.
- The codebase can distinguish between a normal one-shot build and a resumable build job.
- The foundation does not break the existing CLI workflow.

## Deliverables

- enhanced state schema
- durable job metadata model
- workspace artifact layout
- phase-aware workflow skeleton
- updated dependency list if needed


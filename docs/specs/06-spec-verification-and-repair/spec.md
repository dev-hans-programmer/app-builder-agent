# Spec 06: Verification and Repair

## Purpose

Verify each spec after execution and repair failures until the spec passes or the job is blocked.

## Scope

This spec covers test execution, failure analysis, and targeted repair.

## Acceptance Criteria

- The system can run verification steps for the current spec.
- Failures are classified and recorded.
- The repair loop can patch and re-verify failed work.


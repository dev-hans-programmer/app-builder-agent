# Plan 00: Foundation and State Model

## Technical Strategy

This is the first implementation step because every later phase depends on having a stable shared state and artifact structure.

### 1. Introduce a richer state schema

Add fields for:

- `job_id`
- `job_status`
- `current_phase`
- `input_type`
- `raw_request`
- `requirements`
- `architecture_plan`
- `spec_tree`
- `execution_plan`
- `current_spec_id`
- `completed_specs`
- `failed_specs`
- `verification_results`
- `repair_history`
- `artifacts`
- `checkpoint_ref`
- `resume_token`

### 2. Add durable artifact folders

Create a predictable workspace layout:

- `requirements/`
- `architecture/`
- `specs/`
- `plans/`
- `builds/`
- `verification/`
- `repairs/`
- `reports/`
- `checkpoints/`

### 3. Keep compatibility with the current app

The existing CLI should still work while the new fields are introduced. The foundation should be additive, not disruptive.

### 4. Add job lifecycle helpers

Provide helper functions for:

- creating a new job
- resuming an existing job
- updating phase status
- saving checkpoints
- loading checkpoints

### 5. Add serialization-friendly models

Use structured, serialization-safe data for state and artifacts so they can be written to JSON or markdown files without extra transformation.

## Implementation Notes

- Prefer small, explicit structures over deeply nested free-form blobs.
- Make phase transitions visible and traceable.
- Keep the first version local-file based; database persistence can come later if needed.

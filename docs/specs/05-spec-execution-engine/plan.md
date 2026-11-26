# Plan 05: Execution Engine

## Technical Strategy

### 1. Add an executor agent

The executor should:

- read the current spec
- edit the required files
- preserve existing work
- emit a change summary

### 2. Support deterministic workspace writes

All file writes should go through a helper layer so execution remains auditable.

### 3. Connect execution to state transitions

The orchestrator must move the job from planned to executing to verified or failed.


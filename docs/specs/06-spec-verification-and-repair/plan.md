# Plan 06: Verification and Repair

## Technical Strategy

### 1. Add a verifier agent

The verifier should execute the right checks for each spec:

- syntax
- lint
- tests
- build
- smoke checks

### 2. Add a repair agent

The repair agent should:

- inspect failed outputs
- isolate the issue
- patch only the relevant area
- rerun the failing checks

### 3. Classify failures

Track whether a failure is:

- local
- cascading
- environment-related
- blocked by missing input


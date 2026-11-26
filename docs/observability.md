# Run Observability

Each workflow invocation owns an immutable run identity and writes diagnostics
under `projects/<project>/runs/<run-id>/`.

## Files

```text
runs/<run-id>/
├── README.md                 # Start here: outcome, failures, and next actions
├── timeline.md               # Ordered table of step attempts
├── events.jsonl              # Append-only machine event stream
├── steps/
│   ├── 01-parse-input.md
│   ├── 02-requirement-analysis.md
│   ├── 09-python-builder.md
│   ├── 09-python-builder-prompt.md
│   └── 09-python-builder-response.md
└── _machine/                 # Derived indexes; normally do not open directly
    ├── metadata.json
    ├── summary.json
    ├── artifacts.json
    └── step-index.json
```

Repeated full-state `input.json` and `result.json` snapshots are intentionally
not written. Step reports link to the actual requirement, architecture, build,
verification, and report artifacts instead.

## Event Contract

All events include the complete contract, using `null` or zero when a field is
not applicable:

```text
event_id, event_type, sequence, schema_version
run_id, job_id, trace_id, span_id, parent_span_id
step_id, parent_step_id, phase, node, stack
requirement_id, spec_id, task_id, acceptance_criterion_id, attempt
status, started_at, ended_at, duration_ms
model, model_request_id, prompt_version, prompt_hash
input_tokens, output_tokens, cached_tokens, total_tokens, estimated_cost
input_artifacts, output_artifacts, artifact_hashes, files_changed
step_report
command, exit_code, retry_reason
verification_check, expected, actual, severity, suggested_fix
error_type, error_message, stack_trace
worker_id, queue_job_id
```

`sequence` is monotonically increasing within a run. Parallel builders use a
process and file lock so they cannot interleave or overwrite event records.

## Diagnosing A Failure

Run `uv run python main.py --status <project-name>` to see run totals and
action items in the terminal, or inspect the files directly:

1. Open `README.md` for the outcome and recommended actions.
2. Use `timeline.md` to find the failed or blocked step.
3. Open that step's Markdown report and its linked prompt/response if present.
4. Use `events.jsonl` only when an agent or advanced investigation needs the
   complete structured event contract.

## Retry And Queue Compatibility

Retries create a new ordered report such as `12-python-builder-attempt-2.md`;
earlier attempts are never overwritten. The schema already reserves `worker_id`, `queue_job_id`, and
`retry_reason`. A later queue executor can add events such as `queued`,
`leased`, `heartbeat`, `retry_scheduled`, and `dead_lettered` without changing
the run storage model.

## Cost Estimation

Token usage comes from model responses. Cost remains `null` unless these
optional rates are configured:

```env
OPENAI_INPUT_COST_PER_1M=0
OPENAI_OUTPUT_COST_PER_1M=0
OPENAI_CACHED_INPUT_COST_PER_1M=0
```

Rates are configuration rather than hard-coded values so model pricing changes
do not require a code release.

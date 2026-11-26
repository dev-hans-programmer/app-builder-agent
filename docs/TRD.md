# Technical Requirements: Python Project Builder Agent

## Runtime

- Python 3.11+ control plane
- LangGraph workflow orchestration
- OpenAI model calls for analysis, generation, and repair
- FastAPI and Pydantic v2 for the HTTP API
- PostgreSQL and async SQLAlchemy for durable state
- RabbitMQ/Celery for queued execution
- Redis for best-effort live notification fan-out
- Local run-isolated artifact storage

## Workflow state

`BuilderState` contains one generated-code output: `python_output`. It also carries requirements,
architecture, specifications, task plans, quality results, repair history, traceability results,
artifact paths, checkpoints, and run metadata.

## Graph

```text
parse_input → backend_policy → requirement_analysis → acceptance_approval
→ architecture_planning → spec_decomposition → planning → generation_start
→ python_builder → quality_gate ↔ targeted_repair → traceability → generate_report
```

Clarification may be inserted between requirement analysis and acceptance approval. No language
selection or cross-language branch exists.

## Generated project contract

Production-policy projects target Python 3.13+, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL,
Alembic, pytest, Ruff, mypy, uv, Docker, Compose, structured logging, metrics, tracing, pre-commit,
and CI.

The builder writes only beneath `builds/python`. Model responses use complete-file content and are
validated before patch application.

## Verification contract

Required checks include dependency resolution, compilation, formatting, linting, typing, tests,
migration heads, and application import. Compose validation is optional when Docker is unavailable.
The Python production-policy validator is required.

## Delivery contract

GitHub delivery uses the Git database API and publishes `builds/python` at repository root. It is
idempotent by run ID and persists repository/commit references before finalization. Strict delivery
requires successful gates unless `CONTROL_PUBLISH_ON_QUALITY_FAILURE=true`.

## Compatibility

The database retains its original `target_stack` column so existing deployments can migrate
without destructive schema changes. New runs always store `python`; the field is not accepted by
the run creation API and does not influence workflow routing.

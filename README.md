# Python Project Builder Agent

An AI-powered agent that turns a product request into a production-oriented Python/FastAPI
project. It owns one delivery path only: requirements, architecture, Python generation,
verification, repair, traceability, and optional GitHub publishing.

## Capabilities

- Python 3.13 and FastAPI project generation
- Approved acceptance criteria, API/data contracts, and executable task planning
- Versioned Python production policy from `backend-prompt.md`
- Build, Ruff, mypy, pytest, migration, smoke, and container checks
- Bounded model-assisted repair and requirement traceability
- Run-scoped checkpoints, events, readable diagnostics, and artifact hashes
- FastAPI control plane with PostgreSQL, RabbitMQ, Redis, Celery, and SSE monitoring
- Collision-safe, idempotent GitHub repository delivery

## Local CLI

Prerequisites: Python 3.11+, `uv`, and an OpenAI API key.

```bash
cp .env.example .env
# Set OPENAI_API_KEY in .env
uv sync --all-extras
uv run python main.py
```

The CLI asks for the project request and project name. Every run produces Python; there is no
language or framework selection flag.

Useful commands:

```bash
uv run python main.py --status
uv run python main.py --resume
uv run python main.py --no-clarification-gate
```

## Durable API and workers

```bash
make deps-up
make db-migrate
```

Run these in separate terminals:

```bash
make run-api
make run-worker
make run-beat
```

Open `http://127.0.0.1:8080/docs`. Generated files are stored in isolated workspaces under
`data/projects/<project-id>/runs/<run-id>/builds/python/`.

Create a run with a project request; no stack field is accepted or required:

```json
{
  "request": "Build a production movie catalog API",
  "clarification_gate_enabled": false,
  "idempotency_key": "movie-catalog-v1"
}
```

Set `CONTROL_EXECUTION_MODE=dynamic_serial` for dependency-aware task queue execution. The
`legacy` mode runs the same Python workflow in a single worker task.

## GitHub delivery

Set `GITHUB_OWNER` and `GITHUB_TOKEN`, then restart the worker. Successful generated Python code
is published from `builds/python` to the repository root.

By default, failed quality gates prevent publishing. Set
`CONTROL_PUBLISH_ON_QUALITY_FAILURE=true` to publish successfully generated code even when the
quality gate remains failed. The run itself still remains failed and keeps its diagnostics.

Set `CONTROL_RETAIN_LOCAL_BUILDS=false` to remove local build bytes only after a confirmed GitHub
commit.

## Workflow

```text
request
  → Python policy snapshot
  → requirement analysis and acceptance approval
  → architecture and contracts
  → specification and task planning
  → Python project generation
  → quality gate ↔ bounded targeted repair
  → requirement traceability
  → delivery report
  → optional GitHub publishing
```

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

## Documentation

- [User guide](docs/user-guide.md)
- [Current architecture](docs/current-architecture.md)
- [Generation pipeline](docs/generation-pipeline.md)
- [End-to-end operations guide](docs/end-to-end-operations-guide.md)
- [Control-plane API](docs/control-plane-api-contracts.md)
- [GitHub delivery](docs/github-delivery.md)

## License

MIT

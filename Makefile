run-python:
	uv run python main.py --stack python

run-node:
	uv run python main.py --stack nodejs

deps-up:
	docker compose -f docker-compose.control-plane.yml up -d

deps-down:
	docker compose -f docker-compose.control-plane.yml down

db-migrate:
	uv run alembic -c alembic-control-plane.ini upgrade head
	uv run python -m src.control_plane.manage setup-checkpoints

db-delete-all-data:
	uv run python -m src.control_plane.manage delete-all-data

run-api:
	uv run uvicorn src.control_plane.app:app --host 127.0.0.1 --port 8080 --timeout-graceful-shutdown 10

run-api-dev:
	uv run uvicorn src.control_plane.app:app --host 127.0.0.1 --port 8080 --reload --reload-dir src --timeout-graceful-shutdown 5

run-worker:
	uv run celery -A src.control_plane.queue:celery_app worker -Q runs,maintenance --loglevel=INFO

run-maintenance-worker:
	uv run celery -A src.control_plane.queue:celery_app worker -Q maintenance --loglevel=INFO

run-beat:
	uv run celery -A src.control_plane.queue:celery_app beat --loglevel=INFO

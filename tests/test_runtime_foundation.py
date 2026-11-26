"""
Tests for the workflow runtime foundation helpers.
"""

import os
from src.graph import (
    JOB_PHASES,
    JOB_STATUSES,
    WORKSPACE_DIRS,
    advance_job_phase,
    build_checkpoint_data,
    create_artifact_manifest,
    create_initial_state,
    create_job_metadata,
    create_job_state,
    ensure_workspace_layout,
    find_latest_checkpoint,
    load_checkpoint,
    mark_job_status,
    persist_job_checkpoint,
    restore_state_from_checkpoint,
    save_checkpoint,
    validate_state,
)
from src.graph.workflow import python_builder_placeholder


class TestJobMetadata:
    def test_job_metadata_has_required_fields(self):
        metadata = create_job_metadata(input_type="prompt", raw_request="Build API")

        assert metadata["job_id"].startswith("job-")
        assert metadata["checkpoint_ref"].startswith("checkpoint-")
        assert metadata["job_status"] == "initialized"
        assert metadata["current_phase"] == "intake"
        assert metadata["input_type"] == "prompt"
        assert metadata["raw_request"] == "Build API"
        assert metadata["resume_token"]

    def test_create_job_state_uses_input_type(self):
        state = create_job_state("Build API", "Example Project", input_type="prd")

        assert state["input_type"] == "prd"
        assert state["raw_request"] == "Build API"
        assert state["project_name"] == "example-project"


class TestWorkspaceLayout:
    def test_create_artifact_manifest_has_expected_dirs(self, tmp_path):
        manifest = create_artifact_manifest(tmp_path)

        assert manifest["workspace_root"] == str(tmp_path.resolve())
        for key in (
            "requirements_dir",
            "architecture_dir",
            "specs_dir",
            "plans_dir",
            "execution_dir",
            "builds_dir",
            "verification_dir",
            "repairs_dir",
            "reports_dir",
            "checkpoints_dir",
        ):
            assert manifest[key].startswith(str(tmp_path.resolve()))

    def test_ensure_workspace_layout_creates_all_dirs(self, tmp_path):
        manifest = ensure_workspace_layout(tmp_path)

        for directory in WORKSPACE_DIRS:
            assert (tmp_path / directory).exists()
            assert (tmp_path / directory).is_dir()

        assert manifest["workspace_root"] == str(tmp_path.resolve())


class TestCheckpointing:
    def test_save_and_load_checkpoint_round_trip(self, tmp_path):
        checkpoint_path = tmp_path / "checkpoints" / "job-1.json"
        payload = {
            "job_id": "job-1",
            "checkpoint_ref": "checkpoint-1",
            "current_phase": "intake",
            "job_status": "running",
            "state": {"hello": "world"},
        }

        saved_path = save_checkpoint(checkpoint_path, payload)
        loaded = load_checkpoint(saved_path)

        assert saved_path.exists()
        assert loaded["job_id"] == "job-1"
        assert loaded["state"]["hello"] == "world"

    def test_build_checkpoint_data(self, tmp_path):
        state = create_initial_state("Build API", "Test Project")
        manifest = create_artifact_manifest(tmp_path)
        checkpoint = build_checkpoint_data(state, manifest)

        assert checkpoint["job_id"] == state["job_id"]
        assert checkpoint["checkpoint_ref"] == state["checkpoint_ref"]
        assert checkpoint["artifacts"] == manifest

    def test_persist_job_checkpoint_writes_file(self, tmp_path):
        state = create_initial_state("Build API", "Test Project")
        manifest = ensure_workspace_layout(tmp_path)

        checkpoint_path = persist_job_checkpoint(state, manifest, suffix="testing")

        assert checkpoint_path.exists()
        assert checkpoint_path.name == "testing.json"
        loaded = load_checkpoint(checkpoint_path)
        assert loaded["job_id"] == state["job_id"]

    def test_find_latest_checkpoint_returns_most_recent(self, tmp_path):
        checkpoints_dir = tmp_path / "checkpoints"
        checkpoints_dir.mkdir()
        older = checkpoints_dir / "job-1-old.json"
        newer = checkpoints_dir / "job-1-new.json"
        older.write_text("{}", encoding="utf-8")
        newer.write_text("{}", encoding="utf-8")
        os.utime(older, (older.stat().st_atime, older.stat().st_mtime - 10))
        os.utime(newer, (newer.stat().st_atime, newer.stat().st_mtime + 10))

        latest = find_latest_checkpoint(checkpoints_dir)

        assert latest == newer

    def test_find_latest_checkpoint_returns_none_when_directory_missing(self, tmp_path):
        missing_dir = tmp_path / "missing-checkpoints"

        assert find_latest_checkpoint(missing_dir) is None

    def test_restore_state_from_checkpoint_preserves_artifacts(self, tmp_path):
        state = create_initial_state("Build API", "Test Project")
        manifest = ensure_workspace_layout(tmp_path)
        checkpoint = build_checkpoint_data(state, manifest)

        restored = restore_state_from_checkpoint(
            checkpoint, checkpoint_path=tmp_path / "checkpoints" / "job.json"
        )

        assert restored["job_id"] == state["job_id"]
        assert restored["checkpoint_path"].endswith("job.json")
        assert restored["artifacts"] == manifest


class TestJobPhaseHelpers:
    def test_advance_job_phase(self):
        state = create_initial_state("Build API", "Test Project")
        updated = advance_job_phase(state, "planning", status="running")

        assert updated["current_phase"] == "planning"
        assert updated["job_status"] == "running"
        assert updated["updated_at"]

    def test_mark_job_status(self):
        state = create_initial_state("Build API", "Test Project")
        updated = mark_job_status(state, "paused")

        assert updated["job_status"] == "paused"
        assert updated["updated_at"]

    def test_phase_and_status_constants_are_non_empty(self):
        assert "intake" in JOB_PHASES
        assert "completed" in JOB_PHASES
        assert "running" in JOB_STATUSES
        assert "completed" in JOB_STATUSES

    def test_advance_job_phase_rejects_unknown_phase(self):
        state = create_initial_state("Build API", "Test Project")

        try:
            advance_job_phase(state, "not-a-phase")
        except ValueError as exc:
            assert "Unknown workflow phase" in str(exc)
        else:
            raise AssertionError("Expected ValueError for invalid phase")

    def test_advance_job_phase_rejects_unknown_status(self):
        state = create_initial_state("Build API", "Test Project")

        try:
            advance_job_phase(state, "planning", status="not-a-status")
        except ValueError as exc:
            assert "Unknown job status" in str(exc)
        else:
            raise AssertionError("Expected ValueError for invalid status")

    def test_mark_job_status_rejects_unknown_status(self):
        state = create_initial_state("Build API", "Test Project")

        try:
            mark_job_status(state, "not-a-status")
        except ValueError as exc:
            assert "Unknown job status" in str(exc)
        else:
            raise AssertionError("Expected ValueError for invalid status")


class TestWorkflowPlaceholders:
    def test_placeholder_nodes_return_expected_shapes(self):
        state = create_initial_state("Build API", "Test Project")

        python_result = python_builder_placeholder(state)

        assert python_result["python_output"]["status"] == "placeholder"


class TestStateValidationEdges:
    def test_validate_state_flags_empty_job_metadata_and_bad_artifacts(self):
        state = create_initial_state("Build API", "Test Project")
        state["job_id"] = ""
        state["job_status"] = ""
        state["current_phase"] = ""
        state["artifacts"] = []  # type: ignore[assignment]

        errors = validate_state(state)

        assert any("job_id" in err for err in errors)
        assert any("job_status" in err for err in errors)
        assert any("current_phase" in err for err in errors)
        assert any("artifacts" in err for err in errors)

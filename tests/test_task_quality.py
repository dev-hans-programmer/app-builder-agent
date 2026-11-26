from __future__ import annotations

import pytest

from src.agents.task_quality import TaskVerificationError, verify_python_task
from src.control_plane.tasks import _refresh_task_patch_hashes


def test_task_quality_checks_only_patched_python_files(tmp_path, monkeypatch):
    monkeypatch.setattr("src.agents.task_quality.shutil.which", lambda _name: None)
    good = tmp_path / "app/good.py"
    good.parent.mkdir(parents=True)
    good.write_text("value = 1\n", encoding="utf-8")

    result = verify_python_task(tmp_path, [{"path": "app/good.py"}])

    assert result["passed"] is True
    assert result["checks"][0]["category"] == "syntax"


def test_task_quality_rejects_syntax_errors(tmp_path, monkeypatch):
    monkeypatch.setattr("src.agents.task_quality.shutil.which", lambda _name: None)
    broken = tmp_path / "app/broken.py"
    broken.parent.mkdir(parents=True)
    broken.write_text("def broken(:\n", encoding="utf-8")

    with pytest.raises(TaskVerificationError, match="syntax"):
        verify_python_task(tmp_path, [{"path": "app/broken.py"}])


def test_task_patch_hashes_are_refreshed_after_formatting(tmp_path):
    generated = tmp_path / "app/generated.py"
    generated.parent.mkdir(parents=True)
    generated.write_text("formatted = True\n", encoding="utf-8")
    task_patch = {"path": "app/generated.py", "sha256_after": "stale"}
    output = {
        "output_dir": str(tmp_path),
        "patches": [task_patch],
        "task_runs": [{"patches": [{**task_patch}]}],
    }

    _refresh_task_patch_hashes(output)

    assert output["patches"][0]["sha256_after"] != "stale"
    assert (
        output["task_runs"][0]["patches"][0]["sha256_after"]
        == output["patches"][0]["sha256_after"]
    )

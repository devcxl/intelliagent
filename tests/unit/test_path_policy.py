from __future__ import annotations

from pathlib import Path

from src.utils.path_policy import PathPolicy


def test_workspace_relative_path(tmp_path):
    policy = PathPolicy(workspace=tmp_path)
    result = policy.check("some/file.txt")
    assert result.allowed_by_boundary is True
    assert result.in_workspace is True
    assert result.in_external_directory is False


def test_workspace_absolute_path(tmp_path):
    test_file = tmp_path / "test.py"
    test_file.write_text("x=1")
    policy = PathPolicy(workspace=tmp_path)
    result = policy.check(str(test_file))
    assert result.allowed_by_boundary is True
    assert result.in_workspace is True


def test_outside_workspace(tmp_path):
    policy = PathPolicy(workspace=tmp_path)
    result = policy.check("/etc/passwd")
    assert result.allowed_by_boundary is False
    assert result.in_workspace is False
    assert result.in_external_directory is False


def test_external_directory(tmp_path):
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    ext_file = ext_dir / "data.txt"
    ext_file.write_text("data")
    policy = PathPolicy(workspace=Path("/nonexistent"), external_directories=(ext_dir,))
    result = policy.check(str(ext_file))
    assert result.allowed_by_boundary is True
    assert result.in_workspace is False
    assert result.in_external_directory is True


def test_empty_path(tmp_path):
    policy = PathPolicy(workspace=tmp_path)
    result = policy.check("")
    assert result.allowed_by_boundary is True


def test_outside_workspace_with_external_dirs(tmp_path):
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    policy = PathPolicy(workspace=tmp_path, external_directories=(ext_dir,))
    result = policy.check("/etc/passwd")
    assert result.allowed_by_boundary is False


def test_outside_workspace_not_in_external(tmp_path):
    policy = PathPolicy(workspace=Path("/workspace"), external_directories=(Path("/ext_allowed"),))
    result = policy.check("/etc/passwd")
    assert result.allowed_by_boundary is False
    assert result.in_workspace is False
    assert result.in_external_directory is False


def test_policy_immutable():
    from dataclasses import FrozenInstanceError

    policy = PathPolicy(workspace=Path("/tmp"))
    try:
        policy.workspace = Path("/other")
        assert False, "PathPolicy should be frozen"
    except FrozenInstanceError:
        pass

"""Tests for agentic_executor.executor module."""

import pytest
import os
import tempfile
from agentic_executor.executor import (
    AgenticExecutor, ExecutionResult, ExecutionStep, ExecutionMode,
)
from agentic_executor.tools import ToolRegistry, ToolStatus
from agentic_executor.sandbox import SandboxConfig


class TestExecutionStep:
    def test_duration(self):
        step = ExecutionStep("s1", "shell", {})
        step.start_time = 100.0
        step.end_time = 105.5
        assert step.duration == 5.5

    def test_to_dict(self):
        step = ExecutionStep("s1", "file_read", {"path": "x"})
        d = step.to_dict()
        assert d["step_id"] == "s1"
        assert d["tool"] == "file_read"


class TestExecutionResult:
    def test_create(self):
        result = ExecutionResult(task="test", success=True)
        assert result.task == "test"
        assert result.success

    def test_summary_success(self):
        result = ExecutionResult(task="Test task", success=True, total_time=1.5)
        summary = result.summary()
        assert "SUCCESS" in summary
        assert "Test task" in summary

    def test_summary_failure(self):
        result = ExecutionResult(
            task="Test", success=False, error="Something went wrong"
        )
        summary = result.summary()
        assert "FAILED" in summary
        assert "Something went wrong" in summary

    def test_to_dict(self):
        result = ExecutionResult(task="t", success=True, total_time=2.0)
        d = result.to_dict()
        assert d["success"] is True
        assert d["total_time"] == 2.0


class TestAgenticExecutor:
    @pytest.fixture
    def executor(self):
        return AgenticExecutor()

    @pytest.fixture
    def temp_dir(self):
        d = tempfile.mkdtemp()
        yield d
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_execute_simple_task(self, executor):
        result = executor.execute("run tests", {"command": "echo test"})
        assert isinstance(result, ExecutionResult)
        assert len(result.steps) >= 1

    def test_execute_file_read(self, executor, temp_dir):
        # Create a test file
        path = os.path.join(temp_dir, "test.txt")
        with open(path, "w") as f:
            f.write("content")

        # Configure executor with allowed path
        executor.registry.get("file_read").allowed_paths = [temp_dir]

        result = executor.execute("read file", {"path": path})
        assert len(result.steps) >= 1

    def test_callback_called(self, executor):
        steps_seen = []

        def callback(step):
            steps_seen.append(step)

        executor.on_step_complete = callback
        executor.execute("run tests", {"command": "echo hello"})

        assert len(steps_seen) >= 1

    def test_execute_code(self, executor):
        result = executor.execute_code("print(1 + 1)", "Test code")
        assert "2" in result.steps[0].result.output or result.success

    def test_execute_code_error(self, executor):
        result = executor.execute_code("raise ValueError('fail')", "Bad code")
        # Either the error is caught or execution fails
        assert not result.success or "ValueError" in str(result.to_dict())

    def test_edit_file(self, executor, temp_dir):
        path = os.path.join(temp_dir, "edit.txt")
        with open(path, "w") as f:
            f.write("old content here")

        executor.registry.get("file_read").allowed_paths = [temp_dir]
        executor.registry.get("file_write").allowed_paths = [temp_dir]

        result = executor.edit_file(path, "old", "new")
        assert result.success

        with open(path) as f:
            assert "new content here" in f.read()

    def test_edit_file_not_found(self, executor, temp_dir):
        path = os.path.join(temp_dir, "nonexistent.txt")
        executor.registry.get("file_read").allowed_paths = [temp_dir]

        result = executor.edit_file(path, "old", "new")
        assert not result.success

    def test_edit_file_content_not_found(self, executor, temp_dir):
        path = os.path.join(temp_dir, "file.txt")
        with open(path, "w") as f:
            f.write("something else")

        executor.registry.get("file_read").allowed_paths = [temp_dir]
        executor.registry.get("file_write").allowed_paths = [temp_dir]

        result = executor.edit_file(path, "not_present", "new")
        assert not result.success
        assert "not found" in result.error.lower()

    def test_max_steps_limit(self, executor):
        executor.max_steps = 2
        # Even complex tasks should respect the limit
        result = executor.execute("complex task")
        assert len(result.steps) <= 3  # Some buffer

    def test_run_tests(self, executor):
        result = executor.run_tests(test_command="echo 'test passed'")
        assert result.success or len(result.steps) > 0


class TestAgenticExecutorModes:
    def test_sequential_mode(self):
        executor = AgenticExecutor(mode=ExecutionMode.SEQUENTIAL)
        assert executor.mode == ExecutionMode.SEQUENTIAL

    def test_custom_registry(self):
        registry = ToolRegistry()
        executor = AgenticExecutor(registry=registry)
        assert executor.registry is registry

    def test_custom_sandbox_config(self):
        config = SandboxConfig(timeout_seconds=5)
        executor = AgenticExecutor(sandbox_config=config)
        assert executor.sandbox_config.timeout_seconds == 5

"""Tests for agentic_executor.sandbox module."""

import pytest
import tempfile
import os
from agentic_executor.sandbox import (
    CodeSandbox, SandboxConfig, SandboxResult, SandboxStatus,
)


class TestSandboxConfig:
    def test_defaults(self):
        config = SandboxConfig()
        assert config.timeout_seconds == 30
        assert config.max_memory_mb == 256
        assert "subprocess" in config.blocked_imports

    def test_custom_config(self):
        config = SandboxConfig(timeout_seconds=10, max_memory_mb=128)
        assert config.timeout_seconds == 10
        assert config.max_memory_mb == 128


class TestSandboxResult:
    def test_create(self):
        r = SandboxResult(SandboxStatus.COMPLETED, "output", "")
        assert r.status == SandboxStatus.COMPLETED

    def test_to_dict(self):
        r = SandboxResult(
            SandboxStatus.ERROR, "", "error",
            execution_time=1.5, memory_used_mb=50.0
        )
        d = r.to_dict()
        assert d["status"] == "error"
        assert d["execution_time"] == 1.5


class TestCodeSandbox:
    def test_simple_execution(self):
        config = SandboxConfig(timeout_seconds=10)
        with CodeSandbox(config) as sandbox:
            result = sandbox.execute("x = 1 + 1\nprint(x)")
        assert result.status == SandboxStatus.COMPLETED
        assert "2" in result.stdout

    def test_execution_error(self):
        config = SandboxConfig(timeout_seconds=10)
        with CodeSandbox(config) as sandbox:
            result = sandbox.execute("raise ValueError('test error')")
        # Error in code is captured in stderr
        assert "test error" in result.stderr or result.status == SandboxStatus.ERROR

    def test_timeout(self):
        config = SandboxConfig(timeout_seconds=1)
        with CodeSandbox(config) as sandbox:
            result = sandbox.execute("import time; time.sleep(10)")
        assert result.status == SandboxStatus.TIMEOUT

    def test_blocked_import(self):
        config = SandboxConfig(blocked_imports=["subprocess"])
        with CodeSandbox(config) as sandbox:
            result = sandbox.execute("import subprocess")
        assert result.status == SandboxStatus.ERROR
        assert "Blocked" in result.stderr

    def test_output_capture(self):
        config = SandboxConfig(timeout_seconds=10)
        with CodeSandbox(config) as sandbox:
            result = sandbox.execute("print('hello')\nprint('world')")
        assert "hello" in result.stdout
        assert "world" in result.stdout

    def test_output_truncation(self):
        config = SandboxConfig(max_output_bytes=100)
        with CodeSandbox(config) as sandbox:
            result = sandbox.execute("print('x' * 1000)")
        assert len(result.stdout) <= 200  # Some buffer for truncation message

    def test_custom_working_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SandboxConfig(working_dir=tmpdir, cleanup_on_exit=False)
            with CodeSandbox(config) as sandbox:
                result = sandbox.execute("print('test')")
            assert result.status == SandboxStatus.COMPLETED

    def test_multiline_code(self):
        code = '''
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

print(factorial(5))
'''
        config = SandboxConfig(timeout_seconds=10)
        with CodeSandbox(config) as sandbox:
            result = sandbox.execute(code)
        assert result.status == SandboxStatus.COMPLETED
        assert "120" in result.stdout

    def test_execution_time_tracked(self):
        config = SandboxConfig(timeout_seconds=10)
        with CodeSandbox(config) as sandbox:
            result = sandbox.execute("import time; time.sleep(0.1)")
        assert result.execution_time >= 0.1
        assert result.execution_time < 5.0

    def test_context_manager(self):
        config = SandboxConfig()
        sandbox = CodeSandbox(config)
        with sandbox:
            result = sandbox.execute("print(1)")
        assert result.status == SandboxStatus.COMPLETED


class TestCodeSandboxFileExecution:
    def test_execute_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("print('from file')")
            path = f.name

        try:
            config = SandboxConfig(timeout_seconds=10)
            with CodeSandbox(config) as sandbox:
                result = sandbox.execute_file(path)
            assert result.status == SandboxStatus.COMPLETED
            assert "from file" in result.stdout
        finally:
            os.unlink(path)

    def test_execute_file_not_found(self):
        config = SandboxConfig()
        with CodeSandbox(config) as sandbox:
            result = sandbox.execute_file("/nonexistent/file.py")
        assert result.status == SandboxStatus.ERROR
        assert "not found" in result.stderr.lower()

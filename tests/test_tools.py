"""Tests for agentic_executor.tools module."""

import pytest
import os
import tempfile
from agentic_executor.tools import (
    Tool, ToolResult, ToolStatus, ToolParameter, ToolRegistry,
    FileReadTool, FileWriteTool, ShellTool, SearchTool,
)


class TestToolResult:
    def test_create(self):
        r = ToolResult(ToolStatus.SUCCESS, "output")
        assert r.status == ToolStatus.SUCCESS
        assert r.output == "output"

    def test_to_dict(self):
        r = ToolResult(ToolStatus.ERROR, "", "failed")
        d = r.to_dict()
        assert d["status"] == "error"
        assert d["error"] == "failed"


class TestFileReadTool:
    @pytest.fixture
    def temp_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello, World!")
            path = f.name
        yield path
        os.unlink(path)

    def test_read_success(self, temp_file):
        tool = FileReadTool(allowed_paths=[os.path.dirname(temp_file)])
        result = tool.execute(path=temp_file)
        assert result.status == ToolStatus.SUCCESS
        assert result.output == "Hello, World!"

    def test_read_not_found(self):
        tool = FileReadTool(allowed_paths=["."])
        result = tool.execute(path="nonexistent_file.txt")
        assert result.status == ToolStatus.ERROR

    def test_path_not_allowed(self, temp_file):
        tool = FileReadTool(allowed_paths=["/some/other/path"])
        result = tool.execute(path=temp_file)
        assert result.status == ToolStatus.PERMISSION_DENIED

    def test_schema(self):
        tool = FileReadTool()
        schema = tool.to_schema()
        assert schema["name"] == "file_read"
        assert "path" in schema["parameters"]["properties"]


class TestFileWriteTool:
    @pytest.fixture
    def temp_dir(self):
        d = tempfile.mkdtemp()
        yield d
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_write_success(self, temp_dir):
        tool = FileWriteTool(allowed_paths=[temp_dir])
        path = os.path.join(temp_dir, "test.txt")
        result = tool.execute(path=path, content="Hello!")
        assert result.status == ToolStatus.SUCCESS
        with open(path) as f:
            assert f.read() == "Hello!"

    def test_write_append(self, temp_dir):
        tool = FileWriteTool(allowed_paths=[temp_dir])
        path = os.path.join(temp_dir, "test.txt")
        tool.execute(path=path, content="A")
        tool.execute(path=path, content="B", mode="append")
        with open(path) as f:
            assert f.read() == "AB"

    def test_creates_parent_dirs(self, temp_dir):
        tool = FileWriteTool(allowed_paths=[temp_dir])
        path = os.path.join(temp_dir, "nested", "dir", "test.txt")
        result = tool.execute(path=path, content="content")
        assert result.status == ToolStatus.SUCCESS
        assert os.path.exists(path)


class TestShellTool:
    def test_execute_success(self):
        tool = ShellTool()
        result = tool.execute(command="echo hello")
        assert result.status == ToolStatus.SUCCESS
        assert "hello" in result.output

    def test_blocked_command(self):
        tool = ShellTool(blocked_commands=["rm -rf"])
        result = tool.execute(command="rm -rf /")
        assert result.status == ToolStatus.PERMISSION_DENIED

    def test_timeout(self):
        tool = ShellTool(timeout=1)
        # This should work on Windows too
        result = tool.execute(command="ping -n 10 127.0.0.1", timeout=1)
        assert result.status == ToolStatus.TIMEOUT

    def test_allowed_commands(self):
        tool = ShellTool(allowed_commands=["echo", "ls"])
        result = tool.execute(command="echo test")
        assert result.status == ToolStatus.SUCCESS
        result = tool.execute(command="rm file")
        assert result.status == ToolStatus.PERMISSION_DENIED


class TestSearchTool:
    @pytest.fixture
    def temp_dir(self):
        d = tempfile.mkdtemp()
        # Create test files
        with open(os.path.join(d, "file1.py"), "w") as f:
            f.write("def hello():\n    print('world')\n")
        with open(os.path.join(d, "file2.py"), "w") as f:
            f.write("def goodbye():\n    return True\n")
        yield d
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_search_found(self, temp_dir):
        tool = SearchTool(search_paths=[temp_dir])
        result = tool.execute(pattern="hello")
        assert result.status == ToolStatus.SUCCESS
        assert "hello" in result.output

    def test_search_not_found(self, temp_dir):
        tool = SearchTool(search_paths=[temp_dir])
        result = tool.execute(pattern="nonexistent_pattern_xyz")
        assert result.status == ToolStatus.SUCCESS
        assert "No matches" in result.output

    def test_search_max_results(self, temp_dir):
        tool = SearchTool(search_paths=[temp_dir])
        result = tool.execute(pattern="def", max_results=1)
        assert result.metadata["matches"] == 1

    def test_invalid_regex(self):
        tool = SearchTool()
        result = tool.execute(pattern="[invalid")
        assert result.status == ToolStatus.ERROR


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = FileReadTool()
        registry.register(tool)
        assert registry.get("file_read") is tool

    def test_list_tools(self):
        registry = ToolRegistry.default_registry()
        tools = registry.list_tools()
        assert "file_read" in tools
        assert "file_write" in tools
        assert "shell" in tools
        assert "search" in tools

    def test_execute_unknown(self):
        registry = ToolRegistry()
        result = registry.execute("unknown_tool")
        assert result.status == ToolStatus.ERROR

    def test_get_schemas(self):
        registry = ToolRegistry.default_registry()
        schemas = registry.get_schemas()
        assert len(schemas) == 4
        assert all("name" in s for s in schemas)

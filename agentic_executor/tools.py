"""
Tool system for agentic code execution.

Tools are the primary building blocks - they're what the agent uses to
interact with the environment. Each tool has a name, description,
parameters schema, and execution function.

This mirrors how Claude Code works internally.
"""

import os
import re
import subprocess
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable
from enum import Enum


class ToolStatus(Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"


@dataclass
class ToolResult:
    """Result of executing a tool."""
    status: ToolStatus
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class ToolParameter:
    """Parameter definition for a tool."""
    name: str
    param_type: str  # "string", "integer", "boolean", "array"
    description: str
    required: bool = True
    default: Any = None


class Tool(ABC):
    """
    Abstract base class for all tools.

    Tools are the actions an agent can take. Each tool should be:
    - Well-documented with clear descriptions
    - Validated before execution
    - Safe with proper error handling
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the tool does."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> List[ToolParameter]:
        """List of parameters the tool accepts."""
        pass

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass

    def validate_params(self, params: Dict[str, Any]) -> Optional[str]:
        """Validate parameters. Returns error message or None if valid."""
        for param in self.parameters:
            if param.required and param.name not in params:
                return f"Missing required parameter: {param.name}"
        return None

    def to_schema(self) -> dict:
        """Return JSON schema for the tool (for LLM function calling)."""
        properties = {}
        required = []
        for param in self.parameters:
            properties[param.name] = {
                "type": param.param_type,
                "description": param.description,
            }
            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


class FileReadTool(Tool):
    """Read contents of a file."""

    def __init__(self, allowed_paths: Optional[List[str]] = None):
        self.allowed_paths = allowed_paths or ["."]

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return "Read the contents of a file at the given path. Returns the file content as a string."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("path", "string", "Path to the file to read"),
            ToolParameter("encoding", "string", "File encoding", required=False, default="utf-8"),
        ]

    def _is_path_allowed(self, path: str) -> bool:
        abs_path = os.path.abspath(path)
        for allowed in self.allowed_paths:
            allowed_abs = os.path.abspath(allowed)
            if abs_path.startswith(allowed_abs):
                return True
        return False

    def execute(self, **kwargs) -> ToolResult:
        path = kwargs.get("path")
        encoding = kwargs.get("encoding", "utf-8")

        if not path:
            return ToolResult(ToolStatus.ERROR, "", "Path is required")

        if not self._is_path_allowed(path):
            return ToolResult(ToolStatus.PERMISSION_DENIED, "", f"Access to {path} is not allowed")

        try:
            with open(path, "r", encoding=encoding) as f:
                content = f.read()
            return ToolResult(
                ToolStatus.SUCCESS, content,
                metadata={"path": path, "size": len(content)}
            )
        except FileNotFoundError:
            return ToolResult(ToolStatus.ERROR, "", f"File not found: {path}")
        except PermissionError:
            return ToolResult(ToolStatus.PERMISSION_DENIED, "", f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(ToolStatus.ERROR, "", str(e))


class FileWriteTool(Tool):
    """Write contents to a file."""

    def __init__(self, allowed_paths: Optional[List[str]] = None):
        self.allowed_paths = allowed_paths or ["."]

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return "Write content to a file at the given path. Creates the file if it doesn't exist."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("path", "string", "Path to the file to write"),
            ToolParameter("content", "string", "Content to write to the file"),
            ToolParameter("mode", "string", "Write mode: 'overwrite' or 'append'", required=False, default="overwrite"),
        ]

    def _is_path_allowed(self, path: str) -> bool:
        abs_path = os.path.abspath(path)
        for allowed in self.allowed_paths:
            allowed_abs = os.path.abspath(allowed)
            if abs_path.startswith(allowed_abs):
                return True
        return False

    def execute(self, **kwargs) -> ToolResult:
        path = kwargs.get("path")
        content = kwargs.get("content", "")
        mode = kwargs.get("mode", "overwrite")

        if not path:
            return ToolResult(ToolStatus.ERROR, "", "Path is required")

        if not self._is_path_allowed(path):
            return ToolResult(ToolStatus.PERMISSION_DENIED, "", f"Access to {path} is not allowed")

        try:
            # Create parent directories if needed
            parent = os.path.dirname(path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent)

            write_mode = "a" if mode == "append" else "w"
            with open(path, write_mode, encoding="utf-8") as f:
                f.write(content)

            return ToolResult(
                ToolStatus.SUCCESS,
                f"Successfully wrote {len(content)} bytes to {path}",
                metadata={"path": path, "size": len(content), "mode": mode}
            )
        except PermissionError:
            return ToolResult(ToolStatus.PERMISSION_DENIED, "", f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(ToolStatus.ERROR, "", str(e))


class ShellTool(Tool):
    """Execute shell commands."""

    def __init__(
        self,
        allowed_commands: Optional[List[str]] = None,
        blocked_commands: Optional[List[str]] = None,
        timeout: int = 30,
        working_dir: Optional[str] = None,
    ):
        self.allowed_commands = allowed_commands
        self.blocked_commands = blocked_commands or ["rm -rf /", "mkfs", "dd if="]
        self.timeout = timeout
        self.working_dir = working_dir or os.getcwd()

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return "Execute a shell command and return its output. Use for running tests, installing packages, git operations, etc."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("command", "string", "Shell command to execute"),
            ToolParameter("timeout", "integer", "Timeout in seconds", required=False, default=30),
        ]

    def _is_command_allowed(self, command: str) -> bool:
        # Check blocked commands
        for blocked in self.blocked_commands:
            if blocked in command:
                return False

        # If allowed list is specified, command must start with one of them
        if self.allowed_commands:
            return any(command.strip().startswith(cmd) for cmd in self.allowed_commands)

        return True

    def execute(self, **kwargs) -> ToolResult:
        command = kwargs.get("command")
        timeout = kwargs.get("timeout", self.timeout)

        if not command:
            return ToolResult(ToolStatus.ERROR, "", "Command is required")

        if not self._is_command_allowed(command):
            return ToolResult(
                ToolStatus.PERMISSION_DENIED, "",
                f"Command not allowed: {command}"
            )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.working_dir,
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"

            status = ToolStatus.SUCCESS if result.returncode == 0 else ToolStatus.ERROR

            return ToolResult(
                status, output,
                error=result.stderr if result.returncode != 0 else None,
                metadata={"returncode": result.returncode, "command": command}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ToolStatus.TIMEOUT, "", f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(ToolStatus.ERROR, "", str(e))


class SearchTool(Tool):
    """Search for patterns in files."""

    def __init__(self, search_paths: Optional[List[str]] = None):
        self.search_paths = search_paths or ["."]

    @property
    def name(self) -> str:
        return "search"

    @property
    def description(self) -> str:
        return "Search for a pattern in files. Returns matching lines with file paths and line numbers."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("pattern", "string", "Regex pattern to search for"),
            ToolParameter("file_pattern", "string", "Glob pattern for files to search", required=False, default="*"),
            ToolParameter("max_results", "integer", "Maximum number of results", required=False, default=50),
        ]

    def execute(self, **kwargs) -> ToolResult:
        pattern = kwargs.get("pattern")
        file_pattern = kwargs.get("file_pattern", "*")
        max_results = kwargs.get("max_results", 50)

        if not pattern:
            return ToolResult(ToolStatus.ERROR, "", "Pattern is required")

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return ToolResult(ToolStatus.ERROR, "", f"Invalid regex: {e}")

        results = []
        files_searched = 0

        for search_path in self.search_paths:
            for root, _, files in os.walk(search_path):
                for filename in files:
                    # Simple glob matching
                    if file_pattern != "*":
                        if not re.match(file_pattern.replace("*", ".*"), filename):
                            continue

                    filepath = os.path.join(root, filename)
                    files_searched += 1

                    try:
                        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                            for i, line in enumerate(f, 1):
                                if regex.search(line):
                                    results.append(f"{filepath}:{i}: {line.strip()}")
                                    if len(results) >= max_results:
                                        break
                    except (PermissionError, IOError):
                        continue

                    if len(results) >= max_results:
                        break
                if len(results) >= max_results:
                    break

        output = "\n".join(results) if results else "No matches found"
        return ToolResult(
            ToolStatus.SUCCESS, output,
            metadata={"matches": len(results), "files_searched": files_searched}
        )


class ToolRegistry:
    """Registry for managing available tools."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_schemas(self) -> List[dict]:
        """Get JSON schemas for all tools (for LLM function calling)."""
        return [tool.to_schema() for tool in self._tools.values()]

    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """Execute a tool by name."""
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(ToolStatus.ERROR, "", f"Unknown tool: {tool_name}")

        validation_error = tool.validate_params(kwargs)
        if validation_error:
            return ToolResult(ToolStatus.ERROR, "", validation_error)

        return tool.execute(**kwargs)

    @classmethod
    def default_registry(cls) -> "ToolRegistry":
        """Create a registry with default tools."""
        registry = cls()
        registry.register(FileReadTool())
        registry.register(FileWriteTool())
        registry.register(ShellTool())
        registry.register(SearchTool())
        return registry

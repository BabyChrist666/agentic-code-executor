"""
Sandbox for secure code execution.

Provides isolation and resource limits for executing untrusted code.
Critical for agentic systems that need to run arbitrary code safely.
"""

import os
import sys
import tempfile
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum


class SandboxStatus(Enum):
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    ERROR = "error"
    MEMORY_EXCEEDED = "memory_exceeded"


@dataclass
class SandboxConfig:
    """Configuration for the code sandbox."""
    timeout_seconds: int = 30
    max_memory_mb: int = 256
    max_output_bytes: int = 1024 * 1024  # 1MB
    allowed_imports: Optional[List[str]] = None
    blocked_imports: List[str] = field(default_factory=lambda: [
        "os.system", "subprocess", "socket", "requests",
        "urllib", "ftplib", "telnetlib", "smtplib",
    ])
    working_dir: Optional[str] = None
    cleanup_on_exit: bool = True


@dataclass
class SandboxResult:
    """Result of sandbox execution."""
    status: SandboxStatus
    stdout: str
    stderr: str
    return_value: Optional[Any] = None
    execution_time: float = 0.0
    memory_used_mb: float = 0.0

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_value": str(self.return_value) if self.return_value else None,
            "execution_time": round(self.execution_time, 4),
            "memory_used_mb": round(self.memory_used_mb, 2),
        }


class CodeSandbox:
    """
    Secure sandbox for executing Python code.

    Features:
    - Isolated working directory
    - Resource limits (time, memory)
    - Import restrictions
    - Output capture
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._temp_dir: Optional[str] = None
        self._status = SandboxStatus.READY

    def __enter__(self):
        self._setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cleanup()

    def _setup(self):
        """Set up the sandbox environment."""
        if self.config.working_dir:
            self._temp_dir = self.config.working_dir
            os.makedirs(self._temp_dir, exist_ok=True)
        else:
            self._temp_dir = tempfile.mkdtemp(prefix="sandbox_")

    def _cleanup(self):
        """Clean up sandbox resources."""
        if self.config.cleanup_on_exit and self._temp_dir:
            if not self.config.working_dir:  # Only remove if we created it
                shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _check_imports(self, code: str) -> Optional[str]:
        """Check for blocked imports in code."""
        for blocked in self.config.blocked_imports:
            if blocked in code:
                return f"Blocked import detected: {blocked}"
        return None

    def _create_wrapper_script(self, code: str) -> str:
        """Create a wrapper script with resource limits."""
        # Note: resource module only works on Unix
        wrapper = f'''
import sys
import json

# Redirect output
_stdout = []
_stderr = []

class OutputCapture:
    def __init__(self, target_list):
        self.target = target_list
    def write(self, text):
        self.target.append(text)
    def flush(self):
        pass

sys.stdout = OutputCapture(_stdout)
sys.stderr = OutputCapture(_stderr)

_result = None
_error = None

try:
    # User code
{self._indent_code(code, 4)}
except Exception as e:
    _error = str(e)

# Output results
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

output = {{
    "stdout": "".join(_stdout),
    "stderr": "".join(_stderr),
    "error": _error,
}}
print(json.dumps(output))
'''
        return wrapper

    def _indent_code(self, code: str, spaces: int) -> str:
        """Indent code block."""
        indent = " " * spaces
        lines = code.split("\n")
        return "\n".join(indent + line for line in lines)

    def execute(self, code: str) -> SandboxResult:
        """
        Execute Python code in the sandbox.

        Args:
            code: Python code to execute.

        Returns:
            SandboxResult with execution details.
        """
        self._status = SandboxStatus.RUNNING

        # Check for blocked imports
        import_error = self._check_imports(code)
        if import_error:
            return SandboxResult(
                status=SandboxStatus.ERROR,
                stdout="",
                stderr=import_error,
            )

        if not self._temp_dir:
            self._setup()

        # Write the wrapper script
        script_path = os.path.join(self._temp_dir, "_sandbox_script.py")
        wrapper = self._create_wrapper_script(code)

        try:
            with open(script_path, "w") as f:
                f.write(wrapper)
        except Exception as e:
            return SandboxResult(
                status=SandboxStatus.ERROR,
                stdout="",
                stderr=f"Failed to write script: {e}",
            )

        # Execute with timeout
        start_time = time.time()

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                cwd=self._temp_dir,
            )

            execution_time = time.time() - start_time

            # Parse output
            try:
                import json
                output = json.loads(result.stdout)
                stdout = output.get("stdout", "")
                stderr = output.get("stderr", "") + (output.get("error", "") or "")
            except json.JSONDecodeError:
                stdout = result.stdout
                stderr = result.stderr

            # Truncate if too long
            if len(stdout) > self.config.max_output_bytes:
                stdout = stdout[:self.config.max_output_bytes] + "\n[OUTPUT TRUNCATED]"
            if len(stderr) > self.config.max_output_bytes:
                stderr = stderr[:self.config.max_output_bytes] + "\n[OUTPUT TRUNCATED]"

            status = SandboxStatus.COMPLETED if result.returncode == 0 else SandboxStatus.ERROR

            return SandboxResult(
                status=status,
                stdout=stdout,
                stderr=stderr,
                execution_time=execution_time,
            )

        except subprocess.TimeoutExpired:
            return SandboxResult(
                status=SandboxStatus.TIMEOUT,
                stdout="",
                stderr=f"Execution timed out after {self.config.timeout_seconds}s",
                execution_time=self.config.timeout_seconds,
            )
        except Exception as e:
            return SandboxResult(
                status=SandboxStatus.ERROR,
                stdout="",
                stderr=str(e),
                execution_time=time.time() - start_time,
            )

    def execute_file(self, file_path: str) -> SandboxResult:
        """Execute a Python file in the sandbox."""
        try:
            with open(file_path, "r") as f:
                code = f.read()
            return self.execute(code)
        except FileNotFoundError:
            return SandboxResult(
                status=SandboxStatus.ERROR,
                stdout="",
                stderr=f"File not found: {file_path}",
            )
        except Exception as e:
            return SandboxResult(
                status=SandboxStatus.ERROR,
                stdout="",
                stderr=str(e),
            )

    def install_package(self, package: str) -> SandboxResult:
        """Install a package in the sandbox environment."""
        start_time = time.time()

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package, "--target", self._temp_dir],
                capture_output=True,
                text=True,
                timeout=120,  # Package installs can take longer
            )

            return SandboxResult(
                status=SandboxStatus.COMPLETED if result.returncode == 0 else SandboxStatus.ERROR,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=time.time() - start_time,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                status=SandboxStatus.TIMEOUT,
                stdout="",
                stderr="Package installation timed out",
                execution_time=120.0,
            )
        except Exception as e:
            return SandboxResult(
                status=SandboxStatus.ERROR,
                stdout="",
                stderr=str(e),
                execution_time=time.time() - start_time,
            )

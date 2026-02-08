# Agentic Code Executor

Multi-step code execution framework with tool orchestration, error recovery, and secure sandboxing. Built to demonstrate agentic AI patterns used in production systems like Claude Code.

[![Tests](https://github.com/BabyChrist666/agentic-code-executor/actions/workflows/tests.yml/badge.svg)](https://github.com/BabyChrist666/agentic-code-executor/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/BabyChrist666/agentic-code-executor/branch/master/graph/badge.svg)](https://codecov.io/gh/BabyChrist666/agentic-code-executor)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- **Tool Orchestration** - Extensible tool system with file I/O, shell commands, and code search
- **Execution Planning** - Dependency-aware task breakdown with automatic replanning on failures
- **Secure Sandbox** - Isolated Python execution with timeout, memory limits, and import restrictions
- **Error Recovery** - Automatic retry with intelligent fallback strategies
- **LLM-Ready** - Tools export JSON schemas for function calling integration

## Architecture

```
AgenticExecutor
    |
    +-- TaskPlanner (breaks tasks into steps with dependencies)
    |
    +-- ToolRegistry (file_read, file_write, shell, search)
    |
    +-- CodeSandbox (isolated execution environment)
```

## Installation

```bash
pip install -e .
```

## Quick Start

```python
from agentic_executor import AgenticExecutor

# Create executor with default tools
executor = AgenticExecutor()

# Execute a multi-step task
result = executor.execute(
    task="Read config and run tests",
    context={"command": "pytest tests/"}
)

print(result.summary())
```

## Core Components

### AgenticExecutor

The main orchestrator that coordinates planning, tool execution, and error recovery:

```python
from agentic_executor import AgenticExecutor, ExecutionMode
from agentic_executor.sandbox import SandboxConfig

executor = AgenticExecutor(
    mode=ExecutionMode.SEQUENTIAL,
    max_steps=10,
    sandbox_config=SandboxConfig(timeout_seconds=30)
)

# Execute code in sandbox
result = executor.execute_code("""
def fibonacci(n):
    if n <= 1: return n
    return fibonacci(n-1) + fibonacci(n-2)

print(fibonacci(10))
""", description="Calculate fibonacci")

# Edit files with search-and-replace
result = executor.edit_file(
    path="config.py",
    old_content="DEBUG = False",
    new_content="DEBUG = True"
)

# Run test suites
result = executor.run_tests(test_command="pytest -v")
```

### ToolRegistry

Extensible tool system with JSON schema generation for LLM function calling:

```python
from agentic_executor.tools import (
    ToolRegistry, FileReadTool, FileWriteTool,
    ShellTool, SearchTool
)

registry = ToolRegistry.default_registry()

# Execute tools
result = registry.execute("file_read", path="README.md")
result = registry.execute("shell", command="git status")
result = registry.execute("search", pattern="TODO", file_pattern="*.py")

# Get schemas for LLM function calling
schemas = registry.get_schemas()
# [{"name": "file_read", "parameters": {...}}, ...]
```

### TaskPlanner

Breaks complex tasks into executable steps with dependency management:

```python
from agentic_executor.planner import TaskPlanner, ExecutionPlan

planner = TaskPlanner(available_tools=["file_read", "file_write", "shell", "search"])

# Plan a refactoring task
plan = planner.plan(
    task="refactor rename function",
    context={"old_name": "getUserData", "new_name": "fetchUserProfile"}
)

print(plan.summary())
# Task: refactor rename function
# Steps:
#   1. [pending] search - Find occurrences
#   2. [pending] file_read - Read files (depends on: step_1)
#   3. [pending] file_write - Update files (depends on: step_2)
```

### CodeSandbox

Secure execution environment with resource limits:

```python
from agentic_executor.sandbox import CodeSandbox, SandboxConfig

config = SandboxConfig(
    timeout_seconds=10,
    max_memory_mb=256,
    blocked_imports=["subprocess", "socket", "os.system"],
    max_output_bytes=1024 * 1024
)

with CodeSandbox(config) as sandbox:
    result = sandbox.execute("""
import math
print(f"Pi = {math.pi:.10f}")
for i in range(5):
    print(f"  {i}! = {math.factorial(i)}")
""")

print(result.stdout)
# Pi = 3.1415926536
#   0! = 1
#   1! = 1
#   ...
```

## Tool Reference

| Tool | Description | Parameters |
|------|-------------|------------|
| `file_read` | Read file contents | `path` |
| `file_write` | Write/append to file | `path`, `content`, `mode` |
| `shell` | Execute shell command | `command`, `timeout` |
| `search` | Search files with regex | `pattern`, `file_pattern`, `max_results` |

## Error Recovery

The planner implements automatic error recovery:

```python
from agentic_executor.planner import TaskPlanner, ExecutionPlan, StepStatus

planner = TaskPlanner(["file_read", "search"])
plan = ExecutionPlan(task="read config")
step = plan.add_step("file_read", {"path": "config.yaml"}, "Read config")

# Simulate failure
step.status = StepStatus.FAILED

# Get recovery step
recovery = planner.replan_on_failure(plan, step, "file not found")
# Returns search step to find the file
```

## Security

The sandbox provides multiple security layers:

1. **Import Blocking** - Prevents dangerous modules (subprocess, socket, etc.)
2. **Timeout Enforcement** - Kills runaway processes
3. **Output Limits** - Truncates excessive output
4. **Isolated Filesystem** - Runs in temporary directory

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=agentic_executor --cov-report=html
```

## Use Cases

- **AI Coding Assistants** - Safe code execution for LLM-generated code
- **CI/CD Automation** - Multi-step build and deploy pipelines
- **Code Migration** - Automated refactoring with rollback
- **Test Automation** - Running test suites with intelligent retry

## License

MIT


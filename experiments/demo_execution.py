"""
Demonstration of the Agentic Code Executor.

Shows multi-step execution, error recovery, and sandbox features.
"""

import os
import sys
import tempfile
import shutil

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentic_executor import AgenticExecutor
from agentic_executor.tools import ToolRegistry, FileReadTool, FileWriteTool, ShellTool, SearchTool
from agentic_executor.planner import TaskPlanner, ExecutionPlan, StepStatus
from agentic_executor.sandbox import CodeSandbox, SandboxConfig, SandboxStatus


def demo_sandbox_execution():
    """Demonstrate secure code execution in sandbox."""
    print("=" * 60)
    print("DEMO 1: Sandbox Code Execution")
    print("=" * 60)

    config = SandboxConfig(timeout_seconds=10, max_memory_mb=128)

    with CodeSandbox(config) as sandbox:
        # Simple calculation
        print("\n1.1 Simple calculation:")
        result = sandbox.execute("print(sum(range(100)))")
        print(f"    Output: {result.stdout.strip()}")
        print(f"    Status: {result.status.value}")
        print(f"    Time: {result.execution_time:.3f}s")

        # Multiline code with functions
        print("\n1.2 Function definition and call:")
        code = '''
def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True

primes = [n for n in range(2, 50) if is_prime(n)]
print(f"Primes under 50: {primes}")
print(f"Count: {len(primes)}")
'''
        result = sandbox.execute(code)
        for line in result.stdout.strip().split('\n'):
            print(f"    {line}")

        # Blocked import
        print("\n1.3 Security: Blocked import:")
        result = sandbox.execute("import subprocess")
        print(f"    Status: {result.status.value}")
        print(f"    Error: {result.stderr}")

        # Timeout handling
        print("\n1.4 Timeout handling (1s limit):")
        config_timeout = SandboxConfig(timeout_seconds=1)
        with CodeSandbox(config_timeout) as timeout_sandbox:
            result = timeout_sandbox.execute("import time; time.sleep(5)")
            print(f"    Status: {result.status.value}")
            print(f"    Time: {result.execution_time:.1f}s")


def demo_tool_registry():
    """Demonstrate the tool system."""
    print("\n" + "=" * 60)
    print("DEMO 2: Tool Registry")
    print("=" * 60)

    # Create temp directory for file operations
    temp_dir = tempfile.mkdtemp()

    try:
        # Set up registry with allowed paths
        registry = ToolRegistry.default_registry()
        registry.get("file_read").allowed_paths = [temp_dir]
        registry.get("file_write").allowed_paths = [temp_dir]
        registry.get("search").search_paths = [temp_dir]

        print("\n2.1 Available tools:")
        for name in registry.list_tools():
            tool = registry.get(name)
            print(f"    - {name}: {tool.description}")

        # Write a file
        print("\n2.2 Write file:")
        path = os.path.join(temp_dir, "example.py")
        result = registry.execute(
            "file_write",
            path=path,
            content='def hello():\n    print("Hello, World!")\n\nhello()\n'
        )
        print(f"    Status: {result.status.value}")
        print(f"    Created: {os.path.basename(path)}")

        # Read the file back
        print("\n2.3 Read file:")
        result = registry.execute("file_read", path=path)
        print(f"    Status: {result.status.value}")
        print(f"    Content preview: {result.output[:50]}...")

        # Search for pattern
        print("\n2.4 Search for pattern 'hello':")
        result = registry.execute("search", pattern="hello")
        print(f"    Status: {result.status.value}")
        print(f"    Matches: {result.metadata.get('matches', 0)}")

        # Execute shell command
        print("\n2.5 Shell command (echo):")
        result = registry.execute("shell", command="echo Hello from shell")
        print(f"    Status: {result.status.value}")
        print(f"    Output: {result.output.strip()}")

        # Get tool schemas for LLM
        print("\n2.6 Tool schemas (for LLM function calling):")
        schemas = registry.get_schemas()
        for schema in schemas:
            params = list(schema["parameters"]["properties"].keys())
            print(f"    {schema['name']}: {params}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def demo_task_planning():
    """Demonstrate task planning and dependency management."""
    print("\n" + "=" * 60)
    print("DEMO 3: Task Planning")
    print("=" * 60)

    planner = TaskPlanner(["file_read", "file_write", "shell", "search"])

    # Plan a file read task
    print("\n3.1 Simple task plan:")
    plan = planner.plan("read configuration", {"path": "config.yaml"})
    print(f"    Task: {plan.task}")
    print(f"    Steps: {len(plan.steps)}")
    for step in plan.steps:
        print(f"      - {step.tool}: {step.description}")

    # Plan a git workflow
    print("\n3.2 Multi-step task (git commit):")
    plan = planner.plan("git commit changes", {"message": "Fix bug #123"})
    print(f"    Task: {plan.task}")
    print(f"    Steps: {len(plan.steps)}")
    for step in plan.steps:
        deps = f" (after: {step.depends_on})" if step.depends_on else ""
        print(f"      - {step.tool}: {step.description}{deps}")

    # Demonstrate dependency resolution
    print("\n3.3 Dependency-aware execution order:")
    plan = ExecutionPlan(task="Test dependencies")
    s1 = plan.add_step("search", {"pattern": "TODO"}, "Find TODOs")
    s2 = plan.add_step("file_read", {"path": "todo.txt"}, "Read TODO file", depends_on=[s1.id])
    s3 = plan.add_step("file_write", {"path": "report.txt"}, "Write report", depends_on=[s2.id])

    print(f"    Initial ready steps: {[s.id for s in plan.get_ready_steps()]}")

    s1.status = StepStatus.COMPLETED
    print(f"    After step_1 completes: {[s.id for s in plan.get_ready_steps()]}")

    s2.status = StepStatus.COMPLETED
    print(f"    After step_2 completes: {[s.id for s in plan.get_ready_steps()]}")

    # Error recovery
    print("\n3.4 Error recovery (file not found):")
    plan = ExecutionPlan(task="Read missing file")
    step = plan.add_step("file_read", {"path": "missing.txt"}, "Read file")
    step.status = StepStatus.FAILED
    step.retry_count = 3  # Exhausted retries

    recovery = planner.replan_on_failure(plan, step, "File not found")
    if recovery:
        print(f"    Recovery action: {recovery.tool}")
        print(f"    Description: {recovery.description}")


def demo_agentic_executor():
    """Demonstrate the full agentic executor."""
    print("\n" + "=" * 60)
    print("DEMO 4: Agentic Executor")
    print("=" * 60)

    temp_dir = tempfile.mkdtemp()

    try:
        executor = AgenticExecutor()

        # Configure tools for temp directory
        executor.registry.get("file_read").allowed_paths = [temp_dir]
        executor.registry.get("file_write").allowed_paths = [temp_dir]

        # Execute code in sandbox
        print("\n4.1 Execute code:")
        result = executor.execute_code("""
nums = [1, 2, 3, 4, 5]
squared = [n**2 for n in nums]
print(f"Squared: {squared}")
print(f"Sum: {sum(squared)}")
""", description="Square numbers")

        print(f"    Success: {result.success}")
        if result.steps:
            output = result.steps[0].result.output if hasattr(result.steps[0].result, 'output') else str(result.steps[0].result)
            for line in output.strip().split('\n')[:3]:
                print(f"    {line}")

        # File editing workflow
        print("\n4.2 File editing:")
        test_file = os.path.join(temp_dir, "config.py")
        with open(test_file, "w") as f:
            f.write("DEBUG = False\nVERSION = '1.0'\n")

        result = executor.edit_file(test_file, "DEBUG = False", "DEBUG = True")
        print(f"    Edit success: {result.success}")

        with open(test_file) as f:
            print(f"    New content: {f.read().strip()}")

        # Step callback
        print("\n4.3 Execution with step callback:")
        steps_executed = []

        def on_step(step):
            steps_executed.append(step.tool)
            print(f"    -> Step: {step.tool}")

        executor.on_step_complete = on_step
        executor.execute("echo test", {"command": "echo 'Callback test'"})
        print(f"    Total steps: {len(steps_executed)}")

        # Summary
        print("\n4.4 Execution result summary:")
        result = executor.execute_code("print('Final demo')", "Demo task")
        print(result.summary())

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    print("\n" + "#" * 60)
    print("#" + " " * 20 + "AGENTIC CODE EXECUTOR" + " " * 17 + "#")
    print("#" + " " * 15 + "Multi-step Execution Framework" + " " * 12 + "#")
    print("#" * 60)

    demo_sandbox_execution()
    demo_tool_registry()
    demo_task_planning()
    demo_agentic_executor()

    print("\n" + "=" * 60)
    print("All demos completed successfully!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

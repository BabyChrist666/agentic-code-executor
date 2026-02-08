"""
Core agentic executor - orchestrates multi-step code execution.

This is the main entry point that ties together:
- Tool system for actions
- Planner for task breakdown
- Sandbox for safe execution
- Error recovery and retries

Models the agentic loop pattern used by Claude Code.
"""

import time
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum

from agentic_executor.tools import ToolRegistry, ToolResult, ToolStatus
from agentic_executor.planner import TaskPlanner, ExecutionPlan, PlanStep, StepStatus
from agentic_executor.sandbox import CodeSandbox, SandboxConfig, SandboxResult


class ExecutionMode(Enum):
    SEQUENTIAL = "sequential"  # Execute steps one by one
    PARALLEL = "parallel"      # Execute independent steps in parallel
    INTERACTIVE = "interactive"  # Pause for user confirmation


@dataclass
class ExecutionStep:
    """Record of a single execution step."""
    step_id: str
    tool: str
    params: Dict[str, Any]
    result: Optional[ToolResult] = None
    start_time: float = 0.0
    end_time: float = 0.0
    retries: int = 0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time if self.end_time else 0.0

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "tool": self.tool,
            "params": self.params,
            "result": self.result.to_dict() if self.result else None,
            "duration": round(self.duration, 4),
            "retries": self.retries,
        }


@dataclass
class ExecutionResult:
    """Complete result of an agentic execution."""
    task: str
    success: bool
    steps: List[ExecutionStep] = field(default_factory=list)
    total_time: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "success": self.success,
            "steps": [s.to_dict() for s in self.steps],
            "total_time": round(self.total_time, 4),
            "error": self.error,
            "metadata": self.metadata,
        }

    def summary(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        lines = [
            f"Task: {self.task}",
            f"Status: {status}",
            f"Steps: {len(self.steps)} ({sum(1 for s in self.steps if s.result and s.result.status == ToolStatus.SUCCESS)} succeeded)",
            f"Total time: {self.total_time:.2f}s",
        ]
        if self.error:
            lines.append(f"Error: {self.error}")
        return "\n".join(lines)


class AgenticExecutor:
    """
    Orchestrates multi-step agentic code execution.

    The executor:
    1. Takes a high-level task
    2. Plans the execution steps
    3. Executes each step with the appropriate tool
    4. Handles errors and retries
    5. Returns a complete execution result

    This mirrors the agentic loop in Claude Code:
    - Generate plan
    - Execute tools
    - Check results
    - Retry or recover on failure
    - Complete when all steps done
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        sandbox_config: Optional[SandboxConfig] = None,
        mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
        max_steps: int = 50,
        on_step_complete: Optional[Callable[[ExecutionStep], None]] = None,
    ):
        self.registry = registry or ToolRegistry.default_registry()
        self.sandbox_config = sandbox_config
        self.mode = mode
        self.max_steps = max_steps
        self.on_step_complete = on_step_complete

        self.planner = TaskPlanner(self.registry.list_tools())
        self._sandbox: Optional[CodeSandbox] = None

    def execute(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """
        Execute a task with full agentic loop.

        Args:
            task: High-level task description.
            context: Optional context (file paths, patterns, etc.)

        Returns:
            ExecutionResult with all step details.
        """
        start_time = time.time()
        steps_executed: List[ExecutionStep] = []

        # Create execution plan
        plan = self.planner.plan(task, context)

        # Execute the agentic loop
        iteration = 0
        while not plan.is_complete() and iteration < self.max_steps:
            iteration += 1

            # Get steps ready to execute
            ready_steps = plan.get_ready_steps()

            if not ready_steps:
                # No steps ready but plan not complete - dependency issue
                break

            for plan_step in ready_steps:
                exec_step = self._execute_step(plan_step)
                steps_executed.append(exec_step)

                # Notify callback
                if self.on_step_complete:
                    self.on_step_complete(exec_step)

                # Update plan step status
                if exec_step.result and exec_step.result.status == ToolStatus.SUCCESS:
                    plan_step.status = StepStatus.COMPLETED
                    plan_step.result = exec_step.result.output
                else:
                    # Try recovery
                    error_msg = exec_step.result.error if exec_step.result else "Unknown error"
                    recovery_step = self.planner.replan_on_failure(plan, plan_step, error_msg)

                    if not recovery_step:
                        plan_step.status = StepStatus.FAILED
                        plan_step.error = error_msg

        # Determine overall success
        success = all(
            step.status == StepStatus.COMPLETED
            for step in plan.steps
        )

        # Find first error if failed
        error = None
        if not success:
            for step in plan.steps:
                if step.status == StepStatus.FAILED:
                    error = step.error
                    break

        return ExecutionResult(
            task=task,
            success=success,
            steps=steps_executed,
            total_time=time.time() - start_time,
            error=error,
            metadata={"plan": plan.to_dict(), "iterations": iteration},
        )

    def _execute_step(self, plan_step: PlanStep) -> ExecutionStep:
        """Execute a single plan step."""
        exec_step = ExecutionStep(
            step_id=plan_step.id,
            tool=plan_step.tool,
            params=plan_step.params,
            start_time=time.time(),
        )

        plan_step.status = StepStatus.RUNNING

        # Execute the tool
        result = self.registry.execute(plan_step.tool, **plan_step.params)

        exec_step.result = result
        exec_step.end_time = time.time()
        exec_step.retries = plan_step.retry_count

        return exec_step

    def execute_code(
        self,
        code: str,
        description: str = "Execute code",
    ) -> ExecutionResult:
        """
        Execute arbitrary Python code in a sandbox.

        Args:
            code: Python code to execute.
            description: Description for logging.

        Returns:
            ExecutionResult with sandbox execution details.
        """
        start_time = time.time()

        config = self.sandbox_config or SandboxConfig()
        with CodeSandbox(config) as sandbox:
            sandbox_result = sandbox.execute(code)

        # Convert sandbox result to execution result
        success = sandbox_result.status.value == "completed"

        exec_step = ExecutionStep(
            step_id="sandbox_exec",
            tool="sandbox",
            params={"code": code[:200] + "..." if len(code) > 200 else code},
            start_time=start_time,
            end_time=time.time(),
        )

        exec_step.result = ToolResult(
            status=ToolStatus.SUCCESS if success else ToolStatus.ERROR,
            output=sandbox_result.stdout,
            error=sandbox_result.stderr if not success else None,
            metadata={
                "execution_time": sandbox_result.execution_time,
                "memory_used_mb": sandbox_result.memory_used_mb,
            },
        )

        return ExecutionResult(
            task=description,
            success=success,
            steps=[exec_step],
            total_time=time.time() - start_time,
            error=sandbox_result.stderr if not success else None,
        )

    def run_tests(
        self,
        test_command: str = "pytest",
        working_dir: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Run tests and return structured results.

        Args:
            test_command: Test command to run.
            working_dir: Working directory for tests.

        Returns:
            ExecutionResult with test output.
        """
        context = {"command": test_command}

        # Update shell tool working dir if specified
        if working_dir:
            shell_tool = self.registry.get("shell")
            if shell_tool:
                shell_tool.working_dir = working_dir

        return self.execute("run tests", context)

    def edit_file(
        self,
        path: str,
        old_content: str,
        new_content: str,
    ) -> ExecutionResult:
        """
        Edit a file by replacing content.

        Args:
            path: File path.
            old_content: Content to replace.
            new_content: Replacement content.

        Returns:
            ExecutionResult with edit details.
        """
        start_time = time.time()
        steps = []

        # Step 1: Read file
        read_result = self.registry.execute("file_read", path=path)
        steps.append(ExecutionStep(
            step_id="read",
            tool="file_read",
            params={"path": path},
            result=read_result,
            start_time=start_time,
            end_time=time.time(),
        ))

        if read_result.status != ToolStatus.SUCCESS:
            return ExecutionResult(
                task=f"Edit file: {path}",
                success=False,
                steps=steps,
                total_time=time.time() - start_time,
                error=read_result.error,
            )

        # Step 2: Replace content
        if old_content not in read_result.output:
            return ExecutionResult(
                task=f"Edit file: {path}",
                success=False,
                steps=steps,
                total_time=time.time() - start_time,
                error="Old content not found in file",
            )

        updated_content = read_result.output.replace(old_content, new_content)

        # Step 3: Write file
        write_start = time.time()
        write_result = self.registry.execute("file_write", path=path, content=updated_content)
        steps.append(ExecutionStep(
            step_id="write",
            tool="file_write",
            params={"path": path},
            result=write_result,
            start_time=write_start,
            end_time=time.time(),
        ))

        return ExecutionResult(
            task=f"Edit file: {path}",
            success=write_result.status == ToolStatus.SUCCESS,
            steps=steps,
            total_time=time.time() - start_time,
            error=write_result.error if write_result.status != ToolStatus.SUCCESS else None,
        )

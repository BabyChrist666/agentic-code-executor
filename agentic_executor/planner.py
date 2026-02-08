"""
Task planning for agentic execution.

The planner breaks down complex tasks into executable steps,
handles dependencies, and manages the execution order.

This is the "brain" that decides what tools to use and in what order.
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """A single step in an execution plan."""
    id: str
    tool: str
    params: Dict[str, Any]
    description: str
    depends_on: List[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tool": self.tool,
            "params": self.params,
            "description": self.description,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
        }

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries


@dataclass
class ExecutionPlan:
    """A complete execution plan with multiple steps."""
    task: str
    steps: List[PlanStep] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_step(
        self,
        tool: str,
        params: Dict[str, Any],
        description: str,
        depends_on: Optional[List[str]] = None,
    ) -> PlanStep:
        step_id = f"step_{len(self.steps) + 1}"
        step = PlanStep(
            id=step_id,
            tool=tool,
            params=params,
            description=description,
            depends_on=depends_on or [],
        )
        self.steps.append(step)
        return step

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_ready_steps(self) -> List[PlanStep]:
        """Get steps that are ready to execute (all dependencies completed)."""
        ready = []
        for step in self.steps:
            if step.status != StepStatus.PENDING:
                continue

            # Check all dependencies
            deps_met = True
            for dep_id in step.depends_on:
                dep = self.get_step(dep_id)
                if not dep or dep.status != StepStatus.COMPLETED:
                    deps_met = False
                    break

            if deps_met:
                ready.append(step)

        return ready

    def is_complete(self) -> bool:
        """Check if all steps are completed or failed."""
        return all(
            step.status in (StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED)
            for step in self.steps
        )

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "steps": [s.to_dict() for s in self.steps],
            "metadata": self.metadata,
        }

    def summary(self) -> str:
        """Human-readable summary of the plan."""
        lines = [f"Plan: {self.task}", f"Steps: {len(self.steps)}"]
        for step in self.steps:
            status_icon = {
                StepStatus.PENDING: " ",
                StepStatus.RUNNING: ">",
                StepStatus.COMPLETED: "+",
                StepStatus.FAILED: "X",
                StepStatus.SKIPPED: "-",
            }.get(step.status, "?")
            lines.append(f"  [{status_icon}] {step.id}: {step.description}")
        return "\n".join(lines)


class TaskPlanner:
    """
    Plans task execution by breaking down high-level goals into tool calls.

    The planner analyzes the task, identifies required tools,
    determines execution order based on dependencies, and
    handles error recovery with retries.
    """

    # Common task patterns and their typical tool sequences
    TASK_PATTERNS = {
        "read_and_modify": ["file_read", "file_write"],
        "search_and_edit": ["search", "file_read", "file_write"],
        "run_tests": ["shell"],
        "install_deps": ["shell"],
        "git_commit": ["shell", "shell"],
        "refactor": ["search", "file_read", "file_write", "shell"],
    }

    def __init__(self, available_tools: List[str]):
        self.available_tools = available_tools

    def plan(self, task: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
        """
        Create an execution plan for a task.

        This is a simplified planner - in production, this would
        call an LLM to generate the plan.
        """
        plan = ExecutionPlan(task=task, metadata=context or {})
        task_lower = task.lower()

        # Detect task type and create appropriate steps
        if "read" in task_lower and "file" in task_lower:
            self._plan_file_read(plan, task, context)
        elif "write" in task_lower or "create" in task_lower:
            self._plan_file_write(plan, task, context)
        elif "search" in task_lower or "find" in task_lower:
            self._plan_search(plan, task, context)
        elif "test" in task_lower or "pytest" in task_lower:
            self._plan_run_tests(plan, task, context)
        elif "install" in task_lower:
            self._plan_install(plan, task, context)
        elif "git" in task_lower or "commit" in task_lower:
            self._plan_git(plan, task, context)
        elif "refactor" in task_lower or "rename" in task_lower:
            self._plan_refactor(plan, task, context)
        else:
            # Default: try shell command
            self._plan_shell(plan, task, context)

        return plan

    def _plan_file_read(self, plan: ExecutionPlan, task: str, context: Optional[Dict]) -> None:
        path = context.get("path", "unknown") if context else "unknown"
        plan.add_step(
            tool="file_read",
            params={"path": path},
            description=f"Read file: {path}",
        )

    def _plan_file_write(self, plan: ExecutionPlan, task: str, context: Optional[Dict]) -> None:
        path = context.get("path", "output.txt") if context else "output.txt"
        content = context.get("content", "") if context else ""
        plan.add_step(
            tool="file_write",
            params={"path": path, "content": content},
            description=f"Write to file: {path}",
        )

    def _plan_search(self, plan: ExecutionPlan, task: str, context: Optional[Dict]) -> None:
        pattern = context.get("pattern", "TODO") if context else "TODO"
        plan.add_step(
            tool="search",
            params={"pattern": pattern},
            description=f"Search for pattern: {pattern}",
        )

    def _plan_run_tests(self, plan: ExecutionPlan, task: str, context: Optional[Dict]) -> None:
        test_cmd = context.get("command", "pytest") if context else "pytest"
        plan.add_step(
            tool="shell",
            params={"command": test_cmd},
            description="Run tests",
        )

    def _plan_install(self, plan: ExecutionPlan, task: str, context: Optional[Dict]) -> None:
        package = context.get("package", "") if context else ""
        plan.add_step(
            tool="shell",
            params={"command": f"pip install {package}"},
            description=f"Install package: {package}",
        )

    def _plan_git(self, plan: ExecutionPlan, task: str, context: Optional[Dict]) -> None:
        message = context.get("message", "Update") if context else "Update"

        step1 = plan.add_step(
            tool="shell",
            params={"command": "git add -A"},
            description="Stage changes",
        )

        plan.add_step(
            tool="shell",
            params={"command": f'git commit -m "{message}"'},
            description="Create commit",
            depends_on=[step1.id],
        )

    def _plan_refactor(self, plan: ExecutionPlan, task: str, context: Optional[Dict]) -> None:
        old_name = context.get("old_name", "") if context else ""
        new_name = context.get("new_name", "") if context else ""

        step1 = plan.add_step(
            tool="search",
            params={"pattern": old_name},
            description=f"Find occurrences of: {old_name}",
        )

        plan.add_step(
            tool="shell",
            params={"command": f"sed -i 's/{old_name}/{new_name}/g' *.py"},
            description=f"Replace {old_name} with {new_name}",
            depends_on=[step1.id],
        )

    def _plan_shell(self, plan: ExecutionPlan, task: str, context: Optional[Dict]) -> None:
        command = context.get("command", task) if context else task
        plan.add_step(
            tool="shell",
            params={"command": command},
            description=f"Execute: {command}",
        )

    def replan_on_failure(
        self,
        plan: ExecutionPlan,
        failed_step: PlanStep,
        error: str,
    ) -> Optional[PlanStep]:
        """
        Attempt to create a recovery step after a failure.

        Returns a new step to try, or None if no recovery is possible.
        """
        # Check if we can retry
        if failed_step.can_retry():
            failed_step.retry_count += 1
            failed_step.status = StepStatus.PENDING
            return failed_step

        # Try alternative approaches based on the error
        if "not found" in error.lower() and failed_step.tool == "file_read":
            # File not found - try searching for it
            filename = failed_step.params.get("path", "").split("/")[-1]
            recovery = plan.add_step(
                tool="search",
                params={"pattern": filename, "file_pattern": "*"},
                description=f"Search for file: {filename}",
            )
            return recovery

        if "permission denied" in error.lower():
            # Permission issue - try with sudo if shell
            if failed_step.tool == "shell":
                cmd = failed_step.params.get("command", "")
                if not cmd.startswith("sudo"):
                    recovery = plan.add_step(
                        tool="shell",
                        params={"command": f"sudo {cmd}"},
                        description=f"Retry with sudo: {cmd}",
                    )
                    return recovery

        return None

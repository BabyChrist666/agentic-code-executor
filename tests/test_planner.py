"""Tests for agentic_executor.planner module."""

import pytest
from agentic_executor.planner import (
    TaskPlanner, ExecutionPlan, PlanStep, StepStatus,
)


class TestPlanStep:
    def test_create(self):
        step = PlanStep(
            id="step_1",
            tool="file_read",
            params={"path": "test.txt"},
            description="Read test file",
        )
        assert step.id == "step_1"
        assert step.status == StepStatus.PENDING

    def test_to_dict(self):
        step = PlanStep("s1", "shell", {"command": "ls"}, "List files")
        d = step.to_dict()
        assert d["id"] == "s1"
        assert d["tool"] == "shell"

    def test_can_retry(self):
        step = PlanStep("s1", "shell", {}, "test", max_retries=2)
        assert step.can_retry()
        step.retry_count = 2
        assert not step.can_retry()


class TestExecutionPlan:
    def test_add_step(self):
        plan = ExecutionPlan(task="Test task")
        step = plan.add_step("file_read", {"path": "x"}, "Read x")
        assert step.id == "step_1"
        assert len(plan.steps) == 1

    def test_get_step(self):
        plan = ExecutionPlan(task="Test")
        plan.add_step("shell", {}, "Step 1")
        plan.add_step("shell", {}, "Step 2")
        assert plan.get_step("step_1") is not None
        assert plan.get_step("step_3") is None

    def test_get_ready_steps_no_deps(self):
        plan = ExecutionPlan(task="Test")
        plan.add_step("shell", {}, "Step 1")
        plan.add_step("shell", {}, "Step 2")
        ready = plan.get_ready_steps()
        assert len(ready) == 2

    def test_get_ready_steps_with_deps(self):
        plan = ExecutionPlan(task="Test")
        s1 = plan.add_step("shell", {}, "Step 1")
        plan.add_step("shell", {}, "Step 2", depends_on=[s1.id])

        ready = plan.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].id == "step_1"

        s1.status = StepStatus.COMPLETED
        ready = plan.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].id == "step_2"

    def test_is_complete(self):
        plan = ExecutionPlan(task="Test")
        plan.add_step("shell", {}, "Step 1")
        assert not plan.is_complete()

        plan.steps[0].status = StepStatus.COMPLETED
        assert plan.is_complete()

    def test_is_complete_with_failed(self):
        plan = ExecutionPlan(task="Test")
        plan.add_step("shell", {}, "Step 1")
        plan.steps[0].status = StepStatus.FAILED
        assert plan.is_complete()

    def test_summary(self):
        plan = ExecutionPlan(task="Test task")
        plan.add_step("shell", {}, "Do something")
        summary = plan.summary()
        assert "Test task" in summary
        assert "Do something" in summary


class TestTaskPlanner:
    @pytest.fixture
    def planner(self):
        return TaskPlanner(["file_read", "file_write", "shell", "search"])

    def test_plan_file_read(self, planner):
        plan = planner.plan("read file content", {"path": "test.txt"})
        assert len(plan.steps) == 1
        assert plan.steps[0].tool == "file_read"

    def test_plan_file_write(self, planner):
        plan = planner.plan("create new file", {"path": "out.txt", "content": "data"})
        assert plan.steps[0].tool == "file_write"

    def test_plan_search(self, planner):
        plan = planner.plan("search for TODO", {"pattern": "TODO"})
        assert plan.steps[0].tool == "search"

    def test_plan_tests(self, planner):
        plan = planner.plan("run pytest", {"command": "pytest tests/"})
        assert plan.steps[0].tool == "shell"

    def test_plan_git(self, planner):
        plan = planner.plan("git commit changes", {"message": "fix bug"})
        assert len(plan.steps) == 2
        assert plan.steps[1].depends_on == [plan.steps[0].id]

    def test_plan_refactor(self, planner):
        plan = planner.plan("refactor rename", {"old_name": "foo", "new_name": "bar"})
        assert len(plan.steps) >= 2

    def test_replan_on_failure_retry(self, planner):
        plan = ExecutionPlan(task="test")
        step = plan.add_step("file_read", {"path": "x"}, "Read x")
        step.status = StepStatus.FAILED

        recovery = planner.replan_on_failure(plan, step, "error")
        assert recovery is not None
        assert recovery.retry_count == 1

    def test_replan_on_failure_file_not_found(self, planner):
        plan = ExecutionPlan(task="test")
        step = plan.add_step("file_read", {"path": "missing.txt"}, "Read")
        step.status = StepStatus.FAILED
        step.retry_count = 3  # Exhausted retries

        recovery = planner.replan_on_failure(plan, step, "file not found")
        assert recovery is not None
        assert recovery.tool == "search"

#!/usr/bin/env python3
"""
Multi-Step Task Example for Agentic Code Executor

This example shows how the executor handles complex multi-step tasks
with tool use and state management.
"""

from agentic_executor import (
    AgenticExecutor,
    ExecutorConfig,
    Tool,
    ToolRegistry,
)


def create_custom_tools():
    """Create custom tools for the executor."""
    registry = ToolRegistry()

    # Calculator tool
    @registry.register("calculator")
    def calculator(expression: str) -> str:
        """Evaluate a mathematical expression."""
        try:
            result = eval(expression, {"__builtins__": {}}, {})
            return f"Result: {result}"
        except Exception as e:
            return f"Error: {e}"

    # Data fetcher tool (mock)
    @registry.register("fetch_data")
    def fetch_data(source: str) -> str:
        """Fetch data from a source (mock)."""
        mock_data = {
            "users": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25},
                {"name": "Charlie", "age": 35},
            ],
            "products": [
                {"name": "Widget", "price": 9.99},
                {"name": "Gadget", "price": 19.99},
            ],
        }
        return str(mock_data.get(source, "Source not found"))

    # File writer tool (mock)
    @registry.register("write_file")
    def write_file(filename: str, content: str) -> str:
        """Write content to a file (mock - just prints)."""
        print(f"[Mock] Writing to {filename}:")
        print(content[:100] + "..." if len(content) > 100 else content)
        return f"Successfully wrote {len(content)} chars to {filename}"

    return registry


def main():
    # Create executor with custom tools
    config = ExecutorConfig(
        max_iterations=15,
        timeout_seconds=60,
        enable_self_correction=True,
        verbose=True,
    )

    tools = create_custom_tools()
    executor = AgenticExecutor(config, tools=tools)

    # Complex multi-step task
    print("=" * 60)
    print("Multi-Step Data Processing Task")
    print("=" * 60)

    task = """
    Complete the following multi-step task:

    1. Use the fetch_data tool to get "users" data
    2. Filter users who are older than 28
    3. Calculate the average age of filtered users using calculator
    4. Format the results as a JSON report
    5. Use write_file to save the report to "report.json"

    Print a summary at the end.
    """

    result = executor.execute(task)

    print("\n" + "=" * 60)
    print("Execution Summary")
    print("=" * 60)
    print(f"Success: {result.success}")
    print(f"Total iterations: {result.iterations}")
    print(f"Tools used: {result.tools_used}")
    print(f"Final output:\n{result.output}")

    # Show execution trace
    if result.trace:
        print("\n" + "=" * 60)
        print("Execution Trace")
        print("=" * 60)
        for i, step in enumerate(result.trace, 1):
            print(f"\nStep {i}:")
            print(f"  Action: {step.action}")
            print(f"  Result: {step.result[:50]}..." if len(step.result) > 50 else f"  Result: {step.result}")


if __name__ == "__main__":
    main()

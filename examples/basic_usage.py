#!/usr/bin/env python3
"""
Basic Usage Example for Agentic Code Executor

This example demonstrates how to use the executor for simple code tasks.
"""

from agentic_executor import AgenticExecutor, ExecutorConfig

def main():
    # Create executor with default config
    config = ExecutorConfig(
        max_iterations=10,
        timeout_seconds=30,
        enable_self_correction=True,
    )
    executor = AgenticExecutor(config)

    # Example 1: Simple calculation
    print("=" * 50)
    print("Example 1: Simple Calculation")
    print("=" * 50)

    result = executor.execute("""
    Calculate the sum of squares from 1 to 10.
    Print the result.
    """)

    print(f"Success: {result.success}")
    print(f"Output: {result.output}")
    print(f"Iterations: {result.iterations}")

    # Example 2: Data processing
    print("\n" + "=" * 50)
    print("Example 2: Data Processing")
    print("=" * 50)

    result = executor.execute("""
    Create a list of the first 10 Fibonacci numbers.
    Then filter to keep only even numbers.
    Print the result.
    """)

    print(f"Success: {result.success}")
    print(f"Output: {result.output}")

    # Example 3: String manipulation
    print("\n" + "=" * 50)
    print("Example 3: String Manipulation")
    print("=" * 50)

    result = executor.execute("""
    Take the string "Hello, World!" and:
    1. Reverse it
    2. Convert to uppercase
    3. Count the vowels
    Print each step.
    """)

    print(f"Success: {result.success}")
    print(f"Output: {result.output}")

    # Example 4: Error recovery (self-correction)
    print("\n" + "=" * 50)
    print("Example 4: Error Recovery")
    print("=" * 50)

    result = executor.execute("""
    Try to calculate 10 / 0.
    If there's an error, handle it and return "Division by zero detected".
    """)

    print(f"Success: {result.success}")
    print(f"Output: {result.output}")
    print(f"Errors recovered: {len(result.errors)}")


if __name__ == "__main__":
    main()

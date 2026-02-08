#!/usr/bin/env python3
"""
Test Runner Example for Agentic Code Executor

This example demonstrates using the executor to write and run tests,
with automatic error recovery and test fixing.
"""

from agentic_executor import (
    AgenticExecutor,
    ExecutorConfig,
    TestRunner,
    CodeAnalyzer,
)


def main():
    print("=" * 60)
    print("Automated Test Writing and Running")
    print("=" * 60)

    # Configure for test-driven development
    config = ExecutorConfig(
        max_iterations=20,
        timeout_seconds=120,
        enable_self_correction=True,
        enable_test_runner=True,
        auto_fix_tests=True,
    )

    executor = AgenticExecutor(config)

    # Task: Write and test a function
    task = """
    Write a Python function called `is_palindrome` that:
    1. Takes a string as input
    2. Returns True if the string is a palindrome (ignoring case and spaces)
    3. Returns False otherwise

    Then write at least 5 test cases for this function:
    - Test with a simple palindrome like "racecar"
    - Test with a phrase like "A man a plan a canal Panama"
    - Test with a non-palindrome
    - Test with empty string
    - Test with single character

    Run all tests and ensure they pass.
    """

    result = executor.execute(task)

    print("\n" + "=" * 60)
    print("Results")
    print("=" * 60)
    print(f"Success: {result.success}")
    print(f"Tests passed: {result.tests_passed}/{result.tests_total}")
    print(f"Code generated:\n{result.generated_code}")

    # Example 2: Fix failing tests
    print("\n" + "=" * 60)
    print("Example 2: Fix Failing Tests")
    print("=" * 60)

    buggy_code = '''
def factorial(n):
    """Calculate factorial of n."""
    if n == 0:
        return 0  # Bug: should return 1
    return n * factorial(n - 1)

# Tests
assert factorial(0) == 1, "factorial(0) should be 1"
assert factorial(5) == 120, "factorial(5) should be 120"
'''

    fix_task = f"""
    The following code has a bug. Find and fix it, then verify all tests pass:

    ```python
    {buggy_code}
    ```
    """

    result = executor.execute(fix_task)

    print(f"Bug fixed: {result.success}")
    print(f"Fixed code:\n{result.generated_code}")

    # Example 3: Generate tests for existing code
    print("\n" + "=" * 60)
    print("Example 3: Generate Tests for Existing Code")
    print("=" * 60)

    existing_code = '''
def merge_sorted_lists(list1, list2):
    """Merge two sorted lists into one sorted list."""
    result = []
    i = j = 0
    while i < len(list1) and j < len(list2):
        if list1[i] <= list2[j]:
            result.append(list1[i])
            i += 1
        else:
            result.append(list2[j])
            j += 1
    result.extend(list1[i:])
    result.extend(list2[j:])
    return result
'''

    test_gen_task = f"""
    Generate comprehensive tests for this function:

    ```python
    {existing_code}
    ```

    Include edge cases like:
    - Empty lists
    - One empty, one non-empty
    - Lists with duplicates
    - Already merged list
    """

    result = executor.execute(test_gen_task)

    print(f"Tests generated: {result.success}")
    print(f"Number of tests: {result.tests_total}")


if __name__ == "__main__":
    main()

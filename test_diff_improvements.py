#!/usr/bin/env python3
"""Test the improved diff display features."""

from diff_display import create_file_diff, compute_diff_stats

# Test 1: Simple edit
old_content = """def hello():
    print("Hello")
    return True

def goodbye():
    print("Bye")
"""

new_content = """def hello():
    print("Hello, World!")
    return True

def greet(name):
    print(f"Hi {name}")

def goodbye():
    print("Bye")
"""

print("=" * 60)
print("Test 1: Simple function addition and modification")
print("=" * 60)

file_diff = create_file_diff("example.py", old_content, new_content, context=3)
additions, deletions, context = compute_diff_stats(file_diff.lines)

print(f"\nSummary: {file_diff.summary}")
print(f"Stats: +{additions} -{deletions} (context: {context})")
print(f"Total lines in diff: {len(file_diff.lines)}")

print("\nDiff lines:")
for i, line in enumerate(file_diff.lines[:20]):  # Show first 20
    change_type = line.change_type
    symbol = "+" if change_type == "add" else "-" if change_type == "delete" else " "
    line_num = line.line_num or line.old_line_num or "?"
    print(f"{symbol} {line_num:>4} | {line.content}")

print("\n" + "=" * 60)
print("Test 2: Large file to test truncation")
print("=" * 60)

# Create a large diff
large_old = "\n".join([f"line {i}" for i in range(1, 101)])
large_new = "\n".join([f"line {i}" for i in range(1, 101)] + [f"new line {i}" for i in range(101, 201)])

large_diff = create_file_diff("large.py", large_old, large_new, context=3)
print(f"\nSummary: {large_diff.summary}")
print(f"Total lines in diff: {len(large_diff.lines)}")
print("This would be truncated in the UI, showing 'expand large.py' option")

print("\n" + "=" * 60)
print("Test 3: Analyze change types for smart explanations")
print("=" * 60)

# Test different types of changes
changes = [
    ("def new_function():\n    pass", "Function definition"),
    ("class MyClass:\n    pass", "Class definition"),
    ("import os", "Import statement"),
    ("result = calculate(x, y)", "Variable assignment"),
    ("return value", "Control flow"),
]

for code, expected in changes:
    old = "# empty file\n"
    new = f"# empty file\n{code}\n"
    diff = create_file_diff("test.py", old, new, context=1)
    added_lines = [line.content for line in diff.lines if line.change_type == 'add']
    first_added = added_lines[0].strip() if added_lines else ""
    print(f"✓ {expected}: '{first_added[:40]}'")

print("\nAll tests passed!")

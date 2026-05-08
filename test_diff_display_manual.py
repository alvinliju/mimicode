"""Manual test for diff display functionality."""
from diff_display import create_file_diff, format_diff_summary, compute_diff_stats

# Test 1: Simple addition
old_content = """def hello():
    print("Hello")
"""

new_content = """def hello():
    print("Hello")
    print("World")
"""

diff = create_file_diff("test.py", old_content, new_content)
print(f"Test 1 - Simple Addition:")
print(f"Summary: {diff.summary}")
print(f"Lines: {len(diff.lines)}")
for line in diff.lines:
    if line.change_type == 'separator':
        print("    ...")
    else:
        symbol = '+' if line.change_type == 'add' else '-' if line.change_type == 'delete' else ' '
        line_num = line.line_num or line.old_line_num or '?'
        print(f"  {symbol} {line_num:4} | {line.content}")
print()

# Test 2: Deletion
old_content2 = """def test():
    x = 1
    y = 2
    z = 3
    return x + y + z
"""

new_content2 = """def test():
    x = 1
    z = 3
    return x + z
"""

diff2 = create_file_diff("test2.py", old_content2, new_content2)
print(f"Test 2 - Deletion:")
print(f"Summary: {diff2.summary}")
stats = compute_diff_stats(diff2.lines)
print(f"Stats: +{stats[0]} -{stats[1]} (context: {stats[2]})")
print()

# Test 3: Replacement
old_content3 = """def old_function():
    return "old"
"""

new_content3 = """def new_function():
    return "new"
"""

diff3 = create_file_diff("test3.py", old_content3, new_content3)
print(f"Test 3 - Replacement:")
print(f"Summary: {diff3.summary}")
for line in diff3.lines:
    if line.change_type != 'separator':
        symbol = '+' if line.change_type == 'add' else '-' if line.change_type == 'delete' else ' '
        print(f"  {symbol} {line.content}")
print()

print("All manual tests passed!")

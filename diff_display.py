"""Real-time diff generation and display for code changes."""
import difflib
from typing import NamedTuple


class DiffLine(NamedTuple):
    """A single line in a diff with its metadata."""
    line_num: int | None  # None for context lines that don't map to new file
    old_line_num: int | None  # None for added lines
    change_type: str  # 'add', 'delete', 'context'
    content: str


class FileDiff(NamedTuple):
    """Complete diff information for a file."""
    path: str
    lines: list[DiffLine]
    summary: str  # e.g., "+5 -3 lines"


def generate_unified_diff(old_content: str, new_content: str, path: str = "file") -> list[str]:
    """Generate unified diff format between old and new content."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm=""
    )
    
    return list(diff)


def parse_diff_lines(old_content: str, new_content: str) -> list[DiffLine]:
    """Parse content changes into structured diff lines."""
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    
    diff_lines: list[DiffLine] = []
    
    # Use SequenceMatcher for more detailed line-by-line comparison
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            # Context lines (unchanged)
            for i, line in enumerate(old_lines[i1:i2]):
                diff_lines.append(DiffLine(
                    line_num=j1 + i + 1,
                    old_line_num=i1 + i + 1,
                    change_type='context',
                    content=line
                ))
        elif tag == 'delete':
            # Deleted lines
            for i, line in enumerate(old_lines[i1:i2]):
                diff_lines.append(DiffLine(
                    line_num=None,
                    old_line_num=i1 + i + 1,
                    change_type='delete',
                    content=line
                ))
        elif tag == 'insert':
            # Added lines
            for i, line in enumerate(new_lines[j1:j2]):
                diff_lines.append(DiffLine(
                    line_num=j1 + i + 1,
                    old_line_num=None,
                    change_type='add',
                    content=line
                ))
        elif tag == 'replace':
            # Replaced lines (show as delete + insert)
            for i, line in enumerate(old_lines[i1:i2]):
                diff_lines.append(DiffLine(
                    line_num=None,
                    old_line_num=i1 + i + 1,
                    change_type='delete',
                    content=line
                ))
            for i, line in enumerate(new_lines[j1:j2]):
                diff_lines.append(DiffLine(
                    line_num=j1 + i + 1,
                    old_line_num=None,
                    change_type='add',
                    content=line
                ))
    
    return diff_lines


def extract_context_diff(diff_lines: list[DiffLine], context: int = 3) -> list[DiffLine]:
    """Extract only changed lines with surrounding context."""
    if not diff_lines:
        return []
    
    # Find all changed line indices
    changed_indices = {i for i, line in enumerate(diff_lines) if line.change_type != 'context'}
    
    if not changed_indices:
        return diff_lines  # No changes, return all as context
    
    # Expand to include context
    to_include = set()
    for idx in changed_indices:
        for offset in range(-context, context + 1):
            target = idx + offset
            if 0 <= target < len(diff_lines):
                to_include.add(target)
    
    # Build result with range markers
    result: list[DiffLine] = []
    sorted_indices = sorted(to_include)
    
    last_idx = -2
    for idx in sorted_indices:
        # Add range separator if there's a gap
        if idx > last_idx + 1:
            result.append(DiffLine(
                line_num=None,
                old_line_num=None,
                change_type='separator',
                content='...'
            ))
        result.append(diff_lines[idx])
        last_idx = idx
    
    return result


def compute_diff_stats(diff_lines: list[DiffLine]) -> tuple[int, int, int]:
    """Compute statistics: (additions, deletions, context_lines)."""
    additions = sum(1 for line in diff_lines if line.change_type == 'add')
    deletions = sum(1 for line in diff_lines if line.change_type == 'delete')
    context = sum(1 for line in diff_lines if line.change_type == 'context')
    return additions, deletions, context


def format_diff_summary(additions: int, deletions: int) -> str:
    """Format a concise diff summary."""
    parts = []
    if additions:
        parts.append(f"+{additions}")
    if deletions:
        parts.append(f"-{deletions}")
    return " ".join(parts) if parts else "no changes"


def create_file_diff(path: str, old_content: str, new_content: str, context: int = 3) -> FileDiff:
    """Create a complete FileDiff with statistics and context."""
    diff_lines = parse_diff_lines(old_content, new_content)
    context_diff = extract_context_diff(diff_lines, context=context)
    additions, deletions, _ = compute_diff_stats(diff_lines)
    summary = format_diff_summary(additions, deletions)
    
    return FileDiff(
        path=path,
        lines=context_diff,
        summary=summary
    )


def analyze_edit_result(path: str, tool_result: str, old_content: str | None = None) -> FileDiff | None:
    """
    Analyze an edit tool result and generate diff.
    Returns None if unable to generate diff.
    """
    # For edit operations, we need to read the file content before and after
    # This will be called by the TUI when displaying edit results
    # The actual implementation will need to be integrated with the file reading logic
    return None


def analyze_write_result(path: str, content: str, is_new_file: bool = False) -> FileDiff:
    """
    Analyze a write tool result and generate diff.
    For new files, all lines are additions.
    """
    if is_new_file:
        lines = content.splitlines()
        diff_lines = [
            DiffLine(
                line_num=i + 1,
                old_line_num=None,
                change_type='add',
                content=line
            )
            for i, line in enumerate(lines)
        ]
        summary = f"+{len(lines)} lines (new file)"
    else:
        # For overwrite, we'd need the old content
        # This is a simplified version
        lines = content.splitlines()
        diff_lines = [
            DiffLine(
                line_num=i + 1,
                old_line_num=None,
                change_type='add',
                content=line
            )
            for i, line in enumerate(lines)
        ]
        summary = f"+{len(lines)} lines (overwrite)"
    
    return FileDiff(
        path=path,
        lines=diff_lines,
        summary=summary
    )

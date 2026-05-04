"""Simple intent-based model router.

Uses Haiku by default, switches to Sonnet only when needed.
The router asks Haiku itself to classify intent - simple and effective.
"""

from dataclasses import dataclass

# Anthropic model identifiers
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-5-20250929"


@dataclass
class ModelChoice:
    model: str
    reason: str
    guidance: str = ""


def parse_intent(messages: list[dict], step: int) -> ModelChoice:
    """
    Simple intent parser - checks task complexity.
    
    Haiku handles:
    - Simple reads, searches, greps
    - Single-file edits
    - Running tests/commands
    - Straightforward code changes
    
    Sonnet handles:
    - Complex planning and architecture
    - Multi-file refactoring
    - Debugging tricky issues
    - First turn (to understand the full request)
    """
    
    # First turn: use Sonnet to understand the request properly
    if step == 0:
        return ModelChoice(model=SONNET, reason="first_turn")
    
    # Get the last user message
    user_msg = None
    for msg in reversed(messages):
        if msg["role"] == "user":
            user_msg = msg
            break
    
    if not user_msg:
        return ModelChoice(model=HAIKU, reason="fallback")
    
    # Extract text content
    content = user_msg.get("content", "")
    if isinstance(content, list):
        # Could be tool results or mixed content
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    # Tool result - probably debugging, check for errors
                    if block.get("is_error"):
                        return ModelChoice(model=SONNET, reason="debugging_error")
            elif isinstance(block, str):
                text_parts.append(block)
        content = " ".join(text_parts)
    
    if not content or not isinstance(content, str):
        return ModelChoice(model=HAIKU, reason="empty_content")
    
    content_lower = content.lower()
    
    # Complex planning/architecture → Sonnet
    if any(word in content_lower for word in [
        "architecture", "design pattern", "best approach", "should i",
        "strategy", "how to structure", "overall plan"
    ]):
        return ModelChoice(model=SONNET, reason="planning")

    # Multi-file operations → Sonnet
    if any(phrase in content_lower for phrase in [
        "all files", "every file", "across files", "multiple files",
        "entire codebase", "project-wide", "refactor all", "rename everywhere"
    ]):
        return ModelChoice(model=SONNET, reason="multi_file")

    # Debugging / broken behavior → Sonnet
    if any(phrase in content_lower for phrase in [
        "not working", "doesn't work", "does not work", "broken", "bug",
        "debug", "why does", "why is", "why isn't", "why doesn't",
        "error", "fail", "crash", "stall", "stuck", "wrong",
        "issue", "problem", "investigate", "diagnose",
    ]):
        return ModelChoice(model=SONNET, reason="debugging")
    
    # Simple operations → Haiku with guidance
    
    # Running commands (check BEFORE search since "run" is more specific)
    if any(word in content_lower for word in [
        "run", "execute", "pytest", "python "
    ]) or (any(word in content_lower for word in ["test"]) and "run" not in content_lower):
        return ModelChoice(
            model=HAIKU,
            reason="simple_bash",
            guidance="Execute commands directly. Show output clearly."
        )
    
    # Searching/reading
    if any(word in content_lower for word in [
        "find", "search", "where", "show me", "list", "grep", "look for"
    ]):
        return ModelChoice(
            model=HAIKU,
            reason="simple_search",
            guidance="Use `rg` for all searches. Be precise with file:line citations."
        )
    
    # Reading code
    if any(word in content_lower for word in [
        "read", "check", "what does", "what is", "how does"
    ]):
        return ModelChoice(
            model=HAIKU,
            reason="simple_read",
            guidance="Read files systematically. Quote relevant sections."
        )
    
    # Single-file edits
    if any(word in content_lower for word in [
        "change", "fix", "update", "modify", "edit", "replace"
    ]) and any(indicator in content_lower for indicator in [
        ".py", ".js", ".ts", ".go", ".java", ".rb", ".md", ".txt",
        "in file", "in the file", "single file", "one file", "this file"
    ]):
        return ModelChoice(
            model=HAIKU,
            reason="simple_edit",
            guidance=(
                "Read before editing. Use exact old_text with 2-3 lines context. "
                "For multiple changes to one file, use batched edits=[...]."
            )
        )
    
    # Default to Sonnet — ambiguous prompts need reasoning, not speed
    return ModelChoice(model=SONNET, reason="default")


def route_model(
    messages: list[dict],
    step: int,
    last_tool_uses: list[dict] | None = None,
) -> ModelChoice:
    """
    Route to appropriate model based on intent.
    Uses Haiku by default, Sonnet only when necessary.
    """
    choice = parse_intent(messages, step)
    
    # Override: if last tool use had errors, use Sonnet for debugging
    if last_tool_uses:
        for tu in last_tool_uses:
            # Note: tool_uses don't have is_error, that's in tool_results
            # We check this in parse_intent by looking at user messages
            pass
    
    return choice


def augment_system_prompt(base_system: str, guidance: str) -> str:
    """Add task-specific guidance to system prompt."""
    if not guidance:
        return base_system
    return f"{base_system}\n\n**TASK GUIDANCE:**\n{guidance}"


def route_turn(user_text: str) -> ModelChoice:
    """Choose ONE model + guidance for the entire turn.

    Why this exists: the original `route_model` re-decides each step, which
    flips the model (and thus the prompt-cache namespace) mid-turn — every
    subsequent step pays full input price instead of cached. Pinning per
    turn restores caching and produces an auditable, stable system prompt.

    Logic: run the same intent detector as parse_intent against the user's
    original message, but skip the step==0 always-Sonnet rule (which only
    existed to give the first call a stronger model). For an intent-routed
    turn we trust the intent classification end-to-end.
    """
    msgs = [{"role": "user", "content": user_text}]
    return parse_intent(msgs, step=1)

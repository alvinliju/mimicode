"""Tests for smart model routing."""
import pytest

from router import (
    HAIKU,
    SONNET,
    ModelChoice,
    augment_system_prompt,
    parse_intent,
    route_model,
    route_turn,
)


class TestParseIntent:
    """Test routing logic for different task types."""

    def test_first_turn_uses_sonnet(self):
        """First turn should always use Sonnet for planning."""
        messages = [{"role": "user", "content": "Hello"}]
        choice = parse_intent(messages, step=0)
        assert choice.model == SONNET
        assert choice.reason == "first_turn"

    def test_multi_file_keywords_use_sonnet(self):
        """Multi-file refactors should use Sonnet."""
        messages = [
            {"role": "user", "content": "Rename foo to bar in all files"}
        ]
        choice = parse_intent(messages, step=1)
        assert choice.model == SONNET
        assert choice.reason == "multi_file"

    def test_planning_keywords_use_sonnet(self):
        """Planning tasks should use Sonnet."""
        messages = [
            {"role": "user", "content": "What's the best approach to refactor this?"}
        ]
        choice = parse_intent(messages, step=1)
        assert choice.model == SONNET
        assert choice.reason == "planning"

    def test_read_only_uses_haiku(self):
        """Read-only operations should use Haiku."""
        messages = [
            {"role": "user", "content": "Where is the bash function defined?"}
        ]
        choice = parse_intent(messages, step=1)
        assert choice.model == HAIKU
        assert choice.reason == "simple_search"
        assert "rg" in choice.guidance.lower()

    def test_single_file_edit_uses_haiku(self):
        """Simple single-file edits should use Haiku with guidance."""
        messages = [
            {"role": "user", "content": "Change VERSION to 0.2 in config.py"}
        ]
        choice = parse_intent(messages, step=1)
        assert choice.model == HAIKU
        assert choice.reason == "simple_edit"
        assert "read" in choice.guidance.lower()
        assert "old_text" in choice.guidance.lower()

    def test_bash_command_uses_haiku(self):
        """Running tests/commands should use Haiku."""
        messages = [
            {"role": "user", "content": "Run pytest and show me the results"}
        ]
        choice = parse_intent(messages, step=1)
        assert choice.model == HAIKU
        assert choice.reason == "simple_bash"
        assert choice.guidance  # Should have some guidance

    def test_debugging_error_uses_sonnet(self):
        """Debugging after tool errors should use Sonnet."""
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "is_error": True,
                        "content": "Error: file not found"
                    }
                ]
            }
        ]
        choice = parse_intent(messages, step=2)
        assert choice.model == SONNET
        assert choice.reason == "debugging_error"

    def test_rename_without_file_context_uses_haiku_default(self):
        """Rename without multi-file context uses Haiku default."""
        messages = [
            {"role": "user", "content": "Rename function foo to bar"}
        ]
        choice = parse_intent(messages, step=1)
        # Should default to Haiku since no multi-file indicator
        assert choice.model == HAIKU
        assert choice.reason == "default"

    def test_list_content_in_message(self):
        """Handle messages with list content."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Where is the bash function?"}
                ],
            }
        ]
        choice = parse_intent(messages, step=1)
        assert choice.model == HAIKU
        assert choice.reason == "simple_search"


class TestRouteModel:
    """Test the main route_model function."""

    def test_returns_model_choice(self):
        """route_model should return ModelChoice dataclass."""
        messages = [{"role": "user", "content": "Hello"}]
        choice = route_model(messages, step=0)
        assert isinstance(choice, ModelChoice)
        assert choice.model == SONNET
        assert choice.reason == "first_turn"
        assert choice.guidance == ""

    def test_includes_guidance_for_haiku(self):
        """Haiku tasks should include guidance."""
        messages = [
            {"role": "user", "content": "Change VERSION in config.py"}
        ]
        choice = route_model(messages, step=1)
        assert choice.model == HAIKU
        assert choice.reason == "simple_edit"
        assert len(choice.guidance) > 0


class TestAugmentSystemPrompt:
    """Test system prompt augmentation."""

    def test_no_guidance_returns_unchanged(self):
        """If no guidance, return base system prompt."""
        base = "You are a coding agent."
        result = augment_system_prompt(base, "")
        assert result == base

    def test_adds_guidance_section(self):
        """Should add TASK GUIDANCE section."""
        base = "You are a coding agent."
        guidance = "Use rg for searches."
        result = augment_system_prompt(base, guidance)
        assert base in result
        assert "TASK GUIDANCE" in result
        assert guidance in result
        assert result.startswith(base)


class TestEdgeCases:
    """Test edge cases and fallbacks."""

    def test_empty_messages_uses_haiku(self):
        """Empty messages should fall back to Haiku."""
        messages = []
        choice = parse_intent(messages, step=1)
        assert choice.model == HAIKU
        assert choice.reason == "fallback"

    def test_no_user_message_uses_haiku(self):
        """If no user message found, fall back to Haiku."""
        messages = [
            {"role": "assistant", "content": "I did something"}
        ]
        choice = parse_intent(messages, step=1)
        assert choice.model == HAIKU
        assert choice.reason == "fallback"

    def test_ambiguous_task_uses_haiku_default(self):
        """Ambiguous tasks without clear keywords use Haiku default (it's capable!)."""
        messages = [
            {"role": "user", "content": "Do something here"}
        ]
        choice = parse_intent(messages, step=1)
        assert choice.model == HAIKU
        assert choice.reason == "default"


class TestRouteTurn:
    """route_turn pins the route for the whole turn (cache stability)."""

    def test_simple_edit_pins_to_haiku(self):
        choice = route_turn("Change VERSION in config.py to 0.2")
        assert choice.model == HAIKU
        assert choice.reason == "simple_edit"
        assert choice.guidance  # non-empty

    def test_simple_search_pins_to_haiku(self):
        choice = route_turn("Where is the bash function defined in this repo?")
        assert choice.model == HAIKU
        assert "search" in choice.reason or choice.reason == "default"

    def test_multi_file_pins_to_sonnet(self):
        choice = route_turn("Rename foo to bar across all files in the project")
        assert choice.model == SONNET
        assert choice.reason == "multi_file"

    def test_planning_pins_to_sonnet(self):
        choice = route_turn("What is the best approach to refactor this codebase?")
        assert choice.model == SONNET
        assert choice.reason == "planning"

    def test_skips_first_turn_sonnet_rule(self):
        # parse_intent(step=0) returns Sonnet "first_turn"; route_turn must NOT.
        # A simple edit prompt should pin to Haiku, not Sonnet.
        choice = route_turn("Bump VERSION in config.py to 0.2")
        assert choice.reason != "first_turn"
        assert choice.model == HAIKU

    def test_returns_model_choice(self):
        choice = route_turn("Hello")
        assert isinstance(choice, ModelChoice)

    def test_stable_for_same_input(self):
        # Determinism is the whole point — same input = same route every call.
        a = route_turn("Edit helpers.py and rename foo to bar")
        b = route_turn("Edit helpers.py and rename foo to bar")
        assert a.model == b.model
        assert a.reason == b.reason
        assert a.guidance == b.guidance

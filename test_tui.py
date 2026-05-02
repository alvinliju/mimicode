"""Basic tests for TUI module."""
import pytest
from unittest.mock import Mock, patch
from pathlib import Path


def test_tui_imports():
    """Test that TUI module can be imported."""
    try:
        import tui
        assert hasattr(tui, 'MimicodeApp')
        assert hasattr(tui, 'main')
    except ImportError as e:
        pytest.skip(f"Textual not installed: {e}")


def test_tui_app_initialization():
    """Test that TUI app can be initialized."""
    try:
        from tui import MimicodeApp
        
        with patch('tui.start_session') as mock_session:
            mock_session.return_value = Mock(
                id='test123',
                path=Path('sessions/test123.jsonl')
            )
            with patch('tui.load_messages', return_value=[]):
                app = MimicodeApp(session_id='test123')
                assert app.session.id == 'test123'
                assert app.messages == []
                assert app.is_processing == False
                
    except ImportError as e:
        pytest.skip(f"Textual not installed: {e}")


def test_message_box_widget():
    """Test MessageBox widget."""
    try:
        from tui import MessageBox
        
        msg_box = MessageBox("Test message")
        assert msg_box.renderable == "Test message"
        
    except ImportError as e:
        pytest.skip(f"Textual not installed: {e}")


def test_thinking_indicator():
    """Test ThinkingIndicator widget."""
    try:
        from tui import ThinkingIndicator
        
        indicator = ThinkingIndicator()
        assert "thinking" in str(indicator.renderable).lower()
        
    except ImportError as e:
        pytest.skip(f"Textual not installed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

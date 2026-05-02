"""Test that interrupt properly cancels streaming API calls."""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_streaming_respects_cancellation():
    """Verify that cancelling a task stops the streaming loop."""
    from providers import call_claude_streaming
    
    # Create a mock stream that yields events indefinitely
    mock_events = []
    
    # First event: content_block_start
    start_event = MagicMock()
    start_event.type = "content_block_start"
    start_event.index = 0
    start_event.content_block = MagicMock()
    start_event.content_block.type = "text"
    mock_events.append(start_event)
    
    # Then many delta events
    for i in range(100):  # Simulate a long response
        event = MagicMock()
        event.type = "content_block_delta"
        event.index = 0
        event.delta = MagicMock()
        event.delta.type = "text_delta"
        event.delta.text = f"word{i} "
        mock_events.append(event)
    
    # Add a final message_stop event
    stop_event = MagicMock()
    stop_event.type = "message_stop"
    mock_events.append(stop_event)
    
    async def event_generator():
        for event in mock_events:
            await asyncio.sleep(0.01)  # Small delay per event
            yield event
    
    mock_stream = AsyncMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aexit__ = AsyncMock(return_value=None)
    mock_stream.__aiter__ = lambda self: event_generator()
    
    final_message = MagicMock()
    final_message.usage.input_tokens = 100
    final_message.usage.output_tokens = 50
    final_message.usage.cache_read_input_tokens = 0
    final_message.usage.cache_creation_input_tokens = 0
    mock_stream.get_final_message = AsyncMock(return_value=final_message)
    
    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream)
    
    # Track how many events we processed
    events_seen = []
    
    async def track_event(event_type, data):
        events_seen.append(event_type)
        await asyncio.sleep(0)
    
    # Start streaming in a task
    task = asyncio.create_task(
        call_claude_streaming(
            messages=[{"role": "user", "content": "test"}],
            client=mock_client,
            on_event=track_event,
            cache=False,
        )
    )
    
    # Let it process a few events
    await asyncio.sleep(0.05)
    
    # Cancel the task
    task.cancel()
    
    # Wait for cancellation to propagate
    with pytest.raises(asyncio.CancelledError):
        await task
    
    # Should have processed some but not all events
    assert len(events_seen) > 0
    assert len(events_seen) < len(mock_events), "Should have cancelled before processing all events"
    print(f"Processed {len(events_seen)} events before cancellation (out of {len(mock_events)} total)")


@pytest.mark.asyncio 
async def test_tui_interrupt_clears_buffers():
    """Verify that TUI interrupt clears streaming buffers and stops rendering."""
    from tui import MimicodeApp
    
    # This is more of an integration test - just verify the flag logic
    app = MimicodeApp(session_id=None)
    
    # Simulate streaming state
    app._current_text_blocks = {0: "some text"}
    app._current_tool_blocks = {0: {"name": "bash", "input": {}}}
    app.is_cancelled = False
    
    # Simulate a stream event before cancellation
    await app._handle_stream_event("text_delta", {"index": 0, "text": " more"})
    assert app._current_text_blocks[0] == "some text more"
    
    # Cancel
    app.is_cancelled = True
    
    # Further events should be ignored
    await app._handle_stream_event("text_delta", {"index": 0, "text": " ignored"})
    assert app._current_text_blocks[0] == "some text more"  # Unchanged
    
    print("[OK] TUI properly ignores events after cancellation")


if __name__ == "__main__":
    asyncio.run(test_streaming_respects_cancellation())
    asyncio.run(test_tui_interrupt_clears_buffers())
    print("\n[OK] All interrupt tests passed!")

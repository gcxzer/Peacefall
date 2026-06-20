from __future__ import annotations

"""Utilities for composing message log listeners."""

from typing import Callable

from engine.message_log import MessageLogEntry


def combine_message_listeners(
    *listeners: Callable[[MessageLogEntry], None] | None,
) -> Callable[[MessageLogEntry], None] | None:
    """Combine optional message listeners while preserving streaming support."""

    active = [listener for listener in listeners if listener is not None]
    if not active:
        return None
    if len(active) == 1:
        return active[0]

    def combined(entry: MessageLogEntry) -> None:
        for listener in active:
            listener(entry)

    combined.stream_model_output = any(  # type: ignore[attr-defined]
        getattr(listener, "stream_model_output", False)
        for listener in active
    )
    return combined

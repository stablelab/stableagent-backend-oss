from __future__ import annotations

from typing import Callable, Dict, Any, Optional
import contextvars
import threading

# Simple tool event bus that tools can call into while executing.
# The router sets the emitter per-request; tools call emit_tool_event.

_current_emitter: contextvars.ContextVar[Optional[Callable[[str, Dict[str, Any]], None]]] = contextvars.ContextVar(
    "tool_event_emitter", default=None
)
_tls = threading.local()
_global_emitter: Optional[Callable[[str, Dict[str, Any]], None]] = None


def set_tool_event_emitter(emitter: Callable[[str, Dict[str, Any]], None]):
    try:
        _tls.emitter = emitter
    except Exception:
        pass
    try:
        global _global_emitter
        _global_emitter = emitter
    except Exception:
        pass
    return _current_emitter.set(emitter)


def reset_tool_event_emitter(token) -> None:
    try:
        _current_emitter.reset(token)
    except Exception:
        pass
    try:
        _tls.emitter = None
    except Exception:
        pass
    try:
        global _global_emitter
        _global_emitter = None
    except Exception:
        pass


def emit_tool_event(name: str, payload: Dict[str, Any]) -> None:
    try:
        emitter = _current_emitter.get()
        if not callable(emitter):
            emitter = getattr(_tls, "emitter", None)
        if not callable(emitter):
            # cross-thread fallback
            emitter = _global_emitter
        if callable(emitter):
            emitter(name, payload or {})
    except Exception:
        # Never raise from tool event emission
        pass



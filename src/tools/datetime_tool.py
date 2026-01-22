from __future__ import annotations

from typing import Optional, Type
from pydantic import BaseModel, Field

from langchain_core.tools import BaseTool
from src.utils.tool_events import emit_tool_event
import time

from datetime import datetime, timezone as dt_timezone
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover - narrow fallback
    ZoneInfo = None  # type: ignore


class DateTimeInput(BaseModel):
    timezone: Optional[str] = Field(
        default="UTC",
        description="Optional IANA timezone (e.g., 'UTC', 'America/New_York'). Defaults to UTC.",
    )
    format: Optional[str] = Field(
        default=None,
        description=(
            "Optional strftime format string. If omitted, returns ISO 8601 (e.g., 2025-01-31T10:15:30Z for UTC)."
        ),
    )


class CurrentDateTimeTool(BaseTool):
    name: str = "current_datetime_tool"
    description: str = (
        "Return the current date and time. Defaults to ISO 8601 in UTC, or use a provided timezone and format."
    )
    args_schema: Type[BaseModel] = DateTimeInput

    def _run(self, tz_name: Optional[str] = "UTC", format: Optional[str] = None, timezone: Optional[str] = None, **kwargs) -> str:  # type: ignore[override]
        """Return the current datetime as a string.

        Note: parameter name `tz_name` avoids shadowing `datetime.timezone`.
        """
        start_ts = time.time()
        try:
            emit_tool_event("current_datetime.input", {"timezone": tz_name or timezone, "format": format})
            emit_tool_event("tool.start", {"tool": self.name, "input": {"timezone": tz_name or timezone, "format": format}})
        except Exception:
            pass
        # Accept either tz_name or legacy 'timezone' kwarg
        tz_input = tz_name or timezone or "UTC"
        tz = None
        if tz_input and ZoneInfo is not None:
            try:
                tz = ZoneInfo(tz_input)
            except Exception:
                tz = None
        if tz is None:
            tz = timezone_from_string(tz_input)

        now = datetime.now(tz)
        if format:
            try:
                out = now.strftime(format)
                try:
                    emit_tool_event("current_datetime.output", {"timezone": tz_input, "format": format, "value": out})
                    emit_tool_event("tool.end", {"tool": self.name, "status": "ok", "duration_ms": int((time.time() - start_ts) * 1000)})
                except Exception:
                    pass
                return out
            except Exception:
                try:
                    emit_tool_event("current_datetime.error", {"message": "invalid format", "format": format})
                    emit_tool_event("tool.end", {"tool": getattr(self, 'name', 'current_datetime_tool'), "status": "error", "error": "invalid format"})
                except Exception:
                    pass
        # Default ISO 8601; normalize trailing 'Z' for UTC
        iso = now.isoformat()
        if now.utcoffset() == datetime.now(dt_timezone.utc).utcoffset():
            # If effectively UTC, prefer 'Z' suffix for clarity
            if iso.endswith("+00:00"):
                iso = iso[:-6] + "Z"
        try:
            emit_tool_event("current_datetime.output", {"timezone": tz_input, "format": None, "value": iso})
            emit_tool_event("tool.end", {"tool": self.name, "status": "ok", "duration_ms": int((time.time() - start_ts) * 1000)})
        except Exception:
            pass
        return iso

    async def _arun(self, **kwargs) -> str:  # type: ignore[override]
        return self._run(**kwargs)


def timezone_from_string(tz_name: Optional[str]):
    """Fallback timezone resolution when ZoneInfo is unavailable or tz lookup fails."""
    # Minimal fallback: support UTC only
    return dt_timezone.utc



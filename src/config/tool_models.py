"""
Per-tool LLM provider/model overrides.

Edit this mapping to customize which model each tool uses.

Keys should match the tool's `name` attribute (e.g., "sql_query_tool").

Supported providers: "vertex_ai" (Gemini), "openai". If a tool key is not
present here, the system defaults will be used (see `src/llm/factory.py`).

Examples:

TOOL_MODEL_OVERRIDES = TOOL_MODEL_OVERRIDES = {
    "context_expander_tool": {"provider": "vertex_ai", "model": "gemini-3-flash-preview"},
    "sql_query_tool": {"provider": "openai", "model": "gpt-4o-mini"},
    "sql_repair_tool": {"provider": "openai", "model": "gpt-4o-mini"},
    # Optional extras (not agent tools):
    # "web_search_summarizer": {"provider": "openai", "model": "gpt-4o-mini"},
}
"""

from typing import Dict, Any


# Keep the default mapping empty; users can fill it in.
TOOL_MODEL_OVERRIDES: Dict[str, Dict[str, Any]] = {
    # You can also specify "temperature": 1.0 for providers that accept non-default temperatures.
    # Some models accept only temperature=1.0. If unsure, omit to use provider default.
    "context_expander_tool": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 1.0},
    "sql_query_tool": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 1.0},
    # Internal-only tool (removed from public agent toolset). Still used by the system for auto-repair.
    "sql_repair_tool": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 1.0, "reasoning_effort": "medium"},
    "web_search_summarizer": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 1.0},
}



"""Define the state structures for the agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from src.forse_analyze_agent.tools.cgl_types import DaoSpace

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from langgraph.managed import IsLastStep
from typing_extensions import Annotated


@dataclass
class InputState:
    """Defines the input state for the agent, representing a narrower interface to the outside world.

    This class is used to define the initial state and structure of incoming data.
    """

    messages: Annotated[Sequence[AnyMessage], add_messages] = field(
        default_factory=list
    )
    """
    Messages tracking the primary execution state of the agent.

    Typically accumulates a pattern of:
    1. HumanMessage - user input
    2. AIMessage with .tool_calls - agent picking tool(s) to use to collect information
    3. ToolMessage(s) - the responses (or errors) from the executed tools
    4. AIMessage without .tool_calls - agent responding in unstructured format to the user
    5. HumanMessage - user responds with the next conversational turn

    Steps 2-5 may repeat as needed.

    The `add_messages` annotation ensures that new messages are merged with existing ones,
    updating by ID to maintain an "append-only" state unless a message with the same ID is provided.
    """

    # graph generation use this
    # https://docs.langchain.com/langsmith/generative-ui-react#src%2Fagent%2Fui-tsx
    # ui: Annotated[Sequence[AnyUIMessage], ui_message_reducer] = field(default_factory=list)


@dataclass
class State(InputState):
    """Represents the complete state of the agent, extending InputState with additional attributes.

    This class can be used to store any information needed throughout the agent's lifecycle.
    """

    is_last_step: IsLastStep = field(default=False)
    """
    Indicates whether the current step is the last one before the graph raises an error.

    This is a 'managed' variable, controlled by the state machine rather than user code.
    It is set to 'True' when the step count reaches recursion_limit - 1.
    """

    dashboard_id: Optional[str] = field(default=None)
    """
    The unique identifier of the dashboard being analyzed.
    
    Set during step 1 (Dashboard Identification) when the user selects a dashboard.
    Used in step 2 to fetch graphs for the dashboard.
    """

    graph_id: Optional[str] = field(default=None)
    """
    The unique identifier of the graph/chart being analyzed.
    
    Set during step 2 (Graph Metadata Extraction) or step 3 (Chart Selection).
    Used in step 3 to fetch graph configuration and step 4 to fetch graph data.
    """

    category_ids: List[str] = field(default_factory=list)
    """
    List of category IDs to analyze for the current graph.
    
    A graph can have multiple categories (e.g., TVL, Users, etc.), and this list
    tracks which categories need to be analyzed. For full analysis, all categories
    from the graph metadata should be included here.
    
    Used in step 4 to fetch data for each category via step_4_graph_data_by_id_and_category_id.
    """

    analysis_mode: Optional[str] = field(default=None)
    """
    The analysis mode: 'dashboard' for full dashboard analysis, 
    'graph' for single graph analysis, None for auto-detect.
    """
    
    dashboard_context: Optional[dict] = field(default=None)
    """
    Cached dashboard overview data for holistic analysis.
    Contains: total_graphs, graph_summaries, etc.
    """
    
    user_analysis_prompt: Optional[str] = field(default=None)
    """
    User's specific analysis request. If set, overrides system analysis prompts.
    Example: "Compare TVL trends across all protocols" or "Find anomalies in the data"
    """

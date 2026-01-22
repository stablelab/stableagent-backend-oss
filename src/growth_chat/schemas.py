"""
Type definitions for Growth Chat Super Graph.

Defines the unified state for routing between knowledge_hub_agent and app_automation_agent.
"""
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field


class AgentType(Enum):
    """Available agent types in the Growth Chat system."""
    ONBOARDING = "onboarding"
    KNOWLEDGE_HUB = "knowledge_hub"
    APP_AUTOMATION = "app_automation"
    CONVERSATION = "conversation"
    FORSE_ANALYZER = "forse_analyzer"
    RESEARCH = "research"


# Mapping from agent type string to AgentType enum
AGENT_TYPE_MAP: Dict[str, AgentType] = {
    "onboarding": AgentType.ONBOARDING,
    "knowledge_hub": AgentType.KNOWLEDGE_HUB,
    "app_automation": AgentType.APP_AUTOMATION,
    "conversation": AgentType.CONVERSATION,
    "forse_analyzer": AgentType.FORSE_ANALYZER,
    "research": AgentType.RESEARCH,
}

class PlanStepOutput(BaseModel):
    """A single step in the planner output."""
    agent: str = Field(
        description="The agent to use for this step. Must be one of: onboarding, knowledge_hub, app_automation, conversation, forse_analyzer, research"
    )
    task: str = Field(
        description="Brief description of what this step should accomplish"
    )


class PlanOutput(BaseModel):
    """Structured output for planner."""
    steps: List[PlanStepOutput] = Field(
        default_factory=list,
        description="List of plan steps to execute in order"
    )


class SuggestedQueriesOutput(BaseModel):
    """Structured output for suggested follow-up queries."""
    suggested_queries: List[str] = Field(
        default_factory=list,
        description="List of suggested follow-up questions or actions the user might want to ask/take next",
        max_length=3
    )


class UserInfo(TypedDict, total=False):
    """User information extracted from Growth Backend."""
    id: int
    handle: str
    email: str
    display_name: str
    org_slug: str
    is_global_admin: bool


class PlanStep(TypedDict):
    """A single step in the execution plan."""
    agent_type: str  # AgentType value as string (e.g., "research", "app_automation")
    task_description: str  # Brief description of what this step should accomplish


class AttachedFile(BaseModel):
    """
    Metadata for a file attached to a chat message.
    
    Files are stored in GCS and accessed directly by the agent using service account credentials.
    
    Attributes:
        id: Database file ID
        filename: Original filename
        mime_type: File MIME type
        gcs_bucket: GCS bucket name
        gcs_path: Full path within bucket
        size_bytes: File size in bytes
    """
    id: int = Field(..., description="Database file ID")
    filename: str = Field(..., description="Original filename")
    mime_type: str = Field(..., description="File MIME type")
    gcs_bucket: str = Field(..., description="GCS bucket name")
    gcs_path: str = Field(..., description="Full path within bucket")
    size_bytes: int = Field(..., description="File size in bytes", gt=0)


class GrowthChatState(MessagesState):
    """
    State for Growth Chat super graph.
    
    Extends MessagesState with fields needed for routing and sub-agent execution.
    
    Attributes:
        org_id: Organization ID for Knowledge Hub queries
        org_schema: Resolved organization schema name
        which_agent: Current agent to execute (from plan)
        auth_token: Authentication token for API calls (grants_admin)
        rag_documents: Documents retrieved by knowledge_hub_agent
        rag_answer: Final answer from knowledge_hub_agent
        attached_files: Files attached to the current message
        plan: List of steps to execute
        current_step_index: Index of current step in plan
    """
    # Organization context
    org_id: int = 0
    org_schema: Optional[str] = None
    
    # Planner state
    plan: List[PlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    
    # Current agent to execute (set by planner/post_agent based on plan)
    which_agent: Optional[str] = None
    
    # Auth context for grants_admin
    auth_token: Optional[str] = None
    
    # RAG state (for knowledge_hub_agent results)
    rag_documents: List[Dict[str, Any]] = Field(default_factory=list)
    rag_quotes: List[str] = Field(default_factory=list)
    rag_synthesis: Optional[str] = None
    rag_answer: Optional[str] = None
    
    # Suggested follow-up queries
    suggested_queries: List[str] = Field(default_factory=list)
    
    # Attached files
    attached_files: List[AttachedFile] = Field(default_factory=list)


class GrowthChatRequest(BaseModel):
    """
    Request for Growth Chat query endpoint.
    
    Attributes:
        query: Natural language query
        conversation_id: Conversation ID for checkpointer
        org_id: Organization ID (required for Knowledge Hub queries)
        limit: Maximum documents to retrieve (Knowledge Hub)
        attached_files: Files attached to this message (stored in GCS)
    """
    query: str = Field(..., description="Natural language query", min_length=1)
    conversation_id: str = Field(..., description="Conversation ID for session tracking")
    org_id: int = Field(..., description="Organization ID", gt=0)
    limit: int = Field(default=5, ge=1, le=20, description="Max documents to retrieve")
    attached_files: List[AttachedFile] = Field(default_factory=list, description="Files attached to this message")


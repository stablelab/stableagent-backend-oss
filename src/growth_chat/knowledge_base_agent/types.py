"""
Type definitions for Knowledge Hub Agent.

Defines structured formats for Knowledge Hub query requests and responses,
including streaming RAG chatbot types.
"""
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class KnowledgeItem(BaseModel):
    """
    Individual knowledge item from search results.
    
    Attributes:
        id: Unique identifier for the knowledge item
        title: Title of the knowledge item
        content: Full content of the knowledge item
        source_type: Type of source (notion, clickup, confluence, etc.)
        source_item_id: Original item ID from the source system
        distance: Cosine distance (between 0 and 2, lower is more similar)
        metadata: Additional metadata from the source
        created_at: When the item was created
        last_synced_at: When the item was last synced
        visibility: Whether the item is public or org_only
    """
    id: int
    title: str
    content: str
    source_type: str
    source_item_id: str
    distance: float = Field(description="Cosine distance (between 0 and 2, lower is more similar)")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    last_synced_at: Optional[str] = None
    visibility: str
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            float: lambda v: round(v, 4)
        }


class KnowledgeQueryRequest(BaseModel):
    """
    Request to query the Knowledge Hub.
    
    Attributes:
        query: Natural language query to search for
        limit: Maximum number of results to return (default: 5, max: 20)
        org_id: Organization ID to query knowledge from
        stream: Enable streaming RAG chatbot mode (default: True)
    """
    query: str = Field(..., description="Natural language query", min_length=1)
    limit: int = Field(default=5, ge=1, le=20, description="Max results to return")
    org_id: int = Field(..., description="Organization ID (numeric)", gt=0)
    conversation_id: Optional[str] = Field(None, description="Conversation ID")
    stream: bool = Field(default=True, description="Enable streaming RAG")


class KnowledgeQueryResponse(BaseModel):
    """
    Response with relevant knowledge items from the Knowledge Hub.
    
    Attributes:
        query: Original query string
        items: List of relevant knowledge items ordered by relevance
        total_results: Total number of items returned
        org_schema: Organization schema used for the query
    """
    query: str
    items: List[KnowledgeItem]
    total_results: int
    org_schema: str
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            # Custom encoders if needed
        }


class ToolInvocationState(str, Enum):
    CALL = "call"
    PARTIAL_CALL = "partial-call"
    RESULT = "result"


class ToolInvocation(BaseModel):
    """
    Tool invocation payload (aligned with forse router format).
    """
    state: ToolInvocationState
    toolCallId: str
    toolName: str
    args: Optional[Any] = None
    result: Optional[Any] = None


class GrowthChatResult(BaseModel):
    """
    Streaming result for RAG chatbot responses.
    
    Emitted at each stage of the RAG workflow:
    - Stage 0 (routing): Router decision indicating which agent will handle the request
    - Stage 1 (documents): Retrieved knowledge items with similarity scores
    - Stage 2 (context): Extracted quotes and synthesized context
    - Stage 3 (answer): Final answer with inline references (from summarizer)
    - Stage 4 (tool_call): Tool call events
    - Stage 5 (suggested_queries): Suggested follow-up queries
    - Stage 6 (error): Error occurred during processing
    - Stage 7 (reconnecting): Connection lost, attempting reconnect
    
    Attributes:
        stage: Current stage of processing
        query: Original user query
        routed_agent: Name of agent the request was routed to (routing stage only)
        documents: Retrieved knowledge items (documents stage only)
        total_documents: Number of documents retrieved (documents stage only)
        extracted_quotes: Relevant quotes from documents (context stage only)
        context_synthesis: Synthesized context summary (context stage only)
        answer: Final answer to the query (answer stage only)
        tool_call: Tool call event data (tool_call stage only)
        tool_invocation: Tool invocation payload (router-compatible)
        suggested_queries: Suggested follow-up queries (suggested_queries stage only)
        org_schema: Organization schema used for query
        processing_time_ms: Total processing time in milliseconds (answer stage only)
        error_code: HTTP-like error code (error stage only)
        error_message: Human-readable error message (error stage only)
        retryable: Whether the error is retryable (error stage only)
        retry_after: Seconds to wait before retrying (error stage only)
    """
    stage: Literal["routing", "documents", "context", "answer", "tool_call", "suggested_queries", "error", "reconnecting"]
    query: str
    
    # Stage 0: Routing
    routed_agent: Optional[str] = None
    
    # Stage 1: Documents
    documents: Optional[List[KnowledgeItem]] = None
    total_documents: Optional[int] = None
    
    # Stage 2: Context extraction
    extracted_quotes: Optional[List[str]] = None
    context_synthesis: Optional[str] = None
    
    # Stage 3: Final answer
    answer: Optional[str] = None
    
    # Stage 4: Tool invocation
    tool_invocation: Optional[ToolInvocation] = None
    
    # Stage 5: Suggested follow-up queries
    suggested_queries: Optional[List[str]] = None

    # Stage 6: Error handling
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    retryable: Optional[bool] = None
    retry_after: Optional[float] = None  # Seconds to wait before retry
    
    # Stage 7: Reconnecting (informational)
    message: Optional[str] = None  # For reconnecting status messages

    # Metadata
    org_schema: Optional[str] = None
    processing_time_ms: Optional[float] = None
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            float: lambda v: round(v, 2)
        }



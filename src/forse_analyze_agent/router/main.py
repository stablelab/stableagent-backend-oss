"""FastAPI router for Forse Analyze Agent.

Provides HTTP endpoints for:
- Streaming chat (Vercel AI SDK compatible)
- Non-streaming invoke
- Direct dashboard analysis
- Direct graph analysis with custom prompts
"""

from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRouter
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src.forse_analyze_agent.graph import forse_agent_graph
from src.forse_analyze_agent.router.stream import (
    stream_agent_response,
    stream_with_initial_state,
)
from src.forse_analyze_agent.router.types import ClientMessage

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class ChatRequest(BaseModel):
    """Standard chat request with message history."""
    messages: List[ClientMessage]


class ChatResponse(BaseModel):
    """Standard chat response."""
    response: str
    metadata: Optional[Dict[str, Any]] = None


class DashboardAnalysisRequest(BaseModel):
    """Request for dashboard-wide analysis."""
    dashboard_id: str = Field(..., description="The dashboard ID to analyze")
    analysis_prompt: Optional[str] = Field(
        None, 
        description="Custom analysis instructions (e.g., 'Compare TVL trends')"
    )
    stream: bool = Field(True, description="Whether to stream the response")


class GraphAnalysisRequest(BaseModel):
    """Request for single graph analysis."""
    dashboard_id: str = Field(..., description="The parent dashboard ID")
    graph_id: str = Field(..., description="The graph ID to analyze")
    category_id: Optional[str] = Field(
        None, 
        description="Specific category to analyze (uses first if not provided)"
    )
    analysis_prompt: Optional[str] = Field(
        None,
        description="Custom analysis instructions (e.g., 'Find anomalies')"
    )
    stream: bool = Field(True, description="Whether to stream the response")


class AnalysisResponse(BaseModel):
    """Response for direct analysis endpoints."""
    analysis: str
    dashboard_id: str
    graph_id: Optional[str] = None
    category_id: Optional[str] = None
    mode: str


# =============================================================================
# Streaming Endpoints (Vercel AI SDK Compatible)
# =============================================================================

@router.post("/stream")
async def stream_chat(request: ChatRequest):
    """
    Streaming chat endpoint - Vercel AI SDK compatible.
    
    Use for general conversational analysis where user explores dashboards
    through natural language.
    """
    try:
        return StreamingResponse(
            stream_agent_response(request.messages),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/invoke")
async def invoke_chat(request: ChatRequest):
    """
    Non-streaming invoke endpoint.
    
    Returns complete response after full agent execution.
    """
    try:
        lc_messages = []
        for msg in request.messages:
            if msg.role == "user":
                if msg.parts:
                    text_parts = [
                        part.text for part in msg.parts 
                        if part.type == "text" and part.text
                    ]
                    content = " ".join(text_parts) if text_parts else ""
                else:
                    content = msg.content or ""
                if content:
                    lc_messages.append(HumanMessage(content=content))
        
        result = await forse_agent_graph.ainvoke({"messages": lc_messages})
        
        last_message = result["messages"][-1]
        return JSONResponse(
            content=ChatResponse(
                response=last_message.content,
                metadata={"message_id": last_message.id}
            ).model_dump(),
            headers={"Cache-Control": "no-cache"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Direct Analysis Endpoints (For Frontends Needing Specific Analysis)
# =============================================================================

@router.post("/analyze/dashboard", response_model=AnalysisResponse)
async def analyze_dashboard_endpoint(request: DashboardAnalysisRequest):
    """
    Analyze an entire dashboard.
    
    Fetches all graphs and provides holistic analysis including:
    - Common trends across metrics
    - Correlations between graphs
    - Key insights and anomalies
    
    Supports both streaming and non-streaming modes.
    """
    try:
        # Build the analysis message
        user_message = f"Analyze the entire dashboard with ID: {request.dashboard_id}"
        if request.analysis_prompt:
            user_message += f"\n\nSpecific analysis request: {request.analysis_prompt}"
        
        initial_state = {
            "dashboard_id": request.dashboard_id,
            "analysis_mode": "dashboard",
            "user_analysis_prompt": request.analysis_prompt,
        }
        
        if request.stream:
            return StreamingResponse(
                stream_with_initial_state(
                    user_message=user_message,
                    initial_state=initial_state,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        
        # Non-streaming
        result = await forse_agent_graph.ainvoke({
            "messages": [HumanMessage(content=user_message)],
            **initial_state,
        })
        
        return AnalysisResponse(
            analysis=result["messages"][-1].content,
            dashboard_id=request.dashboard_id,
            mode="dashboard_overview",
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/graph", response_model=AnalysisResponse)
async def analyze_graph_endpoint(request: GraphAnalysisRequest):
    """
    Analyze a specific graph with optional custom analysis.
    
    Supports user-defined analysis prompts like:
    - "Find the top 3 growth periods"
    - "Compare with previous month"
    - "Identify anomalies or outliers"
    
    Supports both streaming and non-streaming modes.
    """
    try:
        # Build the analysis message
        user_message = f"Analyze graph {request.graph_id} from dashboard {request.dashboard_id}"
        if request.category_id:
            user_message += f" for category {request.category_id}"
        if request.analysis_prompt:
            user_message += f"\n\nSpecific analysis request: {request.analysis_prompt}"
        
        initial_state = {
            "dashboard_id": request.dashboard_id,
            "graph_id": request.graph_id,
            "category_ids": [request.category_id] if request.category_id else [],
            "analysis_mode": "graph",
            "user_analysis_prompt": request.analysis_prompt,
        }
        
        if request.stream:
            return StreamingResponse(
                stream_with_initial_state(
                    user_message=user_message,
                    initial_state=initial_state,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        
        # Non-streaming
        result = await forse_agent_graph.ainvoke({
            "messages": [HumanMessage(content=user_message)],
            **initial_state,
        })
        
        return AnalysisResponse(
            analysis=result["messages"][-1].content,
            dashboard_id=request.dashboard_id,
            graph_id=request.graph_id,
            category_id=request.category_id,
            mode="graph_analysis",
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

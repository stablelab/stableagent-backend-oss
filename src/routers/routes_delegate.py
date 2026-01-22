from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from src.agent.delegate.reasoning_agent import ReasoningAgent
from src.agent.delegate.two_stage_orchestrator import TwoStageOrchestrator
from src.services.delegate_database import DatabaseServiceClient
# Removed AIAgentConfig import - no longer needed for feature flags
import os
import re
import logging
import json
import asyncio

logger = logging.getLogger(__name__)

# Global agent instance for lazy initialization
_agent = None
_agent_lock = None

def get_agent():
    """Get or create the reasoning agent instance with lazy initialization."""
    global _agent, _agent_lock
    
    if _agent is None:
        try:
            logger.info("🔄 Initializing ReasoningAgent (lazy initialization)")
            
            # Import threading for thread safety
            import threading
            if _agent_lock is None:
                _agent_lock = threading.Lock()
            
            with _agent_lock:
                # Double-check pattern to avoid race conditions
                if _agent is None:
                    backend_url = os.getenv("BACKEND_URL", "")
                    logger.info(f"🔗 Using backend URL: {backend_url}")
                    
                    db_service_client = DatabaseServiceClient(backend_url)
                    
                    # Create agent with increased timeout specifically for the analyse endpoint
                    _agent = ReasoningAgent(
                        db_service_client=db_service_client,
                        llm_timeout=180  # 3 minutes timeout for AI analysis
                    )
                    logger.info("✅ ReasoningAgent initialized successfully")
        
        except Exception as e:
            logger.error(f"❌ Failed to initialize ReasoningAgent: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Agent initialization failed: {str(e)}")
    
    return _agent

# Initialize two-stage orchestrator
# Note: Redis client would be initialized here if available
try:
    logger.info("Initializing TwoStageOrchestrator...")
    two_stage_orchestrator = TwoStageOrchestrator(
        reasoning_agent=get_agent(),
        redis_client=None  # Add Redis client here when available
    )
    logger.info("TwoStageOrchestrator initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize TwoStageOrchestrator: {str(e)}", exc_info=True)
    raise

async def analyse_proposal_with_reasoning(proposal_id: str, dao_id: str, source: str, user_wallet: str = None):
    """
    Analyzes a proposal using two-stage analysis with streaming support.
    
    Args:
        proposal_id: The proposal ID to analyze
        dao_id: DAO identifier 
        source: Source platform ('snapshot' or 'tally')
        user_wallet: Optional user wallet for personalized recommendations
    
    Returns:
        StreamingResponse with server-sent events
    """
    async def generate_streaming_analysis():
        """Generator function for streaming analysis events"""
        logger.info(f"STREAMING: Starting streaming analysis for proposal {proposal_id} (user: {user_wallet or 'anonymous'})")
        
        # Always yield initial progress event
        from datetime import datetime, timezone
        def _now_iso():
            return datetime.now(timezone.utc).isoformat()
        
        yield f"data: {json.dumps({'type': 'stream.initialized', 'message': 'Analysis started', 'timestamp': _now_iso()})}\n\n"
        
        try:
            allowed_types = {
                # cache / overall
                "cache.hit",
                "analysis.started",
                "analysis.completed",
                # data gathering
                "data.gathering.started",
                "data.gathering.proposal_loaded",
                "data.gathering.context_loaded",
                "data.gathering.completed",
                # reasoning (ReAct)
                "reasoning.initialized",
                "reasoning.step.started",
                "reasoning.step.progress",
                "reasoning.action.started",
                "reasoning.action.completed",
                "reasoning.step.completed",
                "reasoning.completed",
                "reasoning.error",
                # perspective analysis
                "perspective.analysis.started",
                "perspective.analysis.completed",
                # user overlay
                "user.overlay.started",
                # errors
                "error",
            }

            # Use the real streaming method from the orchestrator
            async for event in two_stage_orchestrator.analyze_proposal_streaming(
                proposal_id=proposal_id,
                dao_id=dao_id,
                source=source,
                user_wallet=user_wallet
            ):
                try:
                    etype = (event or {}).get("type")
                except Exception:
                    etype = None

                # Skip verbose intermediate events
                if etype not in allowed_types:
                    continue

                logger.info(f"YIELDING EVENT: {event}")
                yield f"data: {json.dumps(event)}\n\n"
            
            logger.info(f"STREAMING: Analysis completed for proposal {proposal_id}")
            
        except Exception as e:
            logger.error(f"STREAMING: Analysis failed for proposal {proposal_id}: {str(e)}", exc_info=True)
            # Yield error as an event for frontend to handle
            error_event = {
                'type': 'error',
                'error': str(e),
                'proposal_id': proposal_id,
                'timestamp': _now_iso()
            }
            yield f"data: {json.dumps(error_event)}\n\n"
        
        # Always end with [DONE]
        yield "data: [DONE]\n\n"
    
    # Always return StreamingResponse, even if there might be errors
    # This ensures the content-type is always text/event-stream
    return StreamingResponse(
        generate_streaming_analysis(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type, Cache-Control, Accept",
            "Access-Control-Allow-Credentials": "true"
        }
    )


async def invalidate_analysis_cache(proposal_id: str, dao_id: str, source: str):
    """
    Manually invalidate cached analysis for a proposal (admin function).
    Expects query parameters: ?proposal_id=xxx&dao_id=xxx&source=xxx
    """
    try:
        success = await two_stage_orchestrator.invalidate_cache(proposal_id, dao_id, source)
        return {"success": success, "message": f"Cache invalidation {'successful' if success else 'failed'} for {proposal_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_analysis_cache_stats():
    """
    Get cache statistics for monitoring (admin function).
    """
    try:
        stats = await two_stage_orchestrator.get_cache_stats()
        stats['analysis_mode'] = 'two_stage'
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_cached_base_analysis(proposal_id: str, dao_id: str, source: str):
    """
    Debug endpoint to see cached BaseAnalysisArtifact (before user preferences).
    """
    try:
        cached_artifact = await two_stage_orchestrator.cache.get_cached_analysis(proposal_id, dao_id, source)
        
        if cached_artifact:
            return {
                "success": True,
                "base_analysis": {
                    # Core fields
                    "proposal_id": cached_artifact.proposal_id,
                    "dao_id": cached_artifact.dao_id,
                    "source": cached_artifact.source,
                    "analyzed_at": str(cached_artifact.analyzed_at),
                    "proposal_summary": cached_artifact.proposal_summary,
                    "proposal_status": cached_artifact.proposal_status,
                    "voting_options": cached_artifact.voting_options,
                    "key_arguments": cached_artifact.key_arguments,
                    "financial_impact": cached_artifact.financial_impact,
                    "similar_proposals": len(cached_artifact.similar_proposals),
                    "similar_proposals_list": cached_artifact.similar_proposals[:3],
                    "data_sources_used": cached_artifact.data_sources_used,
                    "embedding_generated": cached_artifact.embedding_generated,
                    "preliminary_insights": cached_artifact.preliminary_insights,
                    "reasoning_trace": len(cached_artifact.reasoning_trace),
                    
                    # Enhanced fields for multi-perspective analysis
                    "clean_proposal_summary": cached_artifact.clean_proposal_summary,
                    "extracted_arguments": cached_artifact.extracted_arguments,
                    "key_stakeholders": cached_artifact.key_stakeholders,
                    "risk_factors": cached_artifact.risk_factors,
                    "opportunity_factors": cached_artifact.opportunity_factors,
                    "governance_implications": cached_artifact.governance_implications,
                    "economic_implications": cached_artifact.economic_implications,
                    "react_steps": len(cached_artifact.react_steps),
                    "final_reasoning": cached_artifact.final_reasoning[:200] + "..." if len(cached_artifact.final_reasoning) > 200 else cached_artifact.final_reasoning,
                    "proposal_complexity": cached_artifact.proposal_complexity,
                    "proposal_category": cached_artifact.proposal_category,
                    "urgency_level": cached_artifact.urgency_level,
                    
                    # Multi-perspective analysis fields
                    "perspective_analyses": len(cached_artifact.perspective_analyses),
                    "perspective_analyses_details": cached_artifact.perspective_analyses,
                    "synthesis_insights": cached_artifact.synthesis_insights[:300] + "..." if len(cached_artifact.synthesis_insights) > 300 else cached_artifact.synthesis_insights,
                    "perspectives_analyzed": cached_artifact.perspectives_analyzed,
                    "perspective_consensus": cached_artifact.perspective_consensus,
                    "dominant_perspective": cached_artifact.dominant_perspective
                }
            }
        else:
            return {"success": False, "message": "No cached base analysis found"}
            
    except Exception as e:
        logger.error(f"Error in analyse endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _now_iso():
    """Helper function to get current timestamp in ISO format."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()



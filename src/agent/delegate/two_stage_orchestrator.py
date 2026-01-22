# Two-stage orchestrator for delegate analysis with feature flag
import logging
import json
from typing import Dict, Any, Optional
from src.agent.delegate.reasoning_agent import ReasoningAgent
from src.agent.delegate.base_analysis_wrapper import BaseAnalysisWrapper
from src.agent.delegate.user_overlay_chain import UserOverlayChain
from src.services.analysis_cache import AnalysisCache
from src.config.delegate_agent_settings import AIAgentConfig
from src.data_models.analysis_schemas import BaseAnalysisArtifact, UserRecommendation

logger = logging.getLogger(__name__)

class TwoStageOrchestrator:
    """Orchestrates two-stage analysis: Base Analysis + User Overlay"""
    
    def __init__(self, 
                 reasoning_agent: ReasoningAgent,
                 redis_client=None):
        self.reasoning_agent = reasoning_agent
        
        # Initialize components
        self.base_wrapper = BaseAnalysisWrapper(reasoning_agent)
        
        # Use simplified configuration (no feature flags)
        self.config = {
            'cache_ttl_hours': 3,
            'user_overlay_model': None,  # Use same model as reasoning agent
            'max_retries': 1
        }
        
        # Initialize cache with configured TTL
        self.cache = AnalysisCache(
            ttl_hours=self.config['cache_ttl_hours'],
            redis_client=redis_client
        )
        
        # Initialize user overlay chain with faster model if configured
        overlay_model = self.config.get('user_overlay_model')
        if overlay_model:
            try:
                # Create a separate LLM manager for overlay with faster model
                from src.agent.delegate.llm_provider import LLMManager
                
                # Try to get provider info safely
                provider_info = reasoning_agent.reasoner.llm.get_provider_info()
                provider_name = provider_info.get('provider') or provider_info.get('provider_name') or 'openai'
                
                overlay_llm = LLMManager(
                    provider_name=provider_name,
                    model_name=overlay_model,
                    temperature=0.2  # Lower temperature for more consistent overlay
                )
                self.user_overlay = UserOverlayChain(overlay_llm)
                logger.info(f"Created overlay chain with model: {overlay_model}")
            except Exception as e:
                logger.warning(f"Failed to create separate overlay LLM: {e}. Using same LLM as reasoning agent.")
                self.user_overlay = UserOverlayChain(reasoning_agent.reasoner.llm)
        else:
            # Use same LLM as reasoning agent
            self.user_overlay = UserOverlayChain(reasoning_agent.reasoner.llm)
            logger.info("Using same LLM for overlay as reasoning agent")
    
    async def analyze_proposal(self, 
                              proposal_id: str, 
                              dao_id: str, 
                              source: str, 
                              user_wallet: Optional[str] = None) -> Dict[str, Any]:
        """Main two-stage analysis flow with caching"""
        
        logger.info(f"🚀 Starting two-stage analysis for proposal {proposal_id} (user: {user_wallet or 'anonymous'})")
        
        try:
            # Stage 1: Get or create base analysis (with caching)
            base_analysis = await self._get_or_create_base_analysis(proposal_id, dao_id, source)
            
            # Stage 2: Apply user overlay if user provided
            if user_wallet:
                final_result = await self._apply_user_overlay(base_analysis, user_wallet)
            else:
                # Convert base analysis to legacy format for backward compatibility
                final_result = self._convert_to_legacy_format(base_analysis)
            
            logger.info(f"✅ Two-stage analysis completed for {proposal_id}")
            return final_result
            
        except Exception as e:
            logger.error(f"❌ Two-stage analysis failed for {proposal_id}: {str(e)}")
            raise
    
    async def analyze_proposal_streaming(self, 
                                       proposal_id: str, 
                                       dao_id: str, 
                                       source: str, 
                                       user_wallet: Optional[str] = None):
        """Real streaming version that uses the streaming ReAct reasoner"""
        
        logger.info(f"Starting streaming two-stage analysis for proposal {proposal_id} (user: {user_wallet or 'anonymous'})")
        
        try:
            # Check cache first
            cached_analysis = await self.cache.get_cached_analysis(proposal_id, dao_id, source)
            if cached_analysis:
                yield {
                    "type": "cache.hit",
                    "message": "Using cached analysis",
                    "timestamp": self._now_iso()
                }
                base_analysis = cached_analysis
            else:
                yield {
                    "type": "analysis.started",
                    "message": "Generating new analysis",
                    "timestamp": self._now_iso()
                }
                
                # Get proposal data for streaming analysis
                yield {
                    "type": "data.gathering.started",
                    "message": "Gathering proposal data",
                    "timestamp": self._now_iso()
                }
                
                proposal_data = self.reasoning_agent.embedding_agent.get_proposal_data(proposal_id, dao_id, source)
                detected_source = proposal_data['source']
                
                yield {
                    "type": "data.gathering.proposal_loaded",
                    "detected_source": detected_source,
                    "proposal_title": (proposal_data.get('title') or '')[:100],
                    "message": f"Loaded proposal from {detected_source}",
                    "timestamp": self._now_iso()
                }
                
                # Get similar content
                similar_content = self.reasoning_agent.embedding_agent.get_similar_content(
                    proposal_id, detected_source, search_source=source, proposal_data=proposal_data
                )
                
                similar_proposals_count = len(similar_content.get('proposals', []))
                yield {
                    "type": "data.gathering.context_loaded",
                    "similar_proposals_count": similar_proposals_count,
                    "message": f"Found {similar_proposals_count} similar proposals",
                    "timestamp": self._now_iso()
                }
                
                yield {
                    "type": "data.gathering.completed",
                    "message": "Data gathering completed",
                    "timestamp": self._now_iso()
                }
                
                # Format inputs for reasoning
                proposal_text = self.reasoning_agent.embedding_agent.format_proposal_data(proposal_data)
                context_text = self.reasoning_agent.embedding_agent.format_similar_content(similar_content)
                
                # Get voting options
                voting_options = []
                if 'choices' in proposal_data:
                    voting_options = proposal_data['choices']
                elif 'options' in proposal_data:
                    voting_options = proposal_data['options']
                else:
                    voting_options = ["For", "Against", "Abstain"]
                
                # Stream the ReAct reasoning process
                react_result = None
                async for event in self._stream_react_reasoning(proposal_text, context_text, voting_options):
                    # Guard against None events from underlying generators
                    if not event:
                        continue
                    yield event
                    if isinstance(event, dict) and event.get("type") == "reasoning.completed":
                        react_result = event
                
                # Generate base analysis from the ReAct result
                yield {
                    "type": "perspective.analysis.started",
                    "message": "Starting multi-perspective analysis",
                    "timestamp": self._now_iso()
                }
                
                # If reasoning did not complete, emit an error and proceed with minimal base analysis
                if not react_result:
                    yield {
                        "type": "reasoning.error",
                        "error": "Reasoning did not complete",
                        "timestamp": self._now_iso()
                    }
                    # Create a fallback react_result structure to avoid attribute errors downstream
                    react_result = {"justification": "", "decision": "Abstain"}

                base_analysis = await self._generate_base_analysis_from_react(
                    proposal_id, dao_id, source, proposal_data, similar_content, react_result
                )
                
                yield {
                    "type": "perspective.analysis.completed",
                    "perspectives_count": len(base_analysis.perspective_analyses),
                    "message": f"Analyzed {len(base_analysis.perspective_analyses)} perspectives",
                    "timestamp": self._now_iso()
                }
            
            # Apply user overlay if needed
            if user_wallet:
                yield {
                    "type": "user.overlay.started",
                    "message": "Applying user preferences",
                    "timestamp": self._now_iso()
                }
                final_result = await self._apply_user_overlay(base_analysis, user_wallet)
            else:
                final_result = self._convert_to_legacy_format(base_analysis)
            
            # Send final result
            yield {
                "type": "analysis.completed",
                "justification": final_result["justification"],
                "voting_decision": final_result["voting_decision"],
                "timestamp": self._now_iso()
            }
            
        except Exception as e:
            logger.error(f"Streaming analysis failed for {proposal_id}: {str(e)}")
            yield {
                "type": "error",
                "error": str(e),
                "timestamp": self._now_iso()
            }
    
    async def _stream_react_reasoning(self, proposal_text: str, context_text: str, voting_options: list):
        """Stream the ReAct reasoning process"""
        try:
            # Use the existing streaming method from ReActReasoner
            for event in self.reasoning_agent.reasoner.reason_streaming(proposal_text, context_text, voting_options):
                # Convert the final analysis.completed to reasoning.completed to distinguish phases
                if event.get("type") == "analysis.completed":
                    yield {
                        "type": "reasoning.completed",
                        "decision": event.get("decision"),
                        "justification": event.get("justification"),
                        "total_steps": event.get("total_steps"),
                        "message": "ReAct reasoning completed",
                        "timestamp": self._now_iso()
                    }
                else:
                    yield event
                
        except Exception as e:
            logger.error(f"ReAct reasoning streaming failed: {str(e)}")
            yield {
                "type": "reasoning.error",
                "error": str(e),
                "timestamp": self._now_iso()
            }
    
    async def _generate_base_analysis_from_react(self, proposal_id: str, dao_id: str, source: str, 
                                               proposal_data: dict, similar_content: dict, react_result: dict):
        """Generate base analysis artifact using existing ReAct result to avoid duplication"""
        
        # Ensure justification is a string, not None
        justification = react_result.get('justification', '') or ''
        decision = react_result.get('decision', 'Abstain') or 'Abstain'
        
        # Create a mock raw result from the ReAct reasoning and proposal data
        raw_result = {
            'source': proposal_data.get('source', source),
            'dao_id': dao_id,
            'voting_options': proposal_data.get('choices', proposal_data.get('options', ["For", "Against", "Abstain"])),
            'trace': [],  # We already have the reasoning from ReAct
            'analysis': justification,
            'reasoning': justification,
            'decision': decision,
            'proposal_data': proposal_data,
            'similar_content': similar_content,
            'title': proposal_data.get('title', 'Unknown Proposal'),
            'body': proposal_data.get('body', ''),
            'state': proposal_data.get('state', 'active')
        }
        
        # Use the base wrapper to convert to artifact, but skip the ReAct reasoning part
        artifact = self.base_wrapper._convert_to_artifact(raw_result, proposal_id, dao_id, source)
        
        # Cache the result
        cache_success = await self.cache.store_analysis(artifact)
        if cache_success:
            logger.info(f"Cached base analysis for {proposal_id}")
        else:
            logger.warning(f"Failed to cache base analysis for {proposal_id}")
        
        return artifact
    
    async def _get_or_create_base_analysis(self, proposal_id: str, dao_id: str, source: str) -> BaseAnalysisArtifact:
        """Get cached analysis or create new one"""
        
        # Check cache first
        cached_analysis = await self.cache.get_cached_analysis(proposal_id, dao_id, source)
        if cached_analysis:
            logger.info(f"📋 Using cached base analysis for {proposal_id}")
            return cached_analysis
        
        # Generate new base analysis
        logger.info(f"🔧 Generating new base analysis for {proposal_id}")
        
        try:
            artifact = self.base_wrapper.generate_base_analysis(proposal_id, dao_id, source)
            
            # Cache the result
            cache_success = await self.cache.store_analysis(artifact)
            if cache_success:
                logger.info(f"💾 Cached base analysis for {proposal_id}")
            else:
                logger.warning(f"⚠️ Failed to cache base analysis for {proposal_id}")
            
            return artifact
            
        except Exception as e:
            logger.error(f"❌ Failed to generate base analysis for {proposal_id}: {str(e)}")
            raise
    
    async def _apply_user_overlay(self, base_analysis: BaseAnalysisArtifact, user_wallet: str) -> Dict[str, str]:
        """Apply user overlay to generate personalized recommendation"""
        
        logger.info(f"🎯 Applying user overlay for wallet {user_wallet}")
        
        try:
            # Get user preferences (implement this based on existing user preference system)
            user_preferences = await self._get_user_preferences(user_wallet)
            
            # Generate personalized recommendation
            recommendation = await self.user_overlay.generate_personalized_recommendation(
                base_analysis, user_preferences
            )
            
            # Convert to legacy format
            result = {
                'justification': recommendation.justification,
                'voting_decision': recommendation.voting_decision
            }
            
            # Add non-actionable note if proposal is closed
            if not recommendation.is_actionable:
                result['justification'] += " [Note: This proposal is closed - recommendation is historical only]"
            
            return result
            
        except Exception as e:
            logger.error(f"❌ User overlay failed for {user_wallet}: {str(e)}")
            # Fall back to neutral recommendation
            return self._convert_to_legacy_format(base_analysis)
    
    def _convert_to_legacy_format(self, base_analysis: BaseAnalysisArtifact) -> Dict[str, str]:
        """Convert base analysis to legacy API format (neutral, no user preferences)"""
        
        # Build neutral justification from base analysis
        justification_parts = []
        
        # Add proposal summary
        justification_parts.append(f"Analysis of proposal: {base_analysis.proposal_summary}")
        
        # Add key arguments if available
        if base_analysis.key_arguments.get('for'):
            justification_parts.append(f"Arguments in favor: {'; '.join(base_analysis.key_arguments['for'])}")
        
        if base_analysis.key_arguments.get('against'):
            justification_parts.append(f"Concerns raised: {'; '.join(base_analysis.key_arguments['against'])}")
        
        # Add financial impact if available
        if base_analysis.financial_impact:
            justification_parts.append(f"Financial considerations: {base_analysis.financial_impact}")
        
        # Add similar proposals context
        if base_analysis.similar_proposals:
            justification_parts.append(f"Analysis considered {len(base_analysis.similar_proposals)} similar historical proposals")
        
        # Add preliminary insights
        if base_analysis.preliminary_insights:
            justification_parts.append(f"Additional context: {base_analysis.preliminary_insights}")
        
        # Choose neutral voting decision (prefer first option or "Abstain")
        voting_decision = "Abstain"
        if voting_decision not in base_analysis.voting_options:
            voting_decision = base_analysis.voting_options[0] if base_analysis.voting_options else "Abstain"
        
        justification = " ".join(justification_parts)
        
        # Add non-actionable note if proposal is closed
        if not base_analysis.is_proposal_active():
            justification += " [Note: This proposal is closed - analysis is historical only]"
        
        return {
            'justification': justification,
            'voting_decision': voting_decision
        }
    
    async def _get_user_preferences(self, user_wallet: str) -> Optional[Dict[str, Any]]:
        """Get user preferences from backend API system"""
        try:
            logger.debug(f"Fetching user preferences for {user_wallet}")
            
            # Use the existing database client to fetch preferences from backend API
            preferences = self.reasoning_agent.embedding_agent.db_service_client.get_user_preferences(user_wallet)
            
            if preferences:
                logger.info(f"Found user preferences for {user_wallet}: {list(preferences.keys())}")
                return preferences
            else:
                logger.debug(f"No user preferences found for {user_wallet}")
                return None
                
        except Exception as e:
            logger.warning(f"Failed to get user preferences for {user_wallet}: {str(e)}")
            return None
    
    async def invalidate_cache(self, proposal_id: str, dao_id: str, source: str) -> bool:
        """Manually invalidate cached analysis"""
        return await self.cache.invalidate_cache(proposal_id, dao_id, source)
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        return await self.cache.get_cache_stats()
    
    def is_enabled(self) -> bool:
        """Check if two-stage analysis is enabled"""
        return AIAgentConfig.is_two_stage_enabled()
    
    def _now_iso(self):
        """Helper method to get current timestamp in ISO format."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
# Reasoning agent using existing embedding-based pipeline with ReAct reasoning
from src.agent.delegate.embedding_agent import EmbeddingBasedAgent
from src.agent.delegate.react_reasoner import ReActReasoner
import logging

logger = logging.getLogger(__name__)

class ReasoningAgent:
    """Wrapper agent that adds reasoning via ReAct to the embedding-based architecture."""

    def __init__(self, *args, **kwargs):
        # Extract llm_timeout if provided, otherwise use default
        llm_timeout = kwargs.pop('llm_timeout', 60)
        
        self.embedding_agent = EmbeddingBasedAgent(*args, **kwargs)
        
        # Extract provider info from embedding agent
        provider_name = self.embedding_agent.provider_name
        #model_name = self.embedding_agent.llm_manager.model_name
        model_name = getattr(self.embedding_agent.llm_manager.provider, "model_name", None)
        #temperature = self.embedding_agent.llm_manager.temperature
        temperature = getattr(self.embedding_agent.llm_manager.provider, "temperature", None)

        self.reasoner = ReActReasoner(
            provider_name=provider_name,
            model_name=model_name,
            temperature=temperature,
            llm_timeout=llm_timeout,
            #**kwargs
        )

    def analyze_with_reasoning(self, proposal_id: str, dao_id: str = None, source: str = None) -> dict:
        """Analyze the proposal using embeddings and apply ReAct-based reasoning."""
        try:
            logger.info(f"🔍 Starting reasoning analysis for proposal {proposal_id}")
            
            proposal_data = self.embedding_agent.get_proposal_data(proposal_id, dao_id, source)
            detected_source = proposal_data['source']

            # Get similar proposals/discussions
            similar_content = self.embedding_agent.get_similar_content(
                proposal_id, detected_source, search_source=source, proposal_data=proposal_data
            )

            # Format inputs
            proposal_text = self.embedding_agent.format_proposal_data(proposal_data)
            context_text = self.embedding_agent.format_similar_content(similar_content)

            # Get voting options from actual proposal data
            voting_options = []
            if detected_source == 'tally':
                if proposal_data['tally'] and proposal_data['tally'].get('choices'):
                    voting_options = proposal_data['tally']['choices']
                else:
                    voting_options = ["For", "Against", "Abstain"]  # Fallback for Tally
            elif detected_source == 'snapshot':
                if proposal_data['snapshot'] and proposal_data['snapshot'].get('choices'):
                    voting_options = proposal_data['snapshot']['choices']
                else:
                    voting_options = ["Yes", "No", "Abstain"]  # Fallback for Snapshot

            # Use ReAct Reasoner
            analysis = self.reasoner.reason(
                proposal_text=proposal_text,
                context_text=context_text,
                voting_options=voting_options
            )

            return {
                'proposal_id': proposal_id,
                'dao_id': dao_id,
                'source': detected_source,
                'analysis': analysis["output"],
                'reasoning': analysis["reasoning"],
                'voting_decision': analysis["decision"],
                'justification': analysis.get("justification", ""),
                'trace': analysis["trace"],  # ✅ Add this
                'voting_options': voting_options,
                'llm': self.reasoner.provider,
                'model': self.reasoner.model,
                'similar_content_count': {
                    'proposals': len(similar_content['proposals']),
                    'discussions': len(similar_content['discussions'])
                }
            }

        except Exception as e:
            logger.error(f"❌ Error during reasoning analysis: {str(e)}")
            return {'error': str(e)}

    def _now_iso(self):
        """Helper method to get current timestamp in ISO format."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

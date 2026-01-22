"""Embedding-based agent for analyzing governance proposals using existing embeddings."""

import logging
from typing import Dict, Any
from src.services.delegate_database import DatabaseServiceClient
from src.config.delegate_agent_settings import AIAgentConfig
from src.agent.delegate.llm_provider import LLMManager
from src.services.live_proposal_embeddings import LiveProposalEmbeddingService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EmbeddingBasedAgent:
    """Agent for analyzing governance proposals using existing embeddings."""
    
    def __init__(
        self,
        db_service_client: DatabaseServiceClient = None,
        provider_name: str = None,
        model_name: str = None,
        temperature: float = None,
        **kwargs
    ):
        """Initialize the agent.
        
        Args:
            db_service_client: Database service client for accessing data (will create one if not provided)
            provider_name: Name of the LLM provider to use ("gemini", "openai"). If None, will auto-detect based on available API keys.
            model_name: Name of the LLM model to use (from environment variables if not provided)
            temperature: Temperature for LLM generation (from YAML config if not provided)
            **kwargs: Provider-specific parameters (e.g., google_api_key, openai_api_key)
        """
        self.db_service_client = db_service_client or DatabaseServiceClient()
        
        # Initialize live proposal embedding service
        self.live_embedding_service = LiveProposalEmbeddingService()
        
        # Auto-detect provider if not specified
        if provider_name is None:
            try:
                provider_name = LLMManager.detect_provider()
                logger.info(f"Auto-detected provider: {provider_name}")
            except ValueError as e:
                logger.error(f"Provider auto-detection failed: {e}")
                raise
        
        self.provider_name = provider_name
        
        # Initialize LLM manager
        self.llm_manager = LLMManager(
            provider_name=provider_name,
            model_name=model_name,
            temperature=temperature,
            **kwargs
        )
    
    def get_proposal_data(self, proposal_id: str, dao_id: str = None, source: str = None) -> Dict[str, Any]:
        """Get proposal data from live or archive sources based on availability.
        
        Args:
            proposal_id: The proposal ID to search for
            dao_id: DAO ID for Snapshot proposals or slug for Tally proposals
            source: The source platform ('snapshot' or 'tally') to search in
        """
        proposal_data = {
            'snapshot': None,
            'tally': None,
            'source': None,
            'is_live': False  # Track if this is live data
        }
        
        # First, try to get from live data sources
        live_data_found = False
        
        # Try live Snapshot data first
        if source == 'snapshot' or source is None:
            try:
                live_snapshot_result = self.db_service_client.get_live_snapshot_proposal(proposal_id)
                if live_snapshot_result:
                    proposal_data['snapshot'] = live_snapshot_result
                    proposal_data['source'] = 'snapshot'
                    proposal_data['is_live'] = True
                    live_data_found = True
                    logger.info(f"Found LIVE Snapshot proposal: {proposal_id} (DAO: {live_snapshot_result.get('dao_id', 'N/A')}) - Title: {live_snapshot_result.get('title', 'N/A')}")
            except Exception as e:
                logger.debug(f"No live Snapshot proposal found for {proposal_id}: {str(e)}")
        
        # Try live onchain/tally data if not found in snapshot or if source is tally
        if not live_data_found and (source == 'tally' or source is None):
            try:
                live_onchain_result = self.db_service_client.get_live_onchain_proposal(proposal_id)
                if live_onchain_result:
                    proposal_data['tally'] = live_onchain_result
                    proposal_data['source'] = 'tally'
                    proposal_data['is_live'] = True
                    live_data_found = True
                    logger.info(f"Found LIVE onchain proposal: {proposal_id} (DAO: {live_onchain_result.get('dao_id', 'N/A')}) - Title: {live_onchain_result.get('title', 'N/A')}")
            except Exception as e:
                logger.debug(f"No live onchain proposal found for {proposal_id}: {str(e)}")
        
        # If live data found, return early (skip archive data)
        if live_data_found:
            return proposal_data
        
        # Fallback to archive data if no live data found
        logger.info(f"No live data found for proposal {proposal_id}, checking archive data...")
        
        # Check DAO support first for archive data
        if source == 'snapshot':
            # For Snapshot, check if the DAO is supported
            if dao_id:
                if not self.db_service_client.is_snapshot_dao_supported(dao_id):
                    supported_daos = self.db_service_client.get_supported_daos()
                    raise ValueError(
                        f"DAO '{dao_id}' is not supported. "
                        f"Supported DAOs are: {', '.join(supported_daos)}"
                    )
        elif source == 'tally':
            # For Tally, check if the DAO is supported
            if dao_id:
                is_supported, found_slug = self.db_service_client.is_tally_dao_supported(dao_id, proposal_id)
                if not is_supported:
                    supported_daos = self.db_service_client.get_supported_daos()
                    error_slug = found_slug if found_slug else dao_id
                    raise ValueError(
                        f"DAO '{error_slug}' is not supported. "
                        f"Supported DAOs are: {', '.join(supported_daos)}"
                    )
        
        # Try to get from archive Snapshot data
        try:
            if source == 'snapshot' or source is None:
                snapshot_result = self.db_service_client.get_snapshot_proposal(proposal_id)
                
                if snapshot_result:
                    # Check DAO support for Snapshot
                    snapshot_dao_id = snapshot_result.get('dao_id')
                    if snapshot_dao_id:
                        if not self.db_service_client.is_snapshot_dao_supported(snapshot_dao_id):
                            supported_daos = self.db_service_client.get_supported_daos()
                            raise ValueError(
                                f"Snapshot DAO '{snapshot_dao_id}' is not supported. "
                                f"Supported DAOs are: {', '.join(supported_daos)}"
                            )
                    
                    proposal_data['snapshot'] = snapshot_result
                    if not proposal_data['source']:
                        proposal_data['source'] = 'snapshot'
                    logger.info(f"Found ARCHIVE Snapshot proposal: {proposal_id} (DAO: {snapshot_result.get('dao_id', 'N/A')}) - Title: {snapshot_result.get('title', 'N/A')}")
                    
                    # Check if embedding exists
                    if not snapshot_result.get('embedding'):
                        logger.warning(f"Archive proposal {proposal_id} found but has no embedding")
        except Exception as e:
            logger.warning(f"Error getting archive Snapshot proposal {proposal_id}: {str(e)}")
        
        # Try to get from archive Tally data
        try:
            if source == 'tally' or source is None:
                if dao_id:
                    tally_result = self.db_service_client.get_tally_proposal(proposal_id, dao_id)
                else:
                    tally_result = self.db_service_client.get_tally_proposal(proposal_id)
                
                if tally_result:
                    # Check DAO support for Tally
                    tally_dao_id = tally_result.get('dao_id')
                    if tally_dao_id:
                        is_supported, found_slug = self.db_service_client.is_tally_dao_supported(tally_dao_id, proposal_id)
                        if not is_supported:
                            supported_daos = self.db_service_client.get_supported_daos()
                            error_slug = found_slug if found_slug else tally_dao_id
                            raise ValueError(
                                f"Tally DAO '{error_slug}' is not supported. "
                                f"Supported DAOs are: {', '.join(supported_daos)}"
                            )
                    
                    proposal_data['tally'] = tally_result
                    if not proposal_data['source']:
                        proposal_data['source'] = 'tally'
                    logger.info(f"Found ARCHIVE Tally proposal: {proposal_id} (DAO: {tally_result.get('dao_id', 'N/A')}) - Title: {tally_result.get('title', 'N/A')}")
                    
                    # Check if embedding exists
                    if not tally_result.get('embedding'):
                        logger.warning(f"Archive proposal {proposal_id} found but has no embedding")
        except Exception as e:
            logger.warning(f"Error getting archive Tally proposal {proposal_id}: {str(e)}")
        
        if not proposal_data['source']:
            raise ValueError(f"Proposal {proposal_id} not found in any supported platform (live or archive)")
        
        return proposal_data
    
    def get_similar_content(self, proposal_id: str, source: str, search_source: str = None, proposal_data: Dict[str, Any] = None, limit: int = 5) -> Dict[str, Any]:
        """Get similar content for a proposal using embeddings.
        
        Args:
            proposal_id: The proposal ID to find similar content for
            source: The source platform ('snapshot' or 'tally')
            search_source: Optional source to search in (if different from source)
            proposal_data: Pre-fetched proposal data (optional)
            limit: Maximum number of similar items to return
        """
        similar_content = {
            'proposals': [],
            'discussions': []
        }
        
        try:
            embedding = None
            
            # Get proposal data if not provided
            if proposal_data is None:
                proposal_data = self.get_proposal_data(proposal_id, source=source)
            
            # Check if this is live proposal data
            is_live_proposal = proposal_data.get('is_live', False)
            
            if is_live_proposal:
                # Generate embedding for live proposal
                logger.info(f"Generating embedding for LIVE proposal {proposal_id}")
                
                # Get the appropriate proposal data based on source
                current_proposal_data = None
                if source == 'snapshot' and proposal_data.get('snapshot'):
                    current_proposal_data = proposal_data['snapshot']
                elif source == 'tally' and proposal_data.get('tally'):
                    current_proposal_data = proposal_data['tally']
                
                if current_proposal_data:
                    embedding = self.live_embedding_service.generate_proposal_embedding(current_proposal_data)
                    if embedding:
                        logger.info(f"Successfully generated embedding for live proposal: {len(embedding)} dimensions")
                    else:
                        logger.warning(f"Failed to generate embedding for live proposal {proposal_id}")
                else:
                    logger.warning(f"No proposal data available for live proposal {proposal_id}")
            else:
                # Try to get existing embedding for archive proposal
                logger.info(f"Getting existing embedding for ARCHIVE proposal {proposal_id}")
                embedding = self.db_service_client.get_proposal_embedding(proposal_id, source)
                
                if embedding:
                    logger.info(f"Found existing embedding: {type(embedding)}, length: {len(str(embedding)) if embedding else 0}")
                    # Check if embedding is a string that needs to be converted or a numpy array
                    if isinstance(embedding, str):
                        logger.info("Embedding is a string, using as-is")
                    elif hasattr(embedding, 'tolist'):
                        logger.info("Embedding is a numpy array, converting to list")
                        embedding = embedding.tolist()
                    else:
                        logger.info(f"Embedding is of type {type(embedding)}, using as-is")
                else:
                    logger.warning(f"No existing embedding found for archive proposal {proposal_id}")
            
            # If no embedding available (either generation failed for live or not found for archive)
            if not embedding:
                logger.info("No embedding available, attempting to get general context...")
                similar_content = self._get_general_context(proposal_id, source, limit, proposal_data)
                return similar_content
            
            # Use embedding for similarity search against archive data
            logger.info("Performing similarity search against archive data using embedding...")
            
            # Get similar proposals from archive data
            if source == 'snapshot':
                similar_content['proposals'] = self.db_service_client.get_similar_snapshot_proposals(
                    embedding, proposal_id, limit
                )
                logger.info(f"Found {len(similar_content['proposals'])} similar archive Snapshot proposals")
            elif source == 'tally':
                similar_content['proposals'] = self.db_service_client.get_similar_tally_proposals(
                    embedding, proposal_id, limit
                )
                logger.info(f"Found {len(similar_content['proposals'])} similar archive Tally proposals")
            
            # Get similar discussions from archive data
            similar_content['discussions'] = self.db_service_client.get_similar_discussions_by_embedding(
                embedding, limit
            )
            logger.info(f"Found {len(similar_content['discussions'])} similar archive discussions")
            
        except Exception as e:
            logger.error(f"Error getting similar content: {str(e)}")
            # Fallback to general context
            if proposal_data is None:
                proposal_data = self.get_proposal_data(proposal_id, source=source)
            similar_content = self._get_general_context(proposal_id, source, limit, proposal_data)
        
        return similar_content
    
    def _get_general_context(self, proposal_id: str, source: str, limit: int, proposal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get general context when embeddings are not available.
        
        Args:
            proposal_id: The proposal ID
            source: The source platform
            limit: Maximum number of items to return
            proposal_data: Pre-fetched proposal data
        """
        similar_content = {
            'proposals': [],
            'discussions': []
        }
        
        try:
            logger.info(f"Getting general context for {source} proposal: {proposal_id}")
            
            # Get proposal data to extract DAO and keywords
            if proposal_data is None:
                proposal_data = self.get_proposal_data(proposal_id)
            
            if source == 'snapshot' and proposal_data.get('snapshot'):
                dao_id = proposal_data['snapshot'].get('dao_id', '')
                title = proposal_data['snapshot'].get('title', '')
                body = proposal_data['snapshot'].get('body', '')
                discussion_url = proposal_data['snapshot'].get('discussion', '')
                
                logger.info(f"Snapshot proposal data:")
                logger.info(f"   - DAO ID: {dao_id}")
                logger.info(f"   - Title: {title}")
                logger.info(f"   - Discussion URL: {discussion_url}")
                
                # Extract keywords from title and body
                keywords = self.db_service_client.extract_keywords(title + " " + body)
                logger.info(f"Extracted keywords: {keywords}")
                
                # Find recent proposals from the same DAO
                if dao_id:
                    similar_content['proposals'] = self.db_service_client.get_recent_snapshot_proposals_by_dao(
                        dao_id, proposal_id, limit, AIAgentConfig.get_fallback_similarity_score('proposals')
                    )
                    logger.info(f"Found {len(similar_content['proposals'])} recent proposals from same DAO: {dao_id}")
                
                # Find discussions by keywords
                if keywords:
                    similar_content['discussions'] = self.db_service_client.get_discussions_by_keywords(
                        keywords, limit, AIAgentConfig.get_fallback_similarity_score('discussions')
                    )
                    logger.info(f"Found {len(similar_content['discussions'])} discussions by keywords: {keywords}")
                
                # Try to get specific discussions first for Snapshot
                if discussion_url:
                    topic_slug = self.db_service_client.extract_topic_slug_from_url(discussion_url)
                    if topic_slug:
                        specific_discussions = self.db_service_client.get_discussions_by_topic_slug(topic_slug, limit)
                        if specific_discussions:
                            similar_content['discussions'] = specific_discussions
                            logger.info(f"Found {len(similar_content['discussions'])} specific discussions for Snapshot topic: '{topic_slug}'")
            
            elif source == 'tally' and proposal_data.get('tally'):
                governor_address = proposal_data['tally'].get('dao_id', '')  # Using dao_id field for governor address
                title = proposal_data['tally'].get('title', '')
                description = proposal_data['tally'].get('content', '')  # Using content field for description
                discourse_url = proposal_data['tally'].get('discourse_url', '')
                
                logger.info(f"Tally proposal data:")
                logger.info(f"   - Governor Address: {governor_address}")
                logger.info(f"   - Title: {title}")
                logger.info(f"   - Discourse URL: {discourse_url}")
                
                # Extract keywords from title and description
                keywords = self.db_service_client.extract_keywords(title + " " + description)
                logger.info(f"Extracted keywords: {keywords}")
                
                # Find recent proposals from the same governor
                if governor_address:
                    similar_content['proposals'] = self.db_service_client.get_recent_tally_proposals_by_governor(
                        governor_address, proposal_id, limit, AIAgentConfig.get_fallback_similarity_score('proposals')
                    )
                    logger.info(f"Found {len(similar_content['proposals'])} recent proposals from same governor: {governor_address}")
                
                # Try to get specific discussions first for Tally
                if discourse_url:
                    topic_slug = self.db_service_client.extract_topic_slug_from_url(discourse_url)
                    if topic_slug:
                        similar_content['discussions'] = self.db_service_client.get_discussions_by_topic_slug(
                            topic_slug, limit
                        )
                        logger.info(f"Found {len(similar_content['discussions'])} specific discussions for Tally topic: '{topic_slug}'")
                
                # Find discussions by keywords if no specific discussions found
                if not similar_content['discussions'] and keywords:
                    similar_content['discussions'] = self.db_service_client.get_discussions_by_keywords(
                        keywords, limit, AIAgentConfig.get_fallback_similarity_score('discussions')
                    )
                    logger.info(f"Found {len(similar_content['discussions'])} discussions by keywords: {keywords}")
        
        except Exception as e:
            logger.error(f"Error getting general context: {str(e)}")
        
        return similar_content
    
    def format_proposal_data(self, proposal_data: Dict[str, Any]) -> str:
        """Format proposal data for LLM consumption."""
        if proposal_data.get('snapshot'):
            proposal = proposal_data['snapshot']
            
            # Escape curly braces in content to prevent format string errors
            content = proposal.get('content', 'N/A').replace("{", "{{").replace("}", "}}")
            title = proposal.get('title', 'N/A').replace("{", "{{").replace("}", "}}")
            
            return f"""
Snapshot Proposal: {title}
DAO: {proposal.get('dao_id', 'N/A')}
Author: {proposal.get('author', 'N/A')}
State: {proposal.get('state', 'N/A')}
Votes: {proposal.get('votes', 0)}
Created: {proposal.get('created', 'N/A')}
Content: {content}
Choices: {', '.join(proposal.get('choices', []))}
Network: {proposal.get('network', 'N/A')}
"""
        elif proposal_data.get('tally'):
            proposal = proposal_data['tally']
            # Escape curly braces in content to prevent format string errors
            content = proposal.get('content', 'N/A').replace("{", "{{").replace("}", "}}")
            title = proposal.get('title', 'N/A').replace("{", "{{").replace("}", "}}")
            
            return f"""
Tally Proposal: {title}
Governor: {proposal.get('dao_id', 'N/A')}
Author: {proposal.get('author', 'N/A')}
State: {proposal.get('state', 'N/A')}
Votes: {proposal.get('votes', 0)}
Created: {proposal.get('created', 'N/A')}
Content: {content}
Choices: {', '.join(proposal.get('choices', []))}
Network: {proposal.get('network', 'N/A')}
"""
        else:
            return "No proposal data available"
    
    def format_similar_content(self, similar_content: Dict[str, Any]) -> str:
        """Format similar content for LLM consumption."""
        formatted = []
        
        if similar_content.get('proposals'):
            formatted.append("Similar Proposals:")
            for i, proposal in enumerate(similar_content['proposals'][:3], 1):
                similarity = proposal.get('similarity')
                if similarity is None:
                    similarity = 0.0
                # Ensure similarity is a float to prevent format string errors
                try:
                    similarity_float = float(similarity)
                except (ValueError, TypeError):
                    similarity_float = 0.0
                
                # Escape curly braces in title and content to prevent format string errors
                title = proposal.get('title', 'N/A').replace("{", "{{").replace("}", "}}")
                content = proposal.get('content', 'N/A')[:200].replace("{", "{{").replace("}", "}}")
                formatted.append(f"{i}. {title} (Similarity: {similarity_float:.3f})")
                formatted.append(f"   Content: {content}...")
        
        if similar_content.get('discussions'):
            formatted.append("\nRelated Discussions:")
            for i, discussion in enumerate(similar_content['discussions'][:3], 1):
                similarity = discussion.get('similarity')
                if similarity is None:
                    similarity = 0.0
                # Ensure similarity is a float to prevent format string errors
                try:
                    similarity_float = float(similarity)
                except (ValueError, TypeError):
                    similarity_float = 0.0
                
                # Escape curly braces in content to prevent format string errors
                content = discussion.get('content', 'N/A')[:200].replace("{", "{{").replace("}", "}}")
                formatted.append(f"{i}. Discussion (Similarity: {similarity_float:.3f})")
                formatted.append(f"   Content: {content}...")
        
        return "\n".join(formatted) if formatted else "No similar content found"
    
    def analyze_proposal(self, proposal_id: str, dao_id: str = None, source: str = None) -> Dict[str, Any]:
        """Analyze a specific proposal using embeddings.
        
        Args:
            proposal_id: The proposal ID to analyze
            dao_id: DAO ID for Snapshot proposals or slug for Tally proposals
            source: The source platform ('snapshot' or 'tally') to search in
        """
        try:
            logger.info(f"Starting analysis for proposal: {proposal_id}" + (f" in DAO: {dao_id}" if dao_id else "") + (f" from source: {source}" if source else ""))
            
            # Get proposal data from the specified source
            proposal_data = self.get_proposal_data(proposal_id, dao_id, source)
            detected_source = proposal_data['source']
            
            # Use the detected source for similar content search, passing the already-retrieved proposal data
            similar_content = self.get_similar_content(proposal_id, detected_source, search_source=source, proposal_data=proposal_data)
            
            # Format data for LLM
            proposal_text = self.format_proposal_data(proposal_data) 
            context_text = self.format_similar_content(similar_content)
            
            # Determine voting options based on actual proposal data
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
            
            # Create analysis prompt
            # Escape curly braces to prevent format string errors
            proposal_text_escaped = proposal_text.replace("{", "{{").replace("}", "}}")
            context_text_escaped = context_text.replace("{", "{{").replace("}", "}}")
            
            prompt = f"""
You are an AI governance analyst. Analyze the following proposal and provide insights.

PROPOSAL:
{proposal_text_escaped}

SIMILAR CONTENT FOR CONTEXT:
{context_text_escaped}

VOTING OPTIONS: {', '.join(voting_options)}

Please provide:
1. A summary of the proposal
2. Key points and implications
3. Potential risks and benefits
4. Similar historical proposals (if any found)
5. A recommendation with reasoning
6. Voting recommendation: {', '.join(voting_options)}

Format your response in a clear, structured manner.
"""
            
            # Generate analysis using LLM
            analysis = self.llm_manager.generate_from_prompt(prompt)
            
            return {
                'proposal_id': proposal_id,
                'source': detected_source,
                'analysis': analysis,
                'proposal_data': proposal_data,
                'similar_content': similar_content,
                'voting_options': voting_options
            }
            
        except Exception as e:
            logger.error(f"Error analyzing proposal {proposal_id}: {str(e)}")
            raise

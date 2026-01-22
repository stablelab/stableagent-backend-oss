"""Service for generating embeddings for live proposals."""

import logging
from typing import Dict, Any, List, Optional
from .gemini_embeddings import EmbeddingsService, EmbeddingError

logger = logging.getLogger(__name__)


class LiveProposalEmbeddingService:
    """Service for generating embeddings for live proposals using text-embedding-005."""
    
    def __init__(self, model: str = "text-embedding-005", dimensionality: Optional[int] = None):
        """Initialize the live proposal embedding service.
        
        Args:
            model: The embedding model to use (default: "text-embedding-005").
            dimensionality: Optional output dimensionality for embeddings.
        """
        self.embedding_service = EmbeddingsService(model=model, dimensionality=dimensionality)
        self.model = model
        self.dimensionality = dimensionality
        
    def generate_proposal_embedding(self, proposal_data: Dict[str, Any]) -> Optional[List[float]]:
        """Generate embedding for a live proposal.
        
        Args:
            proposal_data: Proposal data dict containing title, content/body, and other metadata
            
        Returns:
            List of floats representing the embedding, or None if generation fails
        """
        try:
            # Extract text content from proposal
            proposal_text = self._extract_proposal_text(proposal_data)
            
            if not proposal_text:
                logger.warning("No text content found in proposal data")
                return None
                
            # Generate embedding using the text-embedding-005 model
            embedding = self.embedding_service.embed_query(proposal_text)
            
            logger.info(f"Successfully generated embedding for proposal with {len(embedding)} dimensions")
            return embedding
            
        except EmbeddingError as e:
            logger.error(f"Embedding generation failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating proposal embedding: {str(e)}")
            return None
    
    def _extract_proposal_text(self, proposal_data: Dict[str, Any]) -> str:
        """Extract and combine text content from proposal data.
        
        Args:
            proposal_data: Proposal data dict
            
        Returns:
            Combined text string suitable for embedding generation
        """
        text_parts = []
        
        # Add title if available
        title = proposal_data.get('title', '').strip()
        if title:
            text_parts.append(f"Title: {title}")
        
        # Add body/content if available
        body = proposal_data.get('content', proposal_data.get('body', '')).strip()
        if body:
            text_parts.append(f"Content: {body}")
        
        # Add choices if available (for voting context)
        choices = proposal_data.get('choices', [])
        if choices and isinstance(choices, list):
            choices_text = ", ".join(str(choice) for choice in choices)
            text_parts.append(f"Voting Options: {choices_text}")
        
        # Add author if available (for context)
        author = proposal_data.get('author', '').strip()
        if author:
            text_parts.append(f"Author: {author}")
        
        # Combine all parts
        combined_text = "\n\n".join(text_parts)
        
        if not combined_text:
            logger.warning("No extractable text found in proposal data")
            return ""
        
        logger.debug(f"Extracted {len(combined_text)} characters of text from proposal")
        return combined_text
    
    def generate_batch_embeddings(self, proposals: List[Dict[str, Any]]) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple proposals.
        
        Args:
            proposals: List of proposal data dicts
            
        Returns:
            List of embeddings (or None for failed generations)
        """
        embeddings = []
        
        for i, proposal in enumerate(proposals):
            try:
                embedding = self.generate_proposal_embedding(proposal)
                embeddings.append(embedding)
                logger.debug(f"Generated embedding for proposal {i+1}/{len(proposals)}")
            except Exception as e:
                logger.error(f"Failed to generate embedding for proposal {i+1}: {str(e)}")
                embeddings.append(None)
        
        success_count = sum(1 for emb in embeddings if emb is not None)
        logger.info(f"Successfully generated {success_count}/{len(proposals)} proposal embeddings")
        
        return embeddings
    
    def is_live_proposal_data(self, proposal_data: Dict[str, Any]) -> bool:
        """Check if proposal data appears to be from live data sources.
        
        Args:
            proposal_data: Proposal data dict
            
        Returns:
            True if this appears to be live proposal data
        """
        # Check for indicators that this is live data
        # Live proposals typically have recent timestamps and active states
        
        # Check if it has fields typical of live proposals
        live_indicators = [
            'active',  # boolean field in socket tables
            'last_updated',  # timestamp field in socket tables
            'vote_start',  # unix timestamp
            'vote_end'  # unix timestamp
        ]
        
        has_live_indicators = any(field in proposal_data for field in live_indicators)
        
        # Check if state indicates it's active/live
        state = proposal_data.get('state', '').lower()
        is_active_state = state in ['active', 'pending', 'open']
        
        return has_live_indicators or is_active_state

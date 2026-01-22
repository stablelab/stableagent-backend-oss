import requests
import logging
from typing import Dict, Any, List, Optional, Union
from urllib.parse import urljoin
import json

logger = logging.getLogger(__name__)

class DatabaseServiceClient:
    """Client for interacting with the shared database service."""
    
    def __init__(self, base_url: str = None):
        """Initialize the database service client.
        
        Args:
            base_url: Base URL for the database service (defaults to localhost:3001)
        """
        # Base URL points to unified backend; DB endpoints are under /api/db/*
        self.base_url = (base_url or "http://localhost:8080").rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make a request to the database service."""
        url = urljoin(self.base_url, endpoint)
        
        try:
            # Always call DB endpoints under /api/db/*
            if not endpoint.startswith('/api/db/'):
                if endpoint.startswith('/api/'):
                    # Replace /api/ with /api/db/ to avoid double /api/
                    endpoint = '/api/db/' + endpoint[5:]  # Remove '/api/' and add to '/api/db/'
                else:
                    endpoint = '/api/db/' + endpoint.lstrip('/')
            response = self.session.request(method, urljoin(self.base_url + '/', endpoint.lstrip('/')), **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise
    
    def get_snapshot_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Get a Snapshot proposal by ID."""
        try:
            response = self._make_request('GET', f'/api/db/proposals/snapshot/{proposal_id}')
            return response.get('data')
        except Exception as e:
            logger.error(f"Error getting Snapshot proposal {proposal_id}: {str(e)}")
            return None
    
    def get_tally_proposal(self, onchain_id: str, dao_id: str = None) -> Optional[Dict[str, Any]]:
        """Get a Tally proposal by onchain_id and optionally dao_id."""
        try:
            params = {}
            if dao_id:
                params['daoId'] = dao_id
            
            response = self._make_request('GET', f'/api/db/proposals/tally/{onchain_id}', params=params)
            return response.get('data')
        except Exception as e:
            logger.error(f"Error getting Tally proposal {onchain_id}: {str(e)}")
            return None
    
    def get_live_snapshot_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Get a live Snapshot proposal by ID from socket_snapshot_proposals table."""
        try:
            response = self._make_request('GET', f'/api/db/proposals/live/snapshot/{proposal_id}')
            return response.get('data')
        except Exception as e:
            logger.error(f"Error getting live Snapshot proposal {proposal_id}: {str(e)}")
            return None
    
    def get_live_onchain_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Get a live onchain proposal by ID from socket_onchain_proposals table."""
        try:
            response = self._make_request('GET', f'/api/db/proposals/live/onchain/{proposal_id}')
            return response.get('data')
        except Exception as e:
            logger.error(f"Error getting live onchain proposal {proposal_id}: {str(e)}")
            return None
    
    def get_proposal_embedding(self, proposal_id: str, source: str) -> Optional[Any]:
        """Get embedding for a proposal."""
        try:
            params = {'source': source}
            response = self._make_request('GET', f'/api/db/proposals/embedding/{proposal_id}', params=params)
            data = response.get('data', {})
            return data.get('embedding')
        except Exception as e:
            logger.error(f"Error getting embedding for {source} proposal {proposal_id}: {str(e)}")
            return None
    
    def get_similar_snapshot_proposals(self, embedding: Any, proposal_id: str, limit: int) -> List[Dict[str, Any]]:
        """Get similar Snapshot proposals using embedding similarity."""
        try:
            data = {
                'embedding': embedding,
                'proposalId': proposal_id,
                'limit': limit
            }
            response = self._make_request('POST', '/api/db/proposals/similar/snapshot', json=data)
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Error getting similar Snapshot proposals: {str(e)}")
            return []
    
    def get_similar_tally_proposals(self, embedding: Any, proposal_id: str, limit: int) -> List[Dict[str, Any]]:
        """Get similar Tally proposals using embedding similarity."""
        try:
            data = {
                'embedding': embedding,
                'proposalId': proposal_id,
                'limit': limit
            }
            response = self._make_request('POST', '/api/db/proposals/similar/tally', json=data)
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Error getting similar Tally proposals: {str(e)}")
            return []
    
    def get_snapshot_discussion_url(self, proposal_id: str) -> Optional[str]:
        """Get discussion URL from Snapshot proposal."""
        try:
            response = self._make_request('GET', f'/api/discussions/snapshot-url/{proposal_id}')
            data = response.get('data', {})
            return data.get('discussionUrl')
        except Exception as e:
            logger.error(f"Error getting Snapshot discussion URL: {str(e)}")
            return None
    
    def get_tally_discourse_url(self, onchain_id: str) -> Optional[str]:
        """Get discourse URL from Tally proposal."""
        try:
            response = self._make_request('GET', f'/api/discussions/tally-url/{onchain_id}')
            data = response.get('data', {})
            return data.get('discourseUrl')
        except Exception as e:
            logger.error(f"Error getting Tally discourse URL: {str(e)}")
            return None
    
    def get_discussions_by_topic_slug(self, topic_slug: str, limit: int) -> List[Dict[str, Any]]:
        """Get discussions by topic slug."""
        try:
            params = {'limit': limit}
            response = self._make_request('GET', f'/api/discussions/topic/{topic_slug}', params=params)
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Error getting discussions by topic slug: {str(e)}")
            return []
    
    def get_similar_discussions_by_embedding(self, embedding: Any, limit: int) -> List[Dict[str, Any]]:
        """Get similar discussions using embedding similarity."""
        try:
            data = {
                'embedding': embedding,
                'limit': limit
            }
            response = self._make_request('POST', '/api/discussions/similar', json=data)
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Error getting similar discussions: {str(e)}")
            return []
    
    def get_discussions_by_keywords(self, keywords: List[str], limit: int, fallback_similarity: float) -> List[Dict[str, Any]]:
        """Get discussions containing keywords."""
        try:
            data = {
                'keywords': keywords,
                'limit': limit,
                'fallbackSimilarity': fallback_similarity
            }
            response = self._make_request('POST', '/api/discussions/keywords', json=data)
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Error getting discussions by keywords: {str(e)}")
            return []
    
    def get_recent_snapshot_proposals_by_dao(self, dao_id: str, proposal_id: str, limit: int, fallback_similarity: float) -> List[Dict[str, Any]]:
        """Get recent proposals from the same DAO."""
        try:
            params = {
                'proposalId': proposal_id,
                'limit': limit,
                'fallbackSimilarity': fallback_similarity
            }
            response = self._make_request('GET', f'/api/db/proposals/recent/snapshot/{dao_id}', params=params)
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Error getting recent Snapshot proposals by DAO: {str(e)}")
            return []
    
    def get_recent_tally_proposals_by_governor(self, governor_address: str, proposal_id: str, limit: int, fallback_similarity: float) -> List[Dict[str, Any]]:
        """Get recent proposals from the same governor."""
        try:
            params = {
                'proposalId': proposal_id,
                'limit': limit,
                'fallbackSimilarity': fallback_similarity
            }
            response = self._make_request('GET', f'/api/db/proposals/recent/tally/{governor_address}', params=params)
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Error getting recent Tally proposals by governor: {str(e)}")
            return []
    
    def get_embeddings_availability(self) -> Dict[str, Any]:
        """Check what embeddings data is available in the database."""
        try:
            response = self._make_request('GET', '/api/daos/embeddings-availability')
            return response.get('data', {})
        except Exception as e:
            logger.error(f"Error getting embeddings availability: {str(e)}")
            return {}
    
    def get_supported_daos(self) -> List[str]:
        """Get list of supported DAOs."""
        try:
            response = self._make_request('GET', '/api/daos/supported')
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Error getting supported DAOs: {str(e)}")
            return []
    
    def is_snapshot_dao_supported(self, dao_id: str) -> bool:
        """Check if a Snapshot DAO is supported."""
        try:
            response = self._make_request('GET', f'/api/daos/snapshot/{dao_id}/supported')
            data = response.get('data', {})
            return data.get('isSupported', False)
        except Exception as e:
            logger.error(f"Error checking if Snapshot DAO is supported: {str(e)}")
            return False
    
    def is_tally_dao_supported(self, dao_id: str, onchain_id: str = None) -> tuple[bool, str]:
        """Check if a Tally DAO is supported."""
        try:
            params = {}
            if onchain_id:
                params['onchainId'] = onchain_id
            
            response = self._make_request('GET', f'/api/daos/tally/{dao_id}/supported', params=params)
            data = response.get('data', {})
            return data.get('supported', False), data.get('foundSlug', dao_id)
        except Exception as e:
            logger.error(f"Error checking if Tally DAO is supported: {str(e)}")
            return False, dao_id
    
    def get_dao_info(self, dao_id: str, source: str, onchain_id: str = None) -> Optional[Dict[str, Any]]:
        """Get DAO information."""
        try:
            params = {'source': source}
            if onchain_id:
                params['onchainId'] = onchain_id
            
            response = self._make_request('GET', f'/api/daos/info/{dao_id}', params=params)
            return response.get('data')
        except Exception as e:
            logger.error(f"Error getting DAO info: {str(e)}")
            return None
    
    def get_user_preferences(self, wallet_address: str) -> Optional[Dict[str, Any]]:
        """Get user preferences for a wallet address from the backend API."""
        try:
            # Call the existing backend user preferences API directly (not via /api/db/)
            response = self.session.request('GET', f'{self.base_url}/api/user-preferences/{wallet_address}')
            response.raise_for_status()
            
            # The endpoint returns preferences object directly, not wrapped in success/data
            preferences = response.json()
            logger.info(f"Retrieved user preferences for {wallet_address}: {list(preferences.keys()) if preferences else 'empty'}")
            return preferences
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug(f"No user preferences found for {wallet_address}")
                return None
            else:
                logger.error(f"HTTP error getting user preferences for {wallet_address}: {e}")
                return None
        except Exception as e:
            logger.error(f"Error getting user preferences for {wallet_address}: {str(e)}")
            return None
    
    def extract_topic_slug_from_url(self, url: str) -> Optional[str]:
        """Extract topic slug from Discourse URL."""
        try:
            import re
            
            # Pattern for Discourse urls: https://forum.example.com/t/topic-slug/12345
            discourse_pattern = r'https?://[^/]+/t/([^/]+)/\d+'
            match = re.search(discourse_pattern, url)
            
            if match:
                topic_slug = match.group(1)
                logger.info(f"Successfully extracted topic slug: '{topic_slug}'")
                return topic_slug
            else:
                logger.warning(f"Could not extract topic slug from URL: {url}")
                return None
            
        except Exception as e:
            logger.error(f"Error extracting topic slug from URL {url}: {str(e)}")
            return None
    
    def extract_keywords(self, text: str) -> List[str]:
        """Extract relevant keywords from text for context matching."""
        if not text:
            return []
        
        # keyword extraction
        common_keywords = [
            'governance', 'proposal', 'vote', 'dao', 'token', 'treasury', 'funding',
            'grants', 'development', 'security', 'upgrade', 'parameter', 'allocation',
            'budget', 'spending', 'revenue', 'fee', 'incentive', 'reward', 'penalty'
        ]
        
        text_lower = text.lower()
        found_keywords = []
        
        for keyword in common_keywords:
            if keyword in text_lower:
                found_keywords.append(keyword)
        
        return found_keywords[:10]

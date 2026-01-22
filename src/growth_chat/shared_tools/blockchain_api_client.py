"""
HTTP client for Blockchain API endpoints.

Provides methods to query blockchain proposals and configuration
from the forse-growth-agent backend.
"""
import os
from typing import Any, Dict, Optional

import httpx

from src.utils.logger import logger

from .schemas.blockchain_schemas import (
    BlockchainConfig,
    BlockchainConfigResponse,
    BlockchainProposal,
    BlockchainProposalResponse,
    BlockchainProposalsResponse,
)


class BlockchainAPIError(Exception):
    """Custom exception for Blockchain API errors."""
    
    def __init__(self, message: str, status_code: int, response: Optional[Dict[str, Any]] = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(f"Blockchain API Error {status_code}: {message}")


class BlockchainAPIClient:
    """
    HTTP client for Blockchain API endpoints.
    
    Provides methods to:
    - List blockchain proposals with filtering
    - Get a specific proposal by ID
    - Check blockchain configuration status
    """
    
    def __init__(self, base_url: str = None, timeout: float = 30.0):
        """
        Initialize the Blockchain API client.
        
        Args:
            base_url: Base URL for the API (default from GROWTH_BACKEND_URL env var)
            timeout: Request timeout in seconds (default 30.0)
        """
        self.base_url = (base_url or os.getenv("GROWTH_BACKEND_URL", "http://localhost:4000")).rstrip("/")
        self.client = httpx.Client(timeout=timeout)
    
    def _get_headers(self, auth_token: str) -> Dict[str, str]:
        """
        Get headers for API requests with Privy authentication token.
        
        Args:
            auth_token: Privy authentication token
            
        Returns:
            Dictionary of headers
        """
        return {
            "privy-id-token": auth_token,
            "Content-Type": "application/json",
        }
    
    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """
        Handle API response and raise errors if needed.
        
        Args:
            response: HTTP response
            
        Returns:
            Parsed JSON response
            
        Raises:
            BlockchainAPIError: If the API returns an error
        """
        if response.status_code == 204:
            return {"success": True}
        
        try:
            data = response.json()
        except Exception:
            data = {"error": "Failed to parse response", "raw": response.text}
        
        if response.status_code >= 400:
            error_msg = data.get("error", "Unknown error")
            if isinstance(data, dict) and "message" in data:
                error_msg = data["message"]
            raise BlockchainAPIError(error_msg, response.status_code, data)
        
        return data
    
    def get_config(self, auth_token: str, org_slug: str) -> Optional[BlockchainConfig]:
        """
        Get blockchain configuration for an organization.
        
        Args:
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            BlockchainConfig if configured, None otherwise
            
        Raises:
            BlockchainAPIError: If the API returns an error
        """
        url = f"{self.base_url}/api/orgs/{org_slug}/blockchain/config"
        
        logger.info(f"[BlockchainAPI] Getting config for org={org_slug}")
        
        try:
            response = self.client.get(url, headers=self._get_headers(auth_token))
            data = self._handle_response(response)
            
            if data.get("config"):
                return BlockchainConfig(**data["config"])
            return None
            
        except BlockchainAPIError:
            raise
        except Exception as e:
            logger.error(f"[BlockchainAPI] get_config error: {e}")
            raise BlockchainAPIError(str(e), 500)
    
    def list_proposals(
        self,
        auth_token: str,
        org_slug: str,
        state: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> BlockchainProposalsResponse:
        """
        List blockchain proposals for an organization.
        
        Args:
            auth_token: Privy authentication token
            org_slug: Organization slug
            state: Filter by proposal state (optional)
            search: Search query for title/description (optional)
            limit: Maximum results per page (default 20)
            offset: Offset for pagination (default 0)
            
        Returns:
            BlockchainProposalsResponse with proposals and pagination info
            
        Raises:
            BlockchainAPIError: If the API returns an error
        """
        params = [f"limit={limit}", f"offset={offset}"]
        if state:
            params.append(f"state={state}")
        if search:
            params.append(f"search={search}")
        
        url = f"{self.base_url}/api/orgs/{org_slug}/blockchain/proposals?{'&'.join(params)}"
        
        logger.info(f"[BlockchainAPI] Listing proposals: org={org_slug}, state={state}, search={search}")
        
        try:
            response = self.client.get(url, headers=self._get_headers(auth_token))
            data = self._handle_response(response)
            
            # Parse proposals
            proposals = [BlockchainProposal(**p) for p in data.get("proposals", [])]
            
            return BlockchainProposalsResponse(
                proposals=proposals,
                total=data.get("total", len(proposals)),
                limit=data.get("limit", limit),
                offset=data.get("offset", offset),
            )
            
        except BlockchainAPIError:
            raise
        except Exception as e:
            logger.error(f"[BlockchainAPI] list_proposals error: {e}")
            raise BlockchainAPIError(str(e), 500)
    
    def get_proposal(
        self,
        auth_token: str,
        org_slug: str,
        proposal_id: str,
    ) -> BlockchainProposal:
        """
        Get a specific blockchain proposal by its on-chain ID.
        
        Args:
            auth_token: Privy authentication token
            org_slug: Organization slug
            proposal_id: On-chain proposal ID
            
        Returns:
            BlockchainProposal
            
        Raises:
            BlockchainAPIError: If the API returns an error or proposal not found
        """
        url = f"{self.base_url}/api/orgs/{org_slug}/blockchain/proposals/{proposal_id}"
        
        logger.info(f"[BlockchainAPI] Getting proposal: org={org_slug}, proposal_id={proposal_id}")
        
        try:
            response = self.client.get(url, headers=self._get_headers(auth_token))
            data = self._handle_response(response)
            
            if not data.get("proposal"):
                raise BlockchainAPIError("Proposal not found", 404)
            
            return BlockchainProposal(**data["proposal"])
            
        except BlockchainAPIError:
            raise
        except Exception as e:
            logger.error(f"[BlockchainAPI] get_proposal error: {e}")
            raise BlockchainAPIError(str(e), 500)
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


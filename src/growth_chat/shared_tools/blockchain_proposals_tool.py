"""
LangChain tools for searching organization blockchain proposals.

Provides tools to query on-chain governance proposals synced from
the organization's configured blockchain.
"""
import json
from typing import Any, List, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from src.utils.logger import logger

from .blockchain_api_client import BlockchainAPIClient, BlockchainAPIError
from .schemas.blockchain_schemas import (
    BlockchainProposal,
    GetOrgBlockchainProposalInput,
    SearchOrgBlockchainProposalsInput,
)


# ==================
# Search Proposals Tool
# ==================

class SearchOrgBlockchainProposalsTool(BaseTool):
    """
    Tool for searching organization's on-chain blockchain proposals.
    
    Searches the organization's synced blockchain governance proposals
    from the configured blockchain (e.g., Rootstock, Ethereum).
    """
    
    name: str = "search_org_blockchain_proposals"
    description: str = """Search your organization's on-chain governance proposals from the configured blockchain.

Use this tool to find governance proposals that have been synced from your organization's blockchain.

CAPABILITIES:
- List all proposals or search by keyword
- Filter by state: Pending, Active, Canceled, Defeated, Succeeded, Queued, Expired, Executed
- View proposal titles, descriptions, vote counts, and proposer addresses

EXAMPLES:
- "What are our active proposals?" → search with state="Active"
- "Find proposals about treasury" → search with query="treasury"
- "List all governance proposals" → search with no filters
- "Show succeeded proposals" → search with state="Succeeded"

NOTE: This tool only works if your organization has configured a blockchain in Settings > Blockchain.
For external DAO proposals (Arbitrum, Aave, etc.), use the research agent's proposal tools instead.
"""
    
    args_schema: Type[BaseModel] = SearchOrgBlockchainProposalsInput
    
    # Configuration injected at creation time
    auth_token: str = ""
    org_slug: str = ""
    
    _client: Optional[BlockchainAPIClient] = None
    
    def _get_client(self) -> BlockchainAPIClient:
        """Get or create the API client."""
        if self._client is None:
            self._client = BlockchainAPIClient()
        return self._client
    
    def _run(
        self,
        query: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 10,
    ) -> str:
        """
        Search blockchain proposals.
        
        Args:
            query: Search query for title/description
            state: Filter by proposal state
            limit: Maximum results to return
            
        Returns:
            JSON string with search results
        """
        logger.info(f"[TOOL] SearchOrgBlockchainProposals: query={query}, state={state}, limit={limit}")
        
        if not self.auth_token or not self.org_slug:
            return json.dumps({
                "error": True,
                "message": "Tool not properly configured. Missing auth_token or org_slug.",
            })
        
        try:
            client = self._get_client()
            
            # First check if blockchain is configured
            config = client.get_config(self.auth_token, self.org_slug)
            if not config:
                return json.dumps({
                    "error": True,
                    "message": "Blockchain is not configured for this organization.",
                    "help": "To enable on-chain proposal tracking:\n1. Go to Settings > Blockchain\n2. Configure your chain, RPC endpoint, and contract address\n3. Run a sync to fetch proposals",
                })
            
            # Search proposals
            response = client.list_proposals(
                auth_token=self.auth_token,
                org_slug=self.org_slug,
                state=state,
                search=query,
                limit=limit,
            )
            
            if not response.proposals:
                return json.dumps({
                    "query": query,
                    "state": state,
                    "count": 0,
                    "proposals": [],
                    "message": "No proposals found matching your criteria.",
                    "chain_id": config.chain_id,
                    "contract_address": config.contract_address,
                })
            
            # Format proposals for output
            proposals_data = []
            for p in response.proposals:
                proposals_data.append({
                    "proposal_id": p.proposal_id,
                    "title": p.title or p.event_title or "Untitled Proposal",
                    "description": self._truncate(p.description or p.event_description or "", 500),
                    "state": p.state,
                    "proposer": p.proposer,
                    "votes_for": p.votes_for,
                    "votes_against": p.votes_against,
                    "votes_abstain": p.votes_abstain,
                    "created_at": p.created_at,
                })
            
            return json.dumps({
                "query": query,
                "state": state,
                "count": len(proposals_data),
                "total": response.total,
                "proposals": proposals_data,
                "chain_id": config.chain_id,
                "contract_address": config.contract_address,
            })
            
        except BlockchainAPIError as e:
            logger.error(f"[TOOL] SearchOrgBlockchainProposals API error: {e}")
            if e.status_code == 401:
                return json.dumps({
                    "error": True,
                    "message": "Authentication failed. Please try again.",
                })
            return json.dumps({
                "error": True,
                "message": f"Failed to fetch proposals: {e.message}",
            })
        except Exception as e:
            logger.error(f"[TOOL] SearchOrgBlockchainProposals error: {e}", exc_info=True)
            return json.dumps({
                "error": True,
                "message": f"An unexpected error occurred: {str(e)}",
            })
    
    async def _arun(
        self,
        query: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 10,
    ) -> str:
        """Async version - delegates to sync."""
        return self._run(query=query, state=state, limit=limit)
    
    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text to max length."""
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."


# ==================
# Get Proposal Tool
# ==================

class GetOrgBlockchainProposalTool(BaseTool):
    """
    Tool for getting detailed information about a specific blockchain proposal.
    
    Retrieves full details of an on-chain governance proposal including
    vote counts, proposer, targets, and execution data.
    """
    
    name: str = "get_org_blockchain_proposal"
    description: str = """Get detailed information about a specific on-chain governance proposal.

Use this tool to retrieve complete details about a proposal when you need:
- Full proposal description
- Exact vote counts (for, against, abstain)
- Proposer address
- Execution targets and parameters
- Proposal state and timeline

INPUT: The on-chain proposal ID (a large number like "12345678901234567890...")

NOTE: This tool only works if your organization has configured a blockchain in Settings > Blockchain.
"""
    
    args_schema: Type[BaseModel] = GetOrgBlockchainProposalInput
    
    # Configuration injected at creation time
    auth_token: str = ""
    org_slug: str = ""
    
    _client: Optional[BlockchainAPIClient] = None
    
    def _get_client(self) -> BlockchainAPIClient:
        """Get or create the API client."""
        if self._client is None:
            self._client = BlockchainAPIClient()
        return self._client
    
    def _run(self, proposal_id: str) -> str:
        """
        Get detailed proposal information.
        
        Args:
            proposal_id: On-chain proposal ID
            
        Returns:
            JSON string with proposal details
        """
        logger.info(f"[TOOL] GetOrgBlockchainProposal: proposal_id={proposal_id}")
        
        if not self.auth_token or not self.org_slug:
            return json.dumps({
                "error": True,
                "message": "Tool not properly configured. Missing auth_token or org_slug.",
            })
        
        try:
            client = self._get_client()
            
            # First check if blockchain is configured
            config = client.get_config(self.auth_token, self.org_slug)
            if not config:
                return json.dumps({
                    "error": True,
                    "message": "Blockchain is not configured for this organization.",
                    "help": "To enable on-chain proposal tracking:\n1. Go to Settings > Blockchain\n2. Configure your chain, RPC endpoint, and contract address\n3. Run a sync to fetch proposals",
                })
            
            # Get proposal
            proposal = client.get_proposal(
                auth_token=self.auth_token,
                org_slug=self.org_slug,
                proposal_id=proposal_id,
            )
            
            return json.dumps({
                "proposal_id": proposal.proposal_id,
                "proposal_index": proposal.proposal_index,
                "title": proposal.title or proposal.event_title or "Untitled Proposal",
                "description": proposal.description or proposal.event_description or "",
                "state": proposal.state,
                "proposer": proposal.proposer,
                "votes": {
                    "for": proposal.votes_for,
                    "against": proposal.votes_against,
                    "abstain": proposal.votes_abstain,
                },
                "blocks": {
                    "snapshot": proposal.snapshot_block,
                    "deadline": proposal.deadline_block,
                },
                "eta": proposal.eta,
                "targets": proposal.targets,
                "values": proposal.values,
                "created_at": proposal.created_at,
                "last_synced_at": proposal.last_synced_at,
                "chain_id": config.chain_id,
                "contract_address": config.contract_address,
            })
            
        except BlockchainAPIError as e:
            logger.error(f"[TOOL] GetOrgBlockchainProposal API error: {e}")
            if e.status_code == 404:
                return json.dumps({
                    "error": True,
                    "message": f"Proposal with ID '{proposal_id}' not found.",
                    "help": "Make sure you're using the correct on-chain proposal ID. You can use search_org_blockchain_proposals to find available proposals.",
                })
            if e.status_code == 401:
                return json.dumps({
                    "error": True,
                    "message": "Authentication failed. Please try again.",
                })
            return json.dumps({
                "error": True,
                "message": f"Failed to fetch proposal: {e.message}",
            })
        except Exception as e:
            logger.error(f"[TOOL] GetOrgBlockchainProposal error: {e}", exc_info=True)
            return json.dumps({
                "error": True,
                "message": f"An unexpected error occurred: {str(e)}",
            })
    
    async def _arun(self, proposal_id: str) -> str:
        """Async version - delegates to sync."""
        return self._run(proposal_id=proposal_id)


# ==================
# Tool Factory
# ==================

def create_blockchain_tools(auth_token: str, org_slug: str) -> List[BaseTool]:
    """
    Create blockchain proposal tools with the given authentication context.
    
    Args:
        auth_token: Privy authentication token
        org_slug: Organization slug
        
    Returns:
        List of blockchain tool instances
    """
    tools = [
        SearchOrgBlockchainProposalsTool(auth_token=auth_token, org_slug=org_slug),
        GetOrgBlockchainProposalTool(auth_token=auth_token, org_slug=org_slug),
    ]
    
    logger.info(f"[BlockchainTools] Created {len(tools)} tools for org={org_slug}")
    
    return tools


"""
Pydantic schemas for blockchain API requests and responses.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==================
# API Response Schemas
# ==================

class BlockchainProposal(BaseModel):
    """Schema for a blockchain proposal from the API."""
    id: int
    org_id: int
    blockchain_config_id: int
    proposal_id: str
    proposal_index: int
    title: Optional[str] = None
    description: Optional[str] = None
    proposer: Optional[str] = None
    state: Optional[str] = None
    votes_for: str = "0"
    votes_against: str = "0"
    votes_abstain: str = "0"
    snapshot_block: Optional[str] = None
    deadline_block: Optional[str] = None
    eta: Optional[str] = None
    snapshot_id: Optional[str] = None
    event_title: Optional[str] = None
    event_description: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_synced_at: Optional[str] = None
    
    # Optional fields that may be included
    targets: Optional[List[str]] = None
    values: Optional[List[str]] = None
    calldatas: Optional[List[str]] = None
    description_hash: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None
    snapshot_data: Optional[Dict[str, Any]] = None


class BlockchainConfig(BaseModel):
    """Schema for blockchain configuration from the API."""
    id: int
    org_id: int
    chain_id: str
    rpc_endpoint: str
    contract_address: str
    contract_abi: List[Dict[str, Any]]
    proposal_count_method: str = "proposalCount"
    proposal_details_at_method: str = "proposalDetailsAt"
    proposal_details_method: str = "proposalDetails"
    proposal_snapshot_method: str = "proposalSnapshot"
    proposal_created_event_name: str = "ProposalCreated"
    deployment_block: Optional[str] = None
    is_active: bool = True
    auto_fetch_enabled: bool = True
    auto_fetch_time: str = "06:00"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BlockchainProposalsResponse(BaseModel):
    """Schema for paginated proposals list response."""
    proposals: List[BlockchainProposal]
    total: int
    limit: int
    offset: int


class BlockchainConfigResponse(BaseModel):
    """Schema for blockchain config response."""
    config: Optional[BlockchainConfig] = None


class BlockchainProposalResponse(BaseModel):
    """Schema for single proposal response."""
    proposal: BlockchainProposal


# ==================
# Tool Input Schemas
# ==================

class SearchOrgBlockchainProposalsInput(BaseModel):
    """Input schema for searching organization blockchain proposals."""
    query: Optional[str] = Field(
        None, 
        description="Search query for title/description. Leave empty to list all proposals."
    )
    state: Optional[str] = Field(
        None, 
        description="Filter by proposal state: Pending, Active, Canceled, Defeated, Succeeded, Queued, Expired, Executed"
    )
    limit: int = Field(
        10, 
        description="Maximum number of results to return (1-50)",
        ge=1,
        le=50
    )


class GetOrgBlockchainProposalInput(BaseModel):
    """Input schema for getting a specific blockchain proposal."""
    proposal_id: str = Field(
        ..., 
        description="On-chain proposal ID to retrieve (the blockchain proposal ID, not the database ID)"
    )


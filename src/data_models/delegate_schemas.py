from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator
import json
import pandas as pd
import uuid
from decimal import Decimal

class DataSource(str, Enum):
    """Enum for different data sources"""
    SNAPSHOT = "snapshot"
    DISCOURSE = "discourse"
    TALLY = "tally"

class DataType(str, Enum):
    """Enum for different data types"""
    PROPOSAL = "proposal"
    VOTE = "vote"
    DISCUSSION = "discussion"
    FORUM_COMMENT = "forum_comment"
    POST_REPLY = "post_reply"
    DAO_LIST = "dao_list"
    GOVERNANCE_DATA = "governance_data"

class ContentType(str, Enum):
    """Enum for different types of content"""
    PROPOSAL = "proposal"
    DISCUSSION = "discussion"
    VOTE = "vote"
    COMMENT = "comment"

class UnifiedDocument(BaseModel):
    """Base model for all document types with unified metadata structure"""
    document_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('metadata')
    def validate_metadata(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that metadata contains required fields and is JSON serializable"""
        required_fields = {'source', 'data_type', 'primary_entity_id', 'timestamp_utc'}
        missing_fields = required_fields - set(v.keys())
        if missing_fields:
            raise ValueError(f"Missing required metadata fields: {missing_fields}")
        
        # Ensure metadata is JSON serializable
        try:
            json.dumps(v)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Metadata must be JSON serializable: {str(e)}")
        
        return v
    
    @property
    def source(self) -> str:
        """Get the source of the document"""
        return self.metadata.get('source', '')
    
    @property
    def data_type(self) -> str:
        """Get the data type of the document"""
        return self.metadata.get('data_type', '')
    
    @property
    def primary_entity_id(self) -> str:
        """Get the primary entity ID of the document"""
        return self.metadata.get('primary_entity_id', '')
    
    @property
    def timestamp_utc(self) -> datetime:
        """Get the timestamp of the document"""
        return self.metadata.get('timestamp_utc')
    
    @property
    def additional_info(self) -> Dict[str, Any]:
        """Get additional information about the document"""
        return self.metadata.get('additional_info', {})

class ProposalDocument(UnifiedDocument):
    """Model for governance proposals"""
    @validator('metadata')
    def validate_proposal_metadata(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate proposal-specific metadata"""
        if v.get('data_type') != 'proposal':
            raise ValueError("ProposalDocument must have data_type 'proposal'")
        return v

class DiscussionDocument(UnifiedDocument):
    """Model for forum discussions"""
    @validator('metadata')
    def validate_discussion_metadata(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate discussion-specific metadata"""
        if v.get('data_type') != 'forum_comment':
            raise ValueError("DiscussionDocument must have data_type 'forum_comment'")
        return v

class VoteDocument(UnifiedDocument):
    """Model for governance votes"""
    @validator('metadata')
    def validate_vote_metadata(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate vote-specific metadata"""
        if v.get('data_type') != 'vote_reason':
            raise ValueError("VoteDocument must have data_type 'vote_reason'")
        return v

def create_unified_document(
    source: str,
    data_type: str,
    primary_entity_id: str,
    content: str,
    timestamp_utc: Union[datetime, str, int, float],
    metadata: Optional[Dict[str, Any]] = None,
    additional_info: Optional[Dict[str, Any]] = None
) -> UnifiedDocument:
    """
    Create a unified document with the given parameters.
    
    Args:
        source: Source of the document (e.g., 'snapshot_proposals', 'discourse_forum')
        data_type: Type of data (e.g., 'proposal', 'forum_comment')
        primary_entity_id: Unique identifier for the primary entity
        content: Main content of the document
        timestamp_utc: Timestamp in UTC (can be datetime, ISO format string, or Unix timestamp)
        metadata: Optional metadata dictionary (if provided, other metadata fields will be ignored)
        additional_info: Optional additional information dictionary
        
    Returns:
        UnifiedDocument instance
    """
    # Convert timestamp to datetime if needed
    if isinstance(timestamp_utc, str):
        try:
            # Try parsing as ISO format first
            timestamp_utc = datetime.fromisoformat(timestamp_utc)
        except ValueError:
            # If that fails, try parsing as Unix timestamp
            timestamp_utc = datetime.fromtimestamp(float(timestamp_utc))
    elif isinstance(timestamp_utc, (int, float)):
        timestamp_utc = datetime.fromtimestamp(float(timestamp_utc))
    
    # If metadata is provided, use it directly
    if metadata is not None:
        # Ensure timestamp_utc is a string in metadata
        if 'timestamp_utc' in metadata and isinstance(metadata['timestamp_utc'], datetime):
            metadata['timestamp_utc'] = metadata['timestamp_utc'].isoformat()
        return UnifiedDocument(content=content, metadata=metadata)
    
    # Otherwise, construct metadata from individual fields
    metadata = {
        'source': source,
        'data_type': data_type,
        'primary_entity_id': primary_entity_id,
        'timestamp_utc': timestamp_utc.isoformat(),  # Convert datetime to ISO format string
        'additional_info': additional_info or {}
    }
    
    return UnifiedDocument(content=content, metadata=metadata)

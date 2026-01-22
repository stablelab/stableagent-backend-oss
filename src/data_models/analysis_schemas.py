# Analysis schemas for two-stage delegate flow
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

class BaseAnalysisArtifact(BaseModel):
    """Structured output from base analysis stage - reusable across users"""
    
    # Core identifiers
    proposal_id: str
    dao_id: str
    source: str  # 'snapshot' | 'tally'
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "1.0"

    # Core proposal information
    proposal_summary: str
    proposal_status: str  # e.g., "active" | "closed" | "pending"
    voting_options: List[str]  # Must be non-empty

    # Reasoned analysis content
    key_arguments: Dict[str, List[str]] = Field(default_factory=dict)  # {"for": [...], "against": [...]}
    financial_impact: Optional[str] = None
    voter_stats: Optional[Dict[str, Any]] = None
    timeline_info: Dict[str, Any] = Field(default_factory=dict)  # start/end, checkpoints if relevant
    similar_proposals: List[Dict[str, Any]] = Field(default_factory=list)  # id/title/outcome/why-similar
    references: List[str] = Field(default_factory=list)  # urls, ids, citations

    # Analysis metadata
    data_sources_used: List[str] = Field(default_factory=list)
    embedding_generated: bool = False
    reasoning_trace: List[Dict[str, Any]] = Field(default_factory=list)  # optional, for debugging
    preliminary_insights: str = ""
    
    # Enhanced fields for multi-perspective analysis
    clean_proposal_summary: str = ""  # Clean summary without ReAct formatting
    extracted_arguments: Dict[str, List[str]] = Field(default_factory=dict)  # Properly extracted pro/con arguments
    key_stakeholders: List[str] = Field(default_factory=list)  # Who is affected
    risk_factors: List[str] = Field(default_factory=list)  # Identified risks
    opportunity_factors: List[str] = Field(default_factory=list)  # Identified opportunities
    governance_implications: List[str] = Field(default_factory=list)  # Governance impact
    economic_implications: List[str] = Field(default_factory=list)  # Economic impact
    
    # ReAct reasoning extraction
    react_steps: List[Dict[str, str]] = Field(default_factory=list)  # Structured ReAct steps
    final_reasoning: str = ""  # The "Final Thought" from ReAct
    
    # Context for perspectives
    proposal_complexity: str = "medium"  # simple/medium/complex
    proposal_category: str = "governance"  # governance/treasury/protocol/etc
    urgency_level: str = "normal"  # urgent/normal/routine
    
    # Multi-perspective analysis fields
    perspective_analyses: List[Dict[str, Any]] = Field(default_factory=list)  # Conservative, Progressive, Balanced, Governance
    synthesis_insights: str = ""  # Combined perspective synthesis
    perspectives_analyzed: List[str] = Field(default_factory=list)  # List of perspective names analyzed
    perspective_consensus: str = "unknown"  # unanimous/majority/mixed/split
    dominant_perspective: str = ""  # Which perspective has strongest case

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        }
    }

    def validate_required_fields(self) -> bool:
        """Validate that required fields are properly set"""
        if not self.voting_options:
            raise ValueError("voting_options cannot be empty")
        if not self.proposal_summary:
            raise ValueError("proposal_summary cannot be empty")
        if not self.proposal_status:
            raise ValueError("proposal_status cannot be empty")
        return True

    def is_proposal_active(self) -> bool:
        """Check if proposal is active for voting"""
        return self.proposal_status.lower() in ['active', 'pending']

    def to_cache_key(self) -> str:
        """Generate cache key for this artifact"""
        return f"base_analysis:{self.source}:{self.dao_id}:{self.proposal_id}"


class UserRecommendation(BaseModel):
    """Final personalized recommendation output"""
    
    justification: str
    voting_decision: str  # Must be one of the voting_options from artifact
    is_actionable: bool = True  # False for closed proposals
    artifact_version: str = "1.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def validate_against_options(self, voting_options: List[str]) -> bool:
        """Validate that voting_decision is in allowed options"""
        if self.voting_decision not in voting_options:
            raise ValueError(f"voting_decision '{self.voting_decision}' not in allowed options: {voting_options}")
        return True

"""
Multi-Perspective Analysis Types.

Dataclasses for perspective analysis, supporting both static predefined perspectives
and dynamically generated perspectives based on program context.
"""
import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


class Perspective(enum.Enum):
    """Legacy enum for predefined perspectives."""
    CONSERVATIVE = "conservative"
    PROGRESSIVE = "progressive"
    BALANCED = "balanced"
    TECHNICAL = "technical"


# Vote type literals
VoteType = Literal["approve", "reject", "abstain", "for", "against"]


# ==================
# Core Analysis Types
# ==================

@dataclass
class ParsedInput:
    """Parsed input data for perspective analysis."""
    clean_summary: str
    arguments: Dict[str, List[str]] = field(default_factory=lambda: {"for": [], "against": []})
    risk_factors: List[str] = field(default_factory=list)
    opportunity_factors: List[str] = field(default_factory=list)
    economic_implications: List[str] = field(default_factory=list)


@dataclass
class PerspectiveAnalysis:
    """Analysis result from a single perspective."""
    perspective: str
    analysis: str
    focus_areas: List[str] = field(default_factory=list)
    key_concerns: List[str] = field(default_factory=list)
    key_benefits: List[str] = field(default_factory=list)
    recommendation_tendency: str = "neutral"
    confidence: int = 5
    criteria_assessments: Dict[str, str] = field(default_factory=dict)


@dataclass
class MultiPerspectiveResult:
    """Combined multi-perspective analysis result."""
    analyses: List[PerspectiveAnalysis] = field(default_factory=list)
    synthesis: str = ""
    perspectives_analyzed: List[str] = field(default_factory=list)
    consensus: str = "unknown"
    dominant_perspective: str = ""


# ==================
# Dynamic Perspective Types
# ==================

@dataclass
class DynamicPerspective:
    """A dynamically generated reviewer perspective."""
    name: str
    description: str
    focus_areas: List[str] = field(default_factory=list)
    key_questions: List[str] = field(default_factory=list)
    relevant_criteria: List[str] = field(default_factory=list)


# ==================
# Context Types (for dynamic perspective generation)
# ==================

@dataclass
class ProgramContext:
    """Context about a program for perspective generation."""
    id: int
    name: str
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    budget: Optional[float] = None
    currency: str = "USD"


@dataclass
class FormFieldContext:
    """Context about a form field for perspective generation."""
    id: str
    name: str
    field_type: str
    description: Optional[str] = None
    required: bool = False
    step_name: Optional[str] = None


@dataclass
class CriteriaContext:
    """Context about evaluation criteria for perspective generation."""
    id: int
    name: str
    description: Optional[str] = None
    weight: float = 1.0
    factors: List[str] = field(default_factory=list)


@dataclass
class PerspectiveContext:
    """Full context for generating dynamic perspectives."""
    program: ProgramContext
    form_name: Optional[str] = None
    form_fields: List[FormFieldContext] = field(default_factory=list)
    criteria: List[CriteriaContext] = field(default_factory=list)
    submission_answers: Dict[str, Any] = field(default_factory=dict)
    team_name: Optional[str] = None
    requested_amount: Optional[float] = None


# ==================
# Vote Recommendation Types
# ==================

@dataclass
class VoteRecommendation:
    """Vote recommendation with rationale (separate from analysis)."""
    recommended_vote: str  # VoteType
    confidence: int = 5
    rationale: str = ""
    key_factors: List[str] = field(default_factory=list)
    suggested_comment: str = ""
    perspective_summary: str = ""
    submission_id: str = ""



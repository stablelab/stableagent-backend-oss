"""
Pydantic schemas for Applications & Review Management.

These models mirror the TypeScript types in @forse/types/reviews.ts
and the Zod schemas in forse-growth-agent validation.
"""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ==================
# Enums and Basic Types
# ==================

ReviewStatus = Literal["pending", "approved", "rejected", "awaiting_tiebreaker"]
VoteType = Literal["approve", "reject"]
ApplicantStatus = Literal["draft", "submitted", "under_review", "approved", "rejected"]
SubmissionReviewStatus = Literal["pending", "approved", "rejected", "awaiting_tiebreaker"]


# ==================
# Vote Models
# ==================

class VoteCounts(BaseModel):
    """Vote tally for a submission."""
    totalReviewers: int
    votesNeeded: int
    approvesCount: int
    rejectsCount: int
    totalVotes: int


class Vote(BaseModel):
    """Individual vote record."""
    id: int
    submission_id: str
    reviewer_id: int
    vote: VoteType
    comment: Optional[str] = None
    voted_at: str


class VoteWithReviewer(BaseModel):
    """Vote record with reviewer information."""
    id: int
    reviewerId: int
    reviewerName: Optional[str] = None
    reviewerHandle: Optional[str] = None
    reviewerEmail: Optional[str] = None
    vote: VoteType
    comment: Optional[str] = None
    votedAt: str


# ==================
# Submission Models
# ==================

class SubmissionForReview(BaseModel):
    """Submission in the review queue."""
    id: str  # UUID
    formId: int
    formName: Optional[str] = None
    programId: int
    programName: Optional[str] = None
    teamId: int
    teamName: Optional[str] = None
    submissionTitle: Optional[str] = None
    userId: int
    userHandle: Optional[str] = None
    userEmail: Optional[str] = None
    status: str
    reviewStatus: ReviewStatus
    submittedAt: Optional[str] = None
    requestedAmount: Optional[float] = None
    aiScore: Optional[float] = None
    voteCounts: VoteCounts
    myVote: Optional[Vote] = None
    allVotes: Optional[List[VoteWithReviewer]] = None


class ReviewQueueResponse(BaseModel):
    """Response from GET /reviews/review-queue."""
    submissions: List[SubmissionForReview]
    total: int


class GetSubmissionForReviewResponse(BaseModel):
    """Response from GET /reviews/submissions/:id."""
    submission: SubmissionForReview


# ==================
# Applicant Models (from programs endpoints)
# ==================

class Applicant(BaseModel):
    """Applicant in the org-wide or program applicants list."""
    userId: int
    email: Optional[str] = None
    handle: Optional[str] = None
    teamId: Optional[int] = None
    teamName: Optional[str] = None
    formId: Optional[int] = None
    formName: Optional[str] = None
    programId: Optional[int] = None
    programName: Optional[str] = None
    status: str = "submitted"
    submittedAt: Optional[str] = None
    submissionTitle: Optional[str] = None


class ApplicantsListResponse(BaseModel):
    """Response from GET /programs/all-applicants or /programs/:id/applicants."""
    applicants: List[Applicant]


# ==================
# Submission Detail Models (for viewing full submission)
# ==================

class FormInfo(BaseModel):
    """Form metadata in submission detail."""
    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    program_id: Optional[int] = None
    program_name: Optional[str] = None


class UserInfo(BaseModel):
    """User info in submission detail."""
    id: int
    email: Optional[str] = None
    handle: Optional[str] = None


class TeamMember(BaseModel):
    """Team member in submission detail."""
    id: int
    email: Optional[str] = None
    handle: Optional[str] = None
    role: Optional[str] = None


class TeamInfo(BaseModel):
    """Team info in submission detail."""
    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    members: Optional[List[TeamMember]] = None


class CriterionScore(BaseModel):
    """Individual criterion score in AI evaluation."""
    id: int
    criterion_id: int
    criterion_name: Optional[str] = None
    criterion_description: Optional[str] = None
    raw_score: float
    weight: float = 1.0
    reasoning: Optional[str] = None
    is_error: bool = False
    error_message: Optional[str] = None


class AIEvaluation(BaseModel):
    """AI evaluation result."""
    id: int
    total_weighted_score: float
    max_possible_score: float
    normalized_score: float
    reasoning: Optional[str] = None
    evaluated_at: Optional[str] = None
    criterion_scores: Optional[List[CriterionScore]] = None


class MilestoneAnswer(BaseModel):
    """Milestone answer in submission."""
    milestone_type: str
    title: Optional[str] = None
    status: Optional[str] = None
    completion_percentage: Optional[float] = None
    success_value: Optional[float] = None
    target_date: Optional[str] = None
    answer: Optional[Dict[str, Any]] = None


class DataSource(BaseModel):
    """Data source in submission."""
    type: str
    value: str
    label: Optional[str] = None
    source: Optional[Dict[str, Any]] = None


class SubmissionDetail(BaseModel):
    """Full submission detail with all answers."""
    form: FormInfo
    user: Optional[UserInfo] = None
    team: Optional[TeamInfo] = None
    status: str = "submitted"
    submitted_at: Optional[str] = None
    submissionId: Optional[str] = None
    answers: Dict[str, Any] = Field(default_factory=dict)
    structuredAnswers: Optional[Dict[str, Dict[str, Any]]] = None
    milestoneAnswers: Optional[List[MilestoneAnswer]] = None
    data_sources: Optional[List[DataSource]] = None


class SubmissionWithEvaluationResponse(BaseModel):
    """Response from GET /programs/applicant-submission."""
    submission: SubmissionDetail
    evaluation: Optional[AIEvaluation] = None


# ==================
# My Votes Response
# ==================

class VoteWithContext(BaseModel):
    """Vote with submission context (for my-votes)."""
    id: int
    submission_id: str
    reviewer_id: int
    vote: VoteType
    comment: Optional[str] = None
    voted_at: str
    formName: Optional[str] = None
    programName: Optional[str] = None
    teamName: Optional[str] = None
    submissionStatus: Optional[str] = None
    reviewStatus: ReviewStatus


class MyVotesResponse(BaseModel):
    """Response from GET /reviews/my-votes."""
    votes: List[VoteWithContext]
    total: int


# ==================
# Vote Request/Response
# ==================

class VoteResponse(BaseModel):
    """Response from POST /reviews/vote."""
    ok: bool
    vote: Vote
    reviewStatus: str
    voteCounts: VoteCounts
    budgetWarning: Optional[str] = None


class TiebreakerResponse(BaseModel):
    """Response from POST /reviews/tiebreaker."""
    ok: bool
    decision: VoteType
    reviewStatus: str


# ==================
# Program Stats
# ==================

class ProgramStats(BaseModel):
    """Program statistics."""
    totalApplicants: int
    activeGrants: int
    timelineProgress: int


class ProgramBudget(BaseModel):
    """Program budget information."""
    totalBudget: Optional[float] = None
    allocated: float = 0
    remaining: float = 0
    percentUsed: float = 0
    currency: str = "USD"


class ProgramInfo(BaseModel):
    """Program info for stats response."""
    id: int
    name: str
    start: int
    end: int
    status: str


class ReviewerInfo(BaseModel):
    """Reviewer info in review context."""
    id: int
    email: Optional[str] = None
    handle: Optional[str] = None


class ProgramStatsResponse(BaseModel):
    """Response from GET /programs/:id/stats."""
    program: ProgramInfo
    stats: ProgramStats
    budget: ProgramBudget


# ==================
# Update Status
# ==================

class UpdateStatusResponse(BaseModel):
    """Response from PATCH /programs/:id/applicants/:userId/status."""
    ok: bool
    status: str
    projectCreated: Optional[bool] = None
    projectId: Optional[int] = None
    error: Optional[str] = None


# ==================
# Tool Input Schemas
# ==================

class ListApplicantsInput(BaseModel):
    """Input for listing all applicants."""
    status_filter: Optional[str] = Field(
        None,
        description="Optional status filter: draft, submitted, under_review, approved, rejected"
    )


class ListProgramApplicantsInput(BaseModel):
    """Input for listing applicants for a specific program."""
    program_id: int = Field(..., description="The program ID to list applicants for")


class GetSubmissionDetailsInput(BaseModel):
    """Input for getting full submission details."""
    form_id: int = Field(..., description="The form ID of the submission")
    user_id: int = Field(..., description="The user ID who submitted")
    team_id: int = Field(..., description="The team ID associated with the submission")


class GetReviewQueueInput(BaseModel):
    """Input for getting review queue."""
    program_id: Optional[int] = Field(None, description="Optional program ID to filter by")
    pending_only: bool = Field(False, description="Only show pending submissions")
    ties_only: bool = Field(False, description="Only show tied submissions (for tiebreakers)")


class GetSubmissionForReviewInput(BaseModel):
    """Input for getting a single submission for review."""
    submission_id: str = Field(..., description="The UUID of the submission to review")


class GetMyVotesInput(BaseModel):
    """Input for getting user's voting history."""
    pass  # No input required


class VoteInput(BaseModel):
    """Input for voting on a submission."""
    submission_id: str = Field(..., description="The UUID of the submission to vote on")
    comment: str = Field(
        ...,
        description="Rationale for the vote (5-500 characters)",
        min_length=5,
        max_length=500,
    )


class TiebreakerInput(BaseModel):
    """Input for tiebreaker decision."""
    submission_id: str = Field(..., description="The UUID of the tied submission")
    comment: str = Field(
        ...,
        description="Rationale for the tiebreaker decision (5-500 characters)",
        min_length=5,
        max_length=500,
    )


class UpdateApplicantStatusInput(BaseModel):
    """Input for updating applicant status."""
    program_id: int = Field(..., description="The program ID")
    user_id: int = Field(..., description="The user ID of the applicant")
    form_id: int = Field(..., description="The form ID of the submission")
    team_id: Optional[int] = Field(None, description="Optional team ID")
    status: str = Field(
        ...,
        description="New status: pending, approved, rejected"
    )


class SearchApplicationsInput(BaseModel):
    """Input for searching applications by keyword."""
    query: str = Field(..., description="Search query (e.g., 'DeFi', 'NFT', 'gaming')")
    program_id: Optional[int] = Field(None, description="Optional program ID to filter by")


# ==================
# Evaluation Criteria Models
# ==================

class ScoringRules(BaseModel):
    """Scoring rules for a criterion."""
    scale: str = "0-100"
    factors: List[str] = Field(default_factory=list)


class FormCriteria(BaseModel):
    """Evaluation criterion attached to a form."""
    id: int
    name: str
    description: Optional[str] = None
    weight: Optional[float] = None
    scoring_rules: Optional[ScoringRules] = None


class FormCriteriaListResponse(BaseModel):
    """Response from GET /criteria/forms/:formId/criteria."""
    criteria: List[FormCriteria]


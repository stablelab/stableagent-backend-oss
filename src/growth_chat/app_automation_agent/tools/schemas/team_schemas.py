"""
Pydantic models for Team Management in App Automation Agent.

Includes all types from the Teams API OpenAPI spec plus custom agent types.
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

# ===========================
# OpenAPI Spec Models
# ===========================

class User(BaseModel):
    """User model."""
    id: int
    email: EmailStr
    handle: Optional[str] = None

class TeamRole(str, Enum):
    """Team member roles."""
    ADMIN = "Admin"
    BUILDER = "Builder"
    ACCOUNT_MANAGER = "Account Manager"


class Team(BaseModel):
    """Team model."""
    id: int
    name: str
    description: Optional[str] = None
    kyc_status: str
    created_by: int
    is_personal: bool
    created_at: datetime
    updated_at: datetime


class TeamMember(BaseModel):
    """Team member model."""
    id: int
    team_id: int
    user_id: int
    role: TeamRole
    invited_by: int
    joined_at: datetime
    user: User = Field(default=None)


class TeamWithMembers(Team):
    """Team with members list."""
    members: List[TeamMember] = []
    member_count: int


class TeamInvitation(BaseModel):
    """Team invitation model."""
    id: int
    team_id: int
    email: EmailStr
    role: TeamRole
    invited_by: int
    status: str
    invited_at: str
    expires_at: str


# Request Models
class CreateTeamRequest(BaseModel):
    """Request to create a new team."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class UpdateTeamRequest(BaseModel):
    """Request to update a team."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class InviteTeamMemberRequest(BaseModel):
    """Request to invite a team member."""
    email: EmailStr
    role: TeamRole


class UpdateTeamMemberRequest(BaseModel):
    """Request to update a team member role."""
    role: TeamRole


# Response Models
class CreateTeamResponse(BaseModel):
    """Response after creating a team."""
    team: Team


class UpdateTeamResponse(BaseModel):
    """Response after updating a team."""
    team: Team


class ListTeamsResponse(BaseModel):
    """Response with list of teams."""
    teams: List[TeamWithMembers]


class GetTeamResponse(BaseModel):
    """Response with team details."""
    team: TeamWithMembers


class InviteTeamMemberResponse(BaseModel):
    """Response after inviting a team member."""
    member: Optional[TeamMember] = None  # Present when user was added immediately (invited=False)
    invitation: Optional[TeamInvitation] = None  # Present when invitation was created (invited=True)
    invited: bool  # False if user exists and was added immediately, true if invitation was created


class UpdateTeamMemberResponse(BaseModel):
    """Response after updating a team member."""
    member: TeamMember


class GetTeamInvitationsResponse(BaseModel):
    """Response with list of team invitations."""
    invitations: List[TeamInvitation]


class APIError(BaseModel):
    """API error response."""
    error: str
    message: Optional[str] = None
    status_code: int


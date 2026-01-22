"""
LangChain tools for App Automation Agent.

Wraps TeamsAPIClient and FormsAPIClient methods as LangChain tools with approval requirements
for mutating operations.
"""
from typing import Any, List, Optional, Type

from langchain_core.tools import BaseTool
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from src.utils.logger import logger

from .api_client import APIError, TeamsAPIClient
from .base import APIBaseTool  # Import from base to avoid circular import
from .form_tools import create_form_tools
from .org_tools import create_org_tools
from .perspective_tools import create_perspective_tools
from .program_tools import create_program_tools
from .review_tools import create_review_tools
from .evaluation_tools import create_evaluation_tools

# Import code execution tool from research agent
from src.growth_chat.research_agent.tools.code_execute_tool import CodeExecuteTool

# Import shared tools
from src.growth_chat.shared_tools import create_blockchain_tools

# ==================
# Tool Input Schemas
# ==================

class ListTeamsInput(BaseModel):
    """Input for listing teams."""

class GetTeamInput(BaseModel):
    """Input for getting team details."""
    team_id: int = Field(..., description="The ID of the team to retrieve")


class CreateTeamInput(BaseModel):
    """Input for creating a new team."""
    name: str = Field(..., description="The name of the new team")
    description: Optional[str] = Field(None, description="Optional description of the team")


class UpdateTeamInput(BaseModel):
    """Input for updating a team."""
    team_id: int = Field(..., description="The ID of the team to update")
    name: Optional[str] = Field(None, description="New name for the team (optional)")
    description: Optional[str] = Field(None, description="New description for the team (optional)")


class DeleteTeamInput(BaseModel):
    """Input for deleting a team."""
    team_id: int = Field(..., description="The ID of the team to delete")


class InviteTeamMemberInput(BaseModel):
    """Input for inviting a member to a team."""
    team_id: int = Field(..., description="The ID of the team")
    email: str = Field(..., description="Email address of the person to invite")
    role: str = Field(..., description="Role for the member (Admin, Builder, or Account Manager)")


class UpdateTeamMemberInput(BaseModel):
    """Input for updating a team member's role."""
    team_id: int = Field(..., description="The ID of the team")
    member_id: int = Field(..., description="The ID of the member to update")
    role: str = Field(..., description="New role for the member (Admin, Builder, or Account Manager)")


class RemoveTeamMemberInput(BaseModel):
    """Input for removing a member from a team."""
    team_id: int = Field(..., description="The ID of the team")
    member_id: int = Field(..., description="The ID of the member to remove")


class GetTeamInvitationsInput(BaseModel):
    """Input for getting team invitations."""
    team_id: int = Field(..., description="The ID of the team")


class CancelTeamInvitationInput(BaseModel):
    """Input for canceling a team invitation."""
    team_id: int = Field(..., description="The ID of the team")
    invitation_id: int = Field(..., description="The ID of the invitation to cancel")


# ==================
# Base Tool Class (imported from base.py, re-exported for compatibility)
# ==================

# APIBaseTool is imported from .base to avoid circular imports


class TeamAPIBaseTool(APIBaseTool):
    """Base class for team API tools with shared functionality and user approval."""
    _client: Optional[TeamsAPIClient] = None

    def _get_client(self) -> TeamsAPIClient:
        """Get shared Team API client instance."""
        if self._client is None:
            self._client = TeamsAPIClient()
        return self._client

# ==================
# Read-Only Tools
# ==================

class ListTeamsTool(TeamAPIBaseTool):
    """Tool for listing teams the user is part of."""
    org_slug: str = ""
    name: str = "list_teams"
    description: str = "List all teams you are part of. Returns: list of teams with name, ID and description."
    requires_approval: bool = False
    args_schema: Type[BaseModel] = ListTeamsInput
    
    def _run_tool(self) -> str:
        """List teams."""
        client = self._get_client()
        result = client.list_teams(self.auth_token, self.org_slug)
        
        # Format response
        teams = result.teams
        if not teams:
            return "You are not part of any teams."
        
        output = f"You are part of {len(teams)} team(s):\n\n"
        for team in teams:
            output += f"- {team.name} (ID: {team.id})"
            if team.description:
                output += f" - {team.description}"
            output += "\n"
        
        return output
    
    # async def _arun(self, org_slug: Optional[str] = None) -> str:
    #     """Async version."""
    #     return self._run(org_slug)


class GetTeamTool(TeamAPIBaseTool):
    """Tool for getting details of a specific team."""
    
    name: str = "get_team"
    description: str = "Get detailed information about a specific team by its ID. Returns: team name, member ID and description, and list of members with their roles."
    requires_approval: bool = False
    args_schema: Type[BaseModel] = GetTeamInput
    
    def _run_tool(self, team_id: int) -> str:
        """Get team details."""
        client = self._get_client()
        result = client.get_team(team_id, self.auth_token)
        
        # Format response
        team = result.team
        output = f"Team: {team.name} (ID: {team.id})\n"
        if team.description:
            output += f"Description: {team.description}\n"
        
        if team.members:
            output += f"\nMembers ({len(team.members)}):\n"
            for member in team.members:
                output += f"- {member.user.handle or member.user.email} ({member.role}), member ID={member.id}\n"
        else:
            output += "\nNo members in this team.\n"
        
        return output
    
    # async def _arun(self, team_id: int) -> str:
    #     """Async version."""
    #     return self._run(team_id)


class GetTeamInvitationsTool(TeamAPIBaseTool):
    """Tool for getting pending invitations for a team."""
    
    name: str = "get_team_invitations"
    description: str = "Get all pending invitations for a specific team. Returns: list of invitations with email, role and ID."
    requires_approval: bool = False
    args_schema: Type[BaseModel] = GetTeamInvitationsInput
    
    def _run_tool(self, team_id: int) -> str:
        """Get team invitations."""
        client = self._get_client()
        result = client.get_team_invitations(team_id, self.auth_token)
        
        # Format response
        invitations = result.invitations
        if not invitations:
            return f"No pending invitations for team {team_id}."
        
        output = f"Pending invitations for team {team_id} ({len(invitations)}):\n\n"
        for inv in invitations:
            output += f"- {inv.email} (Role: {inv.role}, Invitation ID: {inv.id})\n"
        
        return output
    
    # async def _arun(self, team_id: int) -> str:
    #     """Async version."""
    #     return self._run(team_id)


# ==================
# Mutating Tools (Require Approval)
# ==================

class CreateTeamTool(TeamAPIBaseTool):
    """Tool for creating a new team."""
    
    name: str = "create_team"
    description: str = "Create a new team in your organization. Requires user approval."
    args_schema: Type[BaseModel] = CreateTeamInput
    requires_approval: bool = True
    org_slug: str = ""  # Will be set from user's session context
    
    def _run_tool(self, name: str, description: Optional[str] = None) -> str:
        """Create a team in the user's organization."""
        if not self.org_slug:
            return "Error: Organization slug not available. Please ensure you are logged in with an organization."
        
        client = self._get_client()
        result = client.create_team(self.org_slug, name, self.auth_token, description)
        return f"Successfully created team '{result.team.name}' (ID: {result.team.id})"

    # async def _arun(self, name: str, description: Optional[str] = None) -> str:
    #     """Async version."""
    #     return self._run(name, description)


class UpdateTeamTool(TeamAPIBaseTool):
    """Tool for updating a team."""
    
    name: str = "update_team"
    description: str = "Update a team's name or description. Requires user approval."
    args_schema: Type[BaseModel] = UpdateTeamInput
    requires_approval: bool = True
    
    def _run_tool(self, team_id: int, name: Optional[str] = None, description: Optional[str] = None) -> str:
        """Update a team."""
        client = self._get_client()
        result = client.update_team(team_id, self.auth_token, name, description)
        
        return f"Successfully updated team '{result.team.name}' (team ID={result.team.id})."
    
    # async def _arun(self, team_id: int, name: Optional[str] = None, description: Optional[str] = None) -> str:
    #     """Async version."""
    #     return self._run(team_id, name, description)


class DeleteTeamTool(TeamAPIBaseTool):
    """Tool for deleting a team."""
    
    name: str = "delete_team"
    description: str = "Delete a team. This is permanent and requires user approval."
    args_schema: Type[BaseModel] = DeleteTeamInput
    requires_approval: bool = True
    
    def _run_tool(self, team_id: int) -> str:
        """Delete a team."""
        client = self._get_client()
        client.delete_team(team_id, self.auth_token)
        
        return f"Successfully deleted team ID={team_id}."
    
    # async def _arun(self, team_id: int) -> str:
    #     """Async version."""
    #     return self._run(team_id)


class InviteTeamMemberTool(TeamAPIBaseTool):
    """Tool for inviting a member to a team."""
    
    name: str = "invite_team_member"
    description: str = "Invite someone to a team with a specific role (Admin, Builder, or Account Manager). Requires user approval."
    args_schema: Type[BaseModel] = InviteTeamMemberInput
    requires_approval: bool = True
    
    def _run_tool(self, team_id: int, email: str, role: str) -> str:
        """Invite a team member."""
        client = self._get_client()
        result = client.invite_team_member(team_id, email, role, self.auth_token)
        
        if result.invitation:
            return f"Successfully sent invitation email to {email} to team ID={team_id} as {role} (invitation ID: {result.invitation.id})."
        else:
            return f"Successfully added {email} (user ID={result.member.user_id}) to team ID={team_id} as {role}"
    
    # async def _arun(self, team_id: int, email: str, role: str) -> str:
    #     """Async version."""
    #     return self._run(team_id, email, role)


class UpdateTeamMemberTool(TeamAPIBaseTool):
    """Tool for updating a team member's role."""
    
    name: str = "update_team_member"
    description: str = "Update a team member's role. Requires user approval."
    args_schema: Type[BaseModel] = UpdateTeamMemberInput
    requires_approval: bool = True
    
    def _run_tool(self, team_id: int, member_id: int, role: str) -> str:
        """Update a team member."""
        client = self._get_client()
        result = client.update_team_member(team_id, member_id, role, self.auth_token)
        
        return f"Successfully updated member {result.member.user.handle or result.member.user.email} to role: {result.member.role}"
    
    # async def _arun(self, team_id: int, member_id: int, role: str) -> str:
    #     """Async version."""
    #     return self._run(team_id, member_id, role)


class RemoveTeamMemberTool(TeamAPIBaseTool):
    """Tool for removing a member from a team."""
    
    name: str = "remove_team_member"
    description: str = "Remove a member from a team. Requires user approval."
    args_schema: Type[BaseModel] = RemoveTeamMemberInput
    requires_approval: bool = True
    
    def _run_tool(self, team_id: int, member_id: int) -> str:
        """Remove a team member."""
        client = self._get_client()
        client.remove_team_member(team_id, member_id, self.auth_token)
        
        return f"Successfully removed member ID={member_id} from team ID={team_id}"
    
    # async def _arun(self, team_id: int, member_id: int) -> str:
    #     """Async version."""
    #     return self._run(team_id, member_id)


class CancelTeamInvitationTool(TeamAPIBaseTool):
    """Tool for canceling a team invitation."""
    
    name: str = "cancel_team_invitation"
    description: str = "Cancel a pending team invitation. Requires user approval."
    args_schema: Type[BaseModel] = CancelTeamInvitationInput
    requires_approval: bool = True
    
    def _run_tool(self, team_id: int, invitation_id: int) -> str:
        """Cancel a team invitation."""
        client = self._get_client()
        client.cancel_team_invitation(team_id, invitation_id, self.auth_token)
        
        return f"Successfully canceled invitation ID={invitation_id} for team ID={team_id}"
    
    # async def _arun(self, team_id: int, invitation_id: int) -> str:
    #     """Async version."""
    #     return self._run_tool(team_id, invitation_id)


# ==================
# Tool Factory
# ==================

def create_team_tools(auth_token: str, org_id: int = 0, org_slug: str = "") -> List[TeamAPIBaseTool]:
    """
    Create all team management tools with the given auth token and org_id.
    
    Args:
        auth_token: Privy authentication token
        org_id: Organization ID (derived from user's session context)
        org_slug: Organization slug
        
    Returns:
        List of team tool instances
    """
    tools = [
        # Read-only tools
        ListTeamsTool(auth_token=auth_token, org_slug=org_slug),
        GetTeamTool(auth_token=auth_token),
        GetTeamInvitationsTool(auth_token=auth_token),
        # Mutating tools (require approval)
        CreateTeamTool(auth_token=auth_token, org_slug=org_slug),
        UpdateTeamTool(auth_token=auth_token),
        DeleteTeamTool(auth_token=auth_token),
        InviteTeamMemberTool(auth_token=auth_token),
        UpdateTeamMemberTool(auth_token=auth_token),
        RemoveTeamMemberTool(auth_token=auth_token),
        CancelTeamInvitationTool(auth_token=auth_token),
    ]
    
    return tools


def create_all_tools(
    auth_token: str, 
    org_id: int = 0, 
    org_slug: str = "", 
    is_global_admin: bool = False
) -> List[BaseTool]:
    """
    Create all app automation tools (teams + forms + programs + reviews + perspective analysis + 
    org management + evaluation + code execution + blockchain) with the given auth token and org context.
    
    Args:
        auth_token: Privy authentication token
        org_id: Organization ID (derived from user's session context)
        org_slug: Organization slug
        is_global_admin: Whether the user has Global Admin privileges (for org admin tools)
        
    Returns:
        List of all tool instances (team + form + program + review + perspective + org + ai evaluation + code execution + blockchain tools)
    """
    team_tools = create_team_tools(auth_token, org_id, org_slug)
    form_tools = create_form_tools(auth_token, org_id, org_slug)
    program_tools = create_program_tools(auth_token, org_slug, org_id)
    review_tools = create_review_tools(auth_token, org_slug)
    perspective_tools = create_perspective_tools(auth_token, org_slug)
    org_tools = create_org_tools(auth_token, org_id, org_slug, is_global_admin=is_global_admin)
    evaluation_tools = create_evaluation_tools(auth_token, org_id, org_slug)
    
    # Code execution tool (uses Claude Sonnet for code generation/analysis)
    code_execute_tool = CodeExecuteTool()
    
    # Shared blockchain tools (read-only access to org's on-chain proposals)
    blockchain_tools = create_blockchain_tools(auth_token=auth_token, org_slug=org_slug) if org_slug else []
    
    return [*team_tools, *form_tools, *program_tools, *review_tools, *perspective_tools, *org_tools, *evaluation_tools, code_execute_tool, *blockchain_tools]


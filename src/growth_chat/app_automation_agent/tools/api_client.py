"""
HTTP client for Teams API endpoints.

Handles all API communication with proper authentication and error handling.
"""
from typing import Any, Dict, Optional

from .base_api_client import APIError, BaseAPIClient
from .schemas import (
    CreateTeamRequest,
    CreateTeamResponse,
    GetTeamInvitationsResponse,
    GetTeamResponse,
    InviteTeamMemberRequest,
    InviteTeamMemberResponse,
    ListTeamsResponse,
    UpdateTeamMemberRequest,
    UpdateTeamMemberResponse,
    UpdateTeamRequest,
    UpdateTeamResponse,
)

# Re-export APIError for backward compatibility
__all__ = ["APIError", "TeamsAPIClient"]


class TeamsAPIClient(BaseAPIClient):
    """Client for interacting with Teams API."""
    
    # ==================
    # Teams Endpoints
    # ==================
    
    def list_teams(self, auth_token: str, org_slug: Optional[str] = None) -> ListTeamsResponse:
        """
        List teams for authenticated user.
        
        Args:
            auth_token: Privy authentication token
            org_slug: Optional organization slug to filter teams
            
        Returns:
            ListTeamsResponse with teams
        """
        url = f"{self.base_url}/api/teams"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        data = self._handle_response(response)
        return ListTeamsResponse(**data)
    
    def get_team(self, team_id: int, auth_token: str) -> GetTeamResponse:
        """
        Get team details.
        
        Args:
            team_id: Team ID
            auth_token: Privy authentication token
            
        Returns:
            GetTeamResponse with team details
        """
        url = f"{self.base_url}/api/teams/{team_id}"
        
        response = self.client.get(url, headers=self._get_headers(auth_token))
        data = self._handle_response(response)
        return GetTeamResponse(**data)
    
    def create_team(
        self,
        org_slug: str,
        name: str,
        auth_token: str,
        description: Optional[str] = None,
    ) -> CreateTeamResponse:
        """
        Create a new team.
        
        Args:
            org_slug: Organization slug (used for ensureOrgMiddleware)
            name: Team name
            auth_token: Privy authentication token
            description: Optional team description
            
        Returns:
            CreateTeamResponse with created team
        """
        url = f"{self.base_url}/api/teams"
        params = {"org": org_slug}
        body = CreateTeamRequest(name=name, description=description).model_dump(exclude_none=True)
        
        response = self.client.post(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json=body
        )
        data = self._handle_response(response)
        return CreateTeamResponse(**data)
    
    def update_team(
        self,
        team_id: int,
        auth_token: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> UpdateTeamResponse:
        """
        Update team details.
        
        Args:
            team_id: Team ID
            auth_token: Privy authentication token
            name: Optional new team name
            description: Optional new team description
            
        Returns:
            UpdateTeamResponse with updated team
        """
        url = f"{self.base_url}/api/teams/{team_id}"
        body = UpdateTeamRequest(name=name, description=description).model_dump(exclude_none=True)
        
        response = self.client.patch(url, headers=self._get_headers(auth_token), json=body)
        data = self._handle_response(response)
        return UpdateTeamResponse(**data)
    
    def delete_team(self, team_id: int, auth_token: str) -> Dict[str, Any]:
        """
        Delete a team.
        
        Args:
            team_id: Team ID
            auth_token: Privy authentication token
            
        Returns:
            Success dictionary
        """
        url = f"{self.base_url}/api/teams/{team_id}"
        
        response = self.client.delete(url, headers=self._get_headers(auth_token))
        return self._handle_response(response)
    
    # ==================
    # Team Members Endpoints
    # ==================
    
    def invite_team_member(
        self,
        team_id: int,
        email: str,
        role: str,
        auth_token: str,
    ) -> InviteTeamMemberResponse:
        """
        Invite a team member.
        
        Args:
            team_id: Team ID
            email: Email address to invite
            role: Team role (Admin, Builder, Account Manager)
            auth_token: Privy authentication token
            
        Returns:
            InviteTeamMemberResponse with member details
        """
        url = f"{self.base_url}/api/teams/{team_id}/members"
        body = InviteTeamMemberRequest(email=email, role=role).model_dump()
        
        response = self.client.post(url, headers=self._get_headers(auth_token), json=body)
        data = self._handle_response(response)
        
        return InviteTeamMemberResponse(**data)
    
    def update_team_member(
        self,
        team_id: int,
        member_id: int,
        role: str,
        auth_token: str,
    ) -> UpdateTeamMemberResponse:
        """
        Update team member role.
        
        Args:
            team_id: Team ID
            member_id: Member ID
            role: New team role
            auth_token: Privy authentication token
            
        Returns:
            UpdateTeamMemberResponse with updated member
        """
        url = f"{self.base_url}/api/teams/{team_id}/members/{member_id}"
        body = UpdateTeamMemberRequest(role=role).model_dump()
        
        response = self.client.patch(url, headers=self._get_headers(auth_token), json=body)
        data = self._handle_response(response)
        return UpdateTeamMemberResponse(**data)
    
    def remove_team_member(
        self,
        team_id: int,
        member_id: int,
        auth_token: str,
    ) -> Dict[str, Any]:
        """
        Remove team member.
        
        Args:
            team_id: Team ID
            member_id: Member ID
            auth_token: Privy authentication token
            
        Returns:
            Success dictionary
        """
        url = f"{self.base_url}/api/teams/{team_id}/members/{member_id}"
        
        response = self.client.delete(url, headers=self._get_headers(auth_token))
        return self._handle_response(response)
    
    # ==================
    # Team Invitations Endpoints
    # ==================
    
    def get_team_invitations(
        self,
        team_id: int,
        auth_token: str,
    ) -> GetTeamInvitationsResponse:
        """
        Get pending team invitations.
        
        Args:
            team_id: Team ID
            auth_token: Privy authentication token
            
        Returns:
            GetTeamInvitationsResponse with invitations
        """
        url = f"{self.base_url}/api/teams/{team_id}/invitations"
        
        response = self.client.get(url, headers=self._get_headers(auth_token))
        data = self._handle_response(response)
        return GetTeamInvitationsResponse(**data)
    
    def cancel_team_invitation(
        self,
        team_id: int,
        invitation_id: int,
        auth_token: str,
    ) -> Dict[str, Any]:
        """
        Cancel team invitation.
        
        Args:
            team_id: Team ID
            invitation_id: Invitation ID
            auth_token: Privy authentication token
            
        Returns:
            Success dictionary
        """
        url = f"{self.base_url}/api/teams/{team_id}/invitations/{invitation_id}"
        
        response = self.client.delete(url, headers=self._get_headers(auth_token))
        return self._handle_response(response)

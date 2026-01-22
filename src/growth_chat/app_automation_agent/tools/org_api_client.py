"""
HTTP client for Organization API endpoints.

Handles branding, access configuration, org users, and form templates.
Extends BaseAPIClient.
"""
from typing import Any, Dict, List, Optional

from .base_api_client import APIError, BaseAPIClient


class OrgAPIClient(BaseAPIClient):
    """Client for interacting with Organization API endpoints."""
    
    # ==================
    # Branding Endpoints
    # ==================
    
    def get_branding(self, auth_token: str, org_slug: str) -> Dict[str, Any]:
        """
        Get branding settings for an organization.
        
        Args:
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            Branding settings dict
        """
        url = f"{self.base_url}/api/branding"
        params = {"org": org_slug}
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        return self._handle_response(response)
    
    def update_branding(
        self,
        auth_token: str,
        org_slug: str,
        logo_url: Optional[str] = None,
        favicon_url: Optional[str] = None,
        color_primary: Optional[str] = None,
        color_secondary: Optional[str] = None,
        theme_mode: Optional[str] = None,
        custom_domain: Optional[str] = None,
        email_sender_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update branding settings for an organization.
        
        Args:
            auth_token: Privy authentication token
            org_slug: Organization slug
            logo_url: URL to org logo
            favicon_url: URL to favicon
            color_primary: Primary brand color (hex)
            color_secondary: Secondary brand color (hex)
            theme_mode: Theme mode (light, dark, auto)
            custom_domain: Custom domain for the org
            email_sender_name: Sender name for emails
            
        Returns:
            Updated branding settings
        """
        url = f"{self.base_url}/api/branding"
        params = {"org": org_slug}
        
        body = {}
        if logo_url is not None:
            body["logo_url"] = logo_url
        if favicon_url is not None:
            body["favicon_url"] = favicon_url
        if color_primary is not None:
            body["color_primary"] = color_primary
        if color_secondary is not None:
            body["color_secondary"] = color_secondary
        if theme_mode is not None:
            body["theme_mode"] = theme_mode
        if custom_domain is not None:
            body["custom_domain"] = custom_domain
        if email_sender_name is not None:
            body["email_sender_name"] = email_sender_name
        
        response = self.client.patch(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json=body
        )
        return self._handle_response(response)
    
    # ==================
    # Access Configuration Endpoints (Global Admin Only)
    # ==================
    
    def get_org_details(self, auth_token: str, org_id: int) -> Dict[str, Any]:
        """
        Get organization details including access configuration.
        NOTE: This requires Global Admin privileges.
        
        Args:
            auth_token: Privy authentication token
            org_id: Organization ID
            
        Returns:
            Organization details dict
        """
        # There's no direct /api/admin/orgs/{id} endpoint, use organisations list instead
        url = f"{self.base_url}/api/admin/organisations/{org_id}/users"
        
        response = self.client.get(url, headers=self._get_headers(auth_token))
        return self._handle_response(response)
    
    # ==================
    # Org Users Endpoints (Global Admin Only)
    # ==================
    
    def list_org_users(self, auth_token: str, org_id: int) -> Dict[str, Any]:
        """
        List all users in an organization.
        NOTE: This requires Global Admin privileges.
        
        Args:
            auth_token: Privy authentication token
            org_id: Organization ID
            
        Returns:
            List of org users with roles
        """
        url = f"{self.base_url}/api/admin/organisations/{org_id}/users"
        
        response = self.client.get(url, headers=self._get_headers(auth_token))
        return self._handle_response(response)
    
    def list_org_teams(self, auth_token: str, org_id: int) -> Dict[str, Any]:
        """
        List all teams in an organization.
        NOTE: This requires Global Admin privileges.
        
        Args:
            auth_token: Privy authentication token
            org_id: Organization ID
            
        Returns:
            List of org teams with roles
        """
        url = f"{self.base_url}/api/admin/organisations/{org_id}/teams"
        
        response = self.client.get(url, headers=self._get_headers(auth_token))
        return self._handle_response(response)
    
    def invite_to_org(
        self,
        auth_token: str,
        org_id: int,
        team_id: int,
        role_id: int,
    ) -> Dict[str, Any]:
        """
        Assign a team to an organization with a role.
        NOTE: This requires Global Admin privileges.
        
        Args:
            auth_token: Privy authentication token
            org_id: Organization ID
            team_id: Team ID to assign
            role_id: Role ID to assign (1=Superadmin, 2=Admin, 3=Staff, 4=Builder)
            
        Returns:
            Assignment result
        """
        url = f"{self.base_url}/api/admin/org-teams"
        body = {
            "id_org": org_id,
            "team_id": team_id,
            "role_id": role_id,
        }
        
        response = self.client.post(
            url,
            headers=self._get_headers(auth_token),
            json=body
        )
        return self._handle_response(response)
    
    def remove_from_org(
        self,
        auth_token: str,
        org_id: int,
        team_id: int,
    ) -> Dict[str, Any]:
        """
        Remove a team from an organization.
        NOTE: This requires Global Admin privileges.
        
        Args:
            auth_token: Privy authentication token
            org_id: Organization ID
            team_id: Team ID to remove
            
        Returns:
            Removal result
        """
        url = f"{self.base_url}/api/admin/org-teams"
        
        # DELETE with body using request method
        response = self.client.request(
            "DELETE",
            url,
            headers=self._get_headers(auth_token),
            json={"id_org": org_id, "team_id": team_id}
        )
        return self._handle_response(response)
    
    def set_org_role(
        self,
        auth_token: str,
        org_id: int,
        team_id: int,
        role_id: int,
    ) -> Dict[str, Any]:
        """
        Update a team's role in an organization.
        NOTE: This requires Global Admin privileges.
        
        Args:
            auth_token: Privy authentication token
            org_id: Organization ID
            team_id: Team ID
            role_id: New role ID (1=Superadmin, 2=Admin, 3=Staff, 4=Builder)
            
        Returns:
            Updated assignment
        """
        url = f"{self.base_url}/api/admin/org-teams"
        body = {
            "id_org": org_id,
            "team_id": team_id,
            "role_id": role_id,
        }
        
        response = self.client.put(
            url,
            headers=self._get_headers(auth_token),
            json=body
        )
        return self._handle_response(response)
    
    # ==================
    # Form Templates Endpoints
    # ==================
    
    def get_form_templates(self, auth_token: str) -> Dict[str, Any]:
        """
        Get available form templates.
        
        Args:
            auth_token: Privy authentication token
            
        Returns:
            List of form templates with metadata
        """
        url = f"{self.base_url}/api/forms/templates"
        
        response = self.client.get(url, headers=self._get_headers(auth_token))
        return self._handle_response(response)
    
    # ==================
    # Programs for Application
    # ==================
    
    def list_available_programs(self, auth_token: str, org_slug: str) -> Dict[str, Any]:
        """
        List programs available for application in an organization.
        Requires submission.create permission.
        
        Args:
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            List of programs open for application
        """
        url = f"{self.base_url}/api/programs/for-apply"
        params = {"org": org_slug}
        
        response = self.client.get(
            url,
            headers=self._get_headers(auth_token),
            params=params
        )
        return self._handle_response(response)

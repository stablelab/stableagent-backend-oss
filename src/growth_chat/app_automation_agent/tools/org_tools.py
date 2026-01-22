"""
LangChain tools for Organization management.

Includes branding, access configuration, org users/roles, and form templates.
"""
from typing import Any, List, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logger import logger

from .api_client import APIError
from .org_api_client import OrgAPIClient
from .base import APIBaseTool


# ==================
# Tool Input Schemas
# ==================

class GetBrandingInput(BaseModel):
    """Input for getting branding settings."""
    pass


class UpdateBrandingInput(BaseModel):
    """Input for updating branding settings."""
    logo_url: Optional[str] = Field(None, description="URL to the organization logo image")
    favicon_url: Optional[str] = Field(None, description="URL to the favicon image")
    color_primary: Optional[str] = Field(None, description="Primary brand color in hex format (e.g., #FF5500)")
    color_secondary: Optional[str] = Field(None, description="Secondary brand color in hex format")
    theme_mode: Optional[str] = Field(None, description="Theme mode: 'light', 'dark', or 'auto'")
    custom_domain: Optional[str] = Field(None, description="Custom domain for the organization (e.g., grants.myorg.com)")
    email_sender_name: Optional[str] = Field(None, description="Name to use as email sender")


class GetOrgAccessInput(BaseModel):
    """Input for getting org access configuration."""
    pass


class ListOrgUsersInput(BaseModel):
    """Input for listing org users."""
    pass


class InviteToOrgInput(BaseModel):
    """Input for inviting a team to an organization."""
    team_id: int = Field(..., description="The ID of the team to invite")
    role_id: int = Field(..., description="Role ID: 1=Superadmin, 2=Admin, 3=Staff, 4=Builder")


class RemoveFromOrgInput(BaseModel):
    """Input for removing a team from an organization."""
    team_id: int = Field(..., description="The ID of the team to remove")


class SetOrgRoleInput(BaseModel):
    """Input for setting a team's role in an organization."""
    team_id: int = Field(..., description="The ID of the team")
    role_id: int = Field(..., description="New role ID: 1=Superadmin, 2=Admin, 3=Staff, 4=Builder")


class GetFormTemplatesInput(BaseModel):
    """Input for getting form templates."""
    pass


class ListAvailableProgramsInput(BaseModel):
    """Input for listing available programs."""
    pass


# ==================
# Base Tool Class
# ==================

class OrgAPIBaseTool(APIBaseTool):
    """Base class for organization API tools."""
    _client: Optional[OrgAPIClient] = None
    org_id: int = 0
    org_slug: str = ""

    def _get_client(self) -> OrgAPIClient:
        """Get shared Org API client instance."""
        if self._client is None:
            self._client = OrgAPIClient()
        return self._client


# ==================
# Branding Tools
# ==================

class GetBrandingTool(OrgAPIBaseTool):
    """Tool for getting organization branding settings."""
    
    name: str = "get_org_branding"
    description: str = "Get the current branding settings (logo, colors, theme) for the organization."
    requires_approval: bool = False
    args_schema: Type[BaseModel] = GetBrandingInput
    
    def _run_tool(self) -> str:
        """Get branding settings."""
        if not self.org_slug:
            return "Error: Organization slug not available."
        
        client = self._get_client()
        result = client.get_branding(self.auth_token, self.org_slug)
        
        # Format response
        output = "Current branding settings:\n\n"
        output += f"- Logo URL: {result.get('logo_url', 'Not set')}\n"
        output += f"- Favicon URL: {result.get('favicon_url', 'Not set')}\n"
        output += f"- Primary Color: {result.get('color_primary', 'Not set')}\n"
        output += f"- Secondary Color: {result.get('color_secondary', 'Not set')}\n"
        output += f"- Theme Mode: {result.get('theme_mode', 'auto')}\n"
        output += f"- Custom Domain: {result.get('custom_domain', 'Not set')}\n"
        output += f"- Email Sender Name: {result.get('email_sender_name', 'Not set')}\n"
        
        return output


class UpdateBrandingTool(OrgAPIBaseTool):
    """Tool for updating organization branding settings."""
    
    name: str = "update_org_branding"
    description: str = "Update branding settings like logo, colors, theme mode, custom domain, etc. Requires user approval."
    requires_approval: bool = True
    args_schema: Type[BaseModel] = UpdateBrandingInput
    
    def _run_tool(
        self,
        logo_url: Optional[str] = None,
        favicon_url: Optional[str] = None,
        color_primary: Optional[str] = None,
        color_secondary: Optional[str] = None,
        theme_mode: Optional[str] = None,
        custom_domain: Optional[str] = None,
        email_sender_name: Optional[str] = None,
    ) -> str:
        """Update branding settings."""
        if not self.org_slug:
            return "Error: Organization slug not available."
        
        client = self._get_client()
        result = client.update_branding(
            self.auth_token,
            self.org_slug,
            logo_url=logo_url,
            favicon_url=favicon_url,
            color_primary=color_primary,
            color_secondary=color_secondary,
            theme_mode=theme_mode,
            custom_domain=custom_domain,
            email_sender_name=email_sender_name,
        )
        
        return f"Successfully updated branding settings for organization."


# ==================
# Access Configuration Tools (Global Admin Only)
# ==================

class GetOrgAccessTool(OrgAPIBaseTool):
    """Tool for getting organization access configuration. Requires Global Admin."""
    
    name: str = "get_org_access"
    description: str = "Get organization user information. NOTE: Requires Global Admin privileges."
    requires_approval: bool = False
    args_schema: Type[BaseModel] = GetOrgAccessInput
    
    def _run_tool(self) -> str:
        """Get org access configuration."""
        if not self.org_id:
            return "Error: Organization ID not available."
        
        client = self._get_client()
        result = client.get_org_details(self.auth_token, self.org_id)
        
        users = result.get("users", [])
        
        output = f"Organization users ({len(users)}):\n\n"
        for user in users:
            output += f"- {user.get('email', 'Unknown')} (ID: {user.get('id', 'N/A')})\n"
        
        return output


# ==================
# Org Users Tools (Global Admin Only)
# ==================

class ListOrgUsersTool(OrgAPIBaseTool):
    """Tool for listing organization teams. Requires Global Admin."""
    
    name: str = "list_org_teams"
    description: str = "List all teams in the organization with their roles. NOTE: Requires Global Admin privileges."
    requires_approval: bool = False
    args_schema: Type[BaseModel] = ListOrgUsersInput
    
    def _run_tool(self) -> str:
        """List org teams."""
        if not self.org_id:
            return "Error: Organization ID not available."
        
        client = self._get_client()
        result = client.list_org_teams(self.auth_token, self.org_id)
        
        teams = result.get("teams", result.get("orgTeams", []))
        if not teams:
            return "No teams found in this organization."
        
        output = f"Teams in organization ({len(teams)}):\n\n"
        
        role_names = {1: "Superadmin", 2: "Admin", 3: "Staff", 4: "Builder"}
        
        for team_entry in teams:
            team = team_entry.get("team", team_entry)
            role_id = team_entry.get("role_id", team_entry.get("roleId", 4))
            role_name = role_names.get(role_id, f"Role {role_id}")
            
            output += f"- {team.get('name', 'Unknown')} (Team ID: {team.get('id', 'N/A')}) - {role_name}\n"
        
        return output


class InviteToOrgTool(OrgAPIBaseTool):
    """Tool for inviting a team to an organization. Requires Global Admin."""
    
    name: str = "invite_to_org"
    description: str = """Assign a team to this organization with a specific role.
Role IDs: 1=Superadmin, 2=Admin, 3=Staff, 4=Builder
NOTE: Requires Global Admin privileges. Requires user approval."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = InviteToOrgInput
    
    def _run_tool(self, team_id: int, role_id: int) -> str:
        """Invite team to org."""
        if not self.org_id:
            return "Error: Organization ID not available."
        
        role_names = {1: "Superadmin", 2: "Admin", 3: "Staff", 4: "Builder"}
        if role_id not in role_names:
            return f"Error: Invalid role_id. Must be one of: {list(role_names.keys())}"
        
        client = self._get_client()
        result = client.invite_to_org(self.auth_token, self.org_id, team_id, role_id)
        
        return f"Successfully assigned team ID={team_id} to organization with role '{role_names[role_id]}'."


class RemoveFromOrgTool(OrgAPIBaseTool):
    """Tool for removing a team from an organization. Requires Global Admin."""
    
    name: str = "remove_from_org"
    description: str = "Remove a team from the organization. NOTE: Requires Global Admin privileges. Requires user approval."
    requires_approval: bool = True
    args_schema: Type[BaseModel] = RemoveFromOrgInput
    
    def _run_tool(self, team_id: int) -> str:
        """Remove team from org."""
        if not self.org_id:
            return "Error: Organization ID not available."
        
        client = self._get_client()
        result = client.remove_from_org(self.auth_token, self.org_id, team_id)
        
        return f"Successfully removed team ID={team_id} from organization."


class SetOrgRoleTool(OrgAPIBaseTool):
    """Tool for setting a team's role in an organization. Requires Global Admin."""
    
    name: str = "set_org_role"
    description: str = """Update a team's role in the organization.
Role IDs: 1=Superadmin, 2=Admin, 3=Staff, 4=Builder
NOTE: Requires Global Admin privileges. Requires user approval."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = SetOrgRoleInput
    
    def _run_tool(self, team_id: int, role_id: int) -> str:
        """Set team's org role."""
        if not self.org_id:
            return "Error: Organization ID not available."
        
        role_names = {1: "Superadmin", 2: "Admin", 3: "Staff", 4: "Builder"}
        if role_id not in role_names:
            return f"Error: Invalid role_id. Must be one of: {list(role_names.keys())}"
        
        client = self._get_client()
        result = client.set_org_role(self.auth_token, self.org_id, team_id, role_id)
        
        return f"Successfully updated team ID={team_id} to role '{role_names[role_id]}'."


# ==================
# Form Template Tools
# ==================

class GetFormTemplatesTool(OrgAPIBaseTool):
    """Tool for getting available form templates."""
    
    name: str = "get_form_templates"
    description: str = "Get a list of available form templates that can be used to quickly create grant application forms."
    requires_approval: bool = False
    args_schema: Type[BaseModel] = GetFormTemplatesInput
    
    def _run_tool(self) -> str:
        """Get form templates."""
        client = self._get_client()
        result = client.get_form_templates(self.auth_token)
        
        templates = result.get("templates", [])
        if not templates:
            return "No form templates available."
        
        output = f"Available form templates ({len(templates)}):\n\n"
        
        for template in templates:
            output += f"**{template.get('name', 'Unknown')}** (ID: {template.get('id', 'N/A')})\n"
            output += f"  Category: {template.get('category', 'N/A')}\n"
            output += f"  Steps: {template.get('stepCount', 'N/A')}\n"
            output += f"  Est. Time: {template.get('estimatedTimeMinutes', 'N/A')} minutes\n"
            output += f"  {template.get('description', '')}\n"
            if template.get('tags'):
                output += f"  Tags: {', '.join(template['tags'])}\n"
            output += "\n"
        
        return output


# ==================
# Programs Tool
# ==================

class ListAvailableProgramsTool(OrgAPIBaseTool):
    """Tool for listing programs available for application."""
    
    name: str = "list_available_programs"
    description: str = "List grant programs that are currently open for applications in this organization."
    requires_approval: bool = False
    args_schema: Type[BaseModel] = ListAvailableProgramsInput
    
    def _run_tool(self) -> str:
        """List available programs."""
        if not self.org_slug:
            return "Error: Organization slug not available."
        
        client = self._get_client()
        result = client.list_available_programs(self.auth_token, self.org_slug)
        
        programs = result.get("programs", result.get("data", []))
        if not programs:
            return "No programs are currently open for applications."
        
        output = f"Programs open for application ({len(programs)}):\n\n"
        
        for program in programs:
            output += f"**{program.get('name', 'Unknown')}** (ID: {program.get('id', 'N/A')})\n"
            if program.get('description'):
                output += f"  {program['description'][:200]}{'...' if len(program.get('description', '')) > 200 else ''}\n"
            if program.get('deadline'):
                output += f"  Deadline: {program['deadline']}\n"
            output += "\n"
        
        return output


# ==================
# Tool Factory
# ==================

def create_org_tools(auth_token: str, org_id: int = 0, org_slug: str = "", is_global_admin: bool = False) -> List[OrgAPIBaseTool]:
    """
    Create organization management tools.
    
    NOTE: Most org management tools require Global Admin privileges.
    Only branding and form templates are available to non-admin users.
    
    Args:
        auth_token: Privy authentication token
        org_id: Organization ID
        org_slug: Organization slug
        is_global_admin: Whether the user is a Global Admin
        
    Returns:
        List of org tool instances
    """
    # Basic tools available to all org admins
    tools = [
        # Branding tools
        GetBrandingTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
        UpdateBrandingTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
        # Form template tools
        GetFormTemplatesTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
        # Program tools
        ListAvailableProgramsTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
    ]
    
    # Global Admin only tools
    if is_global_admin:
        tools.extend([
            # Access tools
            GetOrgAccessTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
            # Org team management tools
            ListOrgUsersTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
            InviteToOrgTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
            RemoveFromOrgTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
            SetOrgRoleTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
        ])
    
    return tools


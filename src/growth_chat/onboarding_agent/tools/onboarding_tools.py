"""
Onboarding-specific LangChain tools.

These tools are specific to the onboarding flow and handle progress tracking,
step completion, and navigation within the onboarding process.
"""
import os
from typing import Any, Dict, List, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
import httpx

from src.utils.logger import logger
from src.growth_chat.app_automation_agent.tools.base import APIBaseTool
from src.growth_chat.app_automation_agent.tools.api_client import APIError

# Note: create_all_tools is imported lazily inside create_onboarding_tools to avoid circular import


# ==================
# Tool Input Schemas
# ==================

class GetOnboardingStatusInput(BaseModel):
    """Input for getting onboarding status."""
    pass


class CompleteOnboardingStepInput(BaseModel):
    """Input for completing an onboarding step."""
    step: str = Field(..., description="The step to mark as complete (e.g., 'welcome', 'branding', 'program_creation')")
    data: Optional[Dict[str, Any]] = Field(None, description="Optional data to save for this step")


class SaveOnboardingStepDataInput(BaseModel):
    """Input for saving step data without completing."""
    step: str = Field(..., description="The step to save data for")
    data: Dict[str, Any] = Field(..., description="Data to save for this step")


class SkipOnboardingStepInput(BaseModel):
    """Input for skipping an onboarding step."""
    step: Optional[str] = Field(None, description="Optional specific step to skip. If not provided, skips current step.")


class ResetOnboardingInput(BaseModel):
    """Input for resetting onboarding progress."""
    pass


class SkipAllOnboardingInput(BaseModel):
    """Input for skipping all remaining onboarding steps."""
    pass


class StartOnboardingInput(BaseModel):
    """Input for starting a new onboarding flow."""
    flow_type: str = Field(
        ..., 
        description="The type of onboarding flow: 'admin_setup' (for org admins) or 'user_joining' (for new users joining an org)"
    )


class StartGrantApplicationInput(BaseModel):
    """Input for starting a grant application."""
    program_id: int = Field(..., description="The ID of the program to apply for")


# ==================
# API Client
# ==================

class OnboardingAPIClient:
    """Client for interacting with Onboarding API endpoints."""
    
    def __init__(self, base_url: str = os.getenv("GROWTH_BACKEND_URL", "http://localhost:4000")):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=30.0)
    
    def _get_headers(self, auth_token: str) -> Dict[str, str]:
        return {
            "privy-id-token": auth_token,
            "Content-Type": "application/json",
        }
    
    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        if response.status_code == 204:
            return {"success": True}
        
        try:
            data = response.json()
        except Exception:
            data = {"error": "Failed to parse response", "raw": response.text}
        
        if response.status_code >= 400:
            error_msg = data.get("error", "Unknown error")
            raise APIError(error_msg, response.status_code, data)
        
        return data
    
    def get_status(self, auth_token: str, org_slug: Optional[str] = None) -> Dict[str, Any]:
        """Get current onboarding status."""
        url = f"{self.base_url}/api/onboarding/status"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        return self._handle_response(response)
    
    def start(self, auth_token: str, flow_type: str, org_slug: Optional[str] = None) -> Dict[str, Any]:
        """Start onboarding flow."""
        url = f"{self.base_url}/api/onboarding/start"
        params = {"org": org_slug} if org_slug else {}
        body = {"flowType": flow_type}
        
        response = self.client.post(url, headers=self._get_headers(auth_token), params=params, json=body)
        return self._handle_response(response)
    
    def complete_step(
        self,
        auth_token: str,
        step: str,
        data: Optional[Dict[str, Any]] = None,
        org_slug: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Complete an onboarding step."""
        url = f"{self.base_url}/api/onboarding/step/complete"
        params = {"org": org_slug} if org_slug else {}
        body = {"step": step}
        if data:
            body["data"] = data
        
        response = self.client.post(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json=body
        )
        return self._handle_response(response)
    
    def save_step_data(
        self,
        auth_token: str,
        step: str,
        data: Dict[str, Any],
        org_slug: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Save step data without completing."""
        url = f"{self.base_url}/api/onboarding/step/data"
        params = {"org": org_slug} if org_slug else {}
        body = {"step": step, "data": data}
        
        response = self.client.post(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json=body
        )
        return self._handle_response(response)
    
    def skip_step(
        self,
        auth_token: str,
        step: Optional[str] = None,
        org_slug: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Skip an onboarding step."""
        url = f"{self.base_url}/api/onboarding/skip"
        params = {"org": org_slug} if org_slug else {}
        body = {}
        if step:
            body["step"] = step
        
        response = self.client.post(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json=body
        )
        return self._handle_response(response)
    
    def reset(self, auth_token: str, org_slug: Optional[str] = None) -> Dict[str, Any]:
        """Reset onboarding progress."""
        url = f"{self.base_url}/api/onboarding/reset"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.post(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json={}
        )
        return self._handle_response(response)
    
    def skip_all(self, auth_token: str, org_slug: Optional[str] = None) -> Dict[str, Any]:
        """Skip all remaining onboarding steps."""
        url = f"{self.base_url}/api/onboarding/skip-all"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.post(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json={}
        )
        return self._handle_response(response)
    
    def close(self):
        self.client.close()


# ==================
# Base Tool Class
# ==================

class OnboardingAPIBaseTool(APIBaseTool):
    """Base class for onboarding API tools."""
    _client: Optional[OnboardingAPIClient] = None
    org_id: int = 0
    org_slug: str = ""

    def _get_client(self) -> OnboardingAPIClient:
        if self._client is None:
            self._client = OnboardingAPIClient()
        return self._client
    
    def __del__(self):
        if self._client:
            self._client.close()
            self._client = None


# ==================
# Onboarding Tools
# ==================

class GetOnboardingStatusTool(OnboardingAPIBaseTool):
    """Tool for getting current onboarding progress."""
    
    name: str = "get_onboarding_status"
    description: str = """Get the current onboarding progress including:
- Current step in the flow
- Completed steps
- Steps remaining
- Percent complete
- Step data (data collected from completed steps like program_id, invited_emails, etc.)
Use this to understand where the user is in onboarding and what data has been collected."""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = GetOnboardingStatusInput
    
    def _run_tool(self) -> str:
        client = self._get_client()
        result = client.get_status(self.auth_token, self.org_slug if self.org_slug else None)
        
        progress = result.get("progress")
        if not progress:
            return "No onboarding in progress. Would you like to start the onboarding process?"
        
        flow_type = progress.get("flowType", "unknown")
        current_step = progress.get("currentStep", "unknown")
        completed_steps = progress.get("completedSteps", [])
        is_complete = progress.get("isComplete", False)
        step_data = progress.get("stepData", {})
        
        percent = result.get("percentComplete", 0)
        remaining = result.get("stepsRemaining", 0)
        next_step = result.get("nextStep")
        
        if is_complete:
            return f"Onboarding is complete! You've finished all {len(completed_steps)} steps."
        
        output = f"**Onboarding Progress** ({flow_type})\n\n"
        output += f"- Current Step: {current_step}\n"
        output += f"- Progress: {percent}% complete\n"
        output += f"- Steps Remaining: {remaining}\n"
        output += f"- Completed: {', '.join(completed_steps) if completed_steps else 'None yet'}\n"
        
        if next_step:
            output += f"\nNext step: {next_step}"
        
        # Include collected data from previous steps
        if step_data:
            output += "\n\n**Collected Data:**\n"
            if step_data.get("program_id"):
                output += f"- Program ID: {step_data['program_id']}\n"
            if step_data.get("program_name"):
                output += f"- Program Name: {step_data['program_name']}\n"
            if step_data.get("form_id"):
                output += f"- Form ID: {step_data['form_id']}\n"
            if step_data.get("invited_emails"):
                output += f"- Invited Emails: {', '.join(step_data['invited_emails'])}\n"
            if step_data.get("team_id"):
                output += f"- Team ID: {step_data['team_id']}\n"
            if step_data.get("display_name"):
                output += f"- Display Name: {step_data['display_name']}\n"
        
        return output


class CompleteOnboardingStepTool(OnboardingAPIBaseTool):
    """Tool for marking an onboarding step as complete."""
    
    name: str = "complete_onboarding_step"
    description: str = """Mark an onboarding step as complete and advance to the next step.
Available steps depend on the flow type:
- Admin: welcome, org_details, branding, access_config, program_creation, form_setup, eval_criteria, invite_teammates, set_permissions, knowledge_base, completion
- User: welcome, profile_setup, team_selection, permissions_overview, getting_started, apply_for_grant, completion"""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = CompleteOnboardingStepInput
    
    def _run_tool(self, step: str, data: Optional[Dict[str, Any]] = None) -> str:
        client = self._get_client()
        result = client.complete_step(
            self.auth_token,
            step,
            data,
            self.org_slug if self.org_slug else None
        )
        
        progress = result.get("progress", {})
        is_complete = progress.get("isComplete", False)
        current_step = progress.get("currentStep", "unknown")
        
        if is_complete:
            return f"Congratulations! Step '{step}' completed. You've finished the entire onboarding!"
        
        return f"Step '{step}' completed. Moving to: {current_step}"


class SaveOnboardingStepDataTool(OnboardingAPIBaseTool):
    """Tool for saving step data without completing the step."""
    
    name: str = "save_onboarding_step_data"
    description: str = "Save progress data for the current step without marking it complete. Useful for autosaving user input."
    requires_approval: bool = False
    args_schema: Type[BaseModel] = SaveOnboardingStepDataInput
    
    def _run_tool(self, step: str, data: Dict[str, Any]) -> str:
        client = self._get_client()
        result = client.save_step_data(
            self.auth_token,
            step,
            data,
            self.org_slug if self.org_slug else None
        )
        
        return f"Saved data for step '{step}'."


class SkipOnboardingStepTool(OnboardingAPIBaseTool):
    """Tool for skipping an onboarding step."""
    
    name: str = "skip_onboarding_step"
    description: str = "Skip an optional onboarding step. Some steps like 'branding' or 'invite_teammates' can be skipped."
    requires_approval: bool = False
    args_schema: Type[BaseModel] = SkipOnboardingStepInput
    
    def _run_tool(self, step: Optional[str] = None) -> str:
        client = self._get_client()
        result = client.skip_step(
            self.auth_token,
            step,
            self.org_slug if self.org_slug else None
        )
        
        progress = result.get("progress", {})
        current_step = progress.get("currentStep", "unknown")
        
        skipped = step if step else "current step"
        return f"Skipped {skipped}. Moving to: {current_step}"


class ResetOnboardingTool(OnboardingAPIBaseTool):
    """Tool for resetting onboarding progress."""
    
    name: str = "reset_onboarding"
    description: str = "Reset all onboarding progress and start fresh. Use with caution. Requires user approval."
    requires_approval: bool = True
    args_schema: Type[BaseModel] = ResetOnboardingInput
    
    def _run_tool(self) -> str:
        client = self._get_client()
        result = client.reset(self.auth_token, self.org_slug if self.org_slug else None)
        
        return "Onboarding progress has been reset. You can start fresh."


class SkipAllOnboardingTool(OnboardingAPIBaseTool):
    """Tool for skipping all remaining onboarding steps."""
    
    name: str = "skip_all_onboarding"
    description: str = "Skip all remaining onboarding steps and mark onboarding as complete. Use this to quickly exit onboarding."
    requires_approval: bool = False
    args_schema: Type[BaseModel] = SkipAllOnboardingInput
    
    def _run_tool(self) -> str:
        client = self._get_client()
        result = client.skip_all(self.auth_token, self.org_slug if self.org_slug else None)
        
        progress = result.get("progress", {})
        is_complete = progress.get("isComplete", False)
        
        if is_complete:
            return "All remaining onboarding steps have been skipped. Onboarding is now complete. You can access all features from the sidebar and settings."
        
        return "Onboarding steps have been skipped."


class StartOnboardingTool(OnboardingAPIBaseTool):
    """Tool for starting a new onboarding flow."""
    
    name: str = "start_onboarding"
    description: str = """Start a new onboarding flow for the user.
    
Flow types:
- 'admin_setup': For organization admins setting up their organization (programs, branding, team invites)
- 'user_joining': For new users joining an existing organization (profile setup, team selection, permissions)

Use this when:
- User wants to restart onboarding after a reset
- User needs to be guided through setup
- User explicitly asks to begin onboarding"""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = StartOnboardingInput
    
    def _run_tool(self, flow_type: str) -> str:
        if flow_type not in ("admin_setup", "user_joining"):
            return f"Invalid flow type '{flow_type}'. Please use 'admin_setup' or 'user_joining'."
        
        client = self._get_client()
        result = client.start(
            self.auth_token, 
            flow_type, 
            self.org_slug if self.org_slug else None
        )
        
        progress = result.get("progress", {})
        current_step = progress.get("currentStep", "welcome")
        
        flow_label = "Organization Setup" if flow_type == "admin_setup" else "Getting Started"
        
        return f"""Onboarding started: **{flow_label}**

Let's begin with the '{current_step}' step. I'll guide you through each step of the process.

Would you like to continue?"""


class StartGrantApplicationTool(OnboardingAPIBaseTool):
    """Tool for navigating user to start a grant application."""
    
    name: str = "start_grant_application"
    description: str = "Help the user navigate to start a grant application for a specific program. Returns a deep link to the application form."
    requires_approval: bool = False
    args_schema: Type[BaseModel] = StartGrantApplicationInput
    
    def _run_tool(self, program_id: int) -> str:
        # Generate deep link to the application form
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        org_slug = self.org_slug if self.org_slug else "app"
        
        application_url = f"{frontend_url}/dashboard/{org_slug}/programs/{program_id}/apply"
        
        return f"""To start your grant application, please navigate to:

**[Start Application]({application_url})**

Or copy this link: {application_url}

This will take you to the application form where you can submit your proposal."""


# ==================
# Tool Factory
# ==================

def create_onboarding_specific_tools(auth_token: str, org_id: int = 0, org_slug: str = "") -> List[OnboardingAPIBaseTool]:
    """
    Create onboarding-specific tools only.
    
    Args:
        auth_token: Privy authentication token
        org_id: Organization ID
        org_slug: Organization slug
        
    Returns:
        List of onboarding-specific tool instances
    """
    tools = [
        GetOnboardingStatusTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
        CompleteOnboardingStepTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
        SaveOnboardingStepDataTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
        SkipOnboardingStepTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
        ResetOnboardingTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
        SkipAllOnboardingTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
        StartOnboardingTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
        StartGrantApplicationTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
    ]
    
    return tools


def create_onboarding_tools(auth_token: str, org_id: int = 0, org_slug: str = "", is_global_admin: bool = False) -> List[BaseTool]:
    """
    Create all tools for the onboarding agent.
    Combines app automation tools with onboarding-specific tools.
    
    The onboarding agent gets all app_automation tools (teams, forms, programs, etc.)
    plus the onboarding-specific tools for progress tracking and step management.
    
    Args:
        auth_token: Privy authentication token
        org_id: Organization ID
        org_slug: Organization slug
        is_global_admin: Whether the user has Global Admin privileges
        
    Returns:
        List of all tool instances (app automation + onboarding-specific)
    """
    # Lazy import to avoid circular dependency
    from src.growth_chat.app_automation_agent.tools.tools import create_all_tools
    
    # Get all app automation tools (teams, forms, programs, reviews, etc.)
    app_tools = create_all_tools(auth_token, org_id, org_slug, is_global_admin=is_global_admin)
    
    # Add onboarding-specific tools
    onboarding_tools = create_onboarding_specific_tools(auth_token, org_id, org_slug)
    
    return [*app_tools, *onboarding_tools]


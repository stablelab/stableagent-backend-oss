"""
LangChain tools for Form Management in App Automation Agent.

Provides tools for creating, reading, updating, and deleting forms,
as well as listing programs for form association.
"""
from datetime import datetime
from typing import Any, List, Optional, Type, Union

from pydantic import BaseModel, Field

from .base import APIBaseTool
from .schemas import (
    CreateFormInput,
    DynamicFormConfig,
    FormFieldInput,
    FormStepInput,
    UpdateFormInput,
    convert_simplified_to_full_config,
    format_form_config_for_display,
)
from .forms_api_client import FormsAPIClient


# ==================
# Tool Input Schemas
# ==================

class ListProgramsInput(BaseModel):
    """Input for listing programs."""
    pass  # No input required


class ListFormsInput(BaseModel):
    """Input for listing forms."""
    program_id: Optional[int] = Field(None, description="Optional program ID to filter forms by")


class GetFormInput(BaseModel):
    """Input for getting form details."""
    form_id: int = Field(..., description="The ID of the form to retrieve")


class DeleteFormInput(BaseModel):
    """Input for deleting a form."""
    form_id: int = Field(..., description="The ID of the form to delete")


# ==================
# Base Tool Class
# ==================

class FormAPIBaseTool(APIBaseTool):
    """Base class for form API tools. Extends APIBaseTool with Forms-specific client."""
    
    org_slug: str = ""
    _client: Optional[FormsAPIClient] = None

    def _get_client(self) -> FormsAPIClient:
        """Get shared Forms API client instance."""
        if self._client is None:
            self._client = FormsAPIClient()
        return self._client


# ==================
# Read-Only Tools
# ==================

class ListProgramsTool(FormAPIBaseTool):
    """Tool for listing programs to associate forms with."""
    
    name: str = "list_programs"
    description: str = """List all grant programs in the organization. 
Returns: list of programs with ID, name, start/end dates, and budget.
Use this to find program IDs when creating forms associated with a program."""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = ListProgramsInput
    
    def _run_tool(self) -> str:
        """List programs."""
        client = self._get_client()
        result = client.list_programs(self.auth_token, self.org_slug)
        
        programs = result.programs
        if not programs:
            return "No programs found in this organization."
        
        output = f"Found {len(programs)} program(s):\n\n"
        for prog in programs:
            output += f"- **{prog.name}** (ID: {prog.id})\n"
            
            # Format dates
            if prog.start:
                start_date = datetime.fromtimestamp(prog.start / 1000).strftime("%Y-%m-%d")
                output += f"  Start: {start_date}\n"
            if prog.end:
                end_date = datetime.fromtimestamp(prog.end / 1000).strftime("%Y-%m-%d")
                output += f"  End: {end_date}\n"
            
            # Budget info
            if prog.total_budget:
                currency = prog.budget_currency or "USD"
                output += f"  Budget: {prog.total_budget:,.0f} {currency}\n"
            
            output += "\n"
        
        return output


class ListFormsTool(FormAPIBaseTool):
    """Tool for listing existing forms."""
    
    name: str = "list_forms"
    description: str = """List all grant application forms in the organization.
Optionally filter by program ID.
Returns: list of forms with ID, title, description, and program association."""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = ListFormsInput
    
    def _run_tool(self, program_id: Optional[int] = None) -> str:
        """List forms."""
        client = self._get_client()
        result = client.list_forms(
            self.auth_token,
            org_slug=self.org_slug,
            program_id=program_id,
        )
        
        forms = result.forms
        if not forms:
            if program_id:
                return f"No forms found for program ID {program_id}."
            return "No forms found in this organization."
        
        output = f"Found {len(forms)} form(s):\n\n"
        for form in forms:
            output += f"- **{form.title}** (ID: {form.id})\n"
            if form.description:
                output += f"  Description: {form.description}\n"
            if form.programId:
                output += f"  Program ID: {form.programId}\n"
            
            # Show step count if config available
            if form.config and isinstance(form.config, dict):
                steps = form.config.get("steps", [])
                if steps:
                    output += f"  Steps: {len(steps)}\n"
            
            output += "\n"
        
        return output


class GetFormTool(FormAPIBaseTool):
    """Tool for getting full form configuration."""
    
    name: str = "get_form"
    description: str = """Get the full configuration of a specific form by ID.
Returns: complete form structure including all steps, fields, and validation rules.
Use this to inspect an existing form before updating it."""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = GetFormInput
    
    def _run_tool(self, form_id: int) -> str:
        """Get form details."""
        client = self._get_client()
        result = client.get_form(form_id, self.auth_token, self.org_slug)
        
        # Convert to dict for formatting
        config_dict = result.model_dump(exclude_none=True)
        
        # Format for display
        output = format_form_config_for_display(config_dict)
        
        # Add database info
        if result.id:
            output = f"Database ID: {result.id}\n" + output
        if result.proposal_link_mode:
            output += f"\nProposal Link Mode: {result.proposal_link_mode}"
        if result.wallet_address_collection_enabled:
            output += f"\nWallet Address Collection: Enabled"
        
        return output


# ==================
# Mutating Tools (Require Approval)
# ==================

class CreateFormTool(FormAPIBaseTool):
    """Tool for creating a new form."""
    
    name: str = "create_form"
    description: str = """Create a new grant application form.

Input:
- title: Form title (e.g., "DeFi Builder Grant Application")
- description: Form description
- program_id: Optional program ID to associate with (use list_programs first)
- steps: List of form steps, each with title, description, and fields

Each field needs:
- label: Field label shown to user
- type: text, textarea, number, email, url, select, multiselect, checkbox, radio, date, file
- placeholder: Placeholder text (optional)
- required: Whether field is required (default false)
- min_length/max_length: For text fields
- min_value/max_value: For number fields
- options: List of options for select/radio fields

Example steps structure:
[
  {
    "title": "Project Basics",
    "description": "Tell us about your project",
    "fields": [
      {"label": "Project Name", "type": "text", "required": true},
      {"label": "Project Description", "type": "textarea", "required": true, "min_length": 100}
    ]
  }
]

Requires user approval before creation."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = CreateFormInput
    org_id: int = 0
    
    def _run_tool(
        self,
        title: str,
        steps: List[Union[dict, FormStepInput]],
        description: Optional[str] = None,
        program_id: Optional[int] = None,
    ) -> str:
        """Create a form."""
        # Convert steps to Pydantic models (may already be models from LLM parsing)
        step_inputs = []
        for step in steps:
            # If already a FormStepInput, use directly
            if isinstance(step, FormStepInput):
                step_inputs.append(step)
            else:
                # Convert dict to FormStepInput
                fields = []
                for field in step.get("fields", []):
                    if isinstance(field, FormFieldInput):
                        fields.append(field)
                    else:
                        fields.append(FormFieldInput(**field))
                step_inputs.append(FormStepInput(
                    title=step.get("title", "Untitled Step"),
                    description=step.get("description"),
                    fields=fields,
                ))
        
        # Convert to full config
        config = convert_simplified_to_full_config(
            title=title,
            steps=step_inputs,
            description=description,
        )
        
        # Create via API
        client = self._get_client()
        result = client.create_form(
            config=config,
            auth_token=self.auth_token,
            org_slug=self.org_slug,
            program_id=program_id,
        )
        
        return f"Successfully created form '{title}' (ID: {result.id}, formId: {result.formId})"


class UpdateFormTool(FormAPIBaseTool):
    """Tool for updating an existing form."""
    
    name: str = "update_form"
    description: str = """Update an existing grant application form.

Input:
- form_id: ID of the form to update
- title: New form title (optional)
- description: New form description (optional)
- program_id: New program ID to associate with (optional)
- steps: Updated form steps (replaces all existing steps)

Use get_form first to see the current configuration.
Requires user approval before update."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = UpdateFormInput
    
    def _run_tool(
        self,
        form_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        program_id: Optional[int] = None,
        steps: Optional[List[Union[dict, FormStepInput]]] = None,
    ) -> str:
        """Update a form."""
        client = self._get_client()
        
        # First, get the existing form config
        existing = client.get_form(form_id, self.auth_token, self.org_slug)
        
        # Determine new values
        new_title = title or existing.title
        new_description = description if description is not None else existing.description
        
        # Convert steps if provided
        if steps:
            step_inputs = []
            for step in steps:
                # If already a FormStepInput, use directly
                if isinstance(step, FormStepInput):
                    step_inputs.append(step)
                else:
                    # Convert dict to FormStepInput
                    fields = []
                    for field in step.get("fields", []):
                        if isinstance(field, FormFieldInput):
                            fields.append(field)
                        else:
                            fields.append(FormFieldInput(**field))
                    step_inputs.append(FormStepInput(
                        title=step.get("title", "Untitled Step"),
                        description=step.get("description"),
                        fields=fields,
                    ))
            
            config = convert_simplified_to_full_config(
                title=new_title,
                steps=step_inputs,
                description=new_description,
            )
        else:
            # Keep existing steps but update title/description
            config = DynamicFormConfig(
                formId=existing.formId,
                title=new_title,
                description=new_description,
                steps=existing.steps,
                submission=existing.submission,
            )
        
        # Update via API
        result = client.update_form(
            form_id=form_id,
            config=config,
            auth_token=self.auth_token,
            org_slug=self.org_slug,
            program_id=program_id,
        )
        
        return f"Successfully updated form '{new_title}' (ID: {result.id})"


class DeleteFormTool(FormAPIBaseTool):
    """Tool for deleting a form."""
    
    name: str = "delete_form"
    description: str = """Delete a grant application form.

WARNING: This action is permanent and cannot be undone.
Any existing submissions for this form may be affected.

Input:
- form_id: ID of the form to delete

Requires user approval before deletion."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = DeleteFormInput
    
    def _run_tool(self, form_id: int) -> str:
        """Delete a form."""
        client = self._get_client()
        
        # First get the form to show what's being deleted
        try:
            existing = client.get_form(form_id, self.auth_token, self.org_slug)
            form_title = existing.title
        except Exception:
            form_title = f"Form {form_id}"
        
        # Delete via API
        client.delete_form(form_id, self.auth_token, self.org_slug)
        
        return f"Successfully deleted form '{form_title}' (ID: {form_id})"


# ==================
# Tool Factory
# ==================

def create_form_tools(auth_token: str, org_id: int = 0, org_slug: str = "") -> List[FormAPIBaseTool]:
    """
    Create all form management tools with the given auth token and org context.
    
    Args:
        auth_token: Privy authentication token
        org_id: Organization ID
        org_slug: Organization slug
        
    Returns:
        List of form tool instances
    """
    tools = [
        # Read-only tools
        ListProgramsTool(auth_token=auth_token, org_slug=org_slug),
        ListFormsTool(auth_token=auth_token, org_slug=org_slug),
        GetFormTool(auth_token=auth_token, org_slug=org_slug),
        # Mutating tools (require approval)
        CreateFormTool(auth_token=auth_token, org_slug=org_slug, org_id=org_id),
        UpdateFormTool(auth_token=auth_token, org_slug=org_slug),
        DeleteFormTool(auth_token=auth_token, org_slug=org_slug),
    ]
    
    return tools


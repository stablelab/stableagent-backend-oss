"""
LangChain tools for Program Management in App Automation Agent.

Provides CRUD operations for grant programs:
- get_program: Get program details (read-only)
- create_program: Create a new program (requires approval)
- update_program: Update program details (requires approval)
- delete_program: Delete a program (requires approval)
- create_program_with_form: Create program + form together (single approval)
"""
from typing import List, Optional, Type, Union

from pydantic import BaseModel

from .base import APIBaseTool
from .schemas import (
    CreateProgramInput,
    CreateProgramWithFormInput,
    DeleteProgramInput,
    FormStepInput,
    GetProgramInput,
    UpdateProgramInput,
    convert_simplified_to_full_config,
)
from .forms_api_client import FormsAPIClient


class ProgramAPIBaseTool(APIBaseTool):
    """Base class for Program API tools. Extends APIBaseTool with Forms-specific client."""
    
    org_slug: str = ""
    org_id: int = 0
    _client: Optional[FormsAPIClient] = None
    
    def _get_client(self) -> FormsAPIClient:
        """Get or create the Forms API client (shared with forms)."""
        if self._client is None:
            self._client = FormsAPIClient()
        return self._client


# ==================
# Read-Only Tools
# ==================

class GetProgramTool(ProgramAPIBaseTool):
    """Tool for getting program details."""
    
    name: str = "get_program"
    description: str = """Get details of a specific grant program by ID.
Returns: program name, start/end dates, budget information.
Use this to inspect a program before updating it."""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = GetProgramInput
    
    def _run_tool(self, program_id: int) -> str:
        """Get program details."""
        client = self._get_client()
        result = client.get_program(program_id, self.auth_token, self.org_slug)
        
        # Format dates for display
        start_str = "Not set"
        end_str = "Not set"
        if result.start:
            from datetime import datetime
            start_str = datetime.fromtimestamp(result.start / 1000).strftime('%Y-%m-%d')
        if result.end:
            from datetime import datetime
            end_str = datetime.fromtimestamp(result.end / 1000).strftime('%Y-%m-%d')
        
        budget_str = "Not set"
        if result.total_budget:
            budget_str = f"{result.total_budget:,.2f} {result.budget_currency}"
        
        output = f"""Program: {result.name} (ID: {result.id})
Start: {start_str}
End: {end_str}
Budget: {budget_str}"""
        
        return output


# ==================
# Mutating Tools (Require Approval)
# ==================

class CreateProgramTool(ProgramAPIBaseTool):
    """Tool for creating a new grant program."""
    
    name: str = "create_program"
    description: str = """Create a new grant program.

Input:
- name: Program name (e.g., "DeFi Builder Grants Q1 2025")
- start: Start date as Unix timestamp in milliseconds (optional)
- end: End date as Unix timestamp in milliseconds (optional)
- total_budget: Total budget amount (optional)
- budget_currency: Budget currency, default "USD"

Requires user approval before creation."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = CreateProgramInput
    
    def _run_tool(
        self,
        name: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        total_budget: Optional[float] = None,
        budget_currency: str = "USD",
    ) -> str:
        """Create a program."""
        client = self._get_client()
        result = client.create_program(
            name=name,
            auth_token=self.auth_token,
            org_slug=self.org_slug,
            start=start,
            end=end,
            total_budget=total_budget,
            budget_currency=budget_currency,
        )
        
        return f"Successfully created program '{name}' (ID: {result.id})"


class UpdateProgramTool(ProgramAPIBaseTool):
    """Tool for updating an existing grant program."""
    
    name: str = "update_program"
    description: str = """Update an existing grant program.

Input:
- program_id: ID of the program to update
- name: New program name (optional)
- start: New start date as Unix timestamp in milliseconds (optional)
- end: New end date as Unix timestamp in milliseconds (optional)
- total_budget: New total budget (optional)
- budget_currency: New budget currency (optional)

Use get_program first to see the current details.
Requires user approval before update."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = UpdateProgramInput
    
    def _run_tool(
        self,
        program_id: int,
        name: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        total_budget: Optional[float] = None,
        budget_currency: Optional[str] = None,
    ) -> str:
        """Update a program."""
        client = self._get_client()
        result = client.update_program(
            program_id=program_id,
            auth_token=self.auth_token,
            org_slug=self.org_slug,
            name=name,
            start=start,
            end=end,
            total_budget=total_budget,
            budget_currency=budget_currency,
        )
        
        return f"Successfully updated program (ID: {result.id})"


class DeleteProgramTool(ProgramAPIBaseTool):
    """Tool for deleting a grant program."""
    
    name: str = "delete_program"
    description: str = """Delete a grant program.

WARNING: This action is permanent and cannot be undone.
This may also affect associated forms and submissions.

Input:
- program_id: ID of the program to delete

Requires user approval before deletion."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = DeleteProgramInput
    
    def _run_tool(self, program_id: int) -> str:
        """Delete a program."""
        client = self._get_client()
        
        # Get program name first for confirmation message
        try:
            program = client.get_program(program_id, self.auth_token, self.org_slug)
            program_name = program.name
        except Exception:
            program_name = f"Program #{program_id}"
        
        client.delete_program(program_id, self.auth_token, self.org_slug)
        
        return f"Successfully deleted program '{program_name}' (ID: {program_id})"


class CreateProgramWithFormTool(ProgramAPIBaseTool):
    """Tool for creating a program AND form together in a single approval."""
    
    name: str = "create_program_with_form"
    description: str = """Create a new grant program with an attached application form in one step.

This is useful when you want to set up a complete grant program including:
1. The program (name, dates, budget)
2. An application form for builders to apply

Input:
- program_name: Name for the program (e.g., "DeFi Innovation Grants")
- program_start: Start date as Unix timestamp in milliseconds (optional)
- program_end: End date as Unix timestamp in milliseconds (optional)
- total_budget: Total budget for the program (optional)
- budget_currency: Budget currency, default "USD"
- form_title: Title for the application form
- form_description: Description for the form (optional)
- form_steps: Form steps with fields (same format as create_form)

Requires a SINGLE user approval for both the program and form creation."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = CreateProgramWithFormInput
    
    def _run_tool(
        self,
        program_name: str,
        form_title: str,
        form_steps: List[Union[dict, FormStepInput]],
        program_start: Optional[int] = None,
        program_end: Optional[int] = None,
        total_budget: Optional[float] = None,
        budget_currency: str = "USD",
        form_description: Optional[str] = None,
    ) -> str:
        """Create a program with an attached form."""
        client = self._get_client()
        
        # Step 1: Create the program
        program_result = client.create_program(
            name=program_name,
            auth_token=self.auth_token,
            org_slug=self.org_slug,
            start=program_start,
            end=program_end,
            total_budget=total_budget,
            budget_currency=budget_currency,
        )
        program_id = program_result.id
        
        # Step 2: Convert form steps to Pydantic models if needed
        step_inputs = []
        for step in form_steps:
            if isinstance(step, FormStepInput):
                step_inputs.append(step)
            else:
                from .schemas import FormFieldInput
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
        
        # Step 3: Convert to full form config
        config = convert_simplified_to_full_config(
            title=form_title,
            steps=step_inputs,
            description=form_description,
        )
        
        # Step 4: Create the form linked to the program
        try:
            form_result = client.create_form(
                config=config,
                auth_token=self.auth_token,
                org_slug=self.org_slug,
                program_id=program_id,
            )
            
            return (
                f"Successfully created program '{program_name}' (ID: {program_id}) "
                f"with attached form '{form_title}' (Form ID: {form_result.id})"
            )
        except Exception as e:
            # Program was created but form failed - inform user
            return (
                f"Program '{program_name}' created successfully (ID: {program_id}), "
                f"but form creation failed: {str(e)}. "
                f"You can use create_form with program_id={program_id} to retry."
            )


def create_program_tools(
    auth_token: str,
    org_slug: str,
    org_id: int,
) -> List[ProgramAPIBaseTool]:
    """
    Create all program management tools with authentication context.
    
    Args:
        auth_token: Privy authentication token
        org_slug: Organization slug
        org_id: Organization ID
        
    Returns:
        List of program management tools
    """
    tools: List[ProgramAPIBaseTool] = [
        GetProgramTool(auth_token=auth_token, org_slug=org_slug, org_id=org_id),
        CreateProgramTool(auth_token=auth_token, org_slug=org_slug, org_id=org_id),
        UpdateProgramTool(auth_token=auth_token, org_slug=org_slug, org_id=org_id),
        DeleteProgramTool(auth_token=auth_token, org_slug=org_slug, org_id=org_id),
        CreateProgramWithFormTool(auth_token=auth_token, org_slug=org_slug, org_id=org_id),
    ]
    
    return tools


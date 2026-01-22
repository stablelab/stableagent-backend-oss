"""
HTTP client for Forms and Programs API endpoints.

Handles all API communication with proper authentication and error handling.
Extends BaseAPIClient.
"""
from typing import Any, Dict, Optional

import httpx

from .base_api_client import APIError, BaseAPIClient
from .schemas import (
    CreateFormResponse,
    CreateProgramResponse,
    DynamicFormConfig,
    FormConfigResponse,
    FormListItem,
    FormListResponse,
    GetProgramResponse,
    ProgramListItem,
    ProgramListResponse,
    UpdateFormResponse,
    UpdateProgramResponse,
)


class FormsAPIClient(BaseAPIClient):
    """Client for interacting with Forms and Programs API."""
    
    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """
        Handle API response with form-specific error messages.
        
        Extends base handler with user-friendly error messages for form operations.
        """
        if response.status_code == 204:
            return {"success": True}
        
        try:
            data = response.json()
        except Exception:
            data = {"error": "Failed to parse response", "raw": response.text}
        
        if response.status_code >= 400:
            error_msg = data.get("error", "Unknown error")
            if isinstance(data, dict) and "message" in data:
                error_msg = data["message"]
            
            # Provide user-friendly error messages for form operations
            if response.status_code == 400:
                details = data.get("details", {})
                if details:
                    error_msg = f"Invalid form configuration: {details}"
            elif response.status_code == 404:
                error_msg = "Form not found"
            elif response.status_code == 409:
                error_msg = "Form with this formId already exists"
            elif response.status_code >= 500:
                error_msg = "Server error, please try again"
            
            raise APIError(error_msg, response.status_code, data)
        
        return data
    
    # ==================
    # Programs Endpoints
    # ==================
    
    def list_programs(self, auth_token: str, org_slug: Optional[str] = None) -> ProgramListResponse:
        """
        List all programs in the organization.
        
        Args:
            auth_token: Privy authentication token
            org_slug: Organization slug (passed as query param)
            
        Returns:
            ProgramListResponse with list of programs
        """
        url = f"{self.base_url}/api/programs"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        data = self._handle_response(response)
        
        # Parse programs from response
        programs = []
        for prog in data.get("programs", []):
            programs.append(ProgramListItem(
                id=prog.get("id"),
                name=prog.get("name", ""),
                start=prog.get("start"),
                end=prog.get("end"),
                total_budget=prog.get("total_budget"),
                budget_currency=prog.get("budget_currency"),
            ))
        
        return ProgramListResponse(programs=programs)
    
    def get_program(self, program_id: int, auth_token: str, org_slug: Optional[str] = None) -> GetProgramResponse:
        """
        Get a single program by ID.
        
        Args:
            program_id: Program ID
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            GetProgramResponse with program details
        """
        url = f"{self.base_url}/api/programs/{program_id}"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        data = self._handle_response(response)
        
        return GetProgramResponse(
            id=data.get("id"),
            name=data.get("name", ""),
            start=data.get("start"),
            end=data.get("end"),
            total_budget=data.get("total_budget"),
            budget_currency=data.get("budget_currency", "USD"),
        )
    
    def create_program(
        self,
        name: str,
        auth_token: str,
        org_slug: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        total_budget: Optional[float] = None,
        budget_currency: str = "USD",
    ) -> CreateProgramResponse:
        """
        Create a new grant program.
        
        Args:
            name: Program name
            auth_token: Privy authentication token
            org_slug: Organization slug
            start: Start timestamp (Unix ms)
            end: End timestamp (Unix ms)
            total_budget: Total budget amount
            budget_currency: Budget currency (default USD)
            
        Returns:
            CreateProgramResponse with created program ID
        """
        url = f"{self.base_url}/api/programs"
        params = {"org": org_slug} if org_slug else {}
        
        body: Dict[str, Any] = {"name": name}
        if start is not None:
            body["start"] = start
        if end is not None:
            body["end"] = end
        if total_budget is not None:
            body["total_budget"] = total_budget
        if budget_currency:
            body["budget_currency"] = budget_currency
        
        response = self.client.post(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json=body,
        )
        data = self._handle_response(response)
        
        return CreateProgramResponse(id=data.get("id"))
    
    def update_program(
        self,
        program_id: int,
        auth_token: str,
        org_slug: Optional[str] = None,
        name: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        total_budget: Optional[float] = None,
        budget_currency: Optional[str] = None,
    ) -> UpdateProgramResponse:
        """
        Update an existing grant program.
        
        Args:
            program_id: Program ID to update
            auth_token: Privy authentication token
            org_slug: Organization slug
            name: New program name
            start: New start timestamp (Unix ms)
            end: New end timestamp (Unix ms)
            total_budget: New total budget
            budget_currency: New budget currency
            
        Returns:
            UpdateProgramResponse with updated program ID
        """
        url = f"{self.base_url}/api/programs/{program_id}"
        params = {"org": org_slug} if org_slug else {}
        
        body: Dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if start is not None:
            body["start"] = start
        if end is not None:
            body["end"] = end
        if total_budget is not None:
            body["total_budget"] = total_budget
        if budget_currency is not None:
            body["budget_currency"] = budget_currency
        
        response = self.client.put(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json=body,
        )
        data = self._handle_response(response)
        
        return UpdateProgramResponse(id=data.get("id"))
    
    def delete_program(self, program_id: int, auth_token: str, org_slug: Optional[str] = None) -> Dict[str, Any]:
        """
        Delete a grant program.
        
        WARNING: This may cascade and delete associated forms/submissions.
        
        Args:
            program_id: Program ID to delete
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            Success dictionary
        """
        url = f"{self.base_url}/api/programs/{program_id}"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.delete(url, headers=self._get_headers(auth_token), params=params)
        return self._handle_response(response)
    
    # ==================
    # Forms Endpoints
    # ==================
    
    def list_forms(
        self,
        auth_token: str,
        org_slug: Optional[str] = None,
        program_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> FormListResponse:
        """
        List forms in the organization.
        
        Args:
            auth_token: Privy authentication token
            org_slug: Organization slug
            program_id: Optional program ID to filter by
            limit: Maximum number of forms to return
            offset: Offset for pagination
            
        Returns:
            FormListResponse with list of forms
        """
        url = f"{self.base_url}/api/forms"
        params: Dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }
        if org_slug:
            params["org"] = org_slug
        if program_id is not None:
            params["programId"] = program_id
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        data = self._handle_response(response)
        
        # Parse forms from response
        forms = []
        for form in data.get("forms", []):
            forms.append(FormListItem(
                id=form.get("id"),
                formId=str(form.get("formId", form.get("id", ""))),
                title=form.get("title", ""),
                description=form.get("description"),
                programId=form.get("programId"),
                fundingAmountFieldId=form.get("fundingAmountFieldId"),
                config=form.get("config"),
                ownerId=form.get("ownerId"),
                createdAt=form.get("createdAt"),
                updatedAt=form.get("updatedAt"),
            ))
        
        return FormListResponse(forms=forms)
    
    def get_form(self, form_id: int, auth_token: str, org_slug: Optional[str] = None) -> FormConfigResponse:
        """
        Get form configuration by ID.
        
        Args:
            form_id: Form ID
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            FormConfigResponse with full form config
        """
        url = f"{self.base_url}/api/forms/config/{form_id}"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        data = self._handle_response(response)
        
        return FormConfigResponse(**data)
    
    def create_form(
        self,
        config: DynamicFormConfig,
        auth_token: str,
        org_slug: Optional[str] = None,
        program_id: Optional[int] = None,
        funding_amount_field_id: Optional[str] = None,
    ) -> CreateFormResponse:
        """
        Create a new form.
        
        Args:
            config: Form configuration
            auth_token: Privy authentication token
            org_slug: Organization slug
            program_id: Optional program ID to associate with
            funding_amount_field_id: Optional field ID for funding amount
            
        Returns:
            CreateFormResponse with created form ID
        """
        url = f"{self.base_url}/api/forms"
        params = {"org": org_slug} if org_slug else {}
        
        # Build request body
        body: Dict[str, Any] = {
            "config": config.model_dump(exclude_none=True),
        }
        if program_id is not None:
            body["id_program"] = program_id
        if funding_amount_field_id:
            body["funding_amount_field_id"] = funding_amount_field_id
        
        response = self.client.post(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json=body,
        )
        data = self._handle_response(response)
        
        return CreateFormResponse(
            id=data.get("id"),
            formId=str(data.get("formId", data.get("id", ""))),
        )
    
    def update_form(
        self,
        form_id: int,
        config: DynamicFormConfig,
        auth_token: str,
        org_slug: Optional[str] = None,
        program_id: Optional[int] = None,
        funding_amount_field_id: Optional[str] = None,
        proposal_link_mode: Optional[str] = None,
        wallet_address_collection_enabled: Optional[bool] = None,
    ) -> UpdateFormResponse:
        """
        Update an existing form.
        
        Args:
            form_id: Form ID to update
            config: Updated form configuration
            auth_token: Privy authentication token
            org_slug: Organization slug
            program_id: Optional new program ID
            funding_amount_field_id: Optional field ID for funding amount
            proposal_link_mode: Optional proposal linking mode
            wallet_address_collection_enabled: Optional wallet address collection setting
            
        Returns:
            UpdateFormResponse with updated form ID
        """
        url = f"{self.base_url}/api/forms/{form_id}"
        params = {"org": org_slug} if org_slug else {}
        
        # Build request body
        body: Dict[str, Any] = {
            "config": config.model_dump(exclude_none=True),
        }
        if program_id is not None:
            body["id_program"] = program_id
        if funding_amount_field_id is not None:
            body["funding_amount_field_id"] = funding_amount_field_id
        if proposal_link_mode is not None:
            body["proposal_link_mode"] = proposal_link_mode
        if wallet_address_collection_enabled is not None:
            body["wallet_address_collection_enabled"] = wallet_address_collection_enabled
        
        response = self.client.put(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json=body,
        )
        data = self._handle_response(response)
        
        return UpdateFormResponse(
            id=data.get("id"),
            formId=str(data.get("formId", data.get("id", ""))),
        )
    
    def delete_form(self, form_id: int, auth_token: str, org_slug: Optional[str] = None) -> Dict[str, Any]:
        """
        Delete a form.
        
        Args:
            form_id: Form ID to delete
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            Success dictionary
        """
        url = f"{self.base_url}/api/forms/{form_id}"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.delete(url, headers=self._get_headers(auth_token), params=params)
        return self._handle_response(response)

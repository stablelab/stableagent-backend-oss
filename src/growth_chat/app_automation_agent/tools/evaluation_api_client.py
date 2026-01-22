"""
HTTP client for Evaluation/Criteria API endpoints.

Handles criteria management and form-criteria associations.
Extends BaseAPIClient.
"""
from typing import Any, Dict, Optional

import httpx

from .base_api_client import APIError, BaseAPIClient


class EvaluationAPIClient(BaseAPIClient):
    """Client for the Evaluation/Criteria API."""
    
    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """
        Handle API response with evaluation-specific error handling.
        """
        if response.status_code >= 400:
            try:
                error_data = response.json()
                raise APIError(error_data.get("error", f"HTTP {response.status_code}"), response.status_code)
            except APIError:
                raise
            except Exception:
                raise APIError(f"HTTP {response.status_code}", response.status_code)
        return response.json()
    
    # ==================
    # Criteria Operations
    # ==================
    
    def list_criteria(self, auth_token: str, org_slug: str) -> Dict[str, Any]:
        """List all evaluation criteria in the organization."""
        url = f"{self.base_url}/api/criteria"
        response = self.client.get(
            url,
            headers=self._get_headers(auth_token),
            params={"org": org_slug},
        )
        result = self._handle_response(response)
        print(f"[DEBUG] list_criteria: found {len(result.get('criteria', []))} criteria")
        return result
    
    def create_criteria(
        self,
        auth_token: str,
        org_slug: str,
        name: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new evaluation criteria."""
        url = f"{self.base_url}/api/criteria"
        body: Dict[str, Any] = {
            "org": org_slug,  # org goes in body for POST
            "name": name,
        }
        if description:
            body["description"] = description
        
        print(f"[DEBUG] create_criteria: name='{name}', description='{description}'")
        response = self.client.post(
            url,
            headers=self._get_headers(auth_token),
            json=body
        )
        result = self._handle_response(response)
        print(f"[DEBUG] create_criteria result: {result}")
        return result
    
    # ==================
    # Form Criteria Operations
    # ==================
    
    def list_form_criteria(
        self,
        auth_token: str,
        org_slug: str,
        form_id: int,
    ) -> Dict[str, Any]:
        """List criteria attached to a specific form."""
        url = f"{self.base_url}/api/criteria/forms/{form_id}/criteria"
        response = self.client.get(
            url,
            headers=self._get_headers(auth_token),
            params={"org": org_slug},
        )
        result = self._handle_response(response)
        print(f"[DEBUG] list_form_criteria for form {form_id}: {result}")
        return result
    
    def attach_criteria_to_form(
        self,
        auth_token: str,
        org_slug: str,
        form_id: int,
        criteria_id: int,
        weight: int,
    ) -> Dict[str, Any]:
        """Attach a criteria to a form with a specific weight (0-100)."""
        url = f"{self.base_url}/api/criteria/forms/{form_id}/criteria"
        # Ensure criteria_id and weight are integers, org goes in body for POST
        body = {
            "org": org_slug,
            "criteriaId": int(criteria_id) if criteria_id is not None else None,
            "weight": int(weight) if weight is not None else 0,
        }
        print(f"[DEBUG] attach_criteria_to_form: form_id={form_id}, criteria_id={criteria_id}, weight={weight}, body={body}")
        response = self.client.post(
            url,
            headers=self._get_headers(auth_token),
            json=body
        )
        if response.status_code >= 400:
            print(f"[DEBUG] attach_criteria_to_form FAILED: status={response.status_code}, response={response.text}")
        return self._handle_response(response)
    
    def detach_criteria_from_form(
        self,
        auth_token: str,
        org_slug: str,
        form_id: int,
        criteria_id: int,
    ) -> Dict[str, Any]:
        """Remove a criteria from a form."""
        url = f"{self.base_url}/api/criteria/forms/{form_id}/criteria/{criteria_id}"
        response = self.client.delete(
            url,
            headers=self._get_headers(auth_token),
            params={"org": org_slug},
        )
        return self._handle_response(response)
    
    def detach_all_form_criteria(
        self,
        auth_token: str,
        org_slug: str,
        form_id: int,
    ) -> None:
        """Remove all criteria from a form before reconfiguring."""
        current = self.list_form_criteria(auth_token, org_slug, form_id)
        existing_criteria = current.get("criteria", [])
        print(f"[DEBUG] detach_all_form_criteria: form {form_id} has {len(existing_criteria)} existing criteria")
        for c in existing_criteria:
            # Skip any orphaned criteria without valid IDs
            criteria_id = c.get("id")
            if criteria_id:
                print(f"[DEBUG] Detaching criteria {criteria_id} from form {form_id}")
                self.detach_criteria_from_form(auth_token, org_slug, form_id, criteria_id)


"""
AI Evaluation Tools for App Automation Agent.

Simplified tools for configuring how grant applications are evaluated.
Two focused tools that match user mental models:
- get_form_evaluation: View current evaluation configuration
- configure_form_evaluation: Set up or replace evaluation criteria
"""
from typing import List, Optional, Type

from pydantic import BaseModel, Field

from src.utils.logger import logger
from .base import APIBaseTool
from .evaluation_api_client import EvaluationAPIClient


# ==================
# Tool Input Schemas
# ==================

class GetFormEvaluationInput(BaseModel):
    """Input for viewing form evaluation configuration."""
    form_id: int = Field(..., description="ID of the form to check")


class EvaluationCriterion(BaseModel):
    """Single criterion for form evaluation setup."""
    criterion_name: str = Field(..., description="Criterion name (e.g., 'Technical Feasibility', 'Team Experience')")
    weight: int = Field(..., ge=1, le=100, description="Weight as percentage (1-100). All weights must sum to 100")
    criterion_description: Optional[str] = Field(None, description="What this criterion evaluates")


class ConfigureFormEvaluationInput(BaseModel):
    """Input for configuring form evaluation criteria."""
    form_id: int = Field(..., description="ID of the form to configure")
    criteria: List[EvaluationCriterion] = Field(
        ..., 
        description="Criteria with weights. Weights must sum to 100"
    )


# ==================
# Base Tool Class
# ==================

class EvaluationAPIBaseTool(APIBaseTool):
    """Base class for evaluation tools."""
    
    auth_token: str = ""
    org_id: int = 0
    org_slug: str = ""
    
    def _get_client(self) -> EvaluationAPIClient:
        return EvaluationAPIClient()


# ==================
# Tools
# ==================

class GetFormEvaluationTool(EvaluationAPIBaseTool):
    """Tool for viewing the current evaluation configuration of a form."""
    
    name: str = "get_form_evaluation"
    description: str = """View the current AI evaluation configuration for a form.
Shows what criteria are used to evaluate applications and their weights.
Use this before configuring evaluation to see what's currently set up."""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = GetFormEvaluationInput
    
    def _run_tool(self, form_id: int) -> str:
        client = self._get_client()
        result = client.list_form_criteria(self.auth_token, self.org_slug, form_id)
        
        criteria = result.get("criteria", [])
        # Filter out any criteria with null/missing names (orphaned references)
        criteria = [c for c in criteria if c.get("name")]
        
        if not criteria:
            return f"Form {form_id} has no evaluation criteria configured.\n\nUse configure_form_evaluation to set up how applications will be evaluated."
        
        lines = [f"**Evaluation Configuration for Form {form_id}:**\n"]
        total_weight = 0
        
        for c in criteria:
            name = c.get("name", "Unknown")
            weight = c.get("weight", 0)
            total_weight += weight
            desc = c.get("description", "")
            desc_text = f" - {desc}" if desc else ""
            lines.append(f"- **{name}**: {weight}%{desc_text}")
        
        lines.append(f"\n**Total Weight:** {total_weight}%")
        
        if total_weight != 100:
            lines.append(f"⚠️ Weights should sum to 100%")
        
        return "\n".join(lines)


class ConfigureFormEvaluationTool(EvaluationAPIBaseTool):
    """Tool for configuring evaluation criteria on a form."""
    
    name: str = "configure_form_evaluation"
    description: str = """Configure how applications to a form will be evaluated by AI.
This sets up the evaluation criteria and their weights.

REPLACES any existing configuration - specify all criteria you want.
Weights are percentages (1-100) and must sum to 100.

Example:
{
  "form_id": 5,
  "criteria": [
    {"criterion_name": "Technical Feasibility", "weight": 30, "criterion_description": "Can the project be built?"},
    {"criterion_name": "Team Experience", "weight": 25},
    {"criterion_name": "Research Impact", "weight": 25},
    {"criterion_name": "Budget Efficiency", "weight": 20}
  ]
}

Requires user approval."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = ConfigureFormEvaluationInput
    
    def _run_tool(self, form_id: int, criteria: List[EvaluationCriterion]) -> str:
        client = self._get_client()
        
        # Normalize criteria - handle both EvaluationCriterion objects and dicts (from approval flow)
        normalized_criteria: List[EvaluationCriterion] = []
        for i, c in enumerate(criteria):
            try:
                if isinstance(c, dict):
                    # Validate required fields are present
                    if "criterion_name" not in c:
                        return f"❌ Criterion #{i+1} is missing 'criterion_name' field. Each criterion must have a name."
                    if "weight" not in c:
                        return f"❌ Criterion '{c.get('criterion_name', i+1)}' is missing 'weight' field. Each criterion needs a weight (1-100)."
                    normalized_criteria.append(EvaluationCriterion(**c))
                elif isinstance(c, EvaluationCriterion):
                    normalized_criteria.append(c)
                else:
                    return f"❌ Invalid criterion format at position {i+1}. Expected object with 'criterion_name' and 'weight' fields."
            except Exception as e:
                logger.error(f"Failed to normalize criterion {i}: {c}, error: {e}")
                return f"❌ Invalid criterion at position {i+1}: {str(e)}"
        
        # Validate weights sum to 100
        total_weight = sum(c.weight for c in normalized_criteria)
        if total_weight != 100:
            return f"❌ Weights must sum to 100%. Current total: {total_weight}%"
        
        # Get existing org-level criteria for reuse
        existing = client.list_criteria(self.auth_token, self.org_slug)
        # Build map of existing criteria (filter out any with null names)
        existing_map = {
            c["name"].lower(): c["id"] 
            for c in existing.get("criteria", []) 
            if c.get("name") and c.get("id")
        }
        
        # Clear existing form criteria
        client.detach_all_form_criteria(self.auth_token, self.org_slug, form_id)
        
        # Set up each criterion
        created_criteria = []
        attached_criteria = []
        
        for c in normalized_criteria:
            crit_name = c.criterion_name.strip()
            if not crit_name:
                continue
            
            # Find or create the org-level criterion
            criteria_id = existing_map.get(crit_name.lower())
            
            if not criteria_id:
                # Create new org-level criterion
                result = client.create_criteria(
                    self.auth_token,
                    self.org_slug,
                    crit_name,
                    c.criterion_description,
                )
                criteria_id = result.get("id")
                if not criteria_id:
                    logger.error(f"Failed to create criteria '{crit_name}': no ID returned. Response: {result}")
                    return f"❌ Failed to create criterion '{crit_name}'. Please try again."
                created_criteria.append(crit_name)
                # Add to map for potential reuse within same call
                existing_map[crit_name.lower()] = criteria_id
            
            # Attach to form with weight
            logger.info(f"Attaching criteria {criteria_id} to form {form_id} with weight {c.weight}")
            client.attach_criteria_to_form(
                self.auth_token,
                self.org_slug,
                form_id,
                criteria_id,
                c.weight,
            )
            attached_criteria.append(f"{crit_name} ({c.weight}%)")
        
        # Build response
        lines = [f"✅ Configured evaluation for form {form_id}:\n"]
        
        if created_criteria:
            lines.append(f"Created new criteria: {', '.join(created_criteria)}")
        
        lines.append("**Evaluation criteria:**")
        for item in attached_criteria:
            lines.append(f"  - {item}")
        
        lines.append("\nApplications will now be evaluated using these criteria.")
        
        return "\n".join(lines)


# ==================
# Tool Factory
# ==================

def create_evaluation_tools(auth_token: str, org_id: int = 0, org_slug: str = "") -> List[EvaluationAPIBaseTool]:
    """
    Create evaluation tools.
    
    Args:
        auth_token: Privy authentication token
        org_id: Organization ID
        org_slug: Organization slug
        
    Returns:
        List of evaluation tool instances (2 tools)
    """
    return [
        GetFormEvaluationTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
        ConfigureFormEvaluationTool(auth_token=auth_token, org_id=org_id, org_slug=org_slug),
    ]

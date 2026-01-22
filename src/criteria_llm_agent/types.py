"""
Type definitions for Criteria LLM Agent.

Defines structured formats for criteria evaluation responses and scoring.
"""
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CriteriaEvaluationResult(BaseModel):
    """
    Result of evaluating a single criterion against form responses.
    
    Attributes:
        criterion_id: ID of the evaluated criterion
        criterion_name: Name of the criterion
        criterion_description: Description of what the criterion evaluates
        raw_score: AI-determined score (0, 20, 33, 50, 66, 80, or 100)
        weight: Weight multiplier for this criterion
        weighted_score: raw_score * weight
        reasoning: AI explanation for the score
        is_error: Whether an error occurred during evaluation
        error_message: Error details if is_error is True
    """
    criterion_id: int
    criterion_name: str
    criterion_description: Optional[str] = None
    raw_score: Literal[0, 20, 33, 50, 66, 80, 100]
    weight: float
    weighted_score: float
    reasoning: str
    is_error: bool = False
    error_message: Optional[str] = None
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 2)
        }


class CriteriaScore(BaseModel):
    """
    Intermediate scoring result from AI evaluation.
    
    Attributes:
        score: The determined score (0, 20, 33, 50, 66, 80, or 100)
        reasoning: Explanation for the score
    """
    score: Literal[0, 20, 33, 50, 66, 80, 100]
    reasoning: str


class AggregatedScore(BaseModel):
    """
    Final aggregated evaluation results for all criteria.
    
    Attributes:
        form_id: ID of the evaluated form
        user_id: ID of the user whose submission was evaluated
        team_id: Optional ID of the team associated with the evaluation
        total_weighted_score: Sum of all weighted scores
        max_possible_score: Maximum possible weighted score
        normalized_score: total_weighted_score / max_possible_score * 100
        criteria_evaluations: Individual criterion evaluation results
        evaluation_timestamp: When the evaluation was performed
        reasoning: Optional overall reasoning for the complete evaluation
    """
    form_id: int
    user_id: int
    team_id: Optional[int] = None
    total_weighted_score: float
    max_possible_score: float
    normalized_score: float = Field(ge=0, le=100)
    criteria_evaluations: List[CriteriaEvaluationResult]
    evaluation_timestamp: str
    reasoning: Optional[str] = None
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 2)
        }


class EvaluationRequest(BaseModel):
    """
    Request to evaluate criteria for a form submission.
    
    Attributes:
        org_id: Organization ID
        form_id: ID of the form to evaluate
        user_id: ID of the user whose submission to evaluate
        team_id: Optional ID of the team associated with the evaluation
        
    Note:
        Criteria are automatically fetched from the grant_form_selected_criteria
        connection table, which includes the weights for each criterion.
    """
    org_id: int
    form_id: int
    user_id: int
    team_id: Optional[int] = None

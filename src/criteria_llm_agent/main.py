"""
Main module for Criteria LLM Agent.

Provides easy integration with the existing FastAPI application.
"""
from .router import router
from .types import (
    CriteriaEvaluationResult,
    CriteriaScore,
    AggregatedScore,
    EvaluationRequest
)
from .evaluator import CriteriaEvaluator
from .database import CriteriaDatabase
from .graph import evaluate_single_criterion, create_evaluation_graph
from .model_factory import (
    create_chat_model,
    get_model_provider,
    is_anthropic_model,
    is_gemini_model,
    is_xai_model,
    is_anthropic_available,
    is_vertex_available
)
from src.utils.db_utils import (
    initialize_database,
    get_database_connection,
    return_database_connection,
    close_database,
    test_database_connection
)
from .save_evaluation import save_evaluation_result, get_latest_evaluation

__all__ = [
    # Router
    "router",
    
    # Types
    "CriteriaEvaluationResult",
    "CriteriaScore",
    "AggregatedScore",
    "EvaluationRequest",
    
    # Core functionality
    "CriteriaEvaluator",
    "CriteriaDatabase",
    "evaluate_single_criterion",
    "create_evaluation_graph",
    
    # Model factory
    "create_chat_model",
    "get_model_provider",
    "is_anthropic_model",
    "is_gemini_model",
    "is_xai_model",
    "is_anthropic_available",
    "is_vertex_available",
    
    # Database
    "initialize_database",
    "get_database_connection",
    "return_database_connection",
    "close_database",
    "test_database_connection",
    
    # Evaluation persistence
    "save_evaluation_result",
    "get_latest_evaluation"
]

"""
Criteria LLM Agent - AI-powered criteria evaluation for grant applications.

This module provides automated evaluation of grant application criteria using
LangGraph and multi-provider LLM support. Each criterion is evaluated against
form submissions to provide objective scoring.
"""

from .model_factory import create_chat_model, get_model_provider
from .types import CriteriaEvaluationResult, CriteriaScore, AggregatedScore
from src.utils.db_utils import (
    initialize_database,
    get_database_connection,
    return_database_connection,
    close_database,
    test_database_connection
)

__all__ = [
    "create_chat_model",
    "get_model_provider", 
    "CriteriaEvaluationResult",
    "CriteriaScore",
    "AggregatedScore",
    "initialize_database",
    "get_database_connection",
    "return_database_connection",
    "close_database",
    "test_database_connection"
]

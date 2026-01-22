"""
Startup validation utilities to check system health before serving requests.

This module provides comprehensive validation of all critical system components
including database connectivity, API keys, and model availability.
"""

import os
import sys
from typing import Any, Dict, List, Tuple

from src.utils.logger import logger


class ValidationError(Exception):
    """Raised when a critical validation check fails."""
    pass


class StartupValidator:
    """Comprehensive startup validation for the StableAgent backend."""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate_all(self) -> bool:
        """
        Run all validation checks.
        
        Returns:
            True if all critical checks pass, False otherwise.
        """
        logger.info("StartupValidator: Beginning comprehensive system validation")
        
        # Critical validations (must pass)
        self._validate_environment_variables()
        self._validate_database_config()
        self._validate_api_keys()
        
        # Non-critical validations (warnings only)
        self._validate_optional_config()
        self._validate_model_config()
        
        # Report results
        self._report_results()
        
        return len(self.errors) == 0
    
    def _validate_environment_variables(self) -> None:
        """Validate required environment variables."""
        required_vars = [
            "STABLELAB_TOKEN",
            "DATABASE_HOST",
            "DATABASE_NAME", 
            "DATABASE_USER",
            "DATABASE_PASSWORD",
            "DEFAULT_LLM_PROVIDER",
        ]
        
        missing_vars = []
        for var in required_vars:
            if not os.environ.get(var):
                missing_vars.append(var)
        
        if missing_vars:
            self.errors.append(f"Missing required environment variables: {', '.join(missing_vars)}")
        else:
            logger.info("StartupValidator: Environment variables validation passed")
    
    def _validate_database_config(self) -> None:
        """Validate database configuration and connectivity."""
        try:
            from src.config.database_config import \
                validate_database_environment
            if not validate_database_environment():
                self.errors.append("Database configuration validation failed")
                return
            
            # Test database connectivity
            from src.services.database import DatabaseService
            conn = DatabaseService.get_connection()
            conn.close()
            logger.info("StartupValidator: Database connectivity test passed")
            
        except RuntimeError as e:
            self.errors.append(f"Database validation failed: {e}")
        except Exception as e:
            self.errors.append(f"Unexpected database validation error: {e}")
    
    def _validate_api_keys(self) -> None:
        """Validate API key configuration."""
        provider = os.environ.get("DEFAULT_LLM_PROVIDER", "").lower()
        
        if provider in ("openai", "xai", "x-ai", "x_ai", "x.ai", "grok"):
            if not os.environ.get("OPENAI_API_KEY"):
                self.errors.append("OPENAI_API_KEY required for OpenAI/xAI provider")
        elif provider in ("gemini", "vertex_ai"):
            # Check for Google Cloud credentials
            if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") and not os.path.exists(".gcloud.json"):
                self.errors.append("Google Cloud credentials required for Vertex AI provider")
        else:
            self.warnings.append(f"Unknown LLM provider: {provider}")
        
        logger.info("StartupValidator: API key validation completed")
    
    def _validate_optional_config(self) -> None:
        """Validate optional configuration with warnings."""
        optional_configs = {
            "ALLOWED_ORIGINS": "CORS configuration",
            "DATABASE_PORT": "Database port (defaults to 5432)",
            "DB_STATEMENT_TIMEOUT_MS": "Database timeout (defaults to 60000ms)",
            "RAG_MAX_STEPS": "RAG maximum steps (defaults to 15)",
            "RAG_MAX_SECONDS": "RAG timeout (defaults to 120s)",
        }
        
        for var, description in optional_configs.items():
            if not os.environ.get(var):
                self.warnings.append(f"Optional config {var} not set: {description}")
    
    def _validate_model_config(self) -> None:
        """Validate model configuration."""
        provider = os.environ.get("DEFAULT_LLM_PROVIDER", "").lower()
        
        if provider in ("openai", "xai"):
            model = os.environ.get("OPENAI_DEFAULT_MODEL")
            if not model:
                self.warnings.append("OPENAI_DEFAULT_MODEL not specified, will use default")
        elif provider in ("gemini", "vertex_ai"):
            model = os.environ.get("VERTEX_DEFAULT_MODEL")
            if not model:
                self.warnings.append("VERTEX_DEFAULT_MODEL not specified, will use default")
        
        # Check embedding model
        embedding_model = os.environ.get("EMBEDDING_MODEL_NAME")
        if not embedding_model:
            self.warnings.append("EMBEDDING_MODEL_NAME not specified, will use gemini-embedding-001")
    
    def _report_results(self) -> None:
        """Report validation results."""
        if self.errors:
            logger.error("StartupValidator: %d critical errors found:", len(self.errors))
            for error in self.errors:
                logger.error("  - %s", error)
        
        if self.warnings:
            logger.warning("StartupValidator: %d warnings found:", len(self.warnings))
            for warning in self.warnings:
                logger.warning("  - %s", warning)
        
        if not self.errors and not self.warnings:
            logger.info("StartupValidator: All validation checks passed successfully")
        elif not self.errors:
            logger.info("StartupValidator: Critical validation passed with %d warnings", len(self.warnings))


def validate_startup() -> bool:
    """
    Run startup validation and return success status.
    
    Returns:
        True if validation passes, False if critical errors found.
    """
    validator = StartupValidator()
    return validator.validate_all()


def validate_or_exit() -> None:
    """
    Run startup validation and exit if critical errors are found.
    
    This is intended for use in application startup to ensure the system
    is properly configured before accepting requests.
    """
    if not validate_startup():
        logger.error("StartupValidator: Critical validation errors found. Exiting.")
        sys.exit(1)
    
    logger.info("StartupValidator: System validation completed successfully")


if __name__ == "__main__":
    # Allow running validation as a standalone script
    validate_or_exit()

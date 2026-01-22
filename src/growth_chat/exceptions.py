"""
Custom exceptions for Growth Chat module.

Provides a hierarchy of exceptions with HTTP-like error codes
for consistent error handling across the chat processing pipeline.
"""
from typing import Optional


class GrowthChatError(Exception):
    """Base exception for all Growth Chat errors."""
    
    def __init__(
        self,
        message: str,
        code: int = 500,
        retryable: bool = True,
        retry_after: Optional[float] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        result = {
            "error_code": self.code,
            "error_message": self.message,
            "retryable": self.retryable,
        }
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        return result


# ============================================
# 4xx Client Errors
# ============================================

class ValidationError(GrowthChatError):
    """400 Bad Request - Invalid input data."""
    
    def __init__(self, message: str = "Invalid request data"):
        super().__init__(message, code=400, retryable=False)


class AuthenticationError(GrowthChatError):
    """401 Unauthorized - Authentication required or failed."""
    
    def __init__(self, message: str = "Authentication required. Please log in again."):
        super().__init__(message, code=401, retryable=False)


class AuthorizationError(GrowthChatError):
    """403 Forbidden - User doesn't have permission."""
    
    def __init__(self, message: str = "You don't have permission to access this resource."):
        super().__init__(message, code=403, retryable=False)


class ResourceNotFoundError(GrowthChatError):
    """404 Not Found - Requested resource doesn't exist."""
    
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, code=404, retryable=False)


class ConflictError(GrowthChatError):
    """409 Conflict - Resource already exists or is in conflicting state."""
    
    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message, code=409, retryable=False)


class RateLimitError(GrowthChatError):
    """429 Too Many Requests - Rate limit exceeded."""
    
    def __init__(
        self, 
        message: str = "Rate limit exceeded. Please try again later.",
        retry_after: float = 60.0
    ):
        super().__init__(message, code=429, retryable=True, retry_after=retry_after)


# ============================================
# 5xx Server Errors
# ============================================

class InternalError(GrowthChatError):
    """500 Internal Server Error - Unexpected error."""
    
    def __init__(self, message: str = "An unexpected error occurred. Our team has been notified."):
        super().__init__(message, code=500, retryable=True)


class BadGatewayError(GrowthChatError):
    """502 Bad Gateway - Upstream service error."""
    
    def __init__(self, message: str = "A downstream service is unavailable."):
        super().__init__(message, code=502, retryable=True)


class ServiceUnavailableError(GrowthChatError):
    """503 Service Unavailable - Service temporarily down."""
    
    def __init__(
        self,
        message: str = "Service temporarily unavailable. Please try again later.",
        retry_after: float = 30.0
    ):
        super().__init__(message, code=503, retryable=True, retry_after=retry_after)


class GatewayTimeoutError(GrowthChatError):
    """504 Gateway Timeout - Request timed out."""
    
    def __init__(self, message: str = "Request timed out. The response is being processed in the background."):
        super().__init__(message, code=504, retryable=True)


# ============================================
# Specialized Errors
# ============================================

class DatabaseConnectionError(GrowthChatError):
    """Database connection failed."""
    
    def __init__(self, message: str = "Database connection failed. Please try again."):
        super().__init__(message, code=503, retryable=True, retry_after=5.0)


class CheckpointerError(GrowthChatError):
    """Checkpointer operation failed."""
    
    def __init__(self, message: str = "Failed to save conversation state."):
        super().__init__(message, code=503, retryable=True, retry_after=5.0)


class AgentExecutionError(GrowthChatError):
    """Agent execution failed."""
    
    def __init__(self, message: str = "Agent execution failed."):
        super().__init__(message, code=500, retryable=True)


class ToolExecutionError(GrowthChatError):
    """Tool execution failed."""
    
    def __init__(self, message: str = "Tool execution failed.", tool_name: str = ""):
        self.tool_name = tool_name
        full_message = f"Tool '{tool_name}' failed: {message}" if tool_name else message
        super().__init__(full_message, code=500, retryable=True)


class ConversationNotFoundError(ResourceNotFoundError):
    """Conversation/thread not found."""
    
    def __init__(self, conversation_id: str = ""):
        message = f"Conversation '{conversation_id}' not found" if conversation_id else "Conversation not found"
        super().__init__(message)


class OrganizationNotFoundError(ResourceNotFoundError):
    """Organization not found."""
    
    def __init__(self, org_id: int = 0):
        message = f"Organization '{org_id}' not found" if org_id else "Organization not found"
        super().__init__(message)


# ============================================
# Exception Classification Helpers
# ============================================

def is_retryable_exception(error: Exception) -> bool:
    """Check if an exception should trigger a retry."""
    if isinstance(error, GrowthChatError):
        return error.retryable
    
    # Common retryable exception types
    retryable_names = {
        'ConnectionError',
        'TimeoutError',
        'ConnectionResetError',
        'ConnectionRefusedError',
        'BrokenPipeError',
        'OSError',
        'OperationalError',  # SQLAlchemy/psycopg
        'InterfaceError',    # Database
    }
    
    error_type = type(error).__name__
    return error_type in retryable_names


def classify_exception(error: Exception) -> GrowthChatError:
    """
    Convert a generic exception to a GrowthChatError.
    
    This helps normalize error handling across different libraries.
    """
    if isinstance(error, GrowthChatError):
        return error
    
    error_type = type(error).__name__
    error_msg = str(error)
    
    # Timeout errors
    if 'timeout' in error_type.lower() or 'timeout' in error_msg.lower():
        return GatewayTimeoutError(f"Operation timed out: {error_msg}")
    
    # Connection errors
    if 'connection' in error_type.lower() or 'connection' in error_msg.lower():
        return DatabaseConnectionError(f"Connection error: {error_msg}")
    
    # Authentication errors
    if 'auth' in error_type.lower() or 'unauthorized' in error_msg.lower():
        return AuthenticationError(f"Authentication failed: {error_msg}")
    
    # Permission errors
    if 'permission' in error_type.lower() or 'forbidden' in error_msg.lower():
        return AuthorizationError(f"Permission denied: {error_msg}")
    
    # Rate limit errors
    if 'rate' in error_msg.lower() and 'limit' in error_msg.lower():
        return RateLimitError(f"Rate limit: {error_msg}")
    
    # Default to internal error
    return InternalError(f"Unexpected error: {error_msg}")


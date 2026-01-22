"""
Response types for LangGraph results.

Defines the structured format for LangGraph streaming responses.
"""
from typing import Literal, Union, Optional
from pydantic import BaseModel


class LangGraphResult(BaseModel):
    """
    Structured response format for LangGraph streaming results.

    Attributes:
        id: Unique identifier for the advice (advice_{field_id} format)
        field_id: Original field ID this advice is for
        response: Text content of the response (empty if is_clear is True)
        type: Type of response (issue or advice)
        is_error: Boolean indicating if this is an error response from AI
        is_clear: Boolean indicating if the field value is within acceptable parameters
        server_error: Boolean indicating if this is a server/system error (not AI error)
        note: Optional note field for additional context (e.g., "no AI response")
    """
    id: str
    field_id: str
    response: str
    type: Literal["issue", "advice"]
    is_error: bool
    is_clear: bool = False
    server_error: bool = False
    note: Optional[str] = None

    class Config:
        """Pydantic configuration for JSON serialization."""
        json_encoders = {
            # Add custom encoders if needed
        }

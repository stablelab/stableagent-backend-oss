"""
JSON extraction utilities for parsing LLM responses.

Provides robust JSON extraction from text responses that may contain
JSON within markdown code blocks or mixed with other content.
"""
import re
import json
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract and parse the first valid JSON object from text.

    This function handles multiple formats:
    - Plain JSON objects
    - JSON within markdown code blocks (```json ... ```)
    - JSON mixed with other text

    Args:
        text: The text containing JSON

    Returns:
        Parsed JSON dictionary or None if no valid JSON found
    """
    if not text or not isinstance(text, str):
        return None

    # Strategy 1: Look for JSON in markdown code blocks
    json_obj = _extract_from_code_blocks(text)
    if json_obj is not None:
        return json_obj

    # Strategy 2: Look for JSON objects using regex
    json_obj = _extract_with_regex(text)
    if json_obj is not None:
        return json_obj

    # Strategy 3: Try to parse the entire text as JSON
    json_obj = _try_parse_entire_text(text)
    if json_obj is not None:
        return json_obj

    logger.warning("No valid JSON found in text: %s",
                   text[:100] + "..." if len(text) > 100 else text)
    return None


def _extract_from_code_blocks(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from markdown code blocks."""
    # Pattern for ```json ... ``` or ``` ... ``` blocks
    code_block_patterns = [
        r'```json\s*(.*?)\s*```',  # ```json ... ```
        r'```\s*(.*?)\s*```',      # ``` ... ```
    ]

    for pattern in code_block_patterns:
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        for match in matches:
            json_obj = _try_parse_json(match.strip())
            if json_obj is not None:
                return json_obj

    return None


def _extract_with_regex(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON objects using regex patterns."""
    # Pattern to match JSON objects (simplified but robust)
    # Looks for { ... } with proper nesting
    json_pattern = r'\{(?:[^{}]|{[^{}]*})*\}'

    matches = re.findall(json_pattern, text, re.DOTALL)

    # Try each match, starting with the longest (most complete)
    matches.sort(key=len, reverse=True)

    for match in matches:
        json_obj = _try_parse_json(match.strip())
        if json_obj is not None:
            return json_obj

    return None


def _try_parse_entire_text(text: str) -> Optional[Dict[str, Any]]:
    """Try to parse the entire text as JSON."""
    cleaned_text = text.strip()
    return _try_parse_json(cleaned_text)


def _try_parse_json(json_str: str) -> Optional[Dict[str, Any]]:
    """
    Safely attempt to parse a JSON string.

    Args:
        json_str: String that might contain JSON

    Returns:
        Parsed JSON dictionary or None if parsing fails
    """
    if not json_str or not json_str.strip():
        return None

    try:
        parsed = json.loads(json_str)
        # Ensure it's a dictionary (object)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError) as e:
        logger.debug("JSON parsing failed: %s", str(e))

    return None


def extract_all_json_objects(text: str) -> List[Dict[str, Any]]:
    """
    Extract all valid JSON objects from text.

    Args:
        text: The text containing JSON objects

    Returns:
        List of parsed JSON dictionaries
    """
    if not text or not isinstance(text, str):
        return []

    json_objects = []

    # Extract from code blocks
    code_block_patterns = [
        r'```json\s*(.*?)\s*```',
        r'```\s*(.*?)\s*```',
    ]

    for pattern in code_block_patterns:
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        for match in matches:
            json_obj = _try_parse_json(match.strip())
            if json_obj is not None:
                json_objects.append(json_obj)

    # Extract using regex if no code blocks found
    if not json_objects:
        json_pattern = r'\{(?:[^{}]|{[^{}]*})*\}'
        matches = re.findall(json_pattern, text, re.DOTALL)

        for match in matches:
            json_obj = _try_parse_json(match.strip())
            if json_obj is not None:
                json_objects.append(json_obj)

    return json_objects


def validate_langgraph_result_format(json_obj: Dict[str, Any]) -> bool:
    """
    Validate that a JSON object matches the LangGraphResult format.
    Handles both snake_case (new) and camelCase (legacy) field names.

    Args:
        json_obj: Parsed JSON object to validate

    Returns:
        True if the object has all required fields with correct types
    """
    if not isinstance(json_obj, dict):
        return False

    required_fields = {
        "id": str,
        "response": str,
        "type": str,
        "is_error": bool
    }

    # Check all required fields exist and have correct types
    for field, expected_type in required_fields.items():
        if field not in json_obj:
            return False
        if not isinstance(json_obj[field], expected_type):
            return False

    # Check that type is valid
    if json_obj["type"] not in ["issue", "advice"]:
        return False

    # Convert legacy camelCase fields to snake_case for consistency
    if "isClear" in json_obj and "is_clear" not in json_obj:
        json_obj["is_clear"] = json_obj.pop("isClear")

    # Ensure server_error field exists (default to False if not present)
    if "server_error" not in json_obj:
        json_obj["server_error"] = False

    return True


def extract_and_validate_langgraph_result(text: str, field_id: str) -> Dict[str, Any]:
    """
    Extract and validate a LangGraphResult from LLM response text.

    Args:
        text: The LLM response text
        field_id: The field ID for fallback responses

    Returns:
        Valid LangGraphResult dictionary
    """
    # Try to extract JSON
    json_obj = extract_json_from_text(text)

    if json_obj is not None and validate_langgraph_result_format(json_obj):
        # Ensure the ID matches (in case LLM changed it)
        json_obj["id"] = field_id
        return json_obj

    # Fallback: Create structured response from raw text
    return {
        "id": field_id,
        "response": f"Analysis for field {field_id}: {text}",
        "type": "advice",
        "is_error": False,
        "is_clear": False,
        "server_error": False
    }

"""
Base HTTP client for API endpoints.

Contains shared functionality used by all API clients.
"""
import os
from typing import Any, Dict, Optional

import httpx


class APIError(Exception):
    """Custom exception for API errors."""
    
    def __init__(self, message: str, status_code: int, response: Optional[Dict[str, Any]] = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(f"API Error {status_code}: {message}")


class BaseAPIClient:
    """
    Base class for API clients with shared functionality.
    
    Provides common HTTP client setup, authentication headers,
    response handling, and context manager support.
    """
    
    def __init__(self, base_url: str = None, timeout: float = 30.0):
        """
        Initialize the API client.
        
        Args:
            base_url: Base URL for the API (default from GROWTH_BACKEND_URL env var)
            timeout: Request timeout in seconds (default 30.0)
        """
        self.base_url = (base_url or os.getenv("GROWTH_BACKEND_URL", "http://localhost:4000")).rstrip("/")
        self.client = httpx.Client(timeout=timeout)
    
    def _get_headers(self, auth_token: str) -> Dict[str, str]:
        """
        Get headers for API requests with Privy authentication token.
        
        Args:
            auth_token: Privy authentication token
            
        Returns:
            Dictionary of headers
        """
        return {
            "privy-id-token": auth_token,
            "Content-Type": "application/json",
        }
    
    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """
        Handle API response and raise errors if needed.
        
        Args:
            response: HTTP response
            
        Returns:
            Parsed JSON response
            
        Raises:
            APIError: If the API returns an error
        """
        if response.status_code == 204:
            # No content response (e.g., DELETE)
            return {"success": True}
        
        try:
            data = response.json()
        except Exception:
            data = {"error": "Failed to parse response", "raw": response.text}
        
        if response.status_code >= 400:
            error_msg = data.get("error", "Unknown error")
            if isinstance(data, dict) and "message" in data:
                error_msg = data["message"]
            raise APIError(error_msg, response.status_code, data)
        
        return data
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


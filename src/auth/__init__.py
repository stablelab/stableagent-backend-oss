"""
Privy authentication module for FastAPI.

Provides middleware and dependencies for authenticating users via Privy ID tokens.
"""

from src.auth.middleware import PrivyAuthMiddleware
from src.auth.deps import get_current_user, require_permission

__all__ = ["PrivyAuthMiddleware", "get_current_user", "require_permission"]


"""
Privy authentication middleware for FastAPI.

Authenticates users via Privy ID tokens and attaches user information
and permissions to the request state.
"""

from typing import Optional, Callable
from urllib.parse import unquote
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from src.auth.privy_client import get_privy_client, extract_email_from_privy_user
from src.auth.db import (
    get_user_by_privy_subject,
    get_user_org_permissions,
    get_user_team_permissions,
)
from src.auth.permissions import TEAM_ROLE_PERMISSIONS, AUTHENTICATED_USER_PERMISSIONS
from src.utils.logger import logger


class PrivyAuthMiddleware(BaseHTTPMiddleware):
    """
    Passive middleware that authenticates requests using Privy ID tokens.
    
    This middleware attempts to authenticate all requests but does NOT block
    requests if authentication fails. Instead, it sets request.state.user to
    None for unauthenticated requests and lets route dependencies enforce
    authentication requirements.

    Extracts the token from headers or cookies, verifies it with Privy,
    fetches user data from the database, and attaches user info and
    permissions to the request state.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request and attempt to authenticate the user.
        
        This is a PASSIVE middleware - it never rejects requests.
        Authentication is enforced by route dependencies (get_current_user).

        Args:
            request: FastAPI request object
            call_next: Next middleware/route handler

        Returns:
            Response from the next handler (never returns error directly)
        """

        try:
            # Extract ID token from headers or cookies
            id_token = self._extract_token(request)

            logger.debug(f"Extracted token: {'Yes' if id_token else 'No'} (length: {len(id_token) if id_token else 0})")

            if not id_token:
                logger.debug("No token found in request - setting user to None")
                request.state.user = None
                return await call_next(request)

            # Verify token and get user from Privy
            privy_client = get_privy_client()
            privy_user = await privy_client.get_user(id_token)

            if not privy_user:
                logger.debug("Privy user not found after token verification")
                request.state.user = None
                return await call_next(request)

            # Extract email from Privy user object
            email_address = extract_email_from_privy_user(privy_user)
            logger.debug(f"Extracted email: {email_address}")

            # Get user from database by Privy subject
            privy_subject = str(privy_user.get("id"))
            logger.debug(f"Privy subject: {privy_subject}")
            app_user = get_user_by_privy_subject(privy_subject)

            if not app_user:
                logger.warning(f"App user not found for subject: {privy_subject}")
                request.state.user = None
                return await call_next(request)

            # Check if user is deactivated
            try:
                metadata = app_user.get("metadata", {})
                deactivated = bool(metadata.get("deactivated", False))
                logger.debug(f"User deactivated: {deactivated}, is_global_admin: {app_user.get('is_global_admin', False)}")
                if deactivated and not app_user.get("is_global_admin", False):
                    logger.warning(f"User {app_user['id']} is deactivated")
                    request.state.user = None
                    return await call_next(request)
            except Exception as err:
                logger.warning(
                    f"authMiddleware deactivation check failed: {str(err)}"
                )

            # Get permissions from team-org assignments
            org_permissions = get_user_org_permissions(app_user["id"])
            logger.debug(f"Org permissions: {org_permissions}")

            # Get team memberships and permissions
            team_permissions_data, team_memberships = get_user_team_permissions(
                app_user["id"]
            )
            logger.debug(f"Team memberships: {team_memberships}")

            # Build team permissions from roles
            team_permissions = {}
            for membership in team_memberships:
                team_id = membership["teamId"]
                role = membership["role"]
                perms = TEAM_ROLE_PERMISSIONS.get(role, [])
                team_permissions[team_id] = perms

            # Create permission check functions
            def has_permission(org_id: Optional[int], perm: str) -> bool:
                """Check if user has a specific organization permission."""
                if app_user.get("is_global_admin", False):
                    return True
                if perm in AUTHENTICATED_USER_PERMISSIONS:
                    return True
                if not org_id:
                    return False
                perms = org_permissions.get(org_id, [])
                # org.write implies full control within org
                return perm in perms or "org.write" in perms

            def has_team_permission(team_id: Optional[int], perm: str) -> bool:
                """Check if user has a specific team permission."""
                if app_user.get("is_global_admin", False):
                    return True
                if not team_id:
                    return False
                perms = team_permissions.get(team_id, [])
                return perm in perms

            # Attach user to request state
            request.state.user = {
                "sub": app_user["id"],
                "email": app_user.get("email"),
                "handle": app_user.get("handle"),
                "flags": {
                    "is_global_admin": app_user.get("is_global_admin", False)
                },
                "privy": privy_user,
                "orgPermissions": org_permissions,
                "teamPermissions": team_permissions,
                "hasPermission": has_permission,
                "hasTeamPermission": has_team_permission,
            }

            logger.info(f"Successfully authenticated user: {app_user['id']}")

            # Continue to next handler
            response = await call_next(request)
            return response

        except Exception as e:
            logger.warning(f"authMiddleware failure: {str(e)}")
            logger.warning(f"authMiddleware failure traceback:", exc_info=True)
            # Don't block request - let route dependencies handle auth enforcement
            request.state.user = None
            return await call_next(request)

    def _extract_token(self, request: Request) -> Optional[str]:
        """
        Extract Privy ID token from request headers or cookies.

        Tries methods in order:
        1. privy-id-token header
        2. Authorization: Bearer header
        3. privy-id-token cookie (parsed by FastAPI)
        4. Manual parsing of cookie header

        Args:
            request: FastAPI request object

        Returns:
            ID token string or None if not found
        """
        # Try privy-id-token header first
        header_token = request.headers.get("privy-id-token")
        if header_token:
            return header_token

        # Try Authorization: Bearer header (used by backend-to-backend calls)
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]  # Strip "Bearer " prefix

        # Try parsed cookie
        cookie_token = request.cookies.get("privy-id-token")
        if cookie_token:
            return cookie_token

        # Manual cookie parsing (fallback for edge cases)
        cookie_header = request.headers.get("cookie")
        if cookie_header:
            parts = [p.strip() for p in cookie_header.split(";")]
            for part in parts:
                if part.startswith("privy-id-token="):
                    token_value = part[len("privy-id-token="):]
                    return unquote(token_value)

        return None


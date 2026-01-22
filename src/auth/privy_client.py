"""
Privy REST API client for token verification and user retrieval.

Since there is no official Privy Python SDK, this module directly
interacts with Privy's REST API to verify ID tokens and fetch user data.
"""

import os
from typing import Dict, Any, Optional
from privy import PrivyAPI
from src.utils.logger import logger


class PrivyClient:
    """Client for interacting with Privy's authentication API."""

    def __init__(self, app_id: str, app_secret: str):
        """
        Initialize Privy client.

        Args:
            app_id: Privy application ID
            app_secret: Privy application secret
        """
        self.client = PrivyAPI(app_id=app_id, app_secret=app_secret)

    async def get_user(self, id_token: str) -> Optional[Dict[str, Any]]:
        """
        Verify ID token and retrieve user information from Privy.

        This method verifies the provided ID token by using it to fetch
        user information from Privy's API. If the token is valid, it returns
        the user data; otherwise, it returns None.

        Args:
            id_token: The Privy ID token from the request

        Returns:
            Dict containing user information if token is valid, None otherwise
        """
        try:
            print('verifying', id_token)
            user = self.client.users.get_by_id_token(id_token=id_token)
            print('user', user)
            return user.dict()
        except Exception as e:
            logger.error(f"Error verifying token with Privy SDK: {str(e)}")
            print(f"Error verifying token with Privy SDK: {str(e)}")
            raise e


def get_privy_client() -> PrivyClient:
    """
    Get a configured Privy client instance.

    Returns:
        PrivyClient instance configured with environment variables
    """
    app_id = os.getenv("PRIVY_APP_ID")
    app_secret = os.getenv("PRIVY_APP_SECRET")

    if not app_id or not app_secret:
        raise ValueError("PRIVY_APP_ID and PRIVY_APP_SECRET environment variables are required")

    return PrivyClient(app_id, app_secret)


def extract_email_from_privy_user(privy_user: Dict[str, Any]) -> Optional[str]:
    """
    Extract email address from Privy user object.

    Privy stores email in different locations depending on the account type.
    This function checks both the direct email field and linked accounts.

    Args:
        privy_user: User data from Privy API

    Returns:
        Email address if found, None otherwise
    """
    # Try direct email field first
    if privy_user.get("email") and isinstance(privy_user["email"], dict):
        email_address = privy_user["email"].get("address")
        if email_address:
            return email_address

    # Try linked accounts
    linked_accounts = privy_user.get("linkedAccounts", [])
    if isinstance(linked_accounts, list):
        for account in linked_accounts:
            if isinstance(account, dict) and account.get("type") == "email":
                email_address = account.get("address")
                if email_address:
                    return email_address

    return None


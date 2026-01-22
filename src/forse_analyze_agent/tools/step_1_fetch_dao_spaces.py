# src/forse_analyze_agent/tools/step_1_fetch_dao_spaces.py
"""
DAO Spaces fetching tool with built-in caching.

The DAO spaces data rarely changes, so we cache it at the module level.
First call fetches from API, subsequent calls return cached data.
"""

from datetime import datetime, timezone
from typing import List, Optional

import httpx
from langchain_core.tools import tool

from src.forse_analyze_agent.utils.validators import get_required_env
from src.utils.logger import logger

from .cgl_types import DaoSpace


# Module-level cache - persists across all requests while the process runs
_cached_dao_spaces: Optional[List[DaoSpace]] = None
_cache_timestamp: Optional[datetime] = None
_cache_ttl_seconds: int = 3600  # 1 hour


def _is_cache_valid() -> bool:
    """Check if cached data is still fresh."""
    if _cached_dao_spaces is None or _cache_timestamp is None:
        return False
    age = (datetime.now(timezone.utc) - _cache_timestamp).total_seconds()
    return age < _cache_ttl_seconds


def get_cached_dao_spaces() -> Optional[List[DaoSpace]]:
    """Get cached DAO spaces if available and fresh."""
    if _is_cache_valid():
        return _cached_dao_spaces
    return None


def invalidate_cache() -> None:
    """Clear the cache (call when you need fresh data)."""
    global _cached_dao_spaces, _cache_timestamp
    _cached_dao_spaces = None
    _cache_timestamp = None
    logger.debug("DAO spaces cache invalidated")


@tool(
    description="Fetch available DAO spaces. Each space contains dashboards. Data is cached for 1 hour.",
    name_or_callable="step_1_fetch_dao_spaces",
)
async def step_1_fetch_dao_spaces(
    timeout: int = 30,
    force_refresh: bool = False
) -> List[DaoSpace]:
    """
    Fetch DAO spaces from the Forse backend.
    
    Results are cached for 1 hour. Subsequent calls return cached data.
    
    Args:
        timeout: Request timeout in seconds
        force_refresh: If True, bypass cache and fetch fresh data
    
    Returns:
        List of DAO spaces, each containing dashboards
    """
    global _cached_dao_spaces, _cache_timestamp
    
    # Return cached data if valid and not forcing refresh
    if not force_refresh and _is_cache_valid():
        logger.debug("Returning cached DAO spaces")
        return _cached_dao_spaces
    
    # Fetch fresh data
    try:
        base_url = get_required_env("FORSE_BACKEND_URL")
        cookies = {"jwt": get_required_env("FORSE_BACKEND_JWT")}
    except Exception as e:
        logger.error(f"Missing environment variables: {e}")
        # Return cached data as fallback if available
        if _cached_dao_spaces:
            logger.warning("Using stale cache due to env error")
            return _cached_dao_spaces
        return []

    url = f"{base_url}/api/dao_spaces"

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            logger.debug(f"Fetching DAO spaces from: {url}")
            response = await client.get(url, cookies=cookies)
            response.raise_for_status()
            
            data = response.json()
            
            # Update cache
            _cached_dao_spaces = data
            _cache_timestamp = datetime.now(timezone.utc)
            logger.info(f"Cached {len(data)} DAO spaces")
            
            return data

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching dao_spaces: {e.response.status_code}")
            # Return cached data as fallback
            if _cached_dao_spaces:
                logger.warning("Using stale cache due to HTTP error")
                return _cached_dao_spaces
            return []
        except Exception as e:
            logger.error(f"Error fetching dao_spaces: {str(e)}")
            # Return cached data as fallback
            if _cached_dao_spaces:
                logger.warning("Using stale cache due to error")
                return _cached_dao_spaces
            return []

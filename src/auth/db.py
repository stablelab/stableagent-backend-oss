"""
Database utilities for authentication.

Handles querying user data, permissions, and team/org relationships
from the PostgreSQL database.
"""

import psycopg2
import json
from typing import Dict, List, Optional, Any, Tuple
from src.config.common_settings import (
    GROWTH_DATABASE_HOST,
    GROWTH_DATABASE_PORT,
    GROWTH_DATABASE_NAME,
    GROWTH_DATABASE_USER,
    GROWTH_DATABASE_PASSWORD,
)
from src.utils.logger import logger


def get_auth_connection():
    """
    Get a database connection for authentication queries.

    Returns:
        psycopg2 connection object
    """
    return psycopg2.connect(
        host=GROWTH_DATABASE_HOST,
        port=GROWTH_DATABASE_PORT,
        database=GROWTH_DATABASE_NAME,
        user=GROWTH_DATABASE_USER,
        password=GROWTH_DATABASE_PASSWORD,
    )


def get_user_by_privy_subject(sub: str) -> Optional[Dict[str, Any]]:
    """
    Get user by Privy subject ID.

    Args:
        sub: Privy subject ID (privy_subject column)

    Returns:
        User dict with keys: id, privy_subject, email, handle, metadata, is_global_admin
        Returns None if user not found
    """
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, privy_subject, email, handle, metadata, is_global_admin
                FROM users
                WHERE privy_subject = %s
                """,
                (sub,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0],
                    "privy_subject": row[1],
                    "email": row[2],
                    "handle": row[3],
                    "metadata": row[4] if isinstance(row[4], dict) else {},
                    "is_global_admin": row[5],
                }
            return None
    except Exception as e:
        logger.error(f"Error fetching user by privy_subject: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()


def get_user_org_permissions(user_id: int) -> Dict[int, List[str]]:
    """
    Get organization permissions for a user through their team memberships.

    Joins: team_members → org_teams → org_roles
    Returns permissions grouped by organization ID.

    Args:
        user_id: User ID

    Returns:
        Dict mapping org_id to list of permission strings
    """
    org_permissions: Dict[int, List[str]] = {}

    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ot.id_org, r.permissions
                FROM team_members AS tm
                JOIN org_teams AS ot ON ot.id_team = tm.team_id
                LEFT JOIN org_roles AS r ON r.id = ot.id_role
                WHERE tm.user_id = %s
                """,
                (user_id,),
            )

            for row in cur.fetchall():
                org_id = row[0]
                permissions_data = row[1]

                try:
                    # Parse permissions - could be JSON string or already a list
                    if isinstance(permissions_data, list):
                        perms = permissions_data
                    elif isinstance(permissions_data, str):
                        perms = json.loads(permissions_data)
                    elif permissions_data is None:
                        perms = []
                    else:
                        perms = []

                    # Initialize org permissions if not exists
                    if org_id not in org_permissions:
                        org_permissions[org_id] = []

                    # Merge permissions from all teams user belongs to in this org
                    org_permissions[org_id] = list(
                        set(org_permissions[org_id] + perms)
                    )

                except Exception as e:
                    logger.warn(
                        f"Failed parsing team org permissions for org {org_id}: {str(e)}"
                    )

        return org_permissions

    except Exception as e:
        logger.error(f"Error fetching org permissions: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()


def get_user_team_permissions(user_id: int) -> Tuple[Dict[int, List[str]], List[Dict[str, Any]]]:
    """
    Get team permissions for a user based on their team memberships.

    Args:
        user_id: User ID

    Returns:
        Tuple of (team_permissions_dict, team_memberships_list)
        - team_permissions_dict: Dict mapping team_id to list of permission strings
        - team_memberships_list: List of dicts with team_id and role
    """
    team_permissions: Dict[int, List[str]] = {}
    team_memberships: List[Dict[str, Any]] = []

    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT team_id, role
                FROM team_members
                WHERE user_id = %s
                """,
                (user_id,),
            )

            for row in cur.fetchall():
                team_id = row[0]
                role = row[1]

                team_memberships.append({"teamId": team_id, "role": role})

        return team_permissions, team_memberships

    except Exception as e:
        logger.error(f"Error fetching team permissions: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()


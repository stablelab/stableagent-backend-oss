"""
Example usage of Privy authentication middleware.

This file demonstrates various patterns for using the authentication
system in your FastAPI routes.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from src.auth import get_current_user, require_global_admin

# Example router
router = APIRouter(prefix="/api/example", tags=["examples"])


# ============================================================================
# Basic Authentication
# ============================================================================


@router.get("/profile")
async def get_user_profile(user: dict = Depends(get_current_user)):
    """Get the current user's profile."""
    return {
        "user_id": user["sub"],
        "email": user["email"],
        "handle": user["handle"],
        "is_admin": user["flags"]["is_global_admin"],
    }


# ============================================================================
# Organization Permissions
# ============================================================================


@router.get("/org/{org_id}/forms")
async def list_forms(org_id: int, user: dict = Depends(get_current_user)):
    """List forms - requires read permission for the organization."""
    if not user["hasPermission"](org_id, "form.read.all"):
        raise HTTPException(
            status_code=403, detail="Missing permission: form.read.all"
        )

    # Your logic here
    return {"org_id": org_id, "forms": []}


@router.post("/org/{org_id}/forms")
async def create_form(org_id: int, user: dict = Depends(get_current_user)):
    """Create a form - requires form.create permission."""
    if not user["hasPermission"](org_id, "form.create"):
        raise HTTPException(status_code=403, detail="Missing permission: form.create")

    # Your logic here
    return {"message": "Form created"}


@router.put("/org/{org_id}/settings")
async def update_org_settings(org_id: int, user: dict = Depends(get_current_user)):
    """Update organization settings - requires org.write permission."""
    if not user["hasPermission"](org_id, "org.write"):
        raise HTTPException(status_code=403, detail="Missing permission: org.write")

    # Your logic here
    return {"message": "Settings updated"}


# ============================================================================
# Team Permissions
# ============================================================================


@router.get("/team/{team_id}")
async def get_team_info(team_id: int, user: dict = Depends(get_current_user)):
    """Get team info - requires team.read permission."""
    if not user["hasTeamPermission"](team_id, "team.read"):
        raise HTTPException(status_code=403, detail="Missing permission: team.read")

    # Your logic here
    return {"team_id": team_id, "name": "Example Team"}


@router.post("/team/{team_id}/invite")
async def invite_team_member(team_id: int, user: dict = Depends(get_current_user)):
    """Invite a team member - requires team.member.invite permission."""
    if not user["hasTeamPermission"](team_id, "team.member.invite"):
        raise HTTPException(
            status_code=403, detail="Missing permission: team.member.invite"
        )

    # Your logic here
    return {"message": "Invitation sent"}


@router.delete("/team/{team_id}")
async def delete_team(team_id: int, user: dict = Depends(get_current_user)):
    """Delete a team - requires team.delete permission."""
    if not user["hasTeamPermission"](team_id, "team.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: team.delete")

    # Your logic here
    return {"message": "Team deleted"}


# ============================================================================
# Global Admin Only
# ============================================================================


@router.get("/admin/stats")
async def admin_stats(
    user: dict = Depends(get_current_user), _: None = Depends(require_global_admin)
):
    """Get admin statistics - only accessible by global admins."""
    # This endpoint can only be accessed by global admins
    return {"total_users": 100, "total_orgs": 10}


# ============================================================================
# Complex Permission Checks
# ============================================================================


@router.post("/org/{org_id}/submission/{submission_id}/evaluate")
async def trigger_evaluation(
    org_id: int, submission_id: int, user: dict = Depends(get_current_user)
):
    """
    Trigger evaluation for a submission.
    
    Requires either:
    - evaluation.trigger.own (if user owns the submission)
    - evaluation.read.all (if user is staff/admin)
    """
    has_trigger_own = user["hasPermission"](org_id, "evaluation.trigger.own")
    has_read_all = user["hasPermission"](org_id, "evaluation.read.all")

    if not (has_trigger_own or has_read_all):
        raise HTTPException(
            status_code=403,
            detail="Missing permission: evaluation.trigger.own or evaluation.read.all",
        )

    # Your logic here - might need to verify ownership if using trigger.own
    return {"message": "Evaluation triggered"}


@router.get("/org/{org_id}/builders/journey")
async def get_builders_journey(org_id: int, user: dict = Depends(get_current_user)):
    """
    Get builders journey data.
    
    Can return different data based on permission level:
    - builders.journey.read.all: See all builders
    - builders.journey.read.own: See only own journey
    """
    can_read_all = user["hasPermission"](org_id, "builders.journey.read.all")
    can_read_own = user["hasPermission"](org_id, "builders.journey.read.own")

    if not (can_read_all or can_read_own):
        raise HTTPException(
            status_code=403,
            detail="Missing permission: builders.journey.read.all or builders.journey.read.own",
        )

    if can_read_all:
        # Return all builders
        return {"scope": "all", "builders": []}
    else:
        # Return only user's own journey
        return {"scope": "own", "user_id": user["sub"], "journey": {}}


# ============================================================================
# Authenticated User Permissions
# ============================================================================


@router.post("/teams")
async def create_team(user: dict = Depends(get_current_user)):
    """
    Create a new team.
    
    All authenticated users can create teams (team.create is in
    AUTHENTICATED_USER_PERMISSIONS).
    """
    # No permission check needed - all authenticated users can create teams
    # The middleware already verifies authentication

    return {"message": "Team created", "created_by": user["sub"]}


# ============================================================================
# Optional Authentication
# ============================================================================


async def get_optional_user(user: Optional[dict] = None) -> Optional[dict]:
    """Optional user dependency - doesn't require authentication."""
    # Note: This is a placeholder. In practice, you'd need to make
    # get_current_user return None instead of raising an exception
    # for optional auth routes.
    return user


@router.get("/projects/public")
async def list_public_projects(user: Optional[dict] = None):
    """
    List public projects - no authentication required.
    
    Note: This endpoint would need to be excluded from the middleware
    or the middleware would need to be made optional for certain routes.
    """
    if user:
        # Return more info for authenticated users
        return {"projects": [], "authenticated": True}
    else:
        # Return limited info for anonymous users
        return {"projects": [], "authenticated": False}


# ============================================================================
# Utility Functions
# ============================================================================


def check_permission_or_403(user: dict, org_id: int, permission: str):
    """Helper function to check permission and raise 403 if not allowed."""
    if not user["hasPermission"](org_id, permission):
        raise HTTPException(
            status_code=403, detail=f"Missing permission: {permission}"
        )


def check_team_permission_or_403(user: dict, team_id: int, permission: str):
    """Helper function to check team permission and raise 403 if not allowed."""
    if not user["hasTeamPermission"](team_id, permission):
        raise HTTPException(
            status_code=403, detail=f"Missing team permission: {permission}"
        )


# Example using the helper functions
@router.put("/org/{org_id}/form/{form_id}")
async def update_form(
    org_id: int, form_id: int, user: dict = Depends(get_current_user)
):
    """Update a form - requires form.update permission."""
    check_permission_or_403(user, org_id, "form.update")

    # Your logic here
    return {"message": "Form updated", "form_id": form_id}


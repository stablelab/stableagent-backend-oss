# Privy Authentication Module

FastAPI middleware and dependencies for authenticating users via Privy ID tokens, with support for organization and team-based permissions.

## Overview

This module provides:
- **Middleware**: Automatically authenticates requests using Privy ID tokens
- **Dependencies**: FastAPI dependencies for accessing authenticated user data
- **Permissions**: Organization and team-based permission checking

## Setup

### 1. Environment Variables

Add these to your `.env` file:

```bash
# Required for authentication
PRIVY_APP_ID=your_privy_app_id
PRIVY_APP_SECRET=your_privy_app_secret

# Already required by the app
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=your_database
DATABASE_USER=your_user
DATABASE_PASSWORD=your_password
```

### 2. Database Schema

The following tables must exist:
- `users` - User accounts with `privy_subject`, `email`, `handle`, `metadata`, `is_global_admin`
- `teams` - Team definitions
- `team_members` - User memberships in teams with roles
- `organisations` - Organization definitions
- `org_teams` - Team assignments to organizations
- `org_roles` - Organization role definitions with permissions

See the database schema files in the main documentation for details.

### 3. Middleware Configuration

The middleware is automatically enabled in `src/main.py` when `PRIVY_APP_ID` and `PRIVY_APP_SECRET` are set.

It applies to all routes except:
- `/healthz`
- `/health`
- `/`
- `/docs`
- `/openapi.json`
- `/redoc`

## Usage

### Get Current User Info

Use the `/auth/me` endpoint to get the authenticated user's information:

```bash
# With header
curl -H "privy-id-token: YOUR_TOKEN" https://api.example.com/auth/me

# With cookie (if set by browser)
curl -b "privy-id-token=YOUR_TOKEN" https://api.example.com/auth/me
```

Response:
```json
{
  "sub": 123,
  "email": "user@example.com",
  "handle": "username",
  "flags": {
    "is_global_admin": false
  },
  "orgPermissions": {
    "1": ["org.read", "form.create"]
  },
  "teamPermissions": {
    "5": ["team.read", "team.update"]
  },
  "privy": {
    "id": "did:privy:...",
    "email": {...},
    "linkedAccounts": [...]
  }
}
```

### Basic Authentication

Use the `get_current_user` dependency to access the authenticated user:

```python
from fastapi import APIRouter, Depends
from src.auth import get_current_user

router = APIRouter()

@router.get("/me")
async def get_profile(user: dict = Depends(get_current_user)):
    return {
        "id": user["sub"],
        "email": user["email"],
        "handle": user["handle"],
        "is_admin": user["flags"]["is_global_admin"]
    }
```

### Organization Permissions

Check if a user has specific organization permissions:

```python
from fastapi import APIRouter, Depends, HTTPException
from src.auth import get_current_user

router = APIRouter()

@router.post("/org/{org_id}/forms")
async def create_form(
    org_id: int,
    user: dict = Depends(get_current_user)
):
    # Check if user has permission to create forms in this org
    if not user["hasPermission"](org_id, "form.create"):
        raise HTTPException(status_code=403, detail="Missing permission: form.create")
    
    return {"message": "Form created"}
```

### Team Permissions

Check if a user has specific team permissions:

```python
from fastapi import APIRouter, Depends, HTTPException
from src.auth import get_current_user

router = APIRouter()

@router.post("/team/{team_id}/invite")
async def invite_member(
    team_id: int,
    user: dict = Depends(get_current_user)
):
    # Check if user can invite members to this team
    if not user["hasTeamPermission"](team_id, "team.member.invite"):
        raise HTTPException(status_code=403, detail="Missing permission: team.member.invite")
    
    return {"message": "Invitation sent"}
```

### Using Permission Dependencies

Use built-in permission dependencies for cleaner code:

```python
from fastapi import APIRouter, Depends
from src.auth import get_current_user, require_global_admin

router = APIRouter()

@router.get("/admin/stats")
async def admin_stats(
    user: dict = Depends(get_current_user),
    _: None = Depends(require_global_admin)
):
    # Only global admins can access this endpoint
    return {"stats": "admin data"}
```

## User Object Structure

The authenticated user object attached to `request.state.user` contains:

```python
{
    "sub": 123,                          # User ID from database
    "email": "user@example.com",         # User email
    "handle": "username",                # User handle
    "flags": {
        "is_global_admin": False         # Global admin flag
    },
    "privy": { ... },                    # Full Privy user object
    "orgPermissions": {                  # Organization permissions by org ID
        1: ["org.read", "form.create"],
        2: ["org.read", "org.write"]
    },
    "teamPermissions": {                 # Team permissions by team ID
        5: ["team.read", "team.update"],
        6: ["team.read"]
    },
    "hasPermission": function,           # Check org permission
    "hasTeamPermission": function        # Check team permission
}
```

## Permission System

### Organization Permissions

Organization permissions are derived from:
1. User's team memberships
2. Team assignments to organizations (via `org_teams`)
3. Role permissions for each organization (via `org_roles`)

Users with `org.write` permission have full control within that organization.

### Team Permissions

Team permissions are based on the user's role in the team:
- **Admin**: Full team management
- **Builder**: Read-only access
- **Account Manager**: Team and member management

### Global Admin

Users with `is_global_admin = true` bypass all permission checks.

### Authenticated User Permissions

All authenticated users have these permissions:
- `team.create` - Can create new teams

## Available Permissions

See `src/auth/permissions.py` for the complete list of available permissions.

Key permission categories:
- `org.*` - Organization management
- `form.*` - Form operations
- `criteria.*` - Criteria management
- `milestone.*` - Milestone operations
- `workflow.*` - Workflow operations
- `submission.*` - Submission management
- `program.*` - Program management
- `team.*` - Team operations
- `project.*` - Project access
- `evaluation.*` - Evaluation operations

## Token Handling

The middleware extracts Privy ID tokens from:
1. `privy-id-token` header
2. `privy-id-token` cookie
3. Manual cookie header parsing (fallback)

This ensures compatibility with tokens set by other applications in a cross-domain setup.

## Error Responses

- `401 Unauthorized (no token)` - No Privy ID token found
- `401 Unauthorized (no privy user)` - Invalid token or Privy API failure
- `401 Unauthorized (user not found in database)` - Valid token but user doesn't exist in DB
- `401 Unauthorized (auth failure)` - General authentication error
- `403 Account deactivated` - User account is deactivated
- `403 Missing required permission` - User lacks required permission

## Security Notes

1. **Read-Only User Lookup**: The middleware does NOT create users. Users must exist in the database with matching `privy_subject`.
2. **CORS Configuration**: Cookies work across origins with `allow_credentials=True` in CORS middleware.
3. **HTTPS Required**: Cross-origin cookies require HTTPS with `Secure` and `SameSite=None` flags.
4. **Token Verification**: All tokens are verified with Privy's API before acceptance.

## Troubleshooting

### "Unauthorized (no privy user)"
- Check that `PRIVY_APP_ID` and `PRIVY_APP_SECRET` are correct
- Verify the token is valid and not expired
- Check network connectivity to auth.privy.io

### "Unauthorized (user not found in database)"
- Ensure the user exists in the `users` table
- Verify `privy_subject` matches the Privy user ID
- Users must be created separately (middleware is read-only)

### "Account deactivated"
- User's `metadata.deactivated` is set to `true`
- Only global admins can access with deactivated accounts

### Permission denied
- Check user's team memberships in `team_members`
- Verify team assignments to orgs in `org_teams`
- Check org role permissions in `org_roles`
- Ensure role name matches exactly in `team_members.role`


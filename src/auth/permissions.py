"""
Permission definitions and role configurations.

Defines all available permissions and their assignments to roles
for both organization-level and team-level access control.
"""

from typing import Dict, List

# Type alias for permission keys
PermissionKey = str

# Role definition structure
RoleDefinition = Dict[str, any]

# Organization role definitions
ROLE_DEFINITIONS: Dict[str, RoleDefinition] = {
    "Admin": {
        "name": "Admin",
        "description": "Full access to all organisation resources and actions.",
        "permissions": [
            "org.read",
            "org.write",
            "form.create",
            "form.read.all",
            "form.read.own",
            "form.update",
            "form.attach.milestone",
            "form.attach.workflow",
            "form.criteria.attach",
            "criteria.create",
            "criteria.read.all",
            "criteria.update",
            "milestone.create",
            "milestone.read.all",
            "milestone.update",
            "workflow.create",
            "workflow.read.all",
            "workflow.update",
            "submission.create",
            "submission.read.all",
            "submission.read.own",
            "program.create",
            "program.read.all",
            "program.update",
            "program.delete",
            "program.reviewer.add",
            "program.reviewer.remove",
            "org.users.assign",
            "org.users.remove",
            "builders.journey.read.all",
            "project.privacy.manage",
            "evaluation.trigger.own",
            "evaluation.read.own",
            "evaluation.reasoning.read.own",
            "evaluation.read.all",
        ],
    },
    "Staff": {
        "name": "Staff",
        "description": "Manage forms, criteria, milestones, and workflows. View all data.",
        "permissions": [
            "org.read",
            "form.create",
            "form.read.all",
            "form.update",
            "form.attach.milestone",
            "form.attach.workflow",
            "form.criteria.attach",
            "criteria.create",
            "criteria.read.all",
            "criteria.update",
            "milestone.read.all",
            "workflow.read.all",
            "submission.create",
            "submission.read.all",
            "submission.read.own",
            "program.read.all",
            "org.users.assign",
            "org.users.remove",
            "builders.journey.read.all",
            "evaluation.read.all",
            "evaluation.reasoning.read.own",
        ],
    },
    "Builder": {
        "name": "Builder",
        "description": "Submit answers to forms and view own submissions.",
        "permissions": [
            "form.read.own",
            "submission.create",
            "submission.read.own",
            "project.read.org",
            "project.read.public",
            "evaluation.trigger.own",
            "evaluation.read.own",
            "evaluation.reasoning.read.own",
        ],
    },
    "Guest": {
        "name": "Guest",
        "description": "No read or write permissions.",
        "permissions": [],
    },
}

# All available permission keys
PERMISSION_KEYS: List[PermissionKey] = [
    "org.read",
    "org.write",
    "form.create",
    "form.read.all",
    "form.read.own",
    "form.update",
    "form.attach.milestone",
    "form.attach.workflow",
    "form.criteria.attach",
    "criteria.create",
    "criteria.read.all",
    "criteria.update",
    "milestone.create",
    "milestone.read.all",
    "milestone.update",
    "workflow.create",
    "workflow.read.all",
    "workflow.update",
    "submission.create",
    "submission.read.all",
    "submission.read.own",
    "program.create",
    "program.read.all",
    "program.update",
    "program.delete",
    "program.reviewer.add",
    "program.reviewer.remove",
    "org.users.assign",
    "org.users.remove",
    "team.create",
    "team.read",
    "team.update",
    "team.delete",
    "team.member.invite",
    "team.member.remove",
    "team.member.update",
    "builders.journey.read.all",
    "builders.journey.read.own",
    "builders.journey.profile.update",
    "project.read.public",
    "project.read.org",
    "project.privacy.manage",
    "evaluation.trigger.own",
    "evaluation.read.own",
    "evaluation.reasoning.read.own",
    "evaluation.read.all",
]

# Team-scoped permissions: these apply within a specific team based on role
TEAM_ROLE_PERMISSIONS: Dict[str, List[PermissionKey]] = {
    "Admin": [
        "team.read",
        "team.update",
        "team.delete",
        "team.member.invite",
        "team.member.remove",
        "team.member.update",
        "builders.journey.profile.update",
        "project.privacy.manage",
    ],
    "Builder": [
        "team.read",
        "builders.journey.read.own",
    ],
    "Account Manager": [
        "team.read",
        "team.update",
        "team.member.invite",
        "team.member.remove",
        "team.member.update",
        "builders.journey.profile.update",
    ],
}

# Global permission: any authenticated user can create teams
AUTHENTICATED_USER_PERMISSIONS: List[PermissionKey] = [
    "team.create",
]


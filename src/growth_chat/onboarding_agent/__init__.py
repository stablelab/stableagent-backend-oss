"""
Onboarding Agent module.

Provides guided onboarding flows for:
- Admin setup: Organization configuration, branding, programs, forms, invites
- User joining: Profile setup, team selection, getting started
"""

from .graph import create_onboarding_graph
from .prompts import (
    ONBOARDING_SYSTEM_PROMPT_TEMPLATE,
    ADMIN_ONBOARDING_PROMPT,
    USER_ONBOARDING_PROMPT,
)
from .tools.onboarding_tools import create_onboarding_tools

__all__ = [
    "create_onboarding_graph",
    "create_onboarding_tools",
    "ONBOARDING_SYSTEM_PROMPT_TEMPLATE",
    "ADMIN_ONBOARDING_PROMPT",
    "USER_ONBOARDING_PROMPT",
]


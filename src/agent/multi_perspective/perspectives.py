"""
Multi-perspective analysis system with predefined perspectives.

This module provides:
- PREDEFINED_PERSPECTIVES: Dictionary of available perspective prompts that can be used by name
- Functions to access and work with perspectives

Explicitly specify which perspectives to use (no defaults)
"""
from typing import Dict, List, Tuple

# Perspective definition: (name, prompt)
PerspectivePrompt = Tuple[str, str]


# Predefined perspective prompts
# These are the available perspectives that can be used by name
# Users must explicitly specify which ones to use - there are no defaults
PREDEFINED_PERSPECTIVES: Dict[str, str] = {
    "conservative": """
CONSERVATIVE PERSPECTIVE:
Focus on risk mitigation, fiscal prudence, precedent, compliance, operational burden, and long-term sustainability.
Assess budget justification, milestone realism, downside scenarios, maintenance costs, and treasury runway impact.
Provide a cautious, risk-aware analysis that prioritizes stability and resilience over novelty.
""",
    "progressive": """
PROGRESSIVE PERSPECTIVE:
Focus on innovation potential, strategic differentiation, community value creation, ecosystem growth, and compounding upside.
Assess scalability paths, network effects, talent attraction, leverage of prior work, and high-ROI experiments.
Provide an optimistic, opportunity-focused analysis that embraces well-reasoned change with safeguards.
""",
    "balanced": """
BALANCED PERSPECTIVE:
Focus on cost–benefit tradeoffs, stakeholder impacts, execution realism, and measured risk–reward balance.
Weigh evidence quality, clarity of KPIs, milestones and monitoring, and adequacy of risk controls.
Provide an even-handed analysis that integrates both prudence and ambition.
""",
    "technical": """
TECHNICAL PERSPECTIVE:
Focus on technical feasibility, architecture soundness, security, scalability, performance, dependencies, and integration risks.
Assess implementation plan, effort estimate, realism of timelines, quality standards, and required expertise/tooling.
Provide a rigorous engineering analysis centered on feasibility and execution risk.
""",
}


def get_available_perspectives() -> List[str]:
    """Get a list of all available predefined perspective names."""
    return list(PREDEFINED_PERSPECTIVES.keys())


def get_perspective_prompt(name: str) -> str:
    """Get a predefined perspective prompt by name"""
    return PREDEFINED_PERSPECTIVES.get(name.lower(), "")

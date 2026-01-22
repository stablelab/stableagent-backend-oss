"""
Dynamic Perspective Generator for Multi-Perspective Analysis.

Generates 3-5 custom reviewer perspectives based on:
- Program goals and description
- Form structure (what applicants submit)
- Evaluation criteria (what matters for scoring)
"""
import json
import logging
from typing import List, Optional, Protocol, Tuple

from .types import (
    CriteriaContext,
    DynamicPerspective,
    FormFieldContext,
    PerspectiveContext,
    ProgramContext,
)

logger = logging.getLogger(__name__)


class GeneratorLLM(Protocol):
    """Protocol for LLM client used in perspective generation."""
    def generate_from_prompt(self, prompt: str, **kwargs) -> str:  # pragma: no cover
        ...


PERSPECTIVE_GENERATION_SYSTEM_PROMPT = """You are an expert at designing reviewer panels for grant program evaluations.

Your task is to generate 3-5 distinct reviewer perspectives that will provide comprehensive coverage of a grant submission evaluation. Each perspective should represent a different "expert reviewer" role.

Guidelines:
1. Create perspectives that complement each other - avoid overlap
2. Align perspectives with the evaluation criteria and their weights
3. Consider the program's specific goals and focus areas
4. Make each perspective actionable with clear focus areas and questions
5. Ensure perspectives cover both technical and non-technical aspects

Return your response as a JSON array of perspectives."""


PERSPECTIVE_GENERATION_PROMPT_TEMPLATE = """Based on this grant program and its evaluation criteria, generate distinct reviewer perspectives.

## Program Details
**Name:** {program_name}
**Description:** {program_description}
{budget_info}

## Form Fields (What Applicants Submit)
{form_fields_summary}

## Evaluation Criteria
{criteria_summary}

---

Generate 3-5 reviewer perspectives. For each perspective, provide:
- name: A clear role name (e.g., "Technical Feasibility Expert", "Community Impact Analyst")
- description: What this reviewer focuses on and why
- focus_areas: 2-4 key areas this perspective prioritizes
- key_questions: 3-5 questions this reviewer asks when evaluating
- relevant_criteria: Names of criteria this perspective emphasizes (from the list above)

Return as a JSON array:
```json
[
  {{
    "name": "...",
    "description": "...",
    "focus_areas": ["...", "..."],
    "key_questions": ["...", "..."],
    "relevant_criteria": ["...", "..."]
  }}
]
```

Generate the perspectives now:"""


class PerspectiveGenerator:
    """Generates dynamic reviewer perspectives based on program context."""
    
    def __init__(self, llm: GeneratorLLM, num_perspectives: int = 4):
        """
        Initialize the perspective generator.
        
        Args:
            llm: LLM client that implements generate_from_prompt method
            num_perspectives: Target number of perspectives (3-5)
        """
        self.llm = llm
        self.num_perspectives = num_perspectives
    
    def generate(self, context: PerspectiveContext) -> List[DynamicPerspective]:
        """
        Generate custom perspectives based on context.
        
        Args:
            context: Full perspective context including program, criteria, form fields
            
        Returns:
            List of generated DynamicPerspective objects
        """
        return self.generate_perspectives(
            program=context.program,
            form_fields=context.form_fields,
            criteria=context.criteria,
            num_perspectives=self.num_perspectives,
        )
    
    def generate_perspectives(
        self,
        program: ProgramContext,
        form_fields: List[FormFieldContext],
        criteria: List[CriteriaContext],
        num_perspectives: Optional[int] = None,
    ) -> List[DynamicPerspective]:
        """
        Generate custom perspectives based on program context.
        
        Args:
            program: Program information
            form_fields: Form field definitions
            criteria: Evaluation criteria with weights
            num_perspectives: Target number of perspectives (3-5)
            
        Returns:
            List of generated DynamicPerspective objects
        """
        if num_perspectives is None:
            num_perspectives = self.num_perspectives
            
        logger.info(f"Generating perspectives for program: {program.name}")
        
        # Build the prompt with context
        prompt = self._build_generation_prompt(
            program=program,
            form_fields=form_fields,
            criteria=criteria,
        )
        
        try:
            # Build full prompt with system context
            full_prompt = f"{PERSPECTIVE_GENERATION_SYSTEM_PROMPT}\n\n{prompt}"
            
            # Call LLM
            response = self.llm.generate_from_prompt(full_prompt)
            
            # Parse JSON response
            perspectives = self._parse_perspectives_response(response)
            
            # Limit to requested number
            perspectives = perspectives[:min(num_perspectives, 5)]
            
            logger.info(f"Generated {len(perspectives)} perspectives for {program.name}")
            return perspectives
            
        except Exception as e:
            logger.error(f"Failed to generate perspectives: {e}")
            # Return fallback perspectives based on criteria
            return self._generate_fallback_perspectives(criteria)
    
    def to_prompts(self, perspectives: List[DynamicPerspective]) -> List[Tuple[str, str]]:
        """
        Convert DynamicPerspective objects to (name, prompt) tuples for analyzer.
        
        Args:
            perspectives: List of dynamic perspectives
            
        Returns:
            List of (name, prompt) tuples compatible with MultiPerspectiveAnalyzer
        """
        return [(p.name, self._build_perspective_prompt(p)) for p in perspectives]
    
    def _build_perspective_prompt(self, perspective: DynamicPerspective) -> str:
        """Build an analysis prompt from a dynamic perspective."""
        questions = "\n".join(f"- {q}" for q in perspective.key_questions)
        focus = ", ".join(perspective.focus_areas) if perspective.focus_areas else "General analysis"
        
        return f"""
{perspective.name.upper()} PERSPECTIVE:
{perspective.description}

Focus Areas: {focus}

Key Questions to Address:
{questions}

Provide a thorough analysis from this perspective, identifying key strengths and concerns.
Reference specific aspects of the submission when possible.
"""
    
    def _build_generation_prompt(
        self,
        program: ProgramContext,
        form_fields: List[FormFieldContext],
        criteria: List[CriteriaContext],
    ) -> str:
        """Build the prompt for perspective generation."""
        
        # Format program description
        program_description = program.description or "No description available"
        
        # Budget info
        budget_info = ""
        if program.budget:
            budget_info = f"**Budget:** {program.budget:,.2f} {program.currency}"
        
        # Format form fields
        if form_fields:
            form_fields_list = []
            for field in form_fields:
                required_marker = " (required)" if field.required else ""
                step_info = f" [{field.step_name}]" if field.step_name else ""
                form_fields_list.append(
                    f"- **{field.name}**{step_info}: {field.field_type}{required_marker}"
                )
                if field.description:
                    form_fields_list.append(f"  _{field.description}_")
            form_fields_summary = "\n".join(form_fields_list)
        else:
            form_fields_summary = "No form field information available"
        
        # Format criteria with weights
        if criteria:
            criteria_list = []
            for c in sorted(criteria, key=lambda x: x.weight, reverse=True):
                weight_pct = f"{c.weight * 100:.0f}%" if c.weight else "—"
                criteria_list.append(f"- **{c.name}** (Weight: {weight_pct})")
                if c.description:
                    criteria_list.append(f"  {c.description}")
                if c.factors:
                    factors_str = ", ".join(c.factors[:4])
                    criteria_list.append(f"  _Factors: {factors_str}_")
            criteria_summary = "\n".join(criteria_list)
        else:
            criteria_summary = "No evaluation criteria defined"
        
        return PERSPECTIVE_GENERATION_PROMPT_TEMPLATE.format(
            program_name=program.name,
            program_description=program_description,
            budget_info=budget_info,
            form_fields_summary=form_fields_summary,
            criteria_summary=criteria_summary,
        )
    
    def _parse_perspectives_response(self, content: str) -> List[DynamicPerspective]:
        """Parse the LLM response into DynamicPerspective objects."""
        
        # Try to extract JSON from the response
        json_str = content
        
        # Handle markdown code blocks
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end > start:
                json_str = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            if end > start:
                json_str = content[start:end].strip()
        
        # Try to find JSON array
        if not json_str.startswith("["):
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
        
        try:
            data = json.loads(json_str)
            
            perspectives = []
            for item in data:
                perspectives.append(DynamicPerspective(
                    name=item.get("name", "Unknown Perspective"),
                    description=item.get("description", ""),
                    focus_areas=item.get("focus_areas", []),
                    key_questions=item.get("key_questions", []),
                    relevant_criteria=item.get("relevant_criteria", []),
                ))
            
            return perspectives
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse perspectives JSON: {e}")
            return []
    
    def _generate_fallback_perspectives(
        self, 
        criteria: List[CriteriaContext]
    ) -> List[DynamicPerspective]:
        """Generate fallback perspectives based on criteria when LLM fails."""
        
        perspectives = []
        
        # Sort criteria by weight
        sorted_criteria = sorted(criteria, key=lambda x: x.weight, reverse=True)
        
        # Create a perspective for each major criterion
        for c in sorted_criteria[:4]:
            perspectives.append(DynamicPerspective(
                name=f"{c.name} Reviewer",
                description=f"Evaluates submissions based on {c.name.lower()}",
                focus_areas=c.factors[:3] if c.factors else [c.name],
                key_questions=[
                    f"How well does this submission address {c.name.lower()}?",
                    f"What are the strengths in terms of {c.name.lower()}?",
                    f"What concerns exist regarding {c.name.lower()}?",
                ],
                relevant_criteria=[c.name],
            ))
        
        # If we don't have enough criteria-based perspectives, add generic ones
        if len(perspectives) < 3:
            generic_perspectives = [
                DynamicPerspective(
                    name="Technical Reviewer",
                    description="Evaluates technical feasibility and implementation quality",
                    focus_areas=["Technical approach", "Feasibility", "Implementation plan"],
                    key_questions=[
                        "Is the technical approach sound?",
                        "Can the team execute this plan?",
                        "What are the technical risks?",
                    ],
                    relevant_criteria=[],
                ),
                DynamicPerspective(
                    name="Strategic Alignment Reviewer",
                    description="Evaluates alignment with program goals and ecosystem value",
                    focus_areas=["Mission alignment", "Ecosystem impact", "Long-term value"],
                    key_questions=[
                        "Does this align with program goals?",
                        "What value does this bring to the ecosystem?",
                        "Is this sustainable long-term?",
                    ],
                    relevant_criteria=[],
                ),
                DynamicPerspective(
                    name="Budget & Resource Reviewer",
                    description="Evaluates budget appropriateness and resource allocation",
                    focus_areas=["Budget efficiency", "Resource planning", "Cost-benefit"],
                    key_questions=[
                        "Is the budget reasonable?",
                        "Are resources allocated efficiently?",
                        "What is the expected ROI?",
                    ],
                    relevant_criteria=[],
                ),
            ]
            
            # Add generic perspectives to reach at least 3
            for p in generic_perspectives:
                if len(perspectives) >= 3:
                    break
                perspectives.append(p)
        
        return perspectives


"""
LangChain tools for Multi-Perspective Submission Analysis.

Provides tools for:
1. analyze_submission_perspectives - Analysis only, no vote suggestion
2. get_vote_recommendation - Vote recommendation only (separate from analysis)

Uses the unified multi_perspective module for analysis.
"""
from typing import Any, List, Optional, Type

from pydantic import BaseModel, Field

from src.utils.logger import logger
from src.agent.multi_perspective import (
    MultiPerspectiveAnalyzer,
    PerspectiveGenerator,
    VoteSynthesizer,
    PerspectiveContext,
    ProgramContext,
    FormFieldContext,
    CriteriaContext,
    MultiPerspectiveResult,
    VoteRecommendation,
    SubmissionParser,
)

from .base import APIBaseTool
from .reviews_api_client import ReviewsAPIClient


# Cache for storing analysis results (in-memory, per-session)
_analysis_cache: dict = {}


# ==================
# Tool Input Schemas (Pydantic for LangChain)
# ==================

class AnalyzeSubmissionPerspectivesInput(BaseModel):
    """Input for analyzing a submission from multiple perspectives."""
    submission_id: Optional[str] = Field(
        None, 
        description="The UUID of the submission to analyze. Use this OR form_id+team_id."
    )
    form_id: Optional[int] = Field(
        None, 
        description="The form ID (use with team_id if submission_id not known)"
    )
    team_id: Optional[int] = Field(
        None, 
        description="The team ID (use with form_id if submission_id not known)"
    )
    user_id: Optional[int] = Field(
        None, 
        description="The user ID (use with form_id and team_id if needed)"
    )


class GetVoteRecommendationInput(BaseModel):
    """Input for getting a vote recommendation."""
    submission_id: str = Field(..., description="The UUID of the submission to get recommendation for")


# ==================
# LLM Adapter
# ==================

class LLMAdapter:
    """Adapter to make LangChain chat models compatible with multi_perspective LLM Protocol."""
    
    def __init__(self, chat_model: Any):
        """
        Initialize the adapter.
        
        Args:
            chat_model: LangChain chat model (BaseChatModel)
        """
        self.chat_model = chat_model
    
    def generate_from_prompt(self, prompt: str, **kwargs) -> str:
        """Generate response from prompt using LangChain chat model."""
        from langchain_core.messages import HumanMessage
        
        response = self.chat_model.invoke([HumanMessage(content=prompt)])
        
        # Extract text content from response
        content = response.content
        if isinstance(content, list):
            # Handle multi-part content
            text_parts = [
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            ]
            return "".join(text_parts)
        return str(content)


# ==================
# Base Tool Class
# ==================

class PerspectiveBaseTool(APIBaseTool):
    """Base class for perspective analysis tools.
    
    Extends APIBaseTool for consistent error handling and serialization.
    These tools don't require approval (read-only analysis).
    """
    
    org_slug: str = ""
    requires_approval: bool = False  # Analysis tools don't need approval
    _reviews_client: Optional[ReviewsAPIClient] = None
    _llm_adapter: Optional[LLMAdapter] = None

    def _get_client(self) -> ReviewsAPIClient:
        """Get shared Reviews API client instance (required by APIBaseTool)."""
        return self._get_reviews_client()

    def _get_reviews_client(self) -> ReviewsAPIClient:
        """Get shared Reviews API client instance."""
        if self._reviews_client is None:
            self._reviews_client = ReviewsAPIClient()
        return self._reviews_client
    
    def _get_llm_adapter(self) -> LLMAdapter:
        """Get LLM adapter for multi_perspective module."""
        if self._llm_adapter is None:
            from src.llm.factory import create_chat_model
            chat_model = create_chat_model(temperature=0.3)
            self._llm_adapter = LLMAdapter(chat_model)
        return self._llm_adapter
    
    def close(self) -> None:
        """Close the Reviews API client if initialized."""
        super().close()  # Close base client if any
        if self._reviews_client is not None:
            self._reviews_client.close()
            self._reviews_client = None
    
    def _build_perspective_context(
        self,
        submission_id: Optional[str] = None,
        form_id: Optional[int] = None,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> PerspectiveContext:
        """Build full perspective context for analysis."""
        client = self._get_reviews_client()
        
        # If we have submission_id, fetch the submission details
        if submission_id:
            # Get submission from review queue to get form_id, team_id, user_id
            sub_response = client.get_submission_for_review(
                submission_id=submission_id,
                auth_token=self.auth_token,
                org_slug=self.org_slug,
            )
            sub = sub_response.submission
            form_id = sub.formId
            team_id = sub.teamId
            user_id = sub.userId
            program_id = sub.programId
            program_name = sub.programName or f"Program {program_id}"
            team_name = sub.teamName
            form_name = sub.formName
            requested_amount = sub.requestedAmount
        else:
            # We need form_id, team_id, user_id
            if not form_id or not team_id or not user_id:
                raise ValueError("Either submission_id or (form_id, team_id, user_id) required")
            program_id = None
            program_name = "Unknown Program"
            team_name = None
            form_name = None
            requested_amount = None
        
        # Get full submission details with answers
        submission_detail = client.get_submission_details(
            form_id=form_id,
            user_id=user_id,
            team_id=team_id,
            auth_token=self.auth_token,
            org_slug=self.org_slug,
        )
        
        sub_data = submission_detail.submission
        
        # Update names from submission detail
        if sub_data.form:
            form_name = sub_data.form.name or form_name
            if sub_data.form.program_name:
                program_name = sub_data.form.program_name
            if sub_data.form.program_id:
                program_id = sub_data.form.program_id
        
        if sub_data.team:
            team_name = sub_data.team.name or team_name
        
        # Get evaluation criteria for the form
        criteria_response = client.list_form_criteria(
            form_id=form_id,
            auth_token=self.auth_token,
            org_slug=self.org_slug,
        )
        
        # Convert to CriteriaContext (dataclass)
        criteria = []
        for c in criteria_response.criteria:
            factors = []
            if c.scoring_rules and c.scoring_rules.factors:
                factors = c.scoring_rules.factors
            
            criteria.append(CriteriaContext(
                id=c.id,
                name=c.name,
                description=c.description,
                weight=c.weight or 1.0,
                factors=factors,
            ))
        
        # Extract form fields from config if available
        form_fields = []
        if sub_data.form and sub_data.form.config:
            config = sub_data.form.config
            steps = config.get("steps", [])
            for step in steps:
                step_name = step.get("name", "")
                for field in step.get("fields", []):
                    form_fields.append(FormFieldContext(
                        id=field.get("id", ""),
                        name=field.get("name", field.get("id", "")),
                        field_type=field.get("type", "text"),
                        description=field.get("description"),
                        required=field.get("required", False),
                        step_name=step_name,
                    ))
        
        # Build program context (dataclass)
        program = ProgramContext(
            id=program_id or 0,
            name=program_name,
            description=None,  # Could fetch from programs API if needed
        )
        
        # Extract answers
        answers = sub_data.answers or {}
        if sub_data.structuredAnswers:
            # Flatten structured answers
            for step_id, step_answers in sub_data.structuredAnswers.items():
                if isinstance(step_answers, dict):
                    for field_id, answer in step_answers.items():
                        answers[field_id] = answer
        
        return PerspectiveContext(
            program=program,
            form_name=form_name,
            form_fields=form_fields,
            criteria=criteria,
            submission_answers=answers,
            team_name=team_name,
            requested_amount=requested_amount,
        )


# ==================
# Analysis Tool (No Vote Suggestion)
# ==================

class AnalyzeSubmissionPerspectivesTool(PerspectiveBaseTool):
    """Tool for analyzing a submission from multiple dynamically-generated perspectives."""
    
    name: str = "analyze_submission_perspectives"
    description: str = """Analyze a grant submission from multiple dynamically-generated perspectives.

Perspectives are created based on the program's evaluation criteria and form structure.
Returns detailed analysis from 3-5 viewpoints (e.g., Technical Reviewer, Budget Analyst).

NOTE: This tool provides analysis ONLY, not vote recommendations.
Use get_vote_recommendation if the user explicitly asks for a voting suggestion.

Input:
- submission_id: UUID of the submission to analyze (preferred)
- OR form_id + team_id + user_id: Alternative identifiers

Returns: Multi-perspective analysis with strengths, concerns, and confidence from each perspective."""
    args_schema: Type[BaseModel] = AnalyzeSubmissionPerspectivesInput
    
    def _run_tool(
        self,
        submission_id: Optional[str] = None,
        form_id: Optional[int] = None,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> str:
        """Analyze submission from multiple perspectives."""
        
        # Build context
        context = self._build_perspective_context(
            submission_id=submission_id,
            form_id=form_id,
            team_id=team_id,
            user_id=user_id,
        )
        
        # Get LLM adapter
        llm = self._get_llm_adapter()
        
        # Create analyzer with dynamic perspectives
        analyzer = MultiPerspectiveAnalyzer.from_context(
            llm=llm,
            parser=SubmissionParser(),
            context=context,
            num_perspectives=4,
        )
        
        # Run analysis
        result = analyzer.analyze(context)
        
        # Determine submission_id for caching
        cache_id = submission_id or f"form_{form_id}_team_{team_id}"
        
        # Cache the result for potential vote recommendation
        _analysis_cache[cache_id] = {
            "result": result,
            "context": context,
        }
        
        # Format output
        return self._format_analysis_output(result, context, cache_id)
    
    def _format_analysis_output(
        self, 
        result: MultiPerspectiveResult, 
        context: PerspectiveContext,
        submission_id: str,
    ) -> str:
        """Format multi-perspective analysis as readable output."""
        
        lines = [
            "📊 **Multi-Perspective Analysis**",
            "",
            f"**Program:** {context.program.name}",
        ]
        
        if context.form_name:
            lines.append(f"**Form:** {context.form_name}")
        if context.team_name:
            lines.append(f"**Team:** {context.team_name}")
        
        lines.append("")
        lines.append(f"**Perspectives Analyzed:** {len(result.analyses)}")
        lines.append(f"**Consensus:** {result.consensus}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        for analysis in result.analyses:
            lines.append(f"### {analysis.perspective}")
            lines.append(f"**Tendency:** {analysis.recommendation_tendency}")
            lines.append(f"**Confidence:** {analysis.confidence}/10")
            lines.append("")
            
            if analysis.key_benefits:
                lines.append("**Strengths:**")
                for s in analysis.key_benefits[:4]:
                    lines.append(f"- {s}")
                lines.append("")
            
            if analysis.key_concerns:
                lines.append("**Concerns:**")
                for c in analysis.key_concerns[:4]:
                    lines.append(f"- {c}")
                lines.append("")
            
            # Show brief analysis
            analysis_preview = analysis.analysis[:300]
            if len(analysis.analysis) > 300:
                analysis_preview += "..."
            lines.append(f"**Analysis:** {analysis_preview}")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        # Add synthesis
        if result.synthesis:
            lines.append("### Synthesis")
            synthesis_preview = result.synthesis[:500]
            if len(result.synthesis) > 500:
                synthesis_preview += "..."
            lines.append(synthesis_preview)
            lines.append("")
            lines.append("---")
            lines.append("")
        
        # Note about vote recommendation
        lines.append("_To get a vote recommendation based on this analysis, ask: \"Recommend a vote based on this analysis\"_")
        
        return "\n".join(lines)


# ==================
# Vote Recommendation Tool (Separate from Analysis)
# ==================

class GetVoteRecommendationTool(PerspectiveBaseTool):
    """Tool for generating a vote recommendation based on multi-perspective analysis."""
    
    name: str = "get_vote_recommendation"
    description: str = """Generate a vote recommendation based on multi-perspective analysis.

Only call this when user explicitly asks for a recommendation.
Does NOT execute the vote - just provides a recommendation with rationale.

If analyze_submission_perspectives was called first, uses that analysis.
Otherwise, runs analysis internally first.

Input:
- submission_id: UUID of the submission to get recommendation for

Returns: Vote recommendation (approve/reject/abstain) with rationale and suggested comment."""
    args_schema: Type[BaseModel] = GetVoteRecommendationInput
    
    def _run_tool(
        self,
        submission_id: str,
    ) -> str:
        """Generate vote recommendation."""
        
        llm = self._get_llm_adapter()
        
        # Check if we have cached analysis
        cached = _analysis_cache.get(submission_id)
        
        if cached is None:
            # Need to run analysis first
            logger.info(f"No cached analysis for {submission_id}, running analysis first")
            context = self._build_perspective_context(submission_id=submission_id)
            
            # Create analyzer with dynamic perspectives
            analyzer = MultiPerspectiveAnalyzer.from_context(
                llm=llm,
                parser=SubmissionParser(),
                context=context,
                num_perspectives=4,
            )
            
            result = analyzer.analyze(context)
            
            _analysis_cache[submission_id] = {
                "result": result,
                "context": context,
            }
            cached = _analysis_cache[submission_id]
        
        result = cached["result"]
        
        # Generate vote recommendation using VoteSynthesizer
        synthesizer = VoteSynthesizer(llm=llm)
        recommendation = synthesizer.synthesize_vote(
            result=result,
            vote_options=["approve", "reject", "abstain"],
            submission_id=submission_id,
        )
        
        # Format output
        return self._format_recommendation_output(recommendation, result)
    
    def _format_recommendation_output(
        self, 
        rec: VoteRecommendation,
        result: MultiPerspectiveResult,
    ) -> str:
        """Format vote recommendation as readable output."""
        
        vote_emoji = {
            "approve": "✅",
            "reject": "❌",
            "abstain": "⚖️",
            "for": "✅",
            "against": "❌",
        }
        
        lines = [
            "🗳️ **Vote Recommendation**",
            "",
            f"**Recommended Vote:** {vote_emoji.get(rec.recommended_vote, '⚖️')} {rec.recommended_vote.capitalize()}",
            f"**Confidence:** {rec.confidence}/10",
            "",
            "**Rationale:**",
            f"{rec.rationale}",
            "",
        ]
        
        if rec.key_factors:
            lines.append("**Key Factors:**")
            for f in rec.key_factors[:5]:
                lines.append(f"- {f}")
            lines.append("")
        
        if rec.perspective_summary:
            lines.append(f"**Perspective Summary:** {rec.perspective_summary}")
            lines.append("")
        
        if rec.suggested_comment:
            lines.append("**Suggested Comment for Voting:**")
            lines.append(f"> {rec.suggested_comment}")
            lines.append("")
        
        lines.append("---")
        lines.append("")
        lines.append(f"_To vote on this submission, say: \"Vote {rec.recommended_vote} on {rec.submission_id}\"_")
        lines.append("_You can modify the comment before voting._")
        
        return "\n".join(lines)


# ==================
# Tool Factory
# ==================

def create_perspective_tools(
    auth_token: str,
    org_slug: str,
) -> List[PerspectiveBaseTool]:
    """
    Create all perspective analysis tools.
    
    Args:
        auth_token: Privy authentication token
        org_slug: Organization slug
        
    Returns:
        List of configured tool instances
    """
    return [
        AnalyzeSubmissionPerspectivesTool(auth_token=auth_token, org_slug=org_slug),
        GetVoteRecommendationTool(auth_token=auth_token, org_slug=org_slug),
    ]

"""
Vote Synthesizer for Multi-Perspective Analysis.

Generates vote recommendations from multi-perspective analysis results,
synthesizing insights from multiple reviewer perspectives.
"""
import json
import logging
from typing import List, Protocol

from .types import (
    MultiPerspectiveResult,
    PerspectiveAnalysis,
    VoteRecommendation,
)

logger = logging.getLogger(__name__)


class SynthesizerLLM(Protocol):
    """Protocol for LLM client used in vote synthesis."""
    def generate_from_prompt(self, prompt: str, **kwargs) -> str:  # pragma: no cover
        ...


RECOMMENDATION_SYSTEM_PROMPT = """You are synthesizing multiple reviewer perspectives into a voting recommendation.

Your role is to:
1. Weigh the perspectives based on confidence and consensus
2. Identify areas of agreement and disagreement
3. Provide a clear recommendation with rationale
4. Suggest a comment the reviewer could use when voting

Be balanced and explain your reasoning clearly."""


RECOMMENDATION_PROMPT_TEMPLATE = """## Multi-Perspective Analysis Summary

**Analysis ID:** {analysis_id}
**Consensus:** {consensus}
**Dominant Perspective:** {dominant_perspective}

### Perspective Analyses

{perspectives_summary}

---

Based on these perspectives, provide a voting recommendation.

Return as JSON:
```json
{{
  "recommended_vote": "approve" | "reject" | "abstain" | "for" | "against",
  "confidence": 7,
  "rationale": "Clear explanation of why this vote is recommended...",
  "key_factors": ["factor 1", "factor 2", "..."],
  "suggested_comment": "A comment the reviewer could use when voting (5-500 chars)...",
  "perspective_summary": "How the perspectives informed this recommendation..."
}}
```

Provide your recommendation:"""


class VoteSynthesizer:
    """Generates vote recommendations from multi-perspective analysis."""
    
    def __init__(self, llm: SynthesizerLLM):
        """
        Initialize the vote synthesizer.
        
        Args:
            llm: LLM client that implements generate_from_prompt method
        """
        self.llm = llm
    
    def synthesize_vote(
        self,
        result: MultiPerspectiveResult,
        vote_options: List[str] = None,
        submission_id: str = "",
    ) -> VoteRecommendation:
        """
        Generate vote recommendation based on multi-perspective analysis.
        
        Args:
            result: The multi-perspective analysis result
            vote_options: Optional list of valid vote options
            submission_id: Optional submission ID for tracking
            
        Returns:
            VoteRecommendation with suggested vote and rationale
        """
        if vote_options is None:
            vote_options = ["approve", "reject", "abstain"]
            
        logger.info(f"Generating vote recommendation for analysis with {len(result.analyses)} perspectives")
        
        # Build perspectives summary
        perspectives_summary = self._build_perspectives_summary(result.analyses)
        
        prompt = RECOMMENDATION_PROMPT_TEMPLATE.format(
            analysis_id=submission_id or "multi-perspective-analysis",
            consensus=result.consensus,
            dominant_perspective=result.dominant_perspective or "None",
            perspectives_summary=perspectives_summary,
        )
        
        try:
            # Build full prompt with system context
            full_prompt = f"{RECOMMENDATION_SYSTEM_PROMPT}\n\n{prompt}"
            
            # Call LLM
            response = self.llm.generate_from_prompt(full_prompt)
            
            # Parse response
            recommendation = self._parse_recommendation_response(
                response, 
                submission_id,
                vote_options,
            )
            
            return recommendation
            
        except Exception as e:
            logger.error(f"Failed to generate recommendation: {e}")
            return VoteRecommendation(
                submission_id=submission_id,
                recommended_vote="abstain",
                confidence=1,
                rationale=f"Unable to generate recommendation: {str(e)}",
                key_factors=["Synthesis failed"],
                suggested_comment="Unable to provide a recommendation at this time.",
                perspective_summary="",
            )
    
    def _build_perspectives_summary(self, analyses: List[PerspectiveAnalysis]) -> str:
        """Build a summary of all perspective analyses for recommendation."""
        
        lines = []
        for analysis in analyses:
            lines.append(f"### {analysis.perspective}")
            lines.append(f"**Tendency:** {analysis.recommendation_tendency}")
            lines.append(f"**Confidence:** {analysis.confidence}/10")
            
            if analysis.key_benefits:
                lines.append("**Strengths/Benefits:**")
                for s in analysis.key_benefits[:3]:
                    lines.append(f"- {s}")
            
            if analysis.key_concerns:
                lines.append("**Concerns:**")
                for c in analysis.key_concerns[:3]:
                    lines.append(f"- {c}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _parse_recommendation_response(
        self, 
        content: str, 
        submission_id: str,
        vote_options: List[str],
    ) -> VoteRecommendation:
        """Parse the LLM recommendation response."""
        
        json_str = self._extract_json(content)
        
        try:
            data = json.loads(json_str)
            
            # Validate vote type
            vote = data.get("recommended_vote", "abstain").lower()
            if vote not in vote_options:
                # Try to find closest match
                if "for" in vote_options and vote in ("approve", "yes", "support"):
                    vote = "for"
                elif "against" in vote_options and vote in ("reject", "no", "oppose"):
                    vote = "against"
                elif "abstain" in vote_options:
                    vote = "abstain"
                else:
                    vote = vote_options[0] if vote_options else "abstain"
            
            return VoteRecommendation(
                submission_id=submission_id,
                recommended_vote=vote,
                confidence=data.get("confidence", 5),
                rationale=data.get("rationale", ""),
                key_factors=data.get("key_factors", []),
                suggested_comment=data.get("suggested_comment", ""),
                perspective_summary=data.get("perspective_summary", ""),
            )
            
        except json.JSONDecodeError:
            # Fall back to parsing from content
            vote = self._extract_vote_from_text(content, vote_options)
            
            return VoteRecommendation(
                submission_id=submission_id,
                recommended_vote=vote,
                confidence=3,
                rationale=content[:500] if content else "",
                key_factors=[],
                suggested_comment="",
                perspective_summary="",
            )
    
    def _extract_vote_from_text(self, content: str, vote_options: List[str]) -> str:
        """Extract vote from unstructured text content."""
        content_lower = content.lower()
        
        # Check for explicit vote options
        for option in vote_options:
            if option.lower() in content_lower:
                return option.lower()
        
        # Fallback mappings
        if any(word in content_lower for word in ["approve", "yes", "support"]):
            return "for" if "for" in vote_options else "approve" if "approve" in vote_options else vote_options[0]
        elif any(word in content_lower for word in ["reject", "no", "oppose"]):
            return "against" if "against" in vote_options else "reject" if "reject" in vote_options else vote_options[0]
        
        return "abstain" if "abstain" in vote_options else vote_options[0] if vote_options else "abstain"
    
    def _extract_json(self, content: str) -> str:
        """Extract JSON from LLM response."""
        
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
        
        # Try to find JSON object
        if not json_str.startswith("{"):
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
        
        return json_str


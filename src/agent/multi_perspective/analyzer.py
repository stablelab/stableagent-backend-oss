"""
Multi-Perspective Analyzer.

Analyzes data from multiple perspectives, supporting both predefined static perspectives
and dynamically generated perspectives based on program context.
"""
import logging
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Protocol, Union, Tuple, TYPE_CHECKING

from .types import (
    Perspective,
    ParsedInput,
    PerspectiveAnalysis,
    MultiPerspectiveResult,
)
from .perspectives import (
    PerspectivePrompt,
    PREDEFINED_PERSPECTIVES,
    get_perspective_prompt,
    get_available_perspectives,
)

if TYPE_CHECKING:
    from .perspective_generator import PerspectiveGenerator


logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def generate_from_prompt(self, prompt: str, **kwargs) -> str:  # pragma: no cover
        ...


class MultiPerspectiveAnalyzer:
    """
    Accepts a parser to transform arbitrary inputs into a canonical ParsedInput 
    structure and then evaluates multiple perspectives via a provided LLM client.
    
    Supports both:
    - Static predefined perspectives (conservative, progressive, balanced, technical)
    - Dynamically generated perspectives based on program context
    
    See get_available_perspectives() for all available predefined perspectives.
    """

    def __init__(
        self,
        llm: LLMClient,
        parser: Any,
        perspectives: Union[List[PerspectivePrompt], List[str], List[Perspective]],
    ):
        if not perspectives:
            raise ValueError(
                "perspectives must be explicitly provided. "
                f"Available predefined perspectives: {get_available_perspectives()}"
            )
        self.llm = llm
        self.parser = parser
        self.perspectives = self._normalize_perspectives(perspectives)
    
    @classmethod
    def from_context(
        cls,
        llm: LLMClient,
        parser: Any,
        context: PerspectiveContext,
        generator: Optional["PerspectiveGenerator"] = None,
        num_perspectives: int = 4,
    ) -> "MultiPerspectiveAnalyzer":
        """
        Create an analyzer with dynamically generated perspectives.
        
        This factory method generates custom perspectives based on the provided
        context (program info, criteria, form fields) instead of using predefined
        static perspectives.
        
        Args:
            llm: LLM client that implements generate_from_prompt method
            parser: Input parser that implements parse(data) -> ParsedInput
            context: Context for perspective generation (program, criteria, etc.)
            generator: Optional custom PerspectiveGenerator. Creates default if None.
            num_perspectives: Target number of perspectives (3-5)
            
        Returns:
            MultiPerspectiveAnalyzer configured with dynamically generated perspectives
        """
        from .perspective_generator import PerspectiveGenerator
        
        if generator is None:
            generator = PerspectiveGenerator(llm=llm, num_perspectives=num_perspectives)
        
        # Generate dynamic perspectives
        dynamic_perspectives = generator.generate(context)
        
        # Convert to (name, prompt) tuples
        perspective_prompts = generator.to_prompts(dynamic_perspectives)
        
        if not perspective_prompts:
            # Fallback to predefined perspectives if generation fails
            logger.warning("Dynamic perspective generation failed, using predefined perspectives")
            perspective_prompts = [
                ("conservative", get_perspective_prompt("conservative")),
                ("balanced", get_perspective_prompt("balanced")),
                ("technical", get_perspective_prompt("technical")),
            ]
        
        return cls(llm=llm, parser=parser, perspectives=perspective_prompts)

    def _normalize_perspectives(
        self, perspectives: Union[List[PerspectivePrompt], List[str], List[Perspective]]
    ) -> List[PerspectivePrompt]:
        """Normalize perspectives to (name, prompt) tuples."""
        if not perspectives:
            raise ValueError("perspectives cannot be empty")
        
        normalized = []
        for p in perspectives:
            if isinstance(p, tuple) and len(p) == 2:
                # Already a (name, prompt) tuple
                normalized.append((str(p[0]), str(p[1])))
            elif isinstance(p, str):
                # String - check if it's a predefined perspective name
                prompt = get_perspective_prompt(p)
                if prompt:
                    normalized.append((p.lower(), prompt))
                else:
                    # Treat as custom prompt (name will be generated)
                    normalized.append((f"custom_{len(normalized)}", p))
            elif isinstance(p, Perspective):
                # Legacy enum support
                name = p.value
                prompt = PREDEFINED_PERSPECTIVES.get(name, "")
                if prompt:
                    normalized.append((name, prompt))
                else:
                    logger.warning(f"Unknown perspective enum: {p}")
            else:
                logger.warning(f"Invalid perspective format: {p}")
        
        return normalized

    def analyze(self, data: Any) -> MultiPerspectiveResult:
        parsed = self.parser.parse(data)
        analyses: List[PerspectiveAnalysis] = []

        for perspective_name, perspective_prompt in self.perspectives:
            try:
                logger.info(f"MultiPerspective: starting '{perspective_name}' analysis")
                t0 = time.perf_counter()
                prompt = self._build_perspective_prompt(perspective_name, perspective_prompt, parsed)
                response = self.llm.generate_from_prompt(prompt)

                analysis = PerspectiveAnalysis(
                    perspective=perspective_name,
                    analysis=response,
                    focus_areas=self._extract_focus_areas(response),
                    key_concerns=self._extract_between(response, "KEY CONCERNS:", "KEY BENEFITS:"),
                    key_benefits=self._extract_between(response, "KEY BENEFITS:", "RECOMMENDATION TENDENCY:"),
                    recommendation_tendency=self._extract_tendency(response),
                    confidence=self._extract_confidence(response),
                )
                analyses.append(analysis)
                dt_ms = int((time.perf_counter() - t0) * 1000)
                logger.info(
                    f"MultiPerspective: completed '{perspective_name}' analysis in {dt_ms} ms "
                    f"(tendency={analysis.recommendation_tendency}, confidence={analysis.confidence})"
                )
            except Exception as e:
                logger.error(f"Perspective analysis failed for {perspective_name}: {e}")
                analyses.append(PerspectiveAnalysis(
                    perspective=perspective_name,
                    analysis=f"Analysis failed: {e}",
                    focus_areas=[],
                    key_concerns=[],
                    key_benefits=[],
                    recommendation_tendency="neutral",
                    confidence=0,
                ))

        logger.info("MultiPerspective: starting synthesis")
        t_syn = time.perf_counter()
        synthesis = self._synthesize(analyses)
        syn_ms = int((time.perf_counter() - t_syn) * 1000)
        logger.info(f"MultiPerspective: completed synthesis in {syn_ms} ms")
        consensus, dominant = self._consensus_and_dominance(analyses)

        return MultiPerspectiveResult(
            analyses=analyses,
            synthesis=synthesis,
            perspectives_analyzed=[a.perspective for a in analyses],
            consensus=consensus,
            dominant_perspective=dominant,
        )

    # Prompting and extraction helpers

    def _build_perspective_prompt(self, perspective_name: str, perspective_prompt: str, p: ParsedInput) -> str:
        newline = "\n"
        args_for = newline.join(["- " + arg for arg in (p.arguments.get('for') or [])])
        args_against = newline.join(["- " + arg for arg in (p.arguments.get('against') or [])])
        risk_factors = newline.join(["- " + r for r in p.risk_factors])
        opportunity_factors = newline.join(["- " + o for o in p.opportunity_factors])
        economic_implications = newline.join(["- " + e for e in p.economic_implications])
        
        base_context = f"""
PROPOSAL SUMMARY:
{p.clean_summary}

ARGUMENTS FOR:
{args_for}

ARGUMENTS AGAINST:
{args_against}

RISK FACTORS:
{risk_factors}

OPPORTUNITY FACTORS:
{opportunity_factors}

ECONOMIC IMPLICATIONS:
{economic_implications}
"""

        return f"""{base_context}

{perspective_prompt}

Provide your {perspective_name} analysis in the following format:

FOCUS AREAS: [List 2-3 key areas]
KEY CONCERNS: [List 2-3 concerns]
KEY BENEFITS: [List 2-3 benefits]
RECOMMENDATION TENDENCY: [For/Against/Abstain with brief reasoning]
CONFIDENCE: [1-10]

DETAILED ANALYSIS:
[2-3 paragraphs]
"""

    def _extract_focus_areas(self, response: str) -> List[str]:
        if "FOCUS AREAS:" not in response:
            return []
        section = response.split("FOCUS AREAS:")[1]
        # stop at next section header if present
        for stop in ["KEY CONCERNS:", "KEY BENEFITS:", "RECOMMENDATION TENDENCY:", "CONFIDENCE:"]:
            if stop in section:
                section = section.split(stop)[0]
                break
        lines = [l.strip().lstrip("- ") for l in section.splitlines() if l.strip()]
        return [l for l in lines if len(l) > 5][:3]

    def _extract_between(self, response: str, start: str, end: str) -> List[str]:
        if start not in response or end not in response:
            return []
        section = response.split(start)[1].split(end)[0]
        lines = [l.strip().lstrip("- ") for l in section.splitlines() if l.strip()]
        return [l for l in lines if len(l) > 5][:3]

    def _extract_tendency(self, response: str) -> str:
        if "RECOMMENDATION TENDENCY:" not in response:
            return "neutral"
        text = response.split("RECOMMENDATION TENDENCY:")[1]
        text = text.split("CONFIDENCE:")[0] if "CONFIDENCE:" in text else text
        t = text.strip().lower()
        if any(k in t for k in ["for", "support", "yes"]):
            return "for"
        if any(k in t for k in ["against", "oppose", "no"]):
            return "against"
        if "abstain" in t:
            return "abstain"
        return "neutral"

    def _extract_confidence(self, response: str) -> int:
        import re
        if "CONFIDENCE:" not in response:
            return 5
        section = response.split("CONFIDENCE:")[1]
        match = re.search(r"\b([1-9]|10)\b", section)
        return int(match.group(1)) if match else 5

    def _synthesize(self, analyses: List[PerspectiveAnalysis]) -> str:
        if not analyses:
            return "No perspective analyses available for synthesis"

        parts = []
        for a in analyses:
            p = a.perspective.upper()
            parts.append(
                f"""
{p} PERSPECTIVE:
- Recommendation: {a.recommendation_tendency}
- Key Concerns: {', '.join(a.key_concerns[:2])}
- Key Benefits: {', '.join(a.key_benefits[:2])}
"""
            )

        newline = "\n"
        parts_joined = newline.join(parts)
        prompt = f"""
Based on these perspectives, provide a synthesis that identifies:

{parts_joined}

SYNTHESIS TASK:
1. CONSENSUS AREAS
2. KEY TENSIONS
3. BALANCED INSIGHTS
4. RISK-BENEFIT BALANCE

Provide a concise 2-3 paragraph synthesis.
"""
        try:
            return self.llm.generate_from_prompt(prompt)
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return f"Synthesis generation failed: {e}"

    def _consensus_and_dominance(self, analyses: List[PerspectiveAnalysis]) -> (str, str):
        if not analyses:
            return "unknown", ""

        counts: Dict[str, int] = {}
        for a in analyses:
            t = a.recommendation_tendency or "neutral"
            counts[t] = counts.get(t, 0) + 1

        total = len(analyses)
        max_count = max(counts.values()) if counts else 0
        if max_count == total:
            consensus = "unanimous"
        elif max_count >= total * 0.75:
            consensus = "majority"
        elif max_count >= total * 0.5:
            consensus = "mixed"
        else:
            consensus = "split"

        dominant = ""
        best_conf = -1
        for a in analyses:
            if a.confidence > best_conf:
                best_conf = a.confidence
                dominant = a.perspective

        return consensus, dominant


def run_multi_perspective(
    llm: LLMClient,
    data: Any,
    parser: Any,
    perspectives: Union[List[PerspectivePrompt], List[str]],
) -> MultiPerspectiveResult:
    """
    wrapper to run multi-perspective analysis
    
    Args:
        llm: LLM client that implements generate_from_prompt method
        data: Input data to analyze (will be parsed by the parser)
        parser: Parser instance that implements parse(data) -> ParsedInput
        perspectives: List of perspectives (required). Can be:
            - List of (name, prompt) tuples: [("conservative", "prompt text"), ...]
            - List of perspective names: ["conservative", "technical"] - uses predefined prompts
    """
    analyzer = MultiPerspectiveAnalyzer(llm=llm, parser=parser, perspectives=perspectives)
    return analyzer.analyze(data)

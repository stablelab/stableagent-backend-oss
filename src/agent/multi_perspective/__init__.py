"""
Multi-Perspective Analysis Module.

A reusable module for analyzing data from multiple perspectives, supporting
both predefined static perspectives and dynamically generated perspectives
based on program context.

Usage:
    # With predefined perspectives
    from src.agent.multi_perspective import MultiPerspectiveAnalyzer, SimpleTextParser
    
    analyzer = MultiPerspectiveAnalyzer(
        llm=my_llm,
        parser=SimpleTextParser(),
        perspectives=["conservative", "progressive", "technical"],
    )
    result = analyzer.analyze(data)
    
    # With dynamic perspectives
    from src.agent.multi_perspective import (
        MultiPerspectiveAnalyzer,
        PerspectiveContext,
        ProgramContext,
        SubmissionParser,
    )
    
    context = PerspectiveContext(
        program=ProgramContext(id=1, name="My Program"),
        criteria=[...],
        form_fields=[...],
    )
    
    analyzer = MultiPerspectiveAnalyzer.from_context(
        llm=my_llm,
        parser=SubmissionParser(),
        context=context,
    )
    result = analyzer.analyze(data)
    
    # Vote recommendation
    from src.agent.multi_perspective import VoteSynthesizer
    
    synthesizer = VoteSynthesizer(llm=my_llm)
    recommendation = synthesizer.synthesize_vote(result)
"""
from .types import (
    Perspective,
    ParsedInput,
    PerspectiveAnalysis,
    MultiPerspectiveResult,
    DynamicPerspective,
    ProgramContext,
    FormFieldContext,
    CriteriaContext,
    PerspectiveContext,
    VoteRecommendation,
    VoteType,
)

from .perspectives import (
    PerspectivePrompt,
    PREDEFINED_PERSPECTIVES,
    get_perspective_prompt,
    get_available_perspectives,
)

from .analyzer import (
    LLMClient,
    MultiPerspectiveAnalyzer,
    run_multi_perspective,
)

from .perspective_generator import (
    GeneratorLLM,
    PerspectiveGenerator,
)

from .vote_synthesizer import (
    SynthesizerLLM,
    VoteSynthesizer,
)

from .parsers import (
    SimpleTextParser,
    LLMTextParser,
    SubmissionParser,
    ContextParser,
)

__all__ = [
    # Types
    "Perspective",
    "ParsedInput",
    "PerspectiveAnalysis",
    "MultiPerspectiveResult",
    "DynamicPerspective",
    "ProgramContext",
    "FormFieldContext",
    "CriteriaContext",
    "PerspectiveContext",
    "VoteRecommendation",
    "VoteType",
    # Perspectives
    "PerspectivePrompt",
    "PREDEFINED_PERSPECTIVES",
    "get_perspective_prompt",
    "get_available_perspectives",
    # Analyzer
    "LLMClient",
    "MultiPerspectiveAnalyzer",
    "run_multi_perspective",
    # Generator
    "GeneratorLLM",
    "PerspectiveGenerator",
    # Vote Synthesizer
    "SynthesizerLLM",
    "VoteSynthesizer",
    # Parsers
    "SimpleTextParser",
    "LLMTextParser",
    "SubmissionParser",
    "ContextParser",
]


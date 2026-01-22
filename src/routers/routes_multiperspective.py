from fastapi import HTTPException
from pydantic import BaseModel, Field, validator
from typing import Optional, Union, List
import logging

from src.agent.delegate.llm_provider import LLMManager
from src.agent.multi_perspective.analyzer import MultiPerspectiveAnalyzer
from src.agent.multi_perspective.parsers.text_parser import SimpleTextParser, LLMTextParser
from src.agent.multi_perspective.perspectives import get_available_perspectives, get_perspective_prompt


logger = logging.getLogger(__name__)

# Set to True to use llm parser, False to use simple keyowrds based parser (is set in POST body with key 'llmParser')
LLM_PARSER_ENABLED = False


class CustomPerspective(BaseModel):
    """Custom perspective with name and prompt."""
    name: str = Field(..., min_length=1, description="Name of the custom perspective")
    prompt: str = Field(..., min_length=1, description="Prompt text for the custom perspective")

PerspectiveInput = Union[str, CustomPerspective]


class AnalyzeTextRequest(BaseModel):
    """
    Request model for multi-perspective text analysis.
    
    Perspectives can be:
    - Predefined perspectives by name: ["conservative", "technical"]
    - Custom perspectives with name and prompt: [{"name": "security", "prompt": "..."}]
    - Mixed: ["conservative", {"name": "security", "prompt": "..."}]
    
    Available predefined perspectives: conservative, progressive, balanced, technical
    """
    text: str = Field(..., min_length=1, description="Text to analyze")
    perspectives: List[PerspectiveInput] = Field(
        ...,
        min_items=1,
        description="List of perspectives to use. Can be predefined names (strings) or custom perspectives (objects with name and prompt)"
    )
    
    @validator('perspectives')
    def validate_perspectives(cls, v):
        """Validate that at least one perspective is provided and predefined names are valid."""
        if not v:
            raise ValueError("At least one perspective must be provided")
        
        available = get_available_perspectives()
        for p in v:
            if isinstance(p, str):
                if p.lower() not in available:
                    raise ValueError(
                        f"Unknown predefined perspective: '{p}'. "
                        f"Available predefined perspectives: {available}"
                    )
        
        return v


_llm_manager: Optional[LLMManager] = None


def _get_llm() -> LLMManager:
    global _llm_manager
    if _llm_manager is not None:
        return _llm_manager
    try:
        provider = LLMManager.detect_provider()
        _llm_manager = LLMManager(provider_name=provider)
        logger.info(f"Initialized LLMManager for provider: {provider}")
        return _llm_manager
    except Exception as e:
        logger.error(f"Failed to initialize LLMManager: {e}")
        raise HTTPException(status_code=500, detail="LLM initialization failed")


async def analyze_text_multiperspective(payload: AnalyzeTextRequest) -> dict:
    """
    Analyze arbitrary text using the generic multi-perspective module.
    """
    try:
        # Normalize perspectives from API format to analyzer format
        # Convert strings (predefined) and CustomPerspective objects to (name, prompt) tuples
        normalized_perspectives = []
        for p in payload.perspectives:
            if isinstance(p, str):
                # Predefined perspective by name
                prompt = get_perspective_prompt(p)
                if not prompt:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Predefined perspective '{p}' not found. Available: {get_available_perspectives()}"
                    )
                normalized_perspectives.append((p.lower(), prompt))
            else:
                # Custom perspective with name and prompt
                normalized_perspectives.append((p.name, p.prompt))
        
        if LLM_PARSER_ENABLED:
            llm = _get_llm()
            parser = LLMTextParser(llm)
        else:
            parser = SimpleTextParser()

        # We still need an LLM for the perspective analyses and synthesis
        llm = _get_llm()
        analyzer = MultiPerspectiveAnalyzer(llm=llm, parser=parser, perspectives=normalized_perspectives)
        result = analyzer.analyze(payload.text)

        return {
            "analyses": [
                {
                    "perspective": a.perspective,
                    "analysis": a.analysis,
                    "focus_areas": a.focus_areas,
                    "key_concerns": a.key_concerns,
                    "key_benefits": a.key_benefits,
                    "recommendation_tendency": a.recommendation_tendency,
                    "confidence": a.confidence,
                }
                for a in result.analyses
            ],
            "synthesis": result.synthesis,
            "perspectives_analyzed": result.perspectives_analyzed,
            "consensus": result.consensus,
            "dominant_perspective": result.dominant_perspective,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Multi-perspective text analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


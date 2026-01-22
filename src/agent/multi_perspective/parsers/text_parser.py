import re
from typing import Any, List, Dict, Protocol
from ..types import ParsedInput


class ParserLLM(Protocol):
    def generate_from_prompt(self, prompt: str, **kwargs) -> str:  # pragma: no cover
        ...


class SimpleTextParser:
    """Heuristic text parser that extracts a summary and attempts to find
    arguments or risk/opportunity mentions via simple patterns. Safe fallback
    that does not require an LLM.
    """

    def __init__(self, max_summary_words: int = 200):
        self.max_summary_words = max_summary_words

    def parse(self, data: Any) -> ParsedInput:
        text = str(data or "").strip()
        words = text.split()
        clean_summary = " ".join(words[: self.max_summary_words]) + ("..." if len(words) > self.max_summary_words else "")

        # Very naive extraction based on sentence keywords
        sentences = re.split(r"(?<=[.!?])\s+", text)
        def _filter_sentences(keys: List[str]) -> List[str]:
            out: List[str] = []
            for s in sentences:
                if any(k in s.lower() for k in keys):
                    s_clean = s.strip()
                    if 20 < len(s_clean) < 200:
                        out.append(s_clean)
            return list(dict.fromkeys(out))[:3]

        arguments_for = _filter_sentences(["support", "benefit", "positive", "advantage"])
        arguments_against = _filter_sentences(["risk", "concern", "negative", "issue", "problem"])
        risks = _filter_sentences(["risk", "concern", "threat", "challenge"])
        opportunities = _filter_sentences(["opportunity", "improve", "increase", "enhance", "benefit"]) 
        econ_imps = _filter_sentences(["treasury", "fund", "budget", "cost", "economic", "financial"]) 

        return ParsedInput(
            clean_summary=clean_summary or (text[:200] + ("..." if len(text) > 200 else "")),
            arguments={"for": arguments_for, "against": arguments_against},
            risk_factors=risks,
            opportunity_factors=opportunities,
            economic_implications=econ_imps,
        )


class LLMTextParser:
    """LLM-assisted text parser that extracts structured fields from free text using
    a single prompt. Falls back gracefully when extraction is incomplete.
    """

    def __init__(self, llm: ParserLLM, max_summary_words: int = 200):
        self.llm = llm
        self.max_summary_words = max_summary_words

    def parse(self, data: Any) -> ParsedInput:
        text = str(data or "").strip()
        if not text:
            return ParsedInput(clean_summary="")

        prompt = f"""
Extract the following JSON fields from the text below. Be concise.
FIELDS:
- clean_summary: <= {self.max_summary_words} words summary
- arguments.for: up to 3 reasons in favor
- arguments.against: up to 3 concerns
- risk_factors: up to 4 risks (1 sentence each)
- opportunity_factors: up to 4 opportunities (1 sentence each)
- economic_implications: up to 3 (1 sentence each)

Return strictly valid JSON with keys: clean_summary, arguments, risk_factors, opportunity_factors, economic_implications.

TEXT:
{text}
"""
        try:
            raw = self.llm.generate_from_prompt(prompt)
        except Exception:
            # Fallback to heuristic if LLM fails
            return SimpleTextParser(self.max_summary_words).parse(text)

        # Try to locate JSON block
        content = raw.strip()
        json_block = _extract_json_block(content)
        if not json_block:
            return SimpleTextParser(self.max_summary_words).parse(text)

        try:
            import json
            data = json.loads(json_block)
        except Exception:
            return SimpleTextParser(self.max_summary_words).parse(text)

        def _as_list(v: Any) -> List[str]:
            if isinstance(v, list):
                return [str(x).strip() for x in v if str(x).strip()]
            if isinstance(v, str) and v.strip():
                return [v.strip()]
            return []

        arguments: Dict[str, List[str]] = {
            "for": _as_list((data.get("arguments") or {}).get("for")),
            "against": _as_list((data.get("arguments") or {}).get("against")),
        }

        return ParsedInput(
            clean_summary=str(data.get("clean_summary") or "")[:2000],
            arguments=arguments,
            risk_factors=_as_list(data.get("risk_factors")),
            opportunity_factors=_as_list(data.get("opportunity_factors")),
            economic_implications=_as_list(data.get("economic_implications")),
        )


def _extract_json_block(text: str) -> str:
    # Try fenced block first
    fenced = re.search(r"```\s*json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if fenced:
        return fenced.group(1)
    # Try first curly block
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        return text[first:last + 1]
    return ""



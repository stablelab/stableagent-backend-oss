"""
Submission Parser for Multi-Perspective Analysis.

Parses grant submission data into ParsedInput format for perspective analysis.
"""
import json
from typing import Any, Dict, List

from ..types import ParsedInput, PerspectiveContext


class SubmissionParser:
    """
    Parser for grant submission data.
    
    Converts submission context (answers, criteria, form fields) into
    ParsedInput format suitable for multi-perspective analysis.
    """
    
    def __init__(self, max_summary_words: int = 500):
        """
        Initialize the submission parser.
        
        Args:
            max_summary_words: Maximum words for the summary
        """
        self.max_summary_words = max_summary_words
    
    def parse(self, data: Any) -> ParsedInput:
        """
        Parse submission data into ParsedInput format.
        
        Args:
            data: Submission data, can be:
                - PerspectiveContext dataclass
                - Dict with submission_answers, criteria, form_fields, etc.
                - Plain text (falls back to simple parsing)
                
        Returns:
            ParsedInput suitable for perspective analysis
        """
        if isinstance(data, PerspectiveContext):
            return self._parse_context(data)
        elif isinstance(data, dict):
            return self._parse_dict(data)
        elif isinstance(data, str):
            return self._parse_text(data)
        else:
            return ParsedInput(clean_summary=str(data)[:self.max_summary_words])
    
    def _parse_context(self, context: PerspectiveContext) -> ParsedInput:
        """Parse a PerspectiveContext object."""
        
        # Build summary from answers
        summary_parts = []
        
        # Add program info
        if context.program:
            summary_parts.append(f"Program: {context.program.name}")
            if context.program.description:
                summary_parts.append(f"Description: {context.program.description}")
        
        if context.team_name:
            summary_parts.append(f"Team: {context.team_name}")
        
        if context.requested_amount:
            currency = context.program.currency if context.program else "USD"
            summary_parts.append(f"Requested Amount: {context.requested_amount:,.2f} {currency}")
        
        # Add submission answers
        if context.submission_answers:
            summary_parts.append("\n--- Submission Answers ---")
            for field_id, answer in context.submission_answers.items():
                # Find field name from form_fields
                field_name = field_id
                for field in context.form_fields:
                    if field.id == field_id:
                        field_name = field.name
                        break
                
                answer_str = self._format_answer(answer)
                if answer_str:
                    summary_parts.append(f"{field_name}: {answer_str}")
        
        clean_summary = "\n".join(summary_parts)
        
        # Truncate if needed
        words = clean_summary.split()
        if len(words) > self.max_summary_words:
            clean_summary = " ".join(words[:self.max_summary_words]) + "..."
        
        # Extract risk factors from criteria
        risk_factors = []
        opportunity_factors = []
        economic_implications = []
        
        for criterion in context.criteria:
            name_lower = criterion.name.lower()
            if any(word in name_lower for word in ["risk", "security", "compliance", "challenge"]):
                risk_factors.append(f"Criteria: {criterion.name}")
            elif any(word in name_lower for word in ["impact", "benefit", "value", "innovation"]):
                opportunity_factors.append(f"Criteria: {criterion.name}")
            elif any(word in name_lower for word in ["budget", "cost", "financial", "economic", "funding"]):
                economic_implications.append(f"Criteria: {criterion.name}")
        
        return ParsedInput(
            clean_summary=clean_summary,
            arguments={"for": [], "against": []},
            risk_factors=risk_factors[:4],
            opportunity_factors=opportunity_factors[:4],
            economic_implications=economic_implications[:3],
        )
    
    def _parse_dict(self, data: Dict[str, Any]) -> ParsedInput:
        """Parse a dictionary with submission data."""
        
        summary_parts = []
        
        # Check for common keys
        if "program_name" in data or "program" in data:
            program = data.get("program_name") or data.get("program", {})
            if isinstance(program, dict):
                summary_parts.append(f"Program: {program.get('name', 'Unknown')}")
            else:
                summary_parts.append(f"Program: {program}")
        
        if "team_name" in data:
            summary_parts.append(f"Team: {data['team_name']}")
        
        if "requested_amount" in data:
            summary_parts.append(f"Requested Amount: {data['requested_amount']}")
        
        # Handle submission answers
        answers = data.get("submission_answers") or data.get("answers", {})
        if answers:
            summary_parts.append("\n--- Submission Answers ---")
            for field_id, answer in answers.items():
                answer_str = self._format_answer(answer)
                if answer_str:
                    summary_parts.append(f"{field_id}: {answer_str}")
        
        clean_summary = "\n".join(summary_parts)
        
        # Truncate if needed
        words = clean_summary.split()
        if len(words) > self.max_summary_words:
            clean_summary = " ".join(words[:self.max_summary_words]) + "..."
        
        # Extract arguments if provided
        arguments = data.get("arguments", {"for": [], "against": []})
        
        return ParsedInput(
            clean_summary=clean_summary or str(data)[:self.max_summary_words],
            arguments=arguments,
            risk_factors=data.get("risk_factors", [])[:4],
            opportunity_factors=data.get("opportunity_factors", [])[:4],
            economic_implications=data.get("economic_implications", [])[:3],
        )
    
    def _parse_text(self, text: str) -> ParsedInput:
        """Parse plain text into ParsedInput."""
        words = text.split()
        clean_summary = " ".join(words[:self.max_summary_words])
        if len(words) > self.max_summary_words:
            clean_summary += "..."
        
        return ParsedInput(
            clean_summary=clean_summary,
            arguments={"for": [], "against": []},
            risk_factors=[],
            opportunity_factors=[],
            economic_implications=[],
        )
    
    def _format_answer(self, answer: Any) -> str:
        """Format an answer value for display."""
        if answer is None:
            return ""
        elif isinstance(answer, dict):
            return json.dumps(answer, indent=2)
        elif isinstance(answer, list):
            return ", ".join(str(item) for item in answer)
        else:
            return str(answer)


class ContextParser:
    """
    Parser that wraps PerspectiveContext directly.
    
    Use this when you already have a PerspectiveContext and want to
    pass it through the analyzer.
    """
    
    def parse(self, data: PerspectiveContext) -> ParsedInput:
        """
        Parse PerspectiveContext into ParsedInput.
        
        Args:
            data: PerspectiveContext with submission details
            
        Returns:
            ParsedInput for perspective analysis
        """
        return SubmissionParser().parse(data)


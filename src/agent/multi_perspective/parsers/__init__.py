"""
Multi-Perspective Analysis Parsers.

Provides parsers for converting various input formats into ParsedInput
for multi-perspective analysis.
"""
from .text_parser import SimpleTextParser, LLMTextParser
from .submission_parser import SubmissionParser, ContextParser

__all__ = [
    "SimpleTextParser",
    "LLMTextParser",
    "SubmissionParser",
    "ContextParser",
]


"""Tree-sitter syntax facts. Syntax only; no type resolution."""

from harpy.analysis.syntax.extract import extract_file_facts, symbols_from_facts
from harpy.analysis.syntax.imports import filter_hits

__all__ = ["extract_file_facts", "filter_hits", "symbols_from_facts"]

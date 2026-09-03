"""JSON Schema generated from Pydantic models."""

from __future__ import annotations

from typing import Any

from harpy.models import SemanticAnalysisResult


def semantic_json_schema() -> dict[str, Any]:
    return SemanticAnalysisResult.model_json_schema()

"""V2 semantic protocol variants and host-controlled retrieval."""

from __future__ import annotations

from harpy.models import AnalysisResponse, ContextRequest, RetrievalRequest, _require_repo_path

MAX_CONTEXT_ROUNDS = 2
MAX_REQUESTS_PER_ROUND = 12
MAX_CONCURRENT = 2
MAX_CALLS = 16


class RetrievalDenied(ValueError):
    pass


def parse_provider_payload(payload: dict[str, object]) -> AnalysisResponse | ContextRequest:
    kind = payload.get("kind")
    if kind == "needs_context":
        return ContextRequest.model_validate(payload)
    if kind == "result":
        return AnalysisResponse.model_validate(payload)
    raise ValueError("unknown provider payload kind")


def allow_retrieval(request: RetrievalRequest, *, allowed_paths: set[str]) -> RetrievalRequest:
    if request.path is None:
        return request
    path = _require_repo_path(request.path)
    if path not in allowed_paths:
        raise RetrievalDenied(f"disallowed path: {path}")
    return request

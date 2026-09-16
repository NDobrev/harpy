from __future__ import annotations

import json
from pathlib import Path

from harpy.web.dto import CONTRACT_MODELS
from harpy.web.openapi import REQUIRED_PATHS, openapi_document

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "web" / "openapi.json"


def test_openapi_document_lists_required_paths() -> None:
    document = openapi_document()
    assert document["openapi"] == "3.1.0"
    for path in REQUIRED_PATHS:
        assert path in document["paths"], path


def test_openapi_includes_contract_schemas() -> None:
    schemas = openapi_document()["components"]["schemas"]
    for model in CONTRACT_MODELS:
        assert model.__name__ in schemas, model.__name__


def test_committed_openapi_matches_generated_document() -> None:
    generated = json.dumps(openapi_document(), indent=2, sort_keys=True) + "\n"
    assert CONTRACT.is_file(), "docs/web/openapi.json is missing; write it from harpy schema --web"
    assert CONTRACT.read_text(encoding="utf-8") == generated


def test_openapi_does_not_claim_implemented_review_routes() -> None:
    description = openapi_document()["info"]["description"]
    assert "not served" in description

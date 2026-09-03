from __future__ import annotations

from harpy.analysis.diagrams.tree import attach_blast_trees, build_blast_tree, render_blast_tree
from harpy.models import (
    AnalysisResult,
    ApiEndpointImpact,
    EvidenceType,
    PullRequest,
    ReferenceHit,
)


def test_build_tree_from_references_and_files() -> None:
    tree = build_blast_tree(
        root_label="POST /v1/settle",
        references=[
            ReferenceHit(
                symbol="LedgerService.stamp",
                path="src/ledger.py",
                line=40,
                kind="caller",
                evidence=EvidenceType.STATIC_REFERENCE,
            ),
            ReferenceHit(
                symbol="LedgerService.stamp",
                path="tests/test_settle.py",
                line=8,
                kind="test",
                evidence=EvidenceType.TEST_REFERENCE,
            ),
        ],
        callers=["Ops client"],
        files=["src/api/settle.py"],
        symbols=["LedgerService.stamp"],
    )
    assert tree is not None
    kinds = [child.kind for child in tree.root.children]
    assert "caller" in kinds
    assert "test" in kinds
    labels = [child.label for child in tree.root.children]
    assert any("Ops client" in label for label in labels)
    picture = render_blast_tree(tree)
    text = "\n".join(picture.lines)
    assert "POST /v1/settle" in text
    assert "caller" in text
    assert "src/ledger.py:40" in text
    assert any(hit.path == "src/ledger.py" for hit in picture.hits)


def test_attach_blast_trees_fills_empty_api_impact() -> None:
    result = AnalysisResult(
        pr=PullRequest(
            number=1,
            title="t",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="a",
            additions=1,
            deletions=1,
        ),
        references=[
            ReferenceHit(
                symbol="settle",
                path="src/api/settle.py",
                line=12,
                kind="route",
                evidence=EvidenceType.ROUTE_MATCH,
            )
        ],
        api_impacts=[
            ApiEndpointImpact(
                method="POST",
                path="/v1/settle",
                files=["src/api/settle.py"],
            )
        ],
    )
    attach_blast_trees(result)
    assert result.api_impacts[0].tree is not None
    assert result.api_impacts[0].tree.root.children

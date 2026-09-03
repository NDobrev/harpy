from __future__ import annotations

from harpy.analysis.diagrams.mermaid import (
    classify_mermaid,
    parse_flowchart_mermaid,
    parse_sequence_mermaid,
)


def test_classify_mermaid_kinds() -> None:
    assert classify_mermaid("sequenceDiagram\n  A->>B: hi") == "sequence"
    assert classify_mermaid("erDiagram\n  A ||--|| B : r") == "er"
    assert classify_mermaid("flowchart TD\n  A-->B") == "flowchart"


def test_parse_sequence_participants_and_async() -> None:
    source = (
        "sequenceDiagram\n"
        "  participant Ops\n"
        "  participant API\n"
        "  Ops->>API: POST settle\n"
        "  API-->>Ledger: stamp\n"
    )
    parsed = parse_sequence_mermaid(source)
    assert parsed.actors[:2] == ["Ops", "API"]
    assert "Ledger" in parsed.actors
    assert parsed.steps[0].from_actor == "Ops"
    assert parsed.steps[0].to_actor == "API"
    assert parsed.steps[0].message == "POST settle"
    assert parsed.steps[0].kind == "sync"
    assert parsed.steps[1].kind == "async"


def test_parse_flowchart_nodes_and_edge_labels() -> None:
    source = "flowchart TD\n  A[Auth] --> B{Allowed?}\n  B -->|yes| C[Handler]\n"
    parsed = parse_flowchart_mermaid(source)
    by_id = {node.id: node for node in parsed.nodes}
    assert by_id["A"].shape == "process"
    assert by_id["B"].shape == "decision"
    assert by_id["A"].label == "Auth"
    assert any(edge.label == "yes" and edge.from_id == "B" for edge in parsed.edges)

from __future__ import annotations

from harpy.analysis.diagrams.flow import render_flow_diagram
from harpy.models import FlowDiagram, FlowEdge, FlowNode


def test_flow_boxes_and_decision() -> None:
    picture = render_flow_diagram(
        FlowDiagram(
            nodes=[
                FlowNode(id="auth", label="auth", path="src/auth.py"),
                FlowNode(id="gate", label="allowed", shape="decision"),
                FlowNode(id="write", label="write", change="add"),
            ],
            edges=[
                FlowEdge(from_id="auth", to_id="gate"),
                FlowEdge(from_id="gate", to_id="write", label="yes"),
            ],
        )
    )
    text = "\n".join(picture.lines)
    assert "auth" in text
    assert "{ allowed }" in text
    assert "write +" in text
    assert "yes" in text
    assert "▼" in text
    assert any(hit.path == "src/auth.py" for hit in picture.hits)

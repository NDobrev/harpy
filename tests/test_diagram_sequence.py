from __future__ import annotations

from harpy.analysis.diagrams.sequence import render_sequence_diagram
from harpy.models import SequenceDiagram, SequenceStep


def test_sequence_lifelines_and_change_mark() -> None:
    picture = render_sequence_diagram(
        SequenceDiagram(
            actors=["Ops", "API", "Ledger"],
            steps=[
                SequenceStep(from_actor="Ops", to_actor="API", message="POST settle"),
                SequenceStep(
                    from_actor="API",
                    to_actor="Ledger",
                    message="stamp",
                    change="add",
                    path="src/ledger.py",
                ),
            ],
        )
    )
    text = "\n".join(picture.lines)
    assert "Ops" in text
    assert "API" in text
    assert "Ledger" in text
    assert "POST settle" in text
    assert "stamp +" in text
    assert "►" in text
    assert any("│" in line for line in picture.lines)
    assert picture.hits
    assert any(hit.path == "src/ledger.py" for hit in picture.hits)

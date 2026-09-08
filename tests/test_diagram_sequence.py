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
    assert {span.tone for span in picture.spans} == {"add"}


def test_sequence_change_tones_cover_message_and_arrow() -> None:
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
                ),
                SequenceStep(
                    from_actor="Ledger",
                    to_actor="API",
                    message="old capture",
                    change="drop",
                ),
                SequenceStep(
                    from_actor="API",
                    to_actor="Ops",
                    message="200 original",
                    change="alter",
                ),
            ],
        )
    )
    tones = {span.tone for span in picture.spans}
    assert tones == {"add", "drop", "alter"}
    assert all(span.width > 0 for span in picture.spans)
    by_tone: dict[str, list[str]] = {span.tone: [] for span in picture.spans}
    for span in picture.spans:
        by_tone[span.tone].append(picture.lines[span.row][span.col : span.col + span.width])
    assert any("+" in fragment or "─" in fragment or "►" in fragment for fragment in by_tone["add"])
    assert any(
        "-" in fragment or "─" in fragment or "◄" in fragment for fragment in by_tone["drop"]
    )
    assert any(
        "~" in fragment or "─" in fragment or "◄" in fragment for fragment in by_tone["alter"]
    )

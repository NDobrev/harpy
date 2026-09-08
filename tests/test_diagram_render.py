from __future__ import annotations

from harpy.analysis.diagrams.render import paint_rendered, render_pictures, wrap_index
from harpy.models import (
    ApiDiagram,
    SchemaColumn,
    SchemaSnapshot,
    SchemaTable,
    SequenceDiagram,
    SequenceStep,
)


def test_render_pictures_keeps_schema_and_sequence() -> None:
    pictures = render_pictures(
        schema=SchemaSnapshot(
            tables=[
                SchemaTable(
                    name="fees.ledger",
                    change="alter",
                    columns=[SchemaColumn(name="settled_at", type="timestamptz", change="add")],
                )
            ]
        ),
        diagrams=[
            ApiDiagram(
                kind="sequence",
                mermaid="sequenceDiagram\n  Ops->>API: POST settle\n  API->>Ledger: stamp",
            )
        ],
        sequence=SequenceDiagram(
            actors=["Ops", "API"],
            steps=[SequenceStep(from_actor="Ops", to_actor="API", message="POST settle")],
        ),
    )
    kinds = [picture.kind for picture in pictures]
    assert "schema" in kinds
    assert "sequence" in kinds
    sequence = next(picture for picture in pictures if picture.kind == "sequence")
    assert any("│" in line for line in sequence.lines)


def test_paint_and_wrap_hits() -> None:
    pictures = render_pictures(
        schema=SchemaSnapshot(),
        diagrams=[],
        sequence=SequenceDiagram(
            actors=["Ops", "API"],
            steps=[SequenceStep(from_actor="Ops", to_actor="API", message="go")],
        ),
    )
    picture = pictures[0]
    assert picture.hits
    painted = paint_rendered(picture, 0)
    assert "[reverse]" in painted
    assert wrap_index(0, 2, 1) == 1
    assert wrap_index(1, 2, 1) == 0


def test_paint_sequence_change_colors() -> None:
    pictures = render_pictures(
        schema=SchemaSnapshot(),
        diagrams=[],
        sequence=SequenceDiagram(
            actors=["Ops", "API"],
            steps=[
                SequenceStep(from_actor="Ops", to_actor="API", message="keep"),
                SequenceStep(from_actor="API", to_actor="Ops", message="retry", change="add"),
                SequenceStep(from_actor="Ops", to_actor="API", message="old", change="drop"),
                SequenceStep(from_actor="API", to_actor="Ops", message="shape", change="alter"),
            ],
        ),
    )
    painted = paint_rendered(pictures[0], 0)
    assert "[green]" in painted
    assert "[red]" in painted
    assert "[dark_orange]" in painted
    assert "keep" in painted

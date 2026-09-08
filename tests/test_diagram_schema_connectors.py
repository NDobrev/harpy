from __future__ import annotations

from harpy.analysis.diagrams.render import paint_rendered
from harpy.analysis.diagrams.schema import render_schema, schema_picture
from harpy.models import SchemaColumn, SchemaRelation, SchemaSnapshot, SchemaTable


def test_leftover_relation_is_side_connector() -> None:
    text = render_schema(
        SchemaSnapshot(
            tables=[
                SchemaTable(
                    name="fees.settle_audit",
                    columns=[SchemaColumn(name="ledger_id", type="uuid")],
                ),
                SchemaTable(
                    name="fees.other",
                    columns=[SchemaColumn(name="id", type="uuid")],
                ),
                SchemaTable(
                    name="fees.ledger",
                    columns=[SchemaColumn(name="id", type="uuid")],
                ),
            ],
            relations=[
                SchemaRelation(
                    from_table="fees.settle_audit",
                    to_table="fees.ledger",
                    from_column="ledger_id",
                    to_column="id",
                    label="stamps",
                )
            ],
        )
    )
    assert "RELATIONS" in text
    assert "┌ fees.settle_audit.ledger_id" in text
    assert "│ stamps" in text
    assert "└► fees.ledger.id" in text
    picture = schema_picture(
        SchemaSnapshot(
            tables=[SchemaTable(name="fees.ledger", columns=[SchemaColumn(name="id", type="uuid")])]
        )
    )
    assert picture.hits
    assert any(hit.node_id == "table:fees.ledger" for hit in picture.hits)


def test_schema_picture_colors_tables_columns_and_relations() -> None:
    picture = schema_picture(
        SchemaSnapshot(
            tables=[
                SchemaTable(
                    name="fees.ledger",
                    change="alter",
                    columns=[
                        SchemaColumn(name="id", type="uuid", pk=True),
                        SchemaColumn(name="settled_at", type="timestamptz", change="add"),
                        SchemaColumn(
                            name="amount", type="numeric", old_type="integer", change="alter"
                        ),
                    ],
                ),
                SchemaTable(name="fee_pending", change="drop"),
                SchemaTable(
                    name="fees.settle_audit",
                    change="add",
                    columns=[SchemaColumn(name="id", type="uuid", change="add")],
                ),
            ],
            relations=[
                SchemaRelation(
                    from_table="fees.settle_audit",
                    to_table="fees.ledger",
                    from_column="ledger_id",
                    to_column="id",
                    label="stamps",
                    change="add",
                ),
                SchemaRelation(
                    from_table="fee_pending",
                    to_table="fees.ledger",
                    label="legacy",
                    change="drop",
                ),
            ],
        )
    )
    assert {span.tone for span in picture.spans} == {"add", "drop", "alter"}
    painted = paint_rendered(picture, 0)
    assert "[green]" in painted
    assert "[red]" in painted
    assert "[dark_orange]" in painted
    assert any(span.tone == "add" and "ADDED" in picture.lines[span.row] for span in picture.spans)
    assert any(
        span.tone == "drop" and "DROPPED" in picture.lines[span.row] for span in picture.spans
    )

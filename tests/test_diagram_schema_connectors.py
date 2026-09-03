from __future__ import annotations

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

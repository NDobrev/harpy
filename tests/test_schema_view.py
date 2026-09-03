from __future__ import annotations

from harpy.analysis.db_impact import extract_static_db_impacts
from harpy.analysis.schema_view import (
    merge_snapshots,
    parse_er_mermaid,
    render_before_after,
    render_schema,
    render_sequence,
    schema_from_patch,
    visualize_diagrams,
)
from harpy.models import (
    AnalysisResult,
    ChangedFile,
    DiffHunk,
    FileCategory,
    PullRequest,
    SchemaColumn,
    SchemaRelation,
    SchemaSnapshot,
    SchemaTable,
    StaticSignals,
)


def test_render_schema_marks_added_and_dropped() -> None:
    text = render_schema(
        SchemaSnapshot(
            tables=[
                SchemaTable(
                    name="fees.ledger",
                    change="alter",
                    columns=[
                        SchemaColumn(name="id", type="uuid", pk=True),
                        SchemaColumn(name="settled_at", type="timestamptz", change="add"),
                    ],
                ),
                SchemaTable(name="fee_pending", change="drop"),
            ],
            relations=[
                SchemaRelation(
                    from_table="fees.ledger",
                    to_table="fee_pending",
                    label="replaced",
                )
            ],
        ),
        highlight="fees.ledger.settled_at",
    )
    assert "SCHEMA" in text
    assert "fees.ledger" in text
    assert "[ALTERED]" in text
    assert "[DROPPED]" in text
    assert "settled_at" in text
    assert "+" in text
    assert "▸" in text
    assert "replaced" in text
    assert "▼" in text


def test_static_ddl_builds_schema_boxes() -> None:
    hunk = DiffHunk(
        id="H1",
        file_path="src/db/migrations/002_settle.sql",
        old_start=1,
        old_count=1,
        new_start=1,
        new_count=3,
        patch=(
            "@@\n"
            "+DROP TABLE fee_pending;\n"
            "+ALTER TABLE fees.ledger ADD COLUMN settled_at timestamptz;\n"
            "+CREATE TABLE fees.settle_audit (id uuid, ledger_id uuid REFERENCES fees.ledger);\n"
        ),
    )
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
        files=[
            ChangedFile(
                path=hunk.file_path,
                status="modified",
                additions=3,
                deletions=0,
                category_scores={FileCategory.MIGRATION: 0.9},
            )
        ],
        hunks=[hunk],
        signals=[
            StaticSignals(
                file_path=hunk.file_path,
                hunk_id="H1",
                migration=True,
                categories=["MIGRATION"],
            )
        ],
    )
    impacts = extract_static_db_impacts(result)
    merged = merge_snapshots([item.schema_snapshot for item in impacts])
    text = render_schema(merged, highlight="fees.ledger.settled_at")
    names = {table.name for table in merged.tables}
    assert "fee_pending" in names
    assert "fees.ledger" in names
    assert "fees.settle_audit" in names
    added = next(item for item in impacts if item.operation == "add_column")
    assert added.schema_snapshot.tables[0].columns[0].type == "timestamptz"
    assert added.schema_snapshot.tables[0].columns[0].change == "add"
    create = next(item for item in impacts if item.operation == "add_table")
    col_names = {column.name for column in create.schema_snapshot.tables[0].columns}
    assert col_names == {"id", "ledger_id"}
    assert "settled_at" in text
    assert "[NEW]" in text
    assert "[DROPPED]" in text


def test_er_mermaid_becomes_boxes_not_source() -> None:
    source = "erDiagram\n  LEDGER ||--o| SETTLE : stamps\n  LEDGER {\n    uuid id PK\n    timestamptz settled_at\n  }"
    parsed = parse_er_mermaid(source)
    text = visualize_diagrams(schema=SchemaSnapshot(), mermaid=[source])
    assert parsed.relations[0].label == "stamps"
    assert any(column.name == "id" and column.pk for column in parsed.tables[0].columns) or any(
        column.name == "id" for table in parsed.tables for column in table.columns
    )
    assert "LEDGER" in text
    assert "SETTLE" in text
    assert "stamps" in text
    assert "erDiagram" not in text


def test_sequence_mermaid_becomes_arrows() -> None:
    source = "sequenceDiagram\n  Ops->>API: POST settle\n  API->>Ledger: stamp"
    text = render_sequence(source)
    assert "Ops" in text
    assert "POST settle" in text
    assert "Ledger" in text
    assert "sequenceDiagram" not in text


def test_before_after_splits_tables_and_omits_unchanged_relations() -> None:
    text = render_before_after(
        SchemaSnapshot(
            tables=[
                SchemaTable(
                    name="fees.ledger",
                    change="alter",
                    columns=[
                        SchemaColumn(name="id", type="uuid", pk=True),
                        SchemaColumn(
                            name="amount", type="numeric", old_type="integer", change="alter"
                        ),
                        SchemaColumn(name="settled_at", type="timestamptz", change="add"),
                    ],
                ),
                SchemaTable(
                    name="fees.settle_audit",
                    change="add",
                    columns=[
                        SchemaColumn(name="id", type="uuid", pk=True, change="add"),
                        SchemaColumn(
                            name="ledger_id",
                            type="uuid",
                            fk="fees.ledger",
                            fk_column="id",
                            change="add",
                        ),
                    ],
                ),
                SchemaTable(name="fee_pending", change="drop"),
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
                    from_column="ledger_id",
                    to_column="id",
                    label="legacy",
                    change="drop",
                ),
                SchemaRelation(
                    from_table="fees.ledger",
                    to_table="fees.currency",
                    from_column="currency_id",
                    to_column="id",
                    label="currency",
                ),
            ],
        ),
        highlight="fees.ledger.settled_at",
    )
    old, new = text.split("NEW", 1)
    assert "OLD" in old
    assert "fee_pending" in old
    assert "settled_at" not in old
    assert "integer" in old
    assert "settle_audit" not in old
    assert "legacy" in old
    assert "stamps" not in old.split("RELATIONS")[0]
    assert "fees.settle_audit" in new
    assert "settled_at" in new
    assert "numeric" in new
    assert "stamps" in new
    assert "+ ADDED" in text
    assert "- DROPPED" in text
    assert "currency" not in text
    assert "▸" in text


def test_visualize_uses_old_new_when_schema_changed() -> None:
    text = visualize_diagrams(
        schema=SchemaSnapshot(
            tables=[
                SchemaTable(
                    name="fees.ledger",
                    change="alter",
                    columns=[SchemaColumn(name="settled_at", type="timestamptz", change="add")],
                )
            ]
        ),
        mermaid=[],
        highlight="fees.ledger",
    )
    assert "NEW" in text
    assert "settled_at" in text
    assert "OLD" not in text


def test_create_table_references_is_added_relation() -> None:
    snapshot = schema_from_patch(
        "+CREATE TABLE fees.settle_audit (id uuid, ledger_id uuid REFERENCES fees.ledger(id));",
        operation="add_table",
        target="fees.settle_audit",
    )
    assert snapshot.relations
    assert snapshot.relations[0].change == "add"
    assert snapshot.relations[0].from_table == "fees.settle_audit"
    assert snapshot.relations[0].to_table == "fees.ledger"
    assert snapshot.relations[0].from_column == "ledger_id"
    assert snapshot.relations[0].to_column == "id"
    text = visualize_diagrams(schema=snapshot, mermaid=[])
    assert "NEW" in text
    assert "RELATIONS CHANGED" in text
    assert "+ ADDED" in text


def test_schema_from_patch_add_column() -> None:
    snapshot = schema_from_patch(
        "+ALTER TABLE fees.ledger ADD COLUMN settled_at timestamptz;",
        operation="add_column",
        target="fees.ledger.settled_at",
    )
    assert snapshot.tables[0].name == "fees.ledger"
    assert snapshot.tables[0].columns[0].name == "settled_at"
    assert snapshot.tables[0].columns[0].type == "timestamptz"
    assert snapshot.tables[0].columns[0].change == "add"

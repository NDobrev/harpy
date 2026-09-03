from __future__ import annotations

from harpy.models import ApiEndpointImpact, DbChangeImpact
from harpy.tui.impact_entries import (
    ImpactEntry,
    impact_tone,
    row_classes,
    rows_from_entries,
)


def test_tone_priority_breaking_then_bl_then_kind() -> None:
    api = ImpactEntry(kind="api", api=ApiEndpointImpact(method="GET", path="/v1/x"))
    db = ImpactEntry(kind="db", db=DbChangeImpact(operation="add_column", target="fees.t"))
    bl = ImpactEntry(
        kind="api",
        api=ApiEndpointImpact(method="POST", path="/v1/y", business_logic=True),
    )
    breaking = ImpactEntry(
        kind="db",
        db=DbChangeImpact(operation="drop_table", target="old", breaking=True, business_logic=True),
    )
    assert impact_tone(api) == "api"
    assert impact_tone(db) == "db"
    assert impact_tone(bl) == "bl"
    assert impact_tone(breaking) == "breaking"


def test_row_classes_match_tone() -> None:
    rows = rows_from_entries(
        [
            ImpactEntry(
                kind="api", api=ApiEndpointImpact(method="GET", path="/v1/x", files=["a.ts"])
            ),
            ImpactEntry(
                kind="db",
                db=DbChangeImpact(
                    operation="add_column", target="t", breaking=True, files=["m.sql"]
                ),
            ),
        ]
    )
    assert rows[0].tone == "api"
    assert "impact-api" in row_classes(rows[0])
    assert rows[1].tone == "api"
    assert "impact-file" in row_classes(rows[1])
    assert rows[2].tone == "breaking"
    assert "impact-breaking" in row_classes(rows[2])


def test_security_tone_beats_business_logic() -> None:
    item = ImpactEntry(
        kind="api",
        api=ApiEndpointImpact(
            method="POST",
            path="/v1/grant",
            business_logic=True,
            security=True,
        ),
    )
    assert impact_tone(item) == "sec"
    rows = rows_from_entries([item])
    assert "SEC" in rows[0].label
    assert "BL" in rows[0].label
    assert "impact-sec" in row_classes(rows[0])

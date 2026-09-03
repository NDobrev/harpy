"""Pure row rendering for the review-scope dialog."""

from __future__ import annotations

from dataclasses import dataclass

from harpy.models import ScopeCall, ScopeSelection
from harpy.review_scope import SCOPES, normalize, short_model_label

MODIFIER_MODEL = "—"


@dataclass(frozen=True)
class ScopeRowView:
    scope_id: str
    checked: bool
    label: str
    model: str
    selected: bool


def row_views(
    selection: ScopeSelection,
    cursor: int,
    *,
    default_model: str | None = None,
) -> list[ScopeRowView]:
    norm = (
        normalize(selection, default_model=default_model) if default_model else normalize(selection)
    )
    rows: list[ScopeRowView] = []
    for index, item in enumerate(SCOPES):
        model = MODIFIER_MODEL if item.kind == "modifier" else norm.models[item.id]
        rows.append(
            ScopeRowView(
                scope_id=item.id,
                checked=norm.enabled[item.id],
                label=item.label,
                model=model,
                selected=index == cursor,
            )
        )
    return rows


def render_row(row: ScopeRowView) -> str:
    mark = "[x]" if row.checked else "[ ]"
    cursor = "▸ " if row.selected else "  "
    return f"{cursor}{mark} {row.label:<32} {row.model}"


def summary_line(calls: list[ScopeCall]) -> str:
    if not calls:
        return "0 agent calls"
    counts: dict[str, int] = {}
    for call in calls:
        label = short_model_label(call.model)
        n = len([scope_id for scope_id in call.scope_ids if scope_id != "diagrams"])
        counts[label] = counts.get(label, 0) + n
    parts = " ".join(f"{name}({count})" for name, count in counts.items())
    noun = "call" if len(calls) == 1 else "calls"
    return f"{len(calls)} agent {noun} · {parts}"


def preset_line(name: str | None) -> str:
    label = name or "(custom)"
    return f"preset  {label:<24} p/P cycle · S save · x del"


def help_line() -> str:
    return "j/k row  space toggle  m/M model  enter run  esc cancel"

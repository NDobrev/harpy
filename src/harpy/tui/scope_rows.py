"""Pure row rendering for the review-scope dialog."""

from __future__ import annotations

from dataclasses import dataclass

from harpy.models import ScopeCall, ScopeSelection
from harpy.review_scope import SCOPES, normalize, plan_calls, short_model_label

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


@dataclass(frozen=True)
class ScopeCopy:
    id: str
    label: str
    description: str
    help: str
    group: str = ""


SCOPE_COPY: tuple[ScopeCopy, ...] = (
    ScopeCopy(
        "changes",
        "Behavior changes",
        "Group changes and explain before/after",
        "Group hunks into logical changes and explain observable before/after behavior.",
        "UNDERSTAND THE CHANGE",
    ),
    ScopeCopy(
        "security",
        "Security & data",
        "Examine permissions and sensitive data",
        "Examine authentication, permissions, and sensitive-data changes. Findings need verification.",
        "CHECK RISK AND COMPATIBILITY",
    ),
    ScopeCopy(
        "api",
        "API contracts",
        "Identify changes that affect callers",
        "Examine HTTP/RPC contract changes, compatibility, and affected callers.",
    ),
    ScopeCopy(
        "db",
        "Database changes",
        "Examine schema and persistence changes",
        "Examine schema, migrations, constraints, and persistence-contract changes.",
    ),
    ScopeCopy(
        "tests",
        "Test coverage",
        "Identify relevant tests and gaps",
        "Harpy inspects test evidence; this analysis does not run tests or measure runtime coverage.",
        "PREPARE YOUR REVIEW",
    ),
    ScopeCopy(
        "questions",
        "Review questions",
        "Suggest questions worth investigating",
        "Suggest questions about behavior, compatibility, and assumptions worth investigating.",
    ),
    ScopeCopy(
        "omissions",
        "Possible omissions",
        "Look for potentially missing changes",
        "Look for related changes that may be missing, such as callers, migrations, or tests. "
        "Suggestions require your verification.",
    ),
    ScopeCopy(
        "diagrams",
        "Include diagrams",
        "For API and database changes",
        "Add diagrams to API and database analysis. This option inherits those checks' models.",
        "VISUAL EXPLANATIONS",
    ),
)
SCOPE_COPY_BY_ID = {item.id: item for item in SCOPE_COPY}


def diagrams_available(selection: ScopeSelection) -> bool:
    return any(selection.enabled.get(scope_id, False) for scope_id in ("api", "db"))


def model_summary(selection: ScopeSelection) -> str:
    models = set(selection.models.values())
    if len(models) == 1:
        return short_model_label(next(iter(models)))
    return "Multiple models · Customize…"


def run_summary(selection: ScopeSelection, *, default_model: str) -> str:
    calls = plan_calls(selection, default_model=default_model)
    count = sum(bool(selection.enabled.get(item.id)) for item in SCOPES if item.kind == "call")
    if not count:
        return "Select at least one check."
    checks = "check" if count == 1 else "checks"
    diagrams = " + diagrams" if selection.enabled.get("diagrams") else ""
    noun = "call" if len(calls) == 1 else "calls"
    return f"{count} {checks}{diagrams} · {len(calls)} planned AI {noun}"


def run_details(selection: ScopeSelection, *, default_model: str) -> str:
    calls = plan_calls(selection, default_model=default_model)
    lines = []
    has_grouping = any("changes" in call.scope_ids for call in calls)
    for index, call in enumerate(calls, start=1):
        labels = ", ".join(SCOPE_COPY_BY_ID[scope_id].label for scope_id in call.scope_ids)
        timing = " · after grouping" if has_grouping and call.stage == 1 else ""
        lines.append(f"{index}. {call.model}{timing}\n   {labels}")
    lines.append("Duration and usage vary. A failed response may require a repair call.")
    return "\n".join(lines)

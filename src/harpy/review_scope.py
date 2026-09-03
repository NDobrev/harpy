"""Review-scope catalog, presets, and group-by-model call planning."""

from __future__ import annotations

from dataclasses import dataclass

from harpy.config import DEFAULT_MODEL
from harpy.models import ScopeCall, ScopePreset, ScopeSelection

MODIFIER_SCOPE = "diagrams"
CHANGES_SCOPE = "changes"
CONTRACT_SCOPES = ("api", "db")


@dataclass(frozen=True)
class ScopeDefinition:
    id: str
    label: str
    kind: str
    help: str = ""


SCOPES: tuple[ScopeDefinition, ...] = (
    ScopeDefinition(
        "changes",
        "Logical changes & PR intent",
        "call",
        "Hunk grouping, before/after, why, risk, and scoring dimensions.",
    ),
    ScopeDefinition("api", "API contract impact", "call", "HTTP/RPC/route contract changes."),
    ScopeDefinition(
        "db", "Database & schema impact", "call", "Schema, migration, and persistence contracts."
    ),
    ScopeDefinition(
        "security",
        "Security & data sensitivity",
        "call",
        "Disabling this leaves security/data dimensions at 0 and lowers importance.",
    ),
    ScopeDefinition("questions", "Review questions", "call"),
    ScopeDefinition("tests", "Suggested tests", "call"),
    ScopeDefinition("omissions", "Possible omissions", "call"),
    ScopeDefinition(
        "diagrams",
        "Diagrams & blast trees",
        "modifier",
        "Rides along with API/DB. Auto-disabled when both are off.",
    ),
)

SCOPE_IDS: tuple[str, ...] = tuple(item.id for item in SCOPES)
SCOPE_BY_ID: dict[str, ScopeDefinition] = {item.id: item for item in SCOPES}


def _models_for(model: str) -> dict[str, str]:
    return {item.id: model for item in SCOPES if item.kind != "modifier"}


def _enabled_map(ids: set[str]) -> dict[str, bool]:
    return {item.id: item.id in ids for item in SCOPES}


def _builtin(name: str, ids: set[str], *, model: str = DEFAULT_MODEL) -> ScopePreset:
    enabled = _enabled_map(ids)
    if not enabled["api"] and not enabled["db"]:
        enabled[MODIFIER_SCOPE] = False
    return ScopePreset(name=name, builtin=True, enabled=enabled, models=_models_for(model))


BUILTIN_PRESETS: tuple[ScopePreset, ...] = (
    _builtin("Everything", set(SCOPE_IDS)),
    _builtin("Security", {"changes", "security", "questions"}),
    _builtin("API", {"changes", "api", "diagrams"}),
    _builtin("Database", {"changes", "db", "diagrams"}),
    _builtin("Fast triage", {"changes"}),
)


def default_selection(*, model: str | None = None) -> ScopeSelection:
    chosen = model or DEFAULT_MODEL
    return ScopeSelection(
        enabled={item.id: True for item in SCOPES},
        models=_models_for(chosen),
        preset="Everything",
    )


def normalize(selection: ScopeSelection, *, default_model: str = DEFAULT_MODEL) -> ScopeSelection:
    enabled = {item.id: bool(selection.enabled.get(item.id, True)) for item in SCOPES}
    models = {
        item.id: selection.models.get(item.id) or default_model
        for item in SCOPES
        if item.kind != "modifier"
    }
    if not enabled["api"] and not enabled["db"]:
        enabled[MODIFIER_SCOPE] = False
    return ScopeSelection(enabled=enabled, models=models, preset=selection.preset)


def apply_preset(preset: ScopePreset, *, default_model: str = DEFAULT_MODEL) -> ScopeSelection:
    return normalize(
        ScopeSelection(
            enabled=dict(preset.enabled), models=dict(preset.models), preset=preset.name
        ),
        default_model=default_model,
    )


def matching_preset(
    selection: ScopeSelection,
    presets: tuple[ScopePreset, ...] | list[ScopePreset],
    *,
    default_model: str = DEFAULT_MODEL,
) -> str | None:
    norm = normalize(selection, default_model=default_model)
    for preset in presets:
        candidate = normalize(apply_preset(preset, default_model=default_model))
        if candidate.enabled == norm.enabled and candidate.models == norm.models:
            return preset.name
    return None


def plan_calls(selection: ScopeSelection, *, default_model: str = DEFAULT_MODEL) -> list[ScopeCall]:
    norm = normalize(selection, default_model=default_model)
    groups: dict[str, list[str]] = {}
    for item in SCOPES:
        if item.kind == "modifier" or not norm.enabled[item.id]:
            continue
        groups.setdefault(norm.models[item.id], []).append(item.id)
    diagrams = bool(norm.enabled[MODIFIER_SCOPE])
    ordered = sorted(
        groups.items(), key=lambda pair: (0 if CHANGES_SCOPE in pair[1] else 1, pair[0])
    )
    calls: list[ScopeCall] = []
    for index, (model, ids) in enumerate(ordered):
        scope_ids = list(ids)
        if diagrams and any(scope in CONTRACT_SCOPES for scope in scope_ids):
            scope_ids.append(MODIFIER_SCOPE)
        call_id = f"c{index}"
        calls.append(
            ScopeCall(
                id=call_id,
                model=model,
                scope_ids=scope_ids,
                stage=0 if CHANGES_SCOPE in scope_ids else 1,
                context_name=f"ANALYSIS_CONTEXT_{call_id}.md",
            )
        )
    return calls


def signature(selection: ScopeSelection, *, default_model: str = DEFAULT_MODEL) -> str:
    norm = normalize(selection, default_model=default_model)
    if all(norm.enabled[item.id] for item in SCOPES) and all(
        norm.models[item.id] == default_model for item in SCOPES if item.kind != "modifier"
    ):
        return ""
    parts: list[str] = []
    for item in SCOPES:
        if not norm.enabled[item.id]:
            continue
        if item.kind == "modifier":
            parts.append(item.id)
        else:
            parts.append(f"{item.id}:{norm.models[item.id]}")
    return ",".join(parts)


def short_model_label(model: str) -> str:
    name = model.removeprefix("cursor-")
    for suffix in ("-high-fast", "-thinking-high"):
        name = name.removesuffix(suffix)
    return name

"""Versioned analysis bundle. Prompt changes must bump PROMPT_VERSION."""

from __future__ import annotations

from collections.abc import Sequence

from harpy.models import (
    AnalysisResult,
    ChangedFile,
    DiffHunk,
    LogicalChange,
    ReferenceHit,
    SemanticChangeDraft,
    StaticSignals,
)

PROMPT_VERSION = "11"
CONTEXT_FILENAME = "ANALYSIS_CONTEXT.md"
MAX_HUNKS = 40
MAX_HUNK_CHARS = 2500
MAX_REFERENCES = 20
MAX_REF_SNIPPET = 120

INSTRUCTION = """You are Harpy's read-only PR analyzer.
Use only read tools. Do not run shell commands. Do not write files.
Read ANALYSIS_CONTEXT.md in this workspace.
If SYMBOL_FACTS.md exists, grep it by file path for DEF/IMP/ROUTE/DDL records. Syntax only; not a type checker or call graph. Read only the paths you need.
Emit ONE JSON object and no prose. No markdown fences if you can avoid them.
Describe observable before/after behavior, not implementation mechanics.
Group hunks into logical product decisions. Reference hunk ids exactly (H1, H2, ...).
JSON shape:
{
  "pr_intent": "string",
  "changes": [
    {
      "id": "C1",
      "title": "string",
      "business_impact": 0,
      "behavior_change": 0,
      "blast_radius": 0,
      "security_sensitivity": 0,
      "data_sensitivity": 0,
      "novelty": 0,
      "confidence": 0.0,
      "unexpectedness": 0.0,
      "risk": "low|medium|high|critical",
      "before": "string",
      "after": "string",
      "why": "string",
      "business_effect": "string",
      "files": ["path"],
      "hunk_ids": ["H1"],
      "affected_symbols": ["Symbol.name"],
      "affected_components": ["string"],
      "domains": ["authorization"],
      "tests": ["path"],
      "review_questions": ["string"],
      "possible_omissions": ["string"]
    }
  ],
  "api_impacts": [
    {
      "change_id": "C1",
      "method": "POST",
      "path": "/v1/example",
      "summary": "string",
      "before": "observable caller/client behavior",
      "after": "observable caller/client behavior",
      "impact": "who breaks, who must migrate, what callers see",
      "breaking": false,
      "breaking_reason": "string or empty",
      "callers": ["client or route"],
      "files": ["path"],
      "business_logic": false,
      "business_logic_why": "empty if business logic is not impacted",
      "security": false,
      "security_why": "empty if auth, permission, or data exposure is not impacted",
      "sequence": {
        "actors": ["Ops", "API"],
        "steps": [
          {
            "from": "Ops",
            "to": "API",
            "message": "POST /v1/example",
            "kind": "sync",
            "change": "add|drop|alter|",
            "path": "optional source file",
            "symbol": ""
          }
        ]
      },
      "flow": {
        "nodes": [{"id": "auth", "label": "auth", "shape": "process|decision|start|end", "change": "", "path": ""}],
        "edges": [{"from": "auth", "to": "handler", "label": "", "change": ""}]
      },
      "tree": {
        "root": {
          "label": "POST /v1/example",
          "kind": "root",
          "evidence": "",
          "path": "",
          "line": 0,
          "children": [
            {"label": "caller", "kind": "caller", "evidence": "STATIC_REFERENCE", "path": "src/a.py", "line": 1, "children": []}
          ]
        }
      },
      "diagrams": [
        {
          "kind": "before_after|sequence|flowchart",
          "title": "string",
          "mermaid": "mermaid source only if structured sequence/flow is empty and a diagram clarifies a contract",
          "why": "why a diagram is worth a reviewer's time",
          "sequence": {"actors": [], "steps": []},
          "flow": {"nodes": [], "edges": []}
        }
      ]
    }
  ],
  "db_impacts": [
    {
      "change_id": "C1",
      "operation": "add_table|drop_table|add_column|drop_column|alter_column|add_index|rename|backfill|constraint|other",
      "target": "schema.table or schema.table.column",
      "summary": "string",
      "before": "what was stored / constrained",
      "after": "what is stored / constrained",
      "impact": "who reads/writes this, migration risk, downtime, backfill",
      "breaking": false,
      "breaking_reason": "string or empty",
      "files": ["path"],
      "business_logic": false,
      "business_logic_why": "empty if business logic is not impacted",
      "security": false,
      "security_why": "empty if auth, permission, or data exposure is not impacted",
      "objects": ["table or table.column"],
      "schema": {
        "tables": [
          {
            "name": "schema.table",
            "change": "add|drop|alter|",
            "columns": [
              {
                "name": "column",
                "type": "timestamptz",
                "old_type": "type before alter, else empty",
                "nullable": true,
                "pk": false,
                "fk": "",
                "fk_column": "",
                "change": "add|drop|alter|"
              }
            ]
          }
        ],
        "relations": [
          {
            "from_table": "schema.table",
            "to_table": "schema.other",
            "from_column": "id",
            "to_column": "table_id",
            "label": "stamps",
            "change": "add|drop|alter|"
          }
        ]
      },
      "sequence": {"actors": [], "steps": []},
      "flow": {"nodes": [], "edges": []},
      "tree": {"root": {"label": "schema.table", "kind": "root", "path": "", "line": 0, "children": []}},
      "diagrams": [
        {
          "kind": "before_after|er|sequence|flowchart",
          "title": "string",
          "mermaid": "optional mermaid only if structured sequence/flow is empty after schema boxes",
          "why": "why extra mermaid is worth a reviewer's time",
          "sequence": {"actors": [], "steps": []},
          "flow": {"nodes": [], "edges": []}
        }
      ]
    }
  ]
}
Dimension fields are 0-10. confidence and unexpectedness are 0-1.
api_impacts: only HTTP/RPC/route contract changes. Omit the array (or use []) if none.
db_impacts: only schema, migration, or persistence-contract changes (what is stored, uniqueness, cascade, required columns). Omit routine query tweaks. Omit the array (or use []) if none.
files: every source file involved in this impact, including handlers, services, and tests that change because of it.
business_logic: true when domain rules, calculations, or state machines change because of this contract. Say why. False when only the route or schema wrapper moves.
security: true when auth, permission, RBAC, secrets, or data exposure change because of this contract. Say why.
schema: required on each db_impact. Include the tables and columns a reviewer must see, with change marks. The TUI splits them into OLD and NEW tables. Include a neighboring table only when a changed relation needs it.
relations: only associations that changed (new FK, dropped FK, retarget). Omit unchanged FKs. Set change to add|drop|alter.
sequence/flow: optional structured pictures. Prefer these over mermaid. Include only when prose hides the call order or pipeline.
tree: blast-radius callers/routes/tests. If omitted, Harpy builds one from references. Not a perfect call graph.
diagrams: optional. Prefer schema boxes over mermaid. Include at most one small mermaid when structured sequence/flow is empty and a flow is otherwise easy to miss. Do not decorate a rename or a docstring-only change with a diagram.
"""


def context_filename(call_id: str | None = None) -> str:
    if not call_id:
        return CONTEXT_FILENAME
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in call_id)
    return f"ANALYSIS_CONTEXT_{safe}.md"


def short_prompt(context_name: str = CONTEXT_FILENAME) -> str:
    return (
        f"Read {context_name} in this workspace. "
        "Emit one JSON object matching the schema described there. No prose."
    )


SHORT_PROMPT = short_prompt()


def is_noise_file(file: ChangedFile) -> bool:
    if file.generated_probability >= 0.8:
        return True
    return file.category_scores.get("LOCKFILE", 0.0) >= 0.8


def build_bundle(
    *,
    title: str,
    body: str,
    files: list[ChangedFile],
    hunks: list[DiffHunk],
    signals: list[StaticSignals],
    references: list[ReferenceHit],
    scope_ids: Sequence[str] | None = None,
    known_changes: Sequence[SemanticChangeDraft | LogicalChange] = (),
    context_name: str = CONTEXT_FILENAME,
) -> str:
    if scope_ids is None:
        instruction = INSTRUCTION
    else:
        from harpy.semantic.scopes import compose_instruction

        instruction = compose_instruction(scope_ids, context_name=context_name)
    lines = [
        instruction,
        f"PROMPT_VERSION={PROMPT_VERSION}",
        "",
        "PR TITLE",
        title,
        "",
        "PR DESCRIPTION",
        body[:2000],
        "",
        "FILES",
    ]
    for file in files:
        if is_noise_file(file):
            lines.append(f"- {file.path} [{file.status}] noise (omit body)")
            continue
        lines.append(
            f"- {file.path} [{file.status}] +{file.additions}/-{file.deletions} cats={file.category_scores}"
        )
    lines.append("")
    lines.append("STATIC SIGNALS")
    for signal in signals[:80]:
        lines.append(
            f"- {signal.hunk_id or '-'} {signal.file_path} score={signal.raw_score:g} {signal.categories}"
        )
    lines.append("")
    lines.append("HUNKS")
    ranked = sorted(hunks, key=lambda item: item.static_score, reverse=True)
    selected = [hunk for hunk in ranked if not _hunk_is_noise(hunk, files)][:MAX_HUNKS]
    selected.sort(key=lambda item: item.id)
    for hunk in selected:
        lines.append(f"CHANGE {hunk.id} {hunk.file_path} symbols={hunk.changed_symbols}")
        lines.append(hunk.patch[:MAX_HUNK_CHARS])
        lines.append("")
    if len(ranked) > len(selected):
        lines.append(f"(omitted {len(ranked) - len(selected)} lower-score hunks)")
    if known_changes:
        lines.append("KNOWN CHANGES")
        for change in known_changes:
            hunks_for = list(change.hunk_ids) if change.hunk_ids else []
            if not hunks_for and isinstance(change, LogicalChange):
                hunks_for = list(change.hunks)
            lines.append(f"- {change.id} {change.title} hunks={hunks_for}")
        lines.append("")
    lines.append("REFERENCES")
    for hit in references[:MAX_REFERENCES]:
        snippet = hit.snippet[:MAX_REF_SNIPPET]
        lines.append(f"- {hit.symbol} {hit.kind} {hit.path}:{hit.line} {snippet}")
    return "\n".join(lines)


def _hunk_is_noise(hunk: DiffHunk, files: list[ChangedFile]) -> bool:
    return any(file.path == hunk.file_path and is_noise_file(file) for file in files)


def repair_prompt(error: str, *, context_name: str = CONTEXT_FILENAME) -> str:
    return (
        f"The previous JSON failed validation:\n{error[:2000]}\n"
        f"Re-read {context_name} and emit a corrected JSON object only.\n"
    )


def bundle_from_result(
    result: AnalysisResult,
    *,
    scope_ids: Sequence[str] | None = None,
    known_changes: Sequence[SemanticChangeDraft | LogicalChange] = (),
    context_name: str = CONTEXT_FILENAME,
) -> str:
    return build_bundle(
        title=result.pr.title,
        body=result.pr.body,
        files=result.files,
        hunks=result.hunks,
        signals=result.signals,
        references=result.references,
        scope_ids=scope_ids,
        known_changes=known_changes,
        context_name=context_name,
    )

"""Per-scope prompt fragments for a composed semantic instruction."""

from __future__ import annotations

from collections.abc import Iterable

_HEADER = """You are Harpy's read-only PR analyzer.
Use only read tools. Do not run shell commands. Do not write files.
Read {context} in this workspace.
Emit ONE JSON object and no prose. No markdown fences if you can avoid them.
Describe observable before/after behavior, not implementation mechanics.
"""

_FACTS_SCOPES = frozenset({"changes", "api", "db", "diagrams"})
_FACTS_RULE = (
    "If SYMBOL_FACTS.md exists, grep it by file path for DEF/IMP/ROUTE/DDL "
    "records. Syntax only; not a type checker or call graph. Read only the "
    "paths you need."
)

_CHANGES_RULE = (
    "Group hunks into logical product decisions. Reference hunk ids exactly (H1, H2, ...)."
)
_KNOWN_RULE = "Do not regroup hunks. Reference the KNOWN CHANGES ids exactly."

_CHANGE_CORE = """      "id": "C1",
      "title": "string",
      "business_impact": 0,
      "behavior_change": 0,
      "blast_radius": 0,
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
      "domains": ["authorization"]"""

_SECURITY_CHANGE_FIELDS = """      "security_sensitivity": 0,
      "data_sensitivity": 0"""

_QUESTIONS_FIELD = '      "review_questions": ["string"]'
_TESTS_FIELD = '      "tests": ["path"]'
_OMISSIONS_FIELD = '      "possible_omissions": ["string"]'

_API_CORE = """      "change_id": "C1",
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
      "business_logic_why": "empty if business logic is not impacted" """

_SECURITY_IMPACT_FIELDS = """      "security": false,
      "security_why": "empty if auth, permission, or data exposure is not impacted" """

_DIAGRAM_FIELDS = """      "sequence": {
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
          "label": "label",
          "kind": "root",
          "evidence": "",
          "path": "",
          "line": 0,
          "children": []
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
      ]"""

_DB_CORE = """      "change_id": "C1",
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
      }"""

_RULES = """Dimension fields are 0-10. confidence and unexpectedness are 0-1.
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
annotations: attach extra fields to existing change ids. Do not invent new change ids.
"""

_ANNOTATION_FIELDS = {
    "security": ('      "security_sensitivity": 0,\n      "data_sensitivity": 0'),
    "questions": '      "review_questions": ["string"]',
    "tests": '      "tests": ["path"]',
    "omissions": '      "possible_omissions": ["string"]',
}

_INLINE_SCOPES = ("security", "questions", "tests", "omissions")


def _join_fields(fields: list[str]) -> str:
    return ",\n".join(fields)


def compose_instruction(
    scope_ids: Iterable[str],
    *,
    with_changes: bool | None = None,
    context_name: str = "ANALYSIS_CONTEXT.md",
) -> str:
    ids = set(scope_ids)
    include_changes = ("changes" in ids) if with_changes is None else with_changes
    lines = [_HEADER.format(context=context_name)]
    if include_changes:
        lines.append(_CHANGES_RULE)
    else:
        lines.append(_KNOWN_RULE)
    if ids & _FACTS_SCOPES:
        lines.append(_FACTS_RULE)
    lines.append("JSON shape:")
    lines.append("{")
    top: list[str] = []
    if include_changes:
        change_fields = [_CHANGE_CORE]
        if "security" in ids:
            change_fields.append(_SECURITY_CHANGE_FIELDS)
        if "questions" in ids:
            change_fields.append(_QUESTIONS_FIELD)
        if "tests" in ids:
            change_fields.append(_TESTS_FIELD)
        if "omissions" in ids:
            change_fields.append(_OMISSIONS_FIELD)
        top.append('  "pr_intent": "string"')
        top.append('  "changes": [\n    {\n' + _join_fields(change_fields) + "\n    }\n  ]")
    annotation_ids = [item for item in _INLINE_SCOPES if item in ids and not include_changes]
    if annotation_ids:
        fields = ['      "change_id": "C1"']
        for item in annotation_ids:
            fields.append(_ANNOTATION_FIELDS[item])
        top.append('  "annotations": [\n    {\n' + _join_fields(fields) + "\n    }\n  ]")
    if "api" in ids:
        api_fields = [_API_CORE]
        if "security" in ids:
            api_fields.append(_SECURITY_IMPACT_FIELDS)
        if "diagrams" in ids:
            api_fields.append(_DIAGRAM_FIELDS)
        top.append('  "api_impacts": [\n    {\n' + _join_fields(api_fields) + "\n    }\n  ]")
    if "db" in ids:
        db_fields = [_DB_CORE]
        if "security" in ids:
            db_fields.append(_SECURITY_IMPACT_FIELDS)
        if "diagrams" in ids:
            db_fields.append(_DIAGRAM_FIELDS)
        top.append('  "db_impacts": [\n    {\n' + _join_fields(db_fields) + "\n    }\n  ]")
    lines.append(",\n".join(top))
    lines.append("}")
    lines.append(_RULES)
    return "\n".join(lines)

"""Run tree-sitter queries and return FileFacts. Falls back to Python AST."""

from __future__ import annotations

import re
from typing import Any, Protocol

from tree_sitter import Parser, QueryCursor

from harpy.analysis.symbols import build_symbol_map
from harpy.analysis.syntax.grammars import language_for_path, load_language, load_query
from harpy.models import DdlFact, DiffHunk, FileFacts, ImportFact, RouteFact, SymbolFact

MAX_SYMBOLS = 80
MAX_IMPORTS = 40
MAX_ROUTES = 20
MAX_DDL = 20
_SIG_LIMIT = 80

_HTTP = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "handle",
    "handlefunc",
    "controller",
    "route",
}

_FK_RE = re.compile(r"REFERENCES\s+([\w.]+)\s*\(([\w]+)\)", re.I)
_GO_RECV_RE = re.compile(r"\*?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")


class SymbolExtractor(Protocol):
    def extract(self, source: str, *, path: str) -> FileFacts: ...


def extract_file_facts(source: str, *, path: str) -> FileFacts:
    language = language_for_path(path)
    facts = FileFacts(path=path, language=language or "")
    if language:
        try:
            facts = _from_tree_sitter(source, path=path, language=language)
        except (OSError, TypeError, ValueError, RuntimeError):
            facts = FileFacts(path=path, language=language)
    if not facts.symbols and path.endswith(".py"):
        facts = _from_ast(source, path=path, extras=facts)
    return _cap(facts)


def symbols_from_facts(facts: FileFacts, hunk: DiffHunk) -> list[str]:
    start = hunk.new_start
    end = hunk.new_start + max(hunk.new_count, 1) - 1
    names: list[str] = []
    for symbol in facts.symbols:
        if symbol.end_line < start or symbol.start_line > end:
            continue
        if symbol.name not in names:
            names.append(symbol.name)
    return names


def _from_tree_sitter(source: str, *, path: str, language: str) -> FileFacts:
    lang = load_language(language)
    query = load_query(language)
    if lang is None or query is None:
        return FileFacts(path=path, language=language)
    parser = Parser(lang)
    tree = parser.parse(source.encode("utf-8"))
    cursor = QueryCursor(query)
    facts = FileFacts(path=path, language=language)
    seen_symbols: set[tuple[str, int]] = set()
    for _pattern, captures in cursor.matches(tree.root_node):
        item = _first(captures, "item")
        if "name" in captures and item is not None:
            symbol = _symbol(item, captures, path=path, language=language)
            key = (symbol.name, symbol.start_line)
            if symbol.name and key not in seen_symbols:
                seen_symbols.add(key)
                facts.symbols.append(symbol)
        if "imp" in captures:
            fact = _import_fact(_first(captures, "imp") or item, captures, path=path)
            if fact.module or fact.names:
                facts.imports.append(fact)
        if "http" in captures and item is not None:
            route = _route_fact(item, captures, path=path)
            if route is not None:
                facts.routes.append(route)
        if language == "sql" and item is not None and "table" in captures:
            facts.ddl.extend(_sql_item(item, captures, path=path))
        if language == "sql" and "col" in captures:
            facts.ddl.extend(_sql_column(captures, path=path))
    return facts


def _from_ast(source: str, *, path: str, extras: FileFacts | None = None) -> FileFacts:
    facts = extras or FileFacts(path=path, language="python")
    facts.language = "python"
    facts.path = path
    if facts.symbols:
        return facts
    for span in build_symbol_map(source):
        short = span.name.split(".")[-1]
        facts.symbols.append(
            SymbolFact(
                name=span.name,
                kind="method" if "." in span.name else "function",
                path=path,
                start_line=span.start,
                end_line=span.end,
                visibility="private" if short.startswith("_") else "public",
            )
        )
    return facts


def _symbol(item: Any, captures: dict[str, list[Any]], *, path: str, language: str) -> SymbolFact:
    name_node = _first(captures, "name")
    raw = _text(name_node) if name_node is not None else ""
    qualified = _qualify(item, raw, language=language)
    kind = _kind(item, qualified=qualified)
    return SymbolFact(
        name=qualified,
        kind=kind,
        path=path,
        start_line=_line(item),
        end_line=_end_line(item),
        visibility=_visibility(item, qualified, language=language),
        signature=_signature(item),
    )


def _qualify(item: Any, name: str, *, language: str) -> str:
    if language == "python":
        parent = _ancestor_name(item, {"class_definition"})
        if parent and item.type == "function_definition":
            return f"{parent}.{name}"
        return name
    if language in {"typescript", "tsx"}:
        parent = _ancestor_name(item, {"class_declaration"})
        if parent and item.type == "method_definition":
            return f"{parent}.{name}"
        return name
    if language == "go" and item.type == "method_declaration":
        recv = _go_receiver(item)
        return f"{recv}.{name}" if recv else name
    if language == "rust" and item.type == "function_item":
        parent = _rust_impl(item)
        if parent:
            return f"{parent}.{name}"
        return name
    return name


def _kind(item: Any, *, qualified: str) -> str:
    mapping = {
        "class_definition": "class",
        "class_declaration": "class",
        "function_definition": "method" if "." in qualified else "function",
        "function_declaration": "function",
        "function_item": "method" if "." in qualified else "function",
        "method_definition": "method",
        "method_declaration": "method",
        "lexical_declaration": "function",
        "type_declaration": "type",
        "struct_item": "type",
        "enum_item": "type",
    }
    return mapping.get(item.type, "function")


def _visibility(item: Any, name: str, *, language: str) -> str:
    short = name.split(".")[-1]
    if language == "python":
        return "private" if short.startswith("_") else "public"
    if language in {"typescript", "tsx"}:
        return "public" if _has_ancestor(item, {"export_statement"}) else "private"
    if language == "go":
        return "public" if short[:1].isupper() else "private"
    if language == "rust":
        return _rust_visibility(item)
    return "public"


def _import_fact(node: Any, captures: dict[str, list[Any]], *, path: str) -> ImportFact:
    module_node = _first(captures, "module")
    module = _unquote(_text(module_node)) if module_node is not None else ""
    names: list[str] = []
    if node is not None:
        text = _text(node).strip().rstrip(";")
        parsed_module, parsed_names = _parse_import_text(text)
        if not module:
            module = parsed_module
        names = parsed_names
    return ImportFact(path=path, line=_line(node), module=module, names=names)


def _parse_import_text(text: str) -> tuple[str, list[str]]:
    stripped = " ".join(text.split())
    if stripped.startswith("from "):
        rest = stripped[5:]
        if " import " in rest:
            module, names = rest.split(" import ", 1)
            return module.strip(), _split_names(names)
        return rest.strip(), []
    if stripped.startswith("import "):
        body = stripped[7:]
        if " from " in body:
            names, module = body.split(" from ", 1)
            return _unquote(module), _split_names(names)
        first = body.split(",", 1)[0].split(" as ", 1)[0].strip()
        return first, []
    if stripped.startswith("use "):
        body = stripped[4:].rstrip(";")
        parts = [part for part in body.replace("{", "").replace("}", "").split("::") if part]
        if len(parts) >= 2:
            return "::".join(parts[:-1]), _split_names(parts[-1])
        return body, []
    return stripped, []


def _split_names(raw: str) -> list[str]:
    cleaned = raw.replace("{", "").replace("}", "")
    names: list[str] = []
    for part in cleaned.split(","):
        token = part.split(" as ", 1)[0].strip().strip("'\"")
        if token and token != "*":
            names.append(token)
    return names


def _route_fact(item: Any, captures: dict[str, list[Any]], *, path: str) -> RouteFact | None:
    http = _text(_first(captures, "http")).lower()
    if http not in _HTTP:
        return None
    route = _unquote(_text(_first(captures, "path")))
    handler = _text(_first(captures, "handler"))
    if not handler:
        handler = _nearest_handler(item)
    method = "ANY" if http in {"handle", "handlefunc", "controller", "route"} else http.upper()
    return RouteFact(path=path, line=_line(item), method=method, route=route, handler=handler)


def _sql_item(item: Any, captures: dict[str, list[Any]], *, path: str) -> list[DdlFact]:
    table = _text(_first(captures, "table"))
    operation = {
        "create_table": "add_table",
        "drop_table": "drop_table",
        "alter_table": "alter",
    }.get(item.type, "other")
    if item.type == "alter_table":
        inner = [child.type for child in item.children]
        if "add_column" in inner:
            operation = "add_column"
        elif "drop_column" in inner:
            operation = "drop_column"
        elif "alter_column" in inner:
            operation = "alter_column"
        for child in item.children:
            if child.type == "drop_column":
                column = _sql_drop_column_name(child)
                return [
                    DdlFact(
                        path=path,
                        line=_line(item),
                        operation="drop_column",
                        table=table,
                        column=column,
                    )
                ]
            if child.type == "alter_column":
                return [
                    DdlFact(
                        path=path,
                        line=_line(item),
                        operation="alter_column",
                        table=table,
                        column=_sql_alter_column_name(child),
                        col_type=_sql_alter_column_type(child),
                    )
                ]
    if operation == "add_column":
        return []
    return [DdlFact(path=path, line=_line(item), operation=operation, table=table)]


def _sql_column(captures: dict[str, list[Any]], *, path: str) -> list[DdlFact]:
    col = _first(captures, "col")
    if col is None:
        return []
    column = _text(_first(captures, "column"))
    col_type = _text(_first(captures, "col_type"))
    table, operation = _sql_column_owner(col)
    if not table:
        return []
    text = _text(col)
    fk_table = ""
    fk_column = ""
    match = _FK_RE.search(text)
    if match:
        fk_table = match.group(1)
        fk_column = match.group(2)
    nullable: bool | None = None
    upper = text.upper()
    if "NOT NULL" in upper:
        nullable = False
    elif re.search(r"\bNULL\b", upper):
        nullable = True
    return [
        DdlFact(
            path=path,
            line=_line(col),
            operation=operation,
            table=table,
            column=column,
            col_type=col_type,
            nullable=nullable,
            fk_table=fk_table,
            fk_column=fk_column,
        )
    ]


def _sql_column_owner(col: Any) -> tuple[str, str]:
    current = col.parent
    while current is not None:
        if current.type == "create_table":
            table = _child_text(current, "object_reference")
            return table, "add_column"
        if current.type == "add_column":
            alter = current.parent
            table = _child_text(alter, "object_reference") if alter is not None else ""
            return table, "add_column"
        current = current.parent
    return "", "other"


def _sql_drop_column_name(node: Any) -> str:
    for child in node.children:
        if child.type == "identifier":
            return _text(child)
    return ""


def _sql_alter_column_name(node: Any) -> str:
    return _sql_drop_column_name(node)


def _sql_alter_column_type(node: Any) -> str:
    for child in reversed(list(node.children)):
        if child.type not in {"keyword_alter", "keyword_column", "keyword_type", "identifier"}:
            return _text(child)
    return ""


def _cap(facts: FileFacts) -> FileFacts:
    facts.symbols = facts.symbols[:MAX_SYMBOLS]
    facts.imports = facts.imports[:MAX_IMPORTS]
    facts.routes = facts.routes[:MAX_ROUTES]
    facts.ddl = facts.ddl[:MAX_DDL]
    return facts


def _first(captures: dict[str, list[Any]], key: str) -> Any | None:
    nodes = captures.get(key) or []
    return nodes[0] if nodes else None


def _text(node: Any | None) -> str:
    if node is None:
        return ""
    raw = getattr(node, "text", b"")
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] in {"'", '"', "`"} and text[-1] == text[0]:
        return text[1:-1]
    return text


def _line(node: Any | None) -> int:
    if node is None:
        return 0
    point = getattr(node, "start_point", (0, 0))
    return int(point[0]) + 1


def _end_line(node: Any | None) -> int:
    if node is None:
        return 0
    point = getattr(node, "end_point", (0, 0))
    return int(point[0]) + 1


def _signature(node: Any) -> str:
    line = _text(node).splitlines()[0].strip() if node is not None else ""
    return line[:_SIG_LIMIT]


def _ancestor_name(node: Any, types: set[str]) -> str:
    current = getattr(node, "parent", None)
    while current is not None:
        if current.type in types:
            name = current.child_by_field_name("name")
            if name is not None:
                return _text(name)
        current = current.parent
    return ""


def _has_ancestor(node: Any, types: set[str]) -> bool:
    current = getattr(node, "parent", None)
    while current is not None:
        if current.type in types:
            return True
        current = current.parent
    return False


def _go_receiver(item: Any) -> str:
    recv = item.child_by_field_name("receiver")
    if recv is None:
        return ""
    match = _GO_RECV_RE.search(_text(recv))
    return match.group(1) if match else ""


def _rust_impl(node: Any) -> str:
    current = getattr(node, "parent", None)
    while current is not None:
        if current.type == "impl_item":
            typed = current.child_by_field_name("type")
            return _text(typed) if typed is not None else ""
        current = current.parent
    return ""


def _rust_visibility(node: Any) -> str:
    for child in getattr(node, "children", []):
        if child.type == "visibility_modifier":
            text = _text(child)
            if "crate" in text:
                return "crate"
            return "public"
    return "private"


def _child_text(node: Any | None, node_type: str) -> str:
    if node is None:
        return ""
    for child in node.children:
        if child.type == node_type:
            return _text(child)
    return ""


def _nearest_handler(node: Any) -> str:
    current = getattr(node, "parent", None)
    while current is not None:
        if current.type in {
            "function_definition",
            "function_declaration",
            "function_item",
            "method_definition",
            "method_declaration",
        }:
            name = current.child_by_field_name("name")
            return _text(name) if name is not None else ""
        current = current.parent
    return ""

"""Resolver components used by GraphBuilder."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable

import networkx as nx


def split_csv_expressions(text: str) -> list[str]:
    """Split a comma-separated list while preserving nested expressions."""
    parts = []
    buff = []
    depth = 0
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(depth - 1, 0)
        if ch == "," and depth == 0:
            piece = "".join(buff).strip()
            if piece:
                parts.append(piece)
            buff = []
            continue
        buff.append(ch)
    tail = "".join(buff).strip()
    if tail:
        parts.append(tail)
    return parts


def rank_nodes_by_path_similarity(
    graph: nx.DiGraph,
    caller_file: str,
    candidate_ids: list[str],
) -> list[str]:
    """Rank candidate nodes by path-prefix overlap with the caller file."""
    caller_parts = Path(caller_file).parts
    caller_dir = str(Path(caller_file).parent)

    def overlap_score(target_file: str) -> tuple[int, int]:
        target_parts = Path(target_file).parts
        overlap = 0
        for left, right in zip(caller_parts, target_parts):
            if left != right:
                break
            overlap += 1
        same_dir = 1 if str(Path(target_file).parent) == caller_dir else 0
        return same_dir, overlap

    scored = []
    for node_id in candidate_ids:
        target_file = str(graph.nodes[node_id].get("file", ""))
        scored.append((overlap_score(target_file), node_id))
    scored.sort(key=lambda item: (-item[0][0], -item[0][1], item[1]))
    return [node_id for _, node_id in scored]


class ImportResolver:
    """Parses import statements and resolves import-derived targets."""

    def __init__(
        self,
        repo_path: Path,
        graph: nx.DiGraph,
        file_import_map: dict[str, dict[str, list[dict]]],
    ):
        self.repo_path = repo_path
        self.graph = graph
        self.file_import_map = file_import_map

    def record_import_edge(
        self,
        node_type: str,
        text: str,
        file_path: str,
        import_map: dict[str, list[dict]],
    ):
        if node_type == "import_from_statement":
            self.record_import_from_statement(text, file_path, import_map)
            return
        self.record_import_statement(text, file_path, import_map)

    def resolve_module(self, module_name: str, current_file: str) -> str | None:
        """Try to map a Python module name to a file path in the repo."""
        if module_name.startswith("."):
            current_dir = str(Path(current_file).parent)
            dots = len(module_name) - len(module_name.lstrip("."))
            rest = module_name.lstrip(".")
            base = current_dir
            for _ in range(dots - 1):
                base = str(Path(base).parent)
            if rest:
                candidate = os.path.join(base, rest.replace(".", "/"))
            else:
                candidate = base
        else:
            candidate = module_name.replace(".", "/")

        for suffix in [".py", "/__init__.py"]:
            path = candidate + suffix
            if (self.repo_path / path).exists():
                return path
        return None

    def record_import_statement(
        self,
        text: str,
        file_path: str,
        import_map: dict[str, list[dict]],
    ):
        """Parse 'import x [as y]' clauses into IMPORTS edges + import map."""
        normalized = " ".join(text.replace("\\\n", " ").split())
        match = re.match(r"^import\s+(.+)$", normalized)
        if not match:
            return

        for clause in split_csv_expressions(match.group(1)):
            item = clause.strip()
            if not item:
                continue
            if " as " in item:
                module_name, alias = [part.strip() for part in item.split(" as ", 1)]
            else:
                module_name = item
                alias = module_name.split(".", 1)[0]

            target_file = self.resolve_module(module_name, file_path)
            self.register_import_entry(
                import_map,
                alias,
                {
                    "kind": "module",
                    "module_name": module_name,
                    "target_file": target_file,
                    "target_node": None,
                },
            )
            if target_file and target_file in self.graph:
                self.graph.add_edge(file_path, target_file, type="IMPORTS")

    def record_import_from_statement(
        self,
        text: str,
        file_path: str,
        import_map: dict[str, list[dict]],
    ):
        """Parse 'from x import y [as z]' clauses into IMPORTS edges + import map."""
        normalized = " ".join(text.replace("\\\n", " ").split())
        match = re.match(r"^from\s+([.\w]+)\s+import\s+(.+)$", normalized)
        if not match:
            return

        module_name = match.group(1).strip()
        imported_clause = match.group(2).strip()
        if imported_clause.startswith("(") and imported_clause.endswith(")"):
            imported_clause = imported_clause[1:-1].strip()

        target_file = self.resolve_module(module_name, file_path)
        if target_file and target_file in self.graph:
            self.graph.add_edge(file_path, target_file, type="IMPORTS")

        for clause in split_csv_expressions(imported_clause):
            item = clause.strip()
            if not item:
                continue
            if item == "*":
                self.register_import_entry(
                    import_map,
                    "*",
                    {
                        "kind": "wildcard",
                        "module_name": module_name,
                        "target_file": target_file,
                        "target_node": None,
                    },
                )
                continue
            if " as " in item:
                symbol_name, alias = [part.strip() for part in item.split(" as ", 1)]
            else:
                symbol_name = item
                alias = symbol_name

            module_symbol_name = self._compose_from_import_module_name(module_name, symbol_name)
            module_target_file = self.resolve_module(module_symbol_name, file_path)
            if module_target_file:
                self.register_import_entry(
                    import_map,
                    alias,
                    {
                        "kind": "module",
                        "module_name": module_symbol_name,
                        "target_file": module_target_file,
                        "target_node": None,
                    },
                )
                if module_target_file in self.graph:
                    self.graph.add_edge(file_path, module_target_file, type="IMPORTS")
                continue

            candidate_node = f"{target_file}::{symbol_name}" if target_file else None
            self.register_import_entry(
                import_map,
                alias,
                {
                    "kind": "symbol",
                    "module_name": module_name,
                    "symbol_name": symbol_name,
                    "target_file": target_file,
                    "target_node": candidate_node,
                },
            )

    def _compose_from_import_module_name(self, module_name: str, symbol_name: str) -> str:
        if module_name.startswith("."):
            return f"{module_name}{symbol_name}"
        return f"{module_name}.{symbol_name}"

    def register_import_entry(
        self,
        import_map: dict[str, list[dict]],
        alias: str,
        entry: dict,
    ):
        """Track imports with deterministic Python name-binding semantics."""
        if not alias:
            return
        if alias == "*":
            entries = import_map.setdefault(alias, [])
            if entry not in entries:
                entries.append(entry)
            return
        if import_map.get(alias) == [entry]:
            return
        import_map[alias] = [entry]

    def resolve_import_targets(
        self,
        file_path: str,
        import_name: str,
        member_name: str | None = None,
    ) -> list[str]:
        """Resolve an imported alias/symbol to graph node ids."""
        import_map = self.file_import_map.get(file_path, {})
        entries = import_map.get(import_name, [])
        targets: list[str] = []
        for entry in entries:
            target_node = entry.get("target_node")
            target_file = entry.get("target_file")
            if member_name:
                if target_node and target_node in self.graph:
                    if self.graph.nodes[target_node].get("type") == "class":
                        class_candidate = f"{target_node}.{member_name}"
                        if class_candidate in self.graph:
                            targets.append(class_candidate)
                if target_file:
                    candidate = f"{target_file}::{member_name}"
                    if candidate in self.graph:
                        targets.append(candidate)
                continue

            if target_node and target_node in self.graph:
                targets.append(target_node)
                continue
            if entry.get("kind") == "module" and target_file:
                candidate = f"{target_file}::{import_name}"
                if candidate in self.graph:
                    targets.append(candidate)

        if member_name is None:
            for entry in import_map.get("*", []):
                target_file = entry.get("target_file")
                if target_file:
                    candidate = f"{target_file}::{import_name}"
                    if candidate in self.graph:
                        targets.append(candidate)
                    for nested in self.file_import_map.get(str(target_file), {}).get(import_name, []):
                        nested_target = nested.get("target_node")
                        if nested_target and nested_target in self.graph:
                            targets.append(nested_target)
                            continue
                        nested_file = nested.get("target_file")
                        nested_symbol = nested.get("symbol_name", import_name)
                        if nested_file:
                            nested_candidate = f"{nested_file}::{nested_symbol}"
                            if nested_candidate in self.graph:
                                targets.append(nested_candidate)

        seen = set()
        deduped = []
        for node_id in targets:
            if node_id in seen:
                continue
            seen.add(node_id)
            deduped.append(node_id)
        return deduped

    def resolve_base_class(
        self,
        *,
        base_expr: str,
        file_path: str,
        class_name_to_nodes: dict[str, list[str]],
        file_class_name_to_nodes: dict[tuple[str, str], list[str]],
        rank_nodes: Callable[[str, list[str]], list[str]],
    ) -> str | None:
        """Resolve one base-class expression to a class node id when possible."""
        expr = base_expr.strip()
        if not expr:
            return None

        def first_class(candidates: list[str]) -> str | None:
            for node_id in candidates:
                if self.graph.nodes[node_id].get("type") == "class":
                    return node_id
            return None

        if "." in expr:
            qualifier, _, member = expr.partition(".")
            member_name = member.split(".")[-1]
            imported = self.resolve_import_targets(file_path, qualifier, member_name=member_name)
            target = first_class(imported)
            if target:
                return target
            expr = member_name

        imported_symbol = self.resolve_import_targets(file_path, expr)
        target = first_class(imported_symbol)
        if target:
            return target

        same_file_targets = file_class_name_to_nodes.get((file_path, expr), [])
        target = first_class(same_file_targets)
        if target:
            return target

        global_targets = class_name_to_nodes.get(expr, [])
        if global_targets:
            ranked = rank_nodes(file_path, global_targets)
            return first_class(ranked)
        return None


class TypeInferenceEngine:
    """Very small local type-hint/constructor inference for call resolution."""

    _TYPING_NOISE = {
        "Any",
        "None",
        "Optional",
        "Union",
        "Literal",
        "Annotated",
        "Final",
        "ClassVar",
        "Self",
        "Type",
        "list",
        "dict",
        "set",
        "tuple",
    }

    def __init__(self, graph: nx.DiGraph, import_resolver: ImportResolver):
        self.graph = graph
        self.import_resolver = import_resolver

    def collect_local_type_hints(self, body_node) -> dict[str, str]:
        """Collect local variable -> type expression hints from assignments."""
        hints: dict[str, str] = {}

        def walk(node):
            if node.type == "assignment":
                left = node.child_by_field_name("left")
                if left and left.type == "identifier":
                    var_name = left.text.decode("utf-8")
                    type_node = node.child_by_field_name("type")
                    right = node.child_by_field_name("right")
                    type_expr = None
                    if type_node:
                        type_expr = self._extract_type_expression(type_node.text.decode("utf-8"))
                    elif right:
                        type_expr = self._extract_constructor_expression(right)
                    if var_name and type_expr:
                        hints[var_name] = type_expr
            for child in node.children:
                walk(child)

        walk(body_node)
        return hints

    def resolve_method_targets(
        self,
        *,
        file_path: str,
        qualifier: str,
        member_name: str,
        local_type_hints: dict[str, str],
        class_name_to_nodes: dict[str, list[str]],
        file_class_name_to_nodes: dict[tuple[str, str], list[str]],
        class_method_to_nodes: dict[tuple[str, str, str], list[str]],
        rank_nodes: Callable[[str, list[str]], list[str]],
    ) -> list[str]:
        """Resolve `qualifier.member()` against inferred qualifier class type."""
        class_nodes = self.resolve_qualifier_class_nodes(
            file_path=file_path,
            qualifier=qualifier,
            local_type_hints=local_type_hints,
            class_name_to_nodes=class_name_to_nodes,
            file_class_name_to_nodes=file_class_name_to_nodes,
            rank_nodes=rank_nodes,
        )
        targets: list[str] = []
        for class_node in class_nodes:
            class_data = self.graph.nodes[class_node]
            class_file = str(class_data.get("file", ""))
            class_name = str(class_data.get("name", ""))
            targets.extend(class_method_to_nodes.get((class_file, class_name, member_name), []))

        seen = set()
        deduped = []
        for node_id in targets:
            if node_id in seen:
                continue
            seen.add(node_id)
            deduped.append(node_id)
        return deduped

    def resolve_qualifier_class_nodes(
        self,
        *,
        file_path: str,
        qualifier: str,
        local_type_hints: dict[str, str],
        class_name_to_nodes: dict[str, list[str]],
        file_class_name_to_nodes: dict[tuple[str, str], list[str]],
        rank_nodes: Callable[[str, list[str]], list[str]],
    ) -> list[str]:
        """Resolve class nodes for a qualifier token or its inferred local binding."""
        expr = local_type_hints.get(qualifier, qualifier)
        return self.resolve_type_expression(
            file_path=file_path,
            expr=expr,
            class_name_to_nodes=class_name_to_nodes,
            file_class_name_to_nodes=file_class_name_to_nodes,
            rank_nodes=rank_nodes,
        )

    def resolve_type_expression(
        self,
        *,
        file_path: str,
        expr: str,
        class_name_to_nodes: dict[str, list[str]],
        file_class_name_to_nodes: dict[tuple[str, str], list[str]],
        rank_nodes: Callable[[str, list[str]], list[str]],
    ) -> list[str]:
        """Resolve a (possibly compound) type expression to class nodes."""
        candidates = re.findall(r"[A-Za-z_][\w.]*", expr or "")
        for token in candidates:
            if token in self._TYPING_NOISE:
                continue
            resolved = self._resolve_type_token(
                file_path=file_path,
                token=token,
                class_name_to_nodes=class_name_to_nodes,
                file_class_name_to_nodes=file_class_name_to_nodes,
                rank_nodes=rank_nodes,
            )
            if resolved:
                return resolved
        return []

    def _resolve_type_token(
        self,
        *,
        file_path: str,
        token: str,
        class_name_to_nodes: dict[str, list[str]],
        file_class_name_to_nodes: dict[tuple[str, str], list[str]],
        rank_nodes: Callable[[str, list[str]], list[str]],
    ) -> list[str]:
        def only_classes(node_ids: list[str]) -> list[str]:
            return [node_id for node_id in node_ids if self.graph.nodes[node_id].get("type") == "class"]

        if "." in token:
            qualifier, _, member = token.partition(".")
            imported = only_classes(
                self.import_resolver.resolve_import_targets(
                    file_path,
                    qualifier,
                    member_name=member.split(".")[-1],
                )
            )
            if imported:
                return imported
            token = member.split(".")[-1]

        imported_symbol = only_classes(self.import_resolver.resolve_import_targets(file_path, token))
        if imported_symbol:
            return imported_symbol

        same_file_targets = only_classes(file_class_name_to_nodes.get((file_path, token), []))
        if same_file_targets:
            return same_file_targets

        global_targets = only_classes(class_name_to_nodes.get(token, []))
        if global_targets:
            return rank_nodes(file_path, global_targets)
        return []

    def _extract_type_expression(self, raw_type: str) -> str:
        return raw_type.strip()

    def _extract_constructor_expression(self, node) -> str | None:
        if node.type != "call":
            return None
        func_node = node.child_by_field_name("function")
        if not func_node:
            return None
        if func_node.type == "identifier":
            return func_node.text.decode("utf-8")
        if func_node.type == "attribute":
            obj_node = func_node.child_by_field_name("object")
            attr_node = func_node.child_by_field_name("attribute")
            if attr_node:
                if obj_node and obj_node.type == "identifier":
                    return f"{obj_node.text.decode('utf-8')}.{attr_node.text.decode('utf-8')}"
                return attr_node.text.decode("utf-8")
        return None


class CallResolver:
    """Resolves raw call captures into CALLS edges."""

    def __init__(
        self,
        graph: nx.DiGraph,
        import_resolver: ImportResolver,
        type_inference_engine: TypeInferenceEngine,
        include_low_confidence_calls: bool = True,
    ):
        self.graph = graph
        self.import_resolver = import_resolver
        self.type_inference_engine = type_inference_engine
        self.include_low_confidence_calls = include_low_confidence_calls

    def resolve_calls(self):
        """Resolve calls using self, inferred type, local/import, then global heuristics."""
        name_to_nodes: dict[str, list[str]] = {}
        file_name_to_nodes: dict[tuple[str, str], list[str]] = {}
        file_top_level_name_to_nodes: dict[tuple[str, str], list[str]] = {}
        class_method_to_nodes: dict[tuple[str, str, str], list[str]] = {}
        class_name_to_nodes: dict[str, list[str]] = {}
        file_class_name_to_nodes: dict[tuple[str, str], list[str]] = {}
        for node_id, data in self.graph.nodes(data=True):
            node_type = data.get("type")
            if node_type == "function":
                name = str(data.get("name", ""))
                file_path = str(data.get("file", ""))
                parent_class = data.get("parent_class")
                if name:
                    name_to_nodes.setdefault(name, []).append(node_id)
                    file_name_to_nodes.setdefault((file_path, name), []).append(node_id)
                    if parent_class:
                        class_method_to_nodes.setdefault((file_path, str(parent_class), name), []).append(node_id)
                    else:
                        file_top_level_name_to_nodes.setdefault((file_path, name), []).append(node_id)
            elif node_type == "class":
                class_name = str(data.get("name", ""))
                file_path = str(data.get("file", ""))
                if class_name:
                    class_name_to_nodes.setdefault(class_name, []).append(node_id)
                    file_class_name_to_nodes.setdefault((file_path, class_name), []).append(node_id)

        for node_id, data in list(self.graph.nodes(data=True)):
            raw_calls = data.pop("_raw_calls", [])
            if not raw_calls:
                continue
            local_type_hints = data.pop("_local_type_hints", {})
            caller_file = str(data.get("file", ""))
            caller_class = str(data.get("parent_class", "")) if data.get("parent_class") else ""
            seen_calls: set[tuple[str, str]] = set()
            for raw_call in raw_calls:
                if isinstance(raw_call, dict):
                    call_name = str(raw_call.get("name", "")).strip()
                    qualifier = str(raw_call.get("qualifier", "")).strip()
                else:
                    call_name = str(raw_call).strip()
                    qualifier = ""
                if not call_name:
                    continue
                call_key = (call_name, qualifier)
                if call_key in seen_calls:
                    continue
                seen_calls.add(call_key)

                targets: list[str] = []
                confidence: str | None = None

                if qualifier == "self" and caller_class:
                    targets = list(class_method_to_nodes.get((caller_file, caller_class, call_name), []))
                    if targets:
                        confidence = "high"
                elif qualifier:
                    targets = self.type_inference_engine.resolve_method_targets(
                        file_path=caller_file,
                        qualifier=qualifier,
                        member_name=call_name,
                        local_type_hints=local_type_hints,
                        class_name_to_nodes=class_name_to_nodes,
                        file_class_name_to_nodes=file_class_name_to_nodes,
                        class_method_to_nodes=class_method_to_nodes,
                        rank_nodes=self._rank_nodes,
                    )
                    if targets:
                        confidence = "high"
                    if not targets:
                        targets = self.import_resolver.resolve_import_targets(
                            caller_file,
                            qualifier,
                            member_name=call_name,
                        )
                        if targets:
                            confidence = "high"
                else:
                    targets = list(file_top_level_name_to_nodes.get((caller_file, call_name), []))
                    if targets:
                        confidence = "high"
                    if not targets:
                        targets = list(file_name_to_nodes.get((caller_file, call_name), []))
                        if targets:
                            confidence = "medium"
                    if not targets:
                        targets = self.import_resolver.resolve_import_targets(caller_file, call_name)
                        if targets:
                            confidence = "high"

                if not targets:
                    global_targets = name_to_nodes.get(call_name, [])
                    if global_targets:
                        ranked = self._rank_nodes(caller_file, global_targets)
                        targets = ranked[:1]
                        if targets:
                            confidence = "low"

                if confidence == "low" and not self.include_low_confidence_calls:
                    continue
                for target_id in targets:
                    if target_id != node_id:
                        edge_attrs = {"type": "CALLS"}
                        if confidence:
                            edge_attrs["confidence"] = confidence
                        self.graph.add_edge(node_id, target_id, **edge_attrs)

    def _rank_nodes(self, caller_file: str, candidate_ids: list[str]) -> list[str]:
        return rank_nodes_by_path_similarity(self.graph, caller_file, candidate_ids)

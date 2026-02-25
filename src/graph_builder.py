"""
Graph Builder: Parse a Python repository into a knowledge graph using tree-sitter.

Produces a networkx DiGraph where:
  - Nodes: files, classes, functions (with metadata: signature, docstring, line range)
  - Edges: DEFINES, IMPORTS, CALLS, CONTAINS, INHERITS
Plus a FAISS vector index over node names + docstrings for fuzzy search.
"""

import json
from pathlib import Path

import faiss
import networkx as nx
import numpy as np
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

from src.resolvers import (
    CallResolver,
    ImportResolver,
    TypeInferenceEngine,
    rank_nodes_by_path_similarity,
    split_csv_expressions,
)

PY_LANGUAGE = Language(tspython.language())


class GraphBuilder:
    def __init__(
        self,
        repo_path: str,
        include_prefixes: tuple[str, ...] | None = None,
        include_low_confidence_calls: bool = True,
    ):
        self.repo_path = Path(repo_path)
        self.graph = nx.DiGraph()
        self.parser = Parser(PY_LANGUAGE)
        self.include_prefixes = tuple(
            prefix.rstrip("/") for prefix in (include_prefixes or ())
        )
        self.include_low_confidence_calls = include_low_confidence_calls
        self.file_import_map: dict[str, dict[str, list[dict]]] = {}
        self.import_resolver = ImportResolver(
            repo_path=self.repo_path,
            graph=self.graph,
            file_import_map=self.file_import_map,
        )
        self.type_inference_engine = TypeInferenceEngine(
            graph=self.graph,
            import_resolver=self.import_resolver,
        )
        self.call_resolver = CallResolver(
            graph=self.graph,
            import_resolver=self.import_resolver,
            type_inference_engine=self.type_inference_engine,
            include_low_confidence_calls=self.include_low_confidence_calls,
        )

    def build(self) -> nx.DiGraph:
        """Walk all .py files in the repo and build the knowledge graph."""
        self.graph = nx.DiGraph()
        self.import_resolver.graph = self.graph
        self.import_resolver.file_import_map = self.file_import_map
        self.type_inference_engine.graph = self.graph
        self.call_resolver.graph = self.graph
        self.file_import_map.clear()
        py_files = sorted(self.repo_path.rglob("*.py"))
        valid_files = []
        for py_file in py_files:
            rel_path = str(py_file.relative_to(self.repo_path))
            if any(part.startswith(".") for part in py_file.parts):
                continue
            if not self._is_included(rel_path):
                continue
            valid_files.append((rel_path, py_file))

        # Pass 1: Add all file nodes so import resolution can find targets
        for rel_path, py_file in valid_files:
            self.graph.add_node(rel_path, type="file", docstring="")

        # Pass 2: Parse each file for definitions, imports, and calls
        for rel_path, py_file in valid_files:
            try:
                source = py_file.read_bytes()
                self._parse_file(rel_path, source)
            except Exception as e:
                print(f"  Warning: failed to parse {rel_path}: {e}")

        # Resolve inheritance and call edges once all nodes are known.
        self._resolve_inheritance()
        self._resolve_calls()
        return self.graph

    def update_files(self, changed_paths: list[str]) -> nx.DiGraph:
        """Incremental-update interface (current strategy: conservative full rebuild)."""
        _ = changed_paths
        return self.build()

    def recompute_edges_for(self, changed_nodes: list[str], strategy: str = "full") -> nx.DiGraph:
        """Edge recomputation interface; currently rebuilds for deterministic parity."""
        _ = changed_nodes
        if strategy not in {"full", "conservative"}:
            raise ValueError(f"Unsupported recompute strategy: {strategy}")
        return self.build()

    def _is_included(self, rel_path: str) -> bool:
        """Check whether a file should be indexed based on include prefixes."""
        if not self.include_prefixes:
            return True
        return any(
            rel_path == prefix or rel_path.startswith(prefix + "/")
            for prefix in self.include_prefixes
        )

    def _parse_file(self, rel_path: str, source: bytes):
        """Parse a single Python file and add nodes/edges to the graph."""
        tree = self.parser.parse(source)
        root = tree.root_node
        import_map: dict[str, list[dict]] = {}
        self.file_import_map[rel_path] = import_map

        # Update file node with docstring (node was pre-added in build())
        file_docstring = self._extract_module_docstring(root, source)
        self.graph.nodes[rel_path]["docstring"] = file_docstring or ""

        # Walk top-level definitions
        for child in root.children:
            if child.type == "function_definition":
                self._add_function_node(child, source, rel_path, parent_class=None)
            elif child.type == "decorated_definition":
                inner = self._get_decorated_inner(child)
                if inner and inner.type == "function_definition":
                    self._add_function_node(inner, source, rel_path, parent_class=None)
                elif inner and inner.type == "class_definition":
                    self._add_class_node(inner, source, rel_path)
            elif child.type == "class_definition":
                self._add_class_node(child, source, rel_path)
            elif child.type == "import_statement" or child.type == "import_from_statement":
                self._add_import_edge(child, source, rel_path, import_map)

    def _add_function_node(self, node, source: bytes, file_path: str, parent_class: str | None):
        """Add a function/method node to the graph."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        func_name = name_node.text.decode("utf-8")
        params_node = node.child_by_field_name("parameters")
        signature = params_node.text.decode("utf-8") if params_node else "()"
        body_node = node.child_by_field_name("body")
        docstring = self._extract_docstring(body_node, source) if body_node else ""

        # Collect call expressions inside this function body
        calls = []
        local_type_hints: dict[str, str] = {}
        if body_node:
            self._collect_calls(body_node, calls)
            local_type_hints = self.type_inference_engine.collect_local_type_hints(body_node)

        if parent_class:
            node_id = f"{file_path}::{parent_class}.{func_name}"
        else:
            node_id = f"{file_path}::{func_name}"

        self.graph.add_node(
            node_id,
            type="function",
            name=func_name,
            signature=signature,
            docstring=docstring or "",
            file=file_path,
            parent_class=parent_class,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            _raw_calls=calls,  # resolved later
            _local_type_hints=local_type_hints,
        )

        # Edge: file/class DEFINES function
        if parent_class:
            parent_id = f"{file_path}::{parent_class}"
            self.graph.add_edge(parent_id, node_id, type="CONTAINS")
        else:
            self.graph.add_edge(file_path, node_id, type="DEFINES")

    def _add_class_node(self, node, source: bytes, file_path: str):
        """Add a class node and its methods to the graph."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        class_name = name_node.text.decode("utf-8")
        body_node = node.child_by_field_name("body")
        docstring = self._extract_docstring(body_node, source) if body_node else ""

        node_id = f"{file_path}::{class_name}"
        self.graph.add_node(
            node_id,
            type="class",
            name=class_name,
            docstring=docstring or "",
            file=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            _raw_bases=self._extract_class_bases(node),
        )
        self.graph.add_edge(file_path, node_id, type="DEFINES")

        # Parse methods inside the class body
        if body_node:
            for child in body_node.children:
                if child.type == "function_definition":
                    self._add_function_node(child, source, file_path, parent_class=class_name)
                elif child.type == "decorated_definition":
                    inner = self._get_decorated_inner(child)
                    if inner and inner.type == "function_definition":
                        self._add_function_node(inner, source, file_path, parent_class=class_name)

    def _add_import_edge(self, node, source: bytes, file_path: str, import_map: dict[str, list[dict]]):
        """Add IMPORTS edges based on import statements."""
        self.import_resolver.record_import_edge(
            node_type=node.type,
            text=node.text.decode("utf-8"),
            file_path=file_path,
            import_map=import_map,
        )

    def _resolve_module(self, module_name: str, current_file: str) -> str | None:
        return self.import_resolver.resolve_module(module_name, current_file)

    def _record_import_statement(self, text: str, file_path: str, import_map: dict[str, list[dict]]):
        self.import_resolver.record_import_statement(text, file_path, import_map)

    def _record_import_from_statement(self, text: str, file_path: str, import_map: dict[str, list[dict]]):
        self.import_resolver.record_import_from_statement(text, file_path, import_map)

    def _register_import_entry(self, import_map: dict[str, list[dict]], alias: str, entry: dict):
        self.import_resolver.register_import_entry(import_map, alias, entry)

    def _split_csv_expressions(self, text: str) -> list[str]:
        return split_csv_expressions(text)

    def _collect_calls(self, node, calls: list):
        """Recursively collect function call names from an AST subtree."""
        if node.type == "call":
            func_node = node.child_by_field_name("function")
            if func_node:
                call_text = func_node.text.decode("utf-8")
                call_name = ""
                qualifier = ""
                if func_node.type == "attribute":
                    attr_node = func_node.child_by_field_name("attribute")
                    obj_node = func_node.child_by_field_name("object")
                    call_name = attr_node.text.decode("utf-8") if attr_node else call_text.split(".")[-1]
                    obj_text = obj_node.text.decode("utf-8") if obj_node else ""
                    qualifier = obj_text.split(".", 1)[0] if obj_text else ""
                elif func_node.type == "identifier":
                    call_name = call_text
                else:
                    parts = call_text.split(".")
                    call_name = parts[-1]
                    qualifier = parts[0] if len(parts) > 1 else ""

                if call_name:
                    calls.append({
                        "name": call_name,
                        "qualifier": qualifier,
                    })
        for child in node.children:
            self._collect_calls(child, calls)

    def _resolve_inheritance(self):
        """Resolve stored superclass names into INHERITS edges."""
        class_name_to_nodes: dict[str, list[str]] = {}
        file_class_name_to_nodes: dict[tuple[str, str], list[str]] = {}
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") != "class":
                continue
            name = str(data.get("name", ""))
            file_path = str(data.get("file", ""))
            if name:
                class_name_to_nodes.setdefault(name, []).append(node_id)
                file_class_name_to_nodes.setdefault((file_path, name), []).append(node_id)

        for node_id, data in list(self.graph.nodes(data=True)):
            if data.get("type") != "class":
                continue
            raw_bases = data.pop("_raw_bases", [])
            file_path = str(data.get("file", ""))
            for base_expr in raw_bases:
                target = self._resolve_base_class(
                    base_expr=base_expr,
                    file_path=file_path,
                    class_name_to_nodes=class_name_to_nodes,
                    file_class_name_to_nodes=file_class_name_to_nodes,
                )
                if target and target != node_id:
                    self.graph.add_edge(node_id, target, type="INHERITS")

    def _extract_class_bases(self, node) -> list[str]:
        """Extract base class expressions from a class_definition node."""
        super_node = node.child_by_field_name("superclasses")
        if not super_node:
            return []
        raw = super_node.text.decode("utf-8").strip()
        if raw.startswith("(") and raw.endswith(")"):
            raw = raw[1:-1].strip()
        if not raw:
            return []
        bases = []
        for expr in self._split_csv_expressions(raw):
            candidate = expr.strip()
            if not candidate:
                continue
            # Strip generic type params, e.g. Base[T] -> Base.
            candidate = candidate.split("[", 1)[0].strip()
            if candidate:
                bases.append(candidate)
        return bases

    def _resolve_base_class(
        self,
        *,
        base_expr: str,
        file_path: str,
        class_name_to_nodes: dict[str, list[str]],
        file_class_name_to_nodes: dict[tuple[str, str], list[str]],
    ) -> str | None:
        return self.import_resolver.resolve_base_class(
            base_expr=base_expr,
            file_path=file_path,
            class_name_to_nodes=class_name_to_nodes,
            file_class_name_to_nodes=file_class_name_to_nodes,
            rank_nodes=self._rank_nodes_by_path_similarity,
        )

    def _resolve_calls(self):
        self.call_resolver.resolve_calls()

    def _resolve_import_targets(self, file_path: str, import_name: str, member_name: str | None = None) -> list[str]:
        return self.import_resolver.resolve_import_targets(file_path, import_name, member_name=member_name)

    def _rank_nodes_by_path_similarity(self, caller_file: str, candidate_ids: list[str]) -> list[str]:
        return rank_nodes_by_path_similarity(self.graph, caller_file, candidate_ids)

    def _extract_module_docstring(self, root_node, source: bytes) -> str | None:
        """Extract the module-level docstring (first expression statement that is a string)."""
        for child in root_node.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type == "string":
                        return self._clean_docstring(sub.text.decode("utf-8"))
                break  # only check the very first statement
            elif child.type in ("comment",):
                continue
            else:
                break
        return None

    def _extract_docstring(self, body_node, source: bytes) -> str | None:
        """Extract docstring from the first statement in a function/class body."""
        for child in body_node.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type == "string":
                        return self._clean_docstring(sub.text.decode("utf-8"))
                return None
            elif child.type in ("comment",):
                continue
            else:
                return None
        return None

    def _clean_docstring(self, raw: str) -> str:
        """Strip triple-quote markers and normalize whitespace."""
        for quote in ('"""', "'''", '"', "'"):
            if raw.startswith(quote) and raw.endswith(quote):
                raw = raw[len(quote):-len(quote)]
                break
        return raw.strip()

    def _get_decorated_inner(self, node):
        """Get the actual definition inside a decorated_definition node."""
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                return child
        return None

    def save(self, path: str):
        """Serialize the graph to JSON."""
        data = {
            "nodes": [],
            "edges": [],
        }
        for node_id, attrs in self.graph.nodes(data=True):
            entry = {"id": node_id}
            entry.update({k: v for k, v in attrs.items() if not k.startswith("_")})
            data["nodes"].append(entry)
        for src, dst, attrs in self.graph.edges(data=True):
            data["edges"].append({"source": src, "target": dst, **attrs})
        Path(path).write_text(json.dumps(data, indent=2))

    def load(self, path: str) -> nx.DiGraph:
        """Load graph from JSON."""
        data = json.loads(Path(path).read_text())
        self.graph = nx.DiGraph()
        self.import_resolver.graph = self.graph
        self.type_inference_engine.graph = self.graph
        self.call_resolver.graph = self.graph
        for node in data["nodes"]:
            node_id = node.pop("id")
            self.graph.add_node(node_id, **node)
        for edge in data["edges"]:
            src = edge.pop("source")
            dst = edge.pop("target")
            self.graph.add_edge(src, dst, **edge)
        return self.graph


class GraphIndex:
    """FAISS vector index over graph node names and docstrings."""

    def __init__(self, graph: nx.DiGraph, gemini_client):
        self.graph = graph
        self.client = gemini_client
        self.index = None
        self.node_ids: list[str] = []
        self.node_texts: list[str] = []
        self.embedding_tokens_estimate = 0

    def build(self):
        """Embed all function/class nodes and build FAISS index."""
        texts = []
        node_ids = []

        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") not in ("function", "class"):
                continue
            name = data.get("name", "")
            docstring = data.get("docstring", "")
            signature = data.get("signature", "")
            text = f"{name}"
            if signature and data.get("type") == "function":
                text += f"{signature}"
            if docstring:
                text += f": {docstring[:200]}"
            texts.append(text)
            node_ids.append(node_id)

        if not texts:
            print("  Warning: no nodes to index")
            return

        self.node_ids = node_ids
        self.node_texts = texts
        # Estimate embedding tokens (~4 chars per token)
        self.embedding_tokens_estimate = sum(len(t) for t in texts) // 4

        # Batch embed (Gemini allows up to 100 texts per request)
        from src.api_retry import embed_with_retry

        all_embeddings = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            from google.genai import types
            result = embed_with_retry(
                lambda b=batch: self.client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=b,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=768,
                    ),
                )
            )
            for emb in result.embeddings:
                all_embeddings.append(emb.values)

        embeddings = np.array(all_embeddings, dtype=np.float32)
        # Normalize for cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1
        embeddings = embeddings / norms

        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(embeddings)
        print(f"  Indexed {len(node_ids)} nodes ({self.embedding_tokens_estimate} est. embedding tokens)")

    def search(self, query: str, top_k: int = 10) -> dict:
        """Search the index for nodes matching a query."""
        if self.index is None:
            return {"results": [], "query_embedding_tokens": 0}

        from google.genai import types
        from src.api_retry import embed_with_retry
        query_embedding_tokens = max(len(query.strip()) // 4, 0) if query else 0
        result = embed_with_retry(
            lambda: self.client.models.embed_content(
                model="gemini-embedding-001",
                contents=[query],
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY",
                    output_dimensionality=768,
                ),
            )
        )
        query_emb = np.array([result.embeddings[0].values], dtype=np.float32)
        query_emb = query_emb / np.linalg.norm(query_emb)

        k = min(top_k, len(self.node_ids))
        scores, indices = self.index.search(query_emb, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            node_id = self.node_ids[idx]
            data = self.graph.nodes[node_id]
            results.append({
                "node_id": node_id,
                "name": data.get("name", ""),
                "type": data.get("type", ""),
                "file": data.get("file", node_id),
                "docstring": data.get("docstring", "")[:200],
                "signature": data.get("signature", ""),
                "score": float(score),
            })
        return {
            "results": results,
            "query_embedding_tokens": query_embedding_tokens,
        }

    def save(self, path: str):
        """Save the FAISS index and metadata."""
        base = Path(path)
        if self.index is not None:
            faiss.write_index(self.index, str(base.with_suffix(".faiss")))
        meta = {"node_ids": self.node_ids, "node_texts": self.node_texts}
        base.with_suffix(".meta.json").write_text(json.dumps(meta))

    def load(self, path: str):
        """Load the FAISS index and metadata."""
        base = Path(path)
        self.index = faiss.read_index(str(base.with_suffix(".faiss")))
        meta = json.loads(base.with_suffix(".meta.json").read_text())
        self.node_ids = meta["node_ids"]
        self.node_texts = meta["node_texts"]

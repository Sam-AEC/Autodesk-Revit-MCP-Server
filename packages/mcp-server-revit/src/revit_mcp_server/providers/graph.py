from __future__ import annotations

from itertools import combinations
from math import isfinite
from typing import Any, Dict, List, Optional, Sequence

from .base import AECProvider, ProviderTool


RELATION_TYPES = {
    "CONTAINED_IN",
    "SUPPORTED_BY",
    "CONNECTED_TO",
    "ADJACENT_TO",
    "HAS_MATERIAL",
}

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class SemanticGraphProvider(AECProvider):
    def __init__(self) -> None:
        # networkx is imported lazily so a cold start that never touches the
        # graph tools does not pay for it; the graph is built on first use.
        self._graph_obj: Any = None
        self._init_capabilities()

    @property
    def _graph(self) -> Any:
        if self._graph_obj is None:
            import networkx as nx

            self._graph_obj = nx.MultiDiGraph()
        return self._graph_obj

    @_graph.setter
    def _graph(self, value: Any) -> None:
        self._graph_obj = value

    @property
    def graph(self) -> Any:
        """Access the underlying NetworkX MultiDiGraph instance."""
        return self._graph

    def get_identity(self) -> str:
        return "graph"

    def get_capabilities(self) -> List[ProviderTool]:
        return self._capabilities

    async def check_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "provider": "graph",
            "nodes": self._graph.number_of_nodes(),
            "edges": self._graph.number_of_edges(),
            "relation_counts": self._relation_counts(),
        }

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = name.replace(".", "_")
        if tool_name == "graph_health":
            return await self.check_health()
        if tool_name == "graph_compile":
            return self._compile(arguments)
        if tool_name == "graph_add_relation":
            return self._add_relation(arguments)
        if tool_name == "graph_query_relations":
            return self._query_relations(arguments)
        if tool_name == "graph_audit_clashes":
            return self._audit_clashes(arguments)
        if tool_name == "graph_audit_disconnected":
            return self._audit_disconnected(arguments)
        if tool_name == "graph_audit_structural_loads":
            return self._audit_structural_loads(arguments)
        raise ValueError(f"Unknown graph tool '{name}'")

    def _init_capabilities(self) -> None:
        self._capabilities = [
            ProviderTool(
                name="graph_health",
                description="Check graph provider health and current graph size.",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            ProviderTool(
                name="graph_compile",
                description="Compile workspace model nodes and relations into the in-memory semantic graph.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "nodes": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Generic node payloads with id, type, attributes, and optional aabb data.",
                        },
                        "edges": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Generic edge payloads with source, target, relation, and optional attributes.",
                        },
                        "allow_dangling_edges": {
                            "type": "boolean",
                            "default": False,
                            "description": "If true, create placeholder nodes for edge endpoints that are missing from the payload.",
                        },
                        "replace": {
                            "type": "boolean",
                            "default": True,
                            "description": "If true, replace the existing graph atomically. If false, merge into a copied graph.",
                        },
                    },
                    "required": ["nodes", "edges"],
                },
            ),
            ProviderTool(
                name="graph_add_relation",
                description="Add a typed relation between two existing nodes.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string"},
                        "target_id": {"type": "string"},
                        "relation": {
                            "type": "string",
                            "enum": sorted(RELATION_TYPES),
                        },
                        "attributes": {"type": "object"},
                    },
                    "required": ["source_id", "target_id", "relation"],
                },
            ),
            ProviderTool(
                name="graph_query_relations",
                description="Query relations by node, related node, relation type, and direction.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string"},
                        "related_node_id": {"type": "string"},
                        "relation": {
                            "type": "string",
                            "enum": sorted(RELATION_TYPES),
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["outgoing", "incoming", "both"],
                            "default": "both",
                        },
                        "limit": {
                            "type": "integer",
                            "default": DEFAULT_LIMIT,
                        },
                    },
                    "required": [],
                },
            ),
            ProviderTool(
                name="graph_audit_clashes",
                description="Audit axis-aligned bounding boxes for clashes using a tolerance value.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "nodes": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Optional node payloads with id and aabb data. If omitted, use graph nodes with stored aabb attributes.",
                        },
                        "node_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "tolerance": {
                            "type": "number",
                            "default": 0.0,
                        },
                        "limit": {
                            "type": "integer",
                            "default": DEFAULT_LIMIT,
                        },
                    },
                    "required": [],
                },
            ),
            ProviderTool(
                name="graph_audit_disconnected",
                description="Audit disconnected nodes or components using degree and connectivity rules.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "node_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "node_types": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "relation_types": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": sorted(RELATION_TYPES),
                            },
                        },
                        "min_degree": {
                            "type": "integer",
                            "default": 1,
                        },
                        "limit": {
                            "type": "integer",
                            "default": DEFAULT_LIMIT,
                        },
                    },
                    "required": [],
                },
            ),
            ProviderTool(
                name="graph_audit_structural_loads",
                description="Audit structural load-bearing and support consistency using SUPPORTED_BY relations.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "node_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "node_types": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "limit": {
                            "type": "integer",
                            "default": DEFAULT_LIMIT,
                        },
                    },
                    "required": [],
                },
            ),
        ]

    def _compile(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_nodes = arguments.get("nodes", [])
        raw_edges = arguments.get("edges", [])
        if not isinstance(raw_nodes, list):
            raise ValueError("Argument 'nodes' must be a list.")
        if not isinstance(raw_edges, list):
            raise ValueError("Argument 'edges' must be a list.")
        allow_dangling_edges = bool(arguments.get("allow_dangling_edges", False))
        replace = bool(arguments.get("replace", True))

        node_records = [self._normalize_node_payload(node) for node in raw_nodes]
        edge_records = [self._normalize_edge_payload(edge) for edge in raw_edges]

        seen_node_ids: set[str] = set()
        for node in node_records:
            if node["id"] in seen_node_ids:
                raise ValueError(f"Duplicate node id '{node['id']}' in compile payload.")
            seen_node_ids.add(node["id"])

        base_node_ids = set(self._graph.nodes) if not replace else set()
        missing_edge_nodes = []
        for edge in edge_records:
            for endpoint in (edge["source_id"], edge["target_id"]):
                if endpoint not in seen_node_ids and endpoint not in base_node_ids:
                    missing_edge_nodes.append(endpoint)

        if missing_edge_nodes and not allow_dangling_edges:
            unique_missing = sorted(set(missing_edge_nodes))
            raise ValueError(
                "Dangling edges reference missing node ids: " + ", ".join(unique_missing)
            )

        import networkx as nx

        staged = nx.MultiDiGraph() if replace else self._graph.copy(as_view=False)

        for node in node_records:
            staged.add_node(node["id"], **node["attributes"])

        for edge in edge_records:
            if allow_dangling_edges:
                for endpoint in (edge["source_id"], edge["target_id"]):
                    if endpoint not in staged:
                        staged.add_node(endpoint, placeholder=True)
            else:
                if edge["source_id"] not in staged or edge["target_id"] not in staged:
                    raise ValueError(
                        f"Dangling edge '{edge['relation']}' references missing node(s)."
                    )
            staged.add_edge(
                edge["source_id"],
                edge["target_id"],
                relation=edge["relation"],
                **edge["attributes"],
            )

        self._graph = staged
        return {
            "status": "success",
            "compiled": {
                "nodes_received": len(node_records),
                "edges_received": len(edge_records),
                "nodes_total": self._graph.number_of_nodes(),
                "edges_total": self._graph.number_of_edges(),
            },
        }

    def _add_relation(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        source_id = self._normalize_node_id(
            arguments.get("source_id", arguments.get("source"))
        )
        target_id = self._normalize_node_id(
            arguments.get("target_id", arguments.get("target"))
        )
        relation = self._normalize_relation(
            arguments.get("relation", arguments.get("relation_type", arguments.get("type")))
        )
        attributes = arguments.get("attributes", {})
        if not isinstance(attributes, dict):
            raise ValueError("Relation attributes must be an object if provided.")
        attributes = self._normalize_json_safe(attributes)

        self._require_node(source_id)
        self._require_node(target_id)

        edge_key = self._graph.add_edge(source_id, target_id, relation=relation, **attributes)
        return {
            "status": "success",
            "relation": {
                "source_id": source_id,
                "target_id": target_id,
                "relation": relation,
                "edge_key": edge_key,
                "attributes": self._normalize_json_safe(attributes),
            },
        }

    def _query_relations(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        node_id = self._normalize_optional_node_id(arguments.get("node_id"))
        related_node_id = self._normalize_optional_node_id(arguments.get("related_node_id"))
        relation = self._normalize_optional_relation(arguments.get("relation"))
        direction = arguments.get("direction", "both")
        limit = self._bounded_limit(arguments.get("limit", DEFAULT_LIMIT))

        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError("Direction must be one of: outgoing, incoming, both.")
        if "node_id" in arguments and not isinstance(arguments.get("node_id"), (str, int, type(None))):
            raise ValueError("Argument 'node_id' must be a string or integer if provided.")
        if "related_node_id" in arguments and not isinstance(arguments.get("related_node_id"), (str, int, type(None))):
            raise ValueError("Argument 'related_node_id' must be a string or integer if provided.")
        if node_id is not None:
            self._require_node(node_id)
        if related_node_id is not None:
            self._require_node(related_node_id)

        edges = []
        for source_id, target_id, edge_key, data in self._graph.edges(keys=True, data=True):
            rel = self._normalize_relation(data.get("relation", ""))
            if relation is not None and rel != relation:
                continue

            if direction == "outgoing" and node_id is not None and source_id != node_id:
                continue
            if direction == "incoming" and node_id is not None and target_id != node_id:
                continue
            if direction == "both" and node_id is not None and node_id not in {source_id, target_id}:
                continue

            if related_node_id is not None and related_node_id not in {source_id, target_id}:
                continue

            edges.append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation": rel,
                    "edge_key": edge_key,
                    "attributes": self._normalize_json_safe(
                        {k: v for k, v in data.items() if k != "relation"}
                    ),
                }
            )

        edges = self._sort_relation_records(edges)
        total = len(edges)
        return {
            "status": "success",
            "relations": edges[:limit],
            "count": min(total, limit),
            "total": total,
            "truncated": total > limit,
        }

    def _audit_clashes(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tolerance = self._normalize_number(arguments.get("tolerance", 0.0))
        limit = self._bounded_limit(arguments.get("limit", DEFAULT_LIMIT))
        raw_nodes = arguments.get("nodes")
        node_ids = arguments.get("node_ids")
        if raw_nodes is not None and not isinstance(raw_nodes, list):
            raise ValueError("Argument 'nodes' must be a list when provided.")
        if node_ids is not None and not isinstance(node_ids, list):
            raise ValueError("Argument 'node_ids' must be a list when provided.")

        records = self._collect_aabb_records(raw_nodes, node_ids)
        clashes = []
        for first, second in combinations(records, 2):
            if self._aabbs_clash(first["aabb"], second["aabb"], tolerance):
                clashes.append(
                    {
                        "node_a": first["id"],
                        "node_b": second["id"],
                        "aabb_a": first["aabb"],
                        "aabb_b": second["aabb"],
                    }
                )

        clashes = sorted(clashes, key=lambda item: (item["node_a"], item["node_b"]))
        total = len(clashes)
        return {
            "status": "success",
            "tolerance": tolerance,
            "clashes": clashes[:limit],
            "count": min(total, limit),
            "total": total,
            "truncated": total > limit,
        }

    def _audit_disconnected(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        limit = self._bounded_limit(arguments.get("limit", DEFAULT_LIMIT))
        min_degree = self._normalize_int(arguments.get("min_degree", 1), minimum=0)
        node_ids = self._normalize_optional_node_id_list(arguments.get("node_ids"))
        node_types = self._normalize_string_list(arguments.get("node_types"))
        relation_types = self._normalize_relation_list(arguments.get("relation_types"))

        selected_nodes = self._select_nodes(node_ids=node_ids, node_types=node_types)
        if not selected_nodes:
            return {
                "status": "success",
                "selected_nodes": 0,
                "disconnected_nodes": [],
                "components": [],
                "count": 0,
                "total": 0,
                "truncated": False,
            }

        import networkx as nx

        filtered = nx.Graph()
        filtered.add_nodes_from(selected_nodes)

        for source_id, target_id, data in self._graph.edges(data=True):
            rel = self._normalize_relation(data.get("relation", ""))
            if relation_types is not None and rel not in relation_types:
                continue
            if source_id not in selected_nodes or target_id not in selected_nodes:
                continue
            filtered.add_edge(source_id, target_id, relation=rel)

        disconnected_nodes = sorted(
            node_id
            for node_id in filtered.nodes
            if filtered.degree(node_id) < min_degree
        )
        components = [
            sorted(component)
            for component in nx.connected_components(filtered)
        ]
        components.sort(key=lambda component: (len(component), component))

        return {
            "status": "success",
            "selected_nodes": len(selected_nodes),
            "min_degree": min_degree,
            "relation_types": sorted(relation_types) if relation_types is not None else sorted(RELATION_TYPES),
            "disconnected_nodes": disconnected_nodes[:limit],
            "components": components[:limit],
            "count": min(len(disconnected_nodes), limit),
            "total": len(disconnected_nodes),
            "truncated": len(disconnected_nodes) > limit,
        }

    def _audit_structural_loads(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        limit = self._bounded_limit(arguments.get("limit", DEFAULT_LIMIT))
        node_ids = self._normalize_optional_node_id_list(arguments.get("node_ids"))
        node_types = self._normalize_string_list(arguments.get("node_types"))
        selected_nodes = self._select_nodes(node_ids=node_ids, node_types=node_types)
        node_issues = []
        edge_issues = []

        supported_by_edges = [
            (source_id, target_id, data)
            for source_id, target_id, data in self._graph.edges(data=True)
            if self._normalize_relation(data.get("relation", "")) == "SUPPORTED_BY"
        ]

        outgoing_supported_by: Dict[str, List[str]] = {}
        for source_id, target_id, _data in supported_by_edges:
            outgoing_supported_by.setdefault(source_id, []).append(target_id)

        for node_id in sorted(selected_nodes):
            attrs = self._normalize_json_safe(dict(self._graph.nodes[node_id]))
            requires_support = bool(attrs.get("requires_support", False))
            load_bearing = attrs.get("load_bearing")
            is_support = bool(attrs.get("is_support", False))

            supports = sorted(set(outgoing_supported_by.get(node_id, [])))
            if requires_support and not supports:
                node_issues.append(
                    {
                        "node_id": node_id,
                        "issue": "missing_support",
                        "message": "Node is marked as requiring support but has no SUPPORTED_BY relation.",
                    }
                )
            if load_bearing is False and supports:
                node_issues.append(
                    {
                        "node_id": node_id,
                        "issue": "support_target_not_load_bearing",
                        "message": "Node has outgoing SUPPORTED_BY relations but is marked as not load-bearing.",
                    }
                )
            if is_support and load_bearing is False:
                node_issues.append(
                    {
                        "node_id": node_id,
                        "issue": "support_flag_conflict",
                        "message": "Node is marked as a support but explicitly not load-bearing.",
                    }
                )

        for source_id, target_id, _data in supported_by_edges:
            if source_id not in selected_nodes or target_id not in selected_nodes:
                continue
            target_attrs = self._normalize_json_safe(dict(self._graph.nodes[target_id]))
            if target_attrs.get("load_bearing") is False:
                edge_issues.append(
                    {
                        "source_id": source_id,
                        "target_id": target_id,
                        "issue": "unsupported_support_target",
                        "message": "SUPPORTED_BY edge targets a node marked as not load-bearing.",
                    }
                )
            elif not target_attrs.get("load_bearing", False) and not target_attrs.get("is_support", False):
                edge_issues.append(
                    {
                        "source_id": source_id,
                        "target_id": target_id,
                        "issue": "missing_supporting_role",
                        "message": "SUPPORTED_BY edge targets a node without load-bearing or support attributes.",
                    }
                )

        node_issues = self._sort_issue_records(node_issues)
        edge_issues = self._sort_issue_records(edge_issues)
        total = len(node_issues) + len(edge_issues)
        issues = (node_issues + edge_issues)[:limit]
        return {
            "status": "success",
            "selected_nodes": len(selected_nodes),
            "issues": issues,
            "node_issues": node_issues[:limit],
            "edge_issues": edge_issues[:limit],
            "count": min(total, limit),
            "total": total,
            "truncated": total > limit,
        }

    def _collect_aabb_records(
        self,
        raw_nodes: Optional[Sequence[Dict[str, Any]]],
        node_ids: Optional[Sequence[Any]],
    ) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        if raw_nodes is not None:
            for raw_node in raw_nodes:
                if not isinstance(raw_node, dict):
                    raise ValueError("Each node must be an object.")
                node_id = self._normalize_node_id(raw_node["id"])
                aabb = self._parse_aabb(raw_node.get("aabb"))
                records.append({"id": node_id, "aabb": aabb})
            return sorted(records, key=lambda item: item["id"])

        selected_ids = self._normalize_optional_node_id_list(node_ids)
        if selected_ids is None:
            selected_ids = sorted(self._graph.nodes)
        for node_id in selected_ids:
            self._require_node(node_id)
            aabb = self._parse_aabb(self._graph.nodes[node_id].get("aabb"))
            records.append({"id": node_id, "aabb": aabb})
        return sorted(records, key=lambda item: item["id"])

    def _select_nodes(
        self,
        node_ids: Optional[List[str]] = None,
        node_types: Optional[List[str]] = None,
    ) -> List[str]:
        selected = []
        allowed_ids = set(node_ids) if node_ids is not None else None
        allowed_types = set(node_types) if node_types is not None else None
        for node_id, attrs in self._graph.nodes(data=True):
            if allowed_ids is not None and node_id not in allowed_ids:
                continue
            if allowed_types is not None and attrs.get("type") not in allowed_types:
                continue
            selected.append(node_id)
        return sorted(selected)

    def _require_node(self, node_id: str) -> None:
        if node_id not in self._graph:
            raise ValueError(f"Unknown node id '{node_id}'.")

    def _normalize_node_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Each node must be an object.")
        node_id = self._normalize_node_id(
            payload.get("id", payload.get("node_id", payload.get("element_id")))
        )
        attrs = {
            key: self._normalize_json_safe(value)
            for key, value in payload.items()
            if key not in {"id", "attributes"}
        }
        node_attrs = self._normalize_json_safe(payload.get("attributes", {}))
        if not isinstance(node_attrs, dict):
            raise ValueError("Node 'attributes' must be an object if provided.")
        attrs.update(node_attrs)
        if "aabb" in payload:
            attrs["aabb"] = self._parse_aabb(payload.get("aabb"))
        if "type" in payload:
            attrs["type"] = self._normalize_json_safe(payload["type"])
        return {"id": node_id, "attributes": attrs}

    def _normalize_edge_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Each edge must be an object.")
        source_id = self._normalize_node_id(
            payload.get("source_id", payload.get("source", payload.get("from")))
        )
        target_id = self._normalize_node_id(
            payload.get("target_id", payload.get("target", payload.get("to")))
        )
        relation = self._normalize_relation(
            payload.get("relation", payload.get("relation_type", payload.get("type")))
        )
        attrs = {
            key: self._normalize_json_safe(value)
            for key, value in payload.items()
            if key not in {"source_id", "source", "target_id", "target", "relation", "type", "attributes"}
        }
        edge_attrs = self._normalize_json_safe(payload.get("attributes", {}))
        if not isinstance(edge_attrs, dict):
            raise ValueError("Edge 'attributes' must be an object if provided.")
        attrs.update(edge_attrs)
        return {
            "source_id": source_id,
            "target_id": target_id,
            "relation": relation,
            "attributes": attrs,
        }

    def _normalize_node_id(self, value: Any) -> str:
        if isinstance(value, bool) or value is None:
            raise ValueError("Node ids must be non-empty strings or integers.")
        if isinstance(value, int):
            text = str(value)
        elif isinstance(value, str):
            text = value.strip()
        else:
            raise ValueError("Node ids must be non-empty strings or integers.")
        if not text:
            raise ValueError("Node ids must be non-empty strings or integers.")
        return text

    def _normalize_optional_node_id(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        return self._normalize_node_id(value)

    def _normalize_optional_node_id_list(self, values: Any) -> Optional[List[str]]:
        if values is None:
            return None
        if not isinstance(values, list):
            raise ValueError("Node id lists must be lists.")
        return [self._normalize_node_id(value) for value in values]

    def _normalize_relation(self, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Relation type must be a non-empty string.")
        relation = value.strip().upper()
        if relation not in RELATION_TYPES:
            raise ValueError(
                f"Unsupported relation type '{value}'. Allowed types: {', '.join(sorted(RELATION_TYPES))}."
            )
        return relation

    def _normalize_optional_relation(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        return self._normalize_relation(value)

    def _normalize_relation_list(self, values: Any) -> Optional[List[str]]:
        if values is None:
            return None
        if not isinstance(values, list):
            raise ValueError("Relation type lists must be lists.")
        return [self._normalize_relation(value) for value in values]

    def _normalize_string_list(self, values: Any) -> Optional[List[str]]:
        if values is None:
            return None
        if not isinstance(values, list):
            raise ValueError("String lists must be lists.")
        normalized = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("String list values must be non-empty strings.")
            normalized.append(value.strip())
        return normalized

    def _normalize_int(self, value: Any, minimum: int = 0) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Expected an integer value.")
        if value < minimum:
            raise ValueError(f"Integer value must be >= {minimum}.")
        return value

    def _bounded_limit(self, value: Any) -> int:
        limit = self._normalize_int(value, minimum=1)
        return min(limit, MAX_LIMIT)

    def _normalize_number(self, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Expected a numeric value.")
        numeric = float(value)
        if not isfinite(numeric):
            raise ValueError("Numeric value must be finite.")
        return numeric

    def _normalize_json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            if isinstance(value, float) and not isfinite(value):
                return str(value)
            return value
        if isinstance(value, dict):
            return {
                str(key): self._normalize_json_safe(val)
                for key, val in sorted(value.items(), key=lambda item: str(item[0]))
            }
        if isinstance(value, (list, tuple)):
            return [self._normalize_json_safe(item) for item in value]
        if isinstance(value, set):
            return [self._normalize_json_safe(item) for item in sorted(value, key=lambda item: str(item))]
        return str(value)

    def _parse_aabb(self, value: Any) -> Dict[str, List[float]]:
        if not isinstance(value, dict):
            raise ValueError("AABB data must be an object with min/max coordinates.")
        if "min" in value and "max" in value:
            min_values = value["min"]
            max_values = value["max"]
        else:
            min_values = [value.get("min_x"), value.get("min_y"), value.get("min_z")]
            max_values = [value.get("max_x"), value.get("max_y"), value.get("max_z")]
        min_list = self._parse_point3(min_values, "min")
        max_list = self._parse_point3(max_values, "max")
        for axis, (minimum, maximum) in enumerate(zip(min_list, max_list)):
            if minimum > maximum:
                raise ValueError(f"AABB min must be less than or equal to max on axis {axis}.")
        return {"min": min_list, "max": max_list}

    def _parse_point3(self, values: Any, label: str) -> List[float]:
        if not isinstance(values, (list, tuple)) or len(values) != 3:
            raise ValueError(f"AABB '{label}' must contain exactly 3 coordinates.")
        parsed = [self._normalize_number(value) for value in values]
        return parsed

    def _aabbs_clash(
        self,
        first: Dict[str, List[float]],
        second: Dict[str, List[float]],
        tolerance: float,
    ) -> bool:
        for axis in range(3):
            if first["max"][axis] + tolerance < second["min"][axis]:
                return False
            if second["max"][axis] + tolerance < first["min"][axis]:
                return False
        return True

    def _relation_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for _source_id, _target_id, data in self._graph.edges(data=True):
            relation = self._normalize_relation(data.get("relation", ""))
            counts[relation] = counts.get(relation, 0) + 1
        return {key: counts[key] for key in sorted(counts)}

    def _sort_relation_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(
            records,
            key=lambda item: (
                item["source_id"],
                item["target_id"],
                item["relation"],
                item["edge_key"],
            ),
        )

    def _sort_issue_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(
            records,
            key=lambda item: (
                item.get("node_id", item.get("source_id", "")),
                item.get("target_id", ""),
                item["issue"],
            ),
        )

    async def shutdown(self) -> None:
        pass

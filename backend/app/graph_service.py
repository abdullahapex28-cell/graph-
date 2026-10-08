"""
NetworkX-backed knowledge-graph service.

Owns:
  * Loading the FULL graph from Neo4j into a ``networkx.DiGraph``
  * Global validation (duplicate ids, self-loops, prerequisite cycles)
  * Search-space reduction: reverse ancestor retrieval with AUTO strategy choice

All traversal / cycle-detection primitives come from NetworkX so we do not
re-implement well-tested graph algorithms by hand.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    import networkx as nx
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise ModuleNotFoundError(
        f"{exc.name} is not installed in the interpreter running this process.\n"
        "\n"
        "This almost always means you started the server with the system Python\n"
        "instead of the project virtual environment.\n"
        "\n"
        "From the backend directory run:\n"
        "    test\\Scripts\\python.exe -m uvicorn app.main:app --port 8000 --reload\n"
        "\n"
        "If the venv is missing or stale, recreate it:\n"
        "    python -m venv test\n"
        "    test\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from exc

from app.database import get_session
from app.schemas import (
    AutoTraversalDecision,
    RelationshipType,
    TraversalConfig,
    TraversalStrategy,
    ValidationIssue,
    ValidationReport,
    Severity,
)

logger = logging.getLogger(__name__)

NODE_LABEL = "Concept"
REL_LABEL = "RELATES_TO"


# ============================================================================
# GRAPH CONSTRUCTION
# ============================================================================

async def load_full_graph() -> nx.DiGraph:
    """
    Materialise the complete knowledge graph as a NetworkX DiGraph.

    Edge direction follows the stored direction: ``source -> target`` where a
    ``PREREQUISITE_OF`` edge points from prerequisite toward dependent.
    Reverse traversal therefore walks *incoming* edges from the target.
    """
    graph = nx.DiGraph()

    async with get_session() as session:
        node_result = await session.run(
            f"""
            MATCH (n:{NODE_LABEL})
            RETURN n.id AS id, n.name AS name, n.description AS description,
                   n.target_relevance AS target_relevance,
                   n.downstream_utility AS downstream_utility
            """
        )
        for record in await node_result.data():
            node_id = record["id"]
            if node_id is None:
                continue
            graph.add_node(
                node_id,
                id=node_id,
                name=record.get("name") or node_id,
                description=record.get("description") or "",
                target_relevance=float(record.get("target_relevance") or 0.0),
                downstream_utility=float(record.get("downstream_utility") or 0.0),
            )

        edge_result = await session.run(
            f"""
            MATCH (s:{NODE_LABEL})-[r:{REL_LABEL}]->(t:{NODE_LABEL})
            RETURN r.id AS id, s.id AS source, t.id AS target, r.type AS type,
                   r.prerequisite_type AS prerequisite_type,
                   r.time_required_minutes AS time_required_minutes,
                   r.cognitive_effort AS cognitive_effort
            """
        )
        for record in await edge_result.data():
            source = record.get("source")
            target = record.get("target")
            edge_id = record.get("id")
            if not source or not target or edge_id is None:
                continue
            if source not in graph or target not in graph:
                logger.warning(
                    "Skipping dangling relationship %s (%s -> %s)", edge_id, source, target
                )
                continue
            graph.add_edge(
                source,
                target,
                id=edge_id,
                type=record.get("type") or RelationshipType.PART_OF.value,
                prerequisite_type=record.get("prerequisite_type"),
                time_required_minutes=int(record.get("time_required_minutes") or 1),
                cognitive_effort=int(record.get("cognitive_effort") or 1),
            )

    return graph


def build_graph_from_records(
    nodes: Sequence[Dict[str, Any]], edges: Sequence[Dict[str, Any]]
) -> nx.DiGraph:
    """Pure in-memory builder (used by tests / offline solvers)."""
    graph = nx.DiGraph()
    for node in nodes:
        node_id = node["id"]
        graph.add_node(
            node_id,
            id=node_id,
            name=node.get("name") or node_id,
            description=node.get("description") or "",
            target_relevance=float(node.get("target_relevance") or 0.0),
            downstream_utility=float(node.get("downstream_utility") or 0.0),
        )
    for edge in edges:
        graph.add_edge(
            edge["source"],
            edge["target"],
            id=edge["id"],
            type=edge.get("type") or RelationshipType.PART_OF.value,
            prerequisite_type=edge.get("prerequisite_type"),
            time_required_minutes=int(edge.get("time_required_minutes") or 1),
            cognitive_effort=int(edge.get("cognitive_effort") or 1),
        )
    return graph


def prerequisite_subgraph(graph: nx.DiGraph) -> nx.DiGraph:
    """Project the graph onto ``PREREQUISITE_OF`` edges only."""
    return graph.edge_subgraph(
        [
            (u, v)
            for u, v, data in graph.edges(data=True)
            if data.get("type") == RelationshipType.PREREQUISITE_OF.value
        ]
    ).copy()


# ============================================================================
# STEP 1 — GLOBAL VALIDATION
# ============================================================================

def validate_graph(graph: nx.DiGraph) -> ValidationReport:
    """
    Validate duplicates, self-loops and prerequisite cycles.

    Cycle detection uses ``networkx.simple_cycles`` on the prerequisite-only
    projection; DAG-safety is confirmed with ``nx.is_directed_acyclic_graph``.
    """
    errors: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
    cycles: List[List[str]] = []

    # --- Self loops -------------------------------------------------------
    self_loops = list(nx.selfloop_edges(graph))
    if self_loops:
        errors.append(
            ValidationIssue(
                code="SELF_LOOP",
                message=f"Detected {len(self_loops)} self-loop relationship(s).",
                severity=Severity.ERROR,
                entities=[graph.edges[u, v].get("id", f"{u}->{v}") for u, v in self_loops],
            )
        )

    # --- Duplicate relationship ids (multi-edges share node pairs) ---------
    seen_edge_ids: Dict[str, int] = {}
    duplicate_edge_ids: List[str] = []
    for _u, _v, data in graph.edges(data=True):
        edge_id = data.get("id")
        if edge_id is None:
            continue
        seen_edge_ids[edge_id] = seen_edge_ids.get(edge_id, 0) + 1
    duplicate_edge_ids = [eid for eid, count in seen_edge_ids.items() if count > 1]
    if duplicate_edge_ids:
        errors.append(
            ValidationIssue(
                code="DUPLICATE_RELATIONSHIP_ID",
                message=f"Detected {len(duplicate_edge_ids)} duplicate relationship id(s).",
                severity=Severity.ERROR,
                entities=duplicate_edge_ids,
            )
        )

    # --- Node id integrity ------------------------------------------------
    node_ids = [data.get("id", n) for n, data in graph.nodes(data=True)]
    null_ids = [str(n) for n in graph.nodes if graph.nodes[n].get("id") in (None, "")]
    if null_ids:
        errors.append(
            ValidationIssue(
                code="MISSING_NODE_ID",
                message="One or more nodes are missing an id.",
                severity=Severity.ERROR,
                entities=null_ids,
            )
        )

    # --- Prerequisite cycles ---------------------------------------------
    prereq_graph = prerequisite_subgraph(graph)
    if len(prereq_graph) > 0:
        is_dag = nx.is_directed_acyclic_graph(prereq_graph)
        if not is_dag:
            for index, cycle in enumerate(nx.simple_cycles(prereq_graph)):
                cycles.append(list(cycle))
                if len(cycles) >= 25:  # cap reported cycles
                    break
            errors.append(
                ValidationIssue(
                    code="PREREQUISITE_CYCLE",
                    message=(
                        f"Prerequisite relationships contain {len(cycles)}+ cycle(s). "
                        "A prerequisite cycle makes the learning path unsatisfiable."
                    ),
                    severity=Severity.ERROR,
                    entities=[" -> ".join(cycle) for cycle in cycles[:10]],
                )
            )

    # --- Soft warnings ----------------------------------------------------
    isolated = [n for n in graph.nodes if graph.degree(n) == 0]
    if isolated:
        warnings.append(
            ValidationIssue(
                code="ISOLATED_NODES",
                message=f"{len(isolated)} node(s) have no relationships.",
                severity=Severity.WARNING,
                entities=isolated[:20],
            )
        )

    missing_prereq_type: List[str] = []
    for u, v, data in graph.edges(data=True):
        if (
            data.get("type") == RelationshipType.PREREQUISITE_OF.value
            and not data.get("prerequisite_type")
        ):
            missing_prereq_type.append(str(data.get("id", f"{u}->{v}")))
    if missing_prereq_type:
        warnings.append(
            ValidationIssue(
                code="MISSING_PREREQUISITE_TYPE",
                message=(
                    f"{len(missing_prereq_type)} PREREQUISITE_OF relationship(s) have no "
                    "prerequisite_type; they are treated as HARD."
                ),
                severity=Severity.WARNING,
                entities=missing_prereq_type[:20],
            )
        )

    return ValidationReport(
        is_valid=len(errors) == 0,
        total_nodes=graph.number_of_nodes(),
        total_edges=graph.number_of_edges(),
        errors=errors,
        warnings=warnings,
        cycle_details=cycles,
    )


# ============================================================================
# STEP 2 — SEARCH SPACE REDUCTION (AUTO traversal)
# ============================================================================

def _reverse_ancestor_subgraph(
    graph: nx.DiGraph, target: str
) -> nx.DiGraph:
    """Nodes reachable from ``target`` by walking edges backwards."""
    return graph.subgraph(nx.ancestors(graph, target) | {target}).copy()


def _structural_metrics(graph: nx.DiGraph, target: str) -> Dict[str, float]:
    """
    Measure depth / breadth / density of the reverse-reachable region.

    Uses NetworkX shortest-path length and BFS layer counts.
    """
    reverse_graph = graph.reverse(copy=False)
    reachable = set(nx.descendants(reverse_graph, target)) | {target}

    depth_lengths = []
    for node in reachable:
        try:
            depth_lengths.append(nx.shortest_path_length(reverse_graph, target, node))
        except nx.NetworkXNoPath:  # pragma: no cover - defensive
            continue

    max_depth = max(depth_lengths) if depth_lengths else 0

    # Layer widths give us the branching profile.
    layer_widths: List[int] = []
    for layer in nx.bfs_layers(reverse_graph, target):
        layer_widths.append(len(layer))
    if not layer_widths:
        layer_widths = [len(reachable)]

    total_nodes = max(len(reachable), 1)
    total_edges = graph.subgraph(reachable).number_of_edges()
    density = (2.0 * total_edges) / (total_nodes * max(total_nodes - 1, 1))

    # Average nodes per depth level = how "broad" the search is.
    average_width = total_nodes / (max_depth + 1) if max_depth >= 0 else total_nodes

    return {
        "reachable_nodes": float(len(reachable)),
        "max_depth": float(max_depth),
        "average_depth": float(
            sum(depth_lengths) / len(depth_lengths) if depth_lengths else 0.0
        ),
        "average_frontier_width": float(average_width),
        "max_layer_width": float(max(layer_widths)),
        "edge_density": float(density),
        "branching_factor": float(
            graph.subgraph(reachable).number_of_edges() / total_nodes
        ),
    }


def choose_traversal(
    graph: nx.DiGraph, target: str, requested: TraversalStrategy
) -> AutoTraversalDecision:
    """
    AUTO heuristic: pick BFS for shallow/broad prerequisite trees, DFS for
    deep/narrow chains.

    Rationale
    ---------
    * Wide + shallow  -> many sibling branches at low depth. BFS reveals the
      full breadth of alternatives cheaply so the optimizer sees every option.
    * Narrow + deep   -> long prerequisite chains. DFS follows the chain to its
      root without materialising irrelevant sibling subtrees, keeping the
      search space tight on 1000+ node graphs.
    """
    if requested != TraversalStrategy.AUTO:
        return AutoTraversalDecision(
            requested=requested,
            selected=requested,
            reason=f"Traversal explicitly pinned to {requested.value} by the caller.",
            metrics={},
        )

    metrics = _structural_metrics(graph, target)
    max_depth = metrics.get("max_depth", 0.0)
    average_width = metrics.get("average_frontier_width", 0.0)
    branching = metrics.get("branching_factor", 0.0)

    shallow_broad = average_width >= 3.0 or max_depth <= 2.0
    deep_narrow = max_depth >= 5.0 and average_width < 3.0

    if shallow_broad and not deep_narrow:
        selected = TraversalStrategy.BFS
        reason = (
            f"AUTO -> BFS: prerequisite region is broad "
            f"(avg frontier width {average_width:.2f}, max depth {max_depth:.0f}). "
            "Breadth-first retrieval surfaces all alternative branches before "
            "the optimizer commits."
        )
    elif deep_narrow:
        selected = TraversalStrategy.DFS
        reason = (
            f"AUTO -> DFS: prerequisite region is deep and narrow "
            f"(max depth {max_depth:.0f}, avg frontier width {average_width:.2f}). "
            "Depth-first retrieval follows the chain to its root while skipping "
            "irrelevant sibling subtrees."
        )
    else:
        # Ambiguous middle ground — fall back to depth for stable behaviour.
        selected = TraversalStrategy.DFS if max_depth >= 3.0 else TraversalStrategy.BFS
        reason = (
            f"AUTO -> {selected.value}: mixed structure "
            f"(max depth {max_depth:.0f}, avg frontier width {average_width:.2f}, "
            f"branching factor {branching:.2f})."
        )

    return AutoTraversalDecision(
        requested=TraversalStrategy.AUTO,
        selected=selected,
        reason=reason,
        metrics={key: round(value, 4) for key, value in metrics.items()},
    )


def _bfs_ancestors(
    graph: nx.DiGraph, target: str, max_depth: Optional[int]
) -> Tuple[Set[str], List[str]]:
    """Reverse BFS using ``networkx.bfs_layers`` with optional depth cutoff."""
    reverse_graph = graph.reverse(copy=False)
    visited: Set[str] = set()
    order: List[str] = []

    for depth, layer in enumerate(nx.bfs_layers(reverse_graph, target)):
        if max_depth is not None and depth > max_depth:
            break
        for node in layer:
            if node not in visited:
                visited.add(node)
                order.append(node)

    return visited, order


def _dfs_ancestors(
    graph: nx.DiGraph, target: str, max_depth: Optional[int]
) -> Tuple[Set[str], List[str]]:
    """Reverse DFS via ``networkx.dfs_preorder_nodes`` (depth-limited)."""
    reverse_graph = graph.reverse(copy=False)
    visited: Set[str] = set()
    order: List[str] = []

    # NetworkX >=3.1 supports depth_limit on dfs_preorder_nodes; fall back to an
    # explicit stack if running against an older release.
    try:
        for node in nx.dfs_preorder_nodes(reverse_graph, target, depth_limit=max_depth):
            visited.add(node)
            order.append(node)
    except TypeError:  # pragma: no cover - older networkx
        stack: List[Tuple[str, int]] = [(target, 0)]
        while stack:
            node, depth = stack.pop()
            if node in visited:
                continue
            if max_depth is not None and depth > max_depth:
                continue
            visited.add(node)
            order.append(node)
            for predecessor in reverse_graph.successors(node):
                if predecessor not in visited:
                    stack.append((predecessor, depth + 1))

    return visited, order


def retrieve_ancestor_subgraph(
    graph: nx.DiGraph,
    target: str,
    strategy: TraversalStrategy,
    config: TraversalConfig,
) -> Tuple[nx.DiGraph, Dict[str, Any]]:
    """
    Extract the target-specific ancestor subgraph.

    Returns the induced subgraph plus traversal statistics for the UI panel.
    """
    if strategy == TraversalStrategy.BFS:
        visited, order = _bfs_ancestors(graph, target, config.max_depth)
    elif strategy == TraversalStrategy.DFS:
        visited, order = _dfs_ancestors(graph, target, config.max_depth)
    else:  # AUTO already resolved by choose_traversal, default to BFS
        visited, order = _bfs_ancestors(graph, target, config.max_depth)

    subgraph = graph.subgraph(visited).copy()

    # Safety cap: keep the highest-value closest-to-target nodes if the
    # traversal exploded (protects the UI on 1000+ node graphs).
    pruned = False
    if subgraph.number_of_nodes() > config.max_subgraph_nodes:
        pruned = True
        ranked = sorted(
            subgraph.nodes,
            key=lambda n: (
                nx.shortest_path_length(graph.reverse(copy=False), target, n),
                -subgraph.nodes[n].get("target_relevance", 0.0),
            ),
        )
        keep = set(ranked[: config.max_subgraph_nodes])
        keep.add(target)
        subgraph = subgraph.subgraph(keep).copy()
        visited = set(subgraph.nodes)
        order = [n for n in order if n in visited]

    # Keep only edges whose endpoints both survived.
    subgraph.remove_edges_from(
        [edge for edge in list(subgraph.edges) if edge[0] not in subgraph or edge[1] not in subgraph]
    )

    stats = {
        "full_graph_nodes": graph.number_of_nodes(),
        "full_graph_edges": graph.number_of_edges(),
        "retrieved_nodes": subgraph.number_of_nodes(),
        "retrieved_edges": subgraph.number_of_edges(),
        "reduction_ratio": (
            round(1.0 - subgraph.number_of_nodes() / graph.number_of_nodes(), 4)
            if graph.number_of_nodes()
            else 0.0
        ),
        "traversal_order": order,
        "nodes_pruned_by_cap": pruned,
        "max_depth_applied": config.max_depth,
    }

    return subgraph, stats


def hard_prerequisite_closure(
    graph: nx.DiGraph, target: str
) -> Set[str]:
    """
    Transitive closure of HARD prerequisites reachable backwards from target.

    HARD prerequisites are mandatory and cannot be skipped by any solver.
    """
    reverse_graph = graph.reverse(copy=False)
    mandatory: Set[str] = set()
    queue = [target]

    while queue:
        node = queue.pop()
        for predecessor in reverse_graph.successors(node):
            edge_data = graph.edges[predecessor, node]
            prereq_type = edge_data.get("prerequisite_type") or "HARD"
            if (
                edge_data.get("type") == RelationshipType.PREREQUISITE_OF.value
                and prereq_type == "HARD"
                and predecessor not in mandatory
            ):
                mandatory.add(predecessor)
                queue.append(predecessor)

    mandatory.discard(target)
    return mandatory
